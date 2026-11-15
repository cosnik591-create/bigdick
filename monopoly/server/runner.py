"""TCP-сервер на stdlib socketserver."""

from __future__ import annotations

import logging
import socketserver
import threading

from ..config import CONNECTION_IDLE_TIMEOUT, MAX_MESSAGE_BYTES, PROTOCOL_VERSION, VERSION
from ..protocol import ProtocolError, decode, message
from .connection import Connection
from .core import ServerCore

log = logging.getLogger("monopoly.server")


class RequestHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        server: "MonopolyServer" = self.server  # type: ignore[assignment]
        core = server.core
        conn = Connection(self.request, self.client_address, core.new_connection_id())
        core.register(conn)
        conn.send(
            message(
                "hello_ok",
                player_id=conn.id,
                version=PROTOCOL_VERSION,
                app_version=VERSION,
            )
        )
        try:
            while not core.stopped:
                raw = self.rfile.readline(MAX_MESSAGE_BYTES + 1)
                if not raw:
                    break
                if len(raw) > MAX_MESSAGE_BYTES:
                    conn.send(
                        message(
                            "error",
                            code="message_too_large",
                            message="Слишком большое сообщение",
                        )
                    )
                    break
                try:
                    decoded = decode(raw)
                except ProtocolError as exc:
                    conn.send(
                        message("error", code="bad_message", message=str(exc))
                    )
                    continue
                core.handle_message(conn, decoded)
                if conn.closed:
                    break
        except (ConnectionResetError, ConnectionAbortedError, OSError):
            pass
        except Exception:  # pragma: no cover
            log.exception("Необработанная ошибка в обработчике подключения")
        finally:
            core.unregister(conn)
            conn.close()


class MonopolyServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, address: tuple[str, int], core: ServerCore | None = None):
        self.core = core or ServerCore()
        super().__init__(address, RequestHandler)
        self._stop_flag = threading.Event()
        self._serve_thread: threading.Thread | None = None
        self._watchdog_thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        return int(self.server_address[1])

    def start(self) -> None:
        self._serve_thread = threading.Thread(
            target=self.serve_forever,
            kwargs={"poll_interval": 0.2},
            name="monopoly-server",
            daemon=True,
        )
        self._serve_thread.start()
        self._watchdog_thread = threading.Thread(
            target=self._watchdog,
            name="monopoly-watchdog",
            daemon=True,
        )
        self._watchdog_thread.start()

    def _watchdog(self) -> None:
        while not self._stop_flag.wait(10):
            self.core.sweep_stale(CONNECTION_IDLE_TIMEOUT)

    def stop(self) -> None:
        if self._stop_flag.is_set():
            return
        self._stop_flag.set()
        self.core.shutdown()
        if self._serve_thread is not None and self._serve_thread.is_alive():
            try:
                self.shutdown()
            except Exception:  # pragma: no cover
                pass
        self.server_close()
        for thread in (self._serve_thread, self._watchdog_thread):
            if thread is not None and thread.is_alive():
                thread.join(timeout=2)
