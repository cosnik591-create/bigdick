"""Сетевой клиент с фоновым потоком чтения."""

from __future__ import annotations

import queue
import socket
import threading
from typing import Any

from ..config import MAX_MESSAGE_BYTES
from ..protocol import ProtocolError, decode, encode, message


class NetworkError(Exception):
    """Не удалось установить соединение."""


class NetworkClient:
    """Тонкая обёртка: отправка сообщений и очередь входящих событий.

    UI-поток забирает события из ``events`` и не работает с сокетом напрямую.
    """

    def __init__(self) -> None:
        self.events: "queue.Queue[dict[str, Any]]" = queue.Queue()
        self.player_id: str | None = None
        self._sock: socket.socket | None = None
        self._reader: threading.Thread | None = None
        self._send_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._closed = threading.Event()

    @property
    def connected(self) -> bool:
        return self._sock is not None and not self._closed.is_set()

    def connect(self, host: str, port: int, timeout: float = 5.0) -> None:
        if self._sock is not None:
            raise NetworkError("Клиент уже подключён")
        try:
            sock = socket.create_connection((host, port), timeout=timeout)
        except socket.timeout as exc:
            raise NetworkError(
                f"Не удалось подключиться к {host}:{port}: истекло время ожидания"
            ) from exc
        except OSError as exc:
            reason = exc.strerror or str(exc)
            raise NetworkError(f"Не удалось подключиться к {host}:{port} ({reason})") from exc

        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        sock.settimeout(None)
        self._sock = sock
        self._closed.clear()
        self._reader = threading.Thread(
            target=self._read_loop,
            name="monopoly-client",
            daemon=True,
        )
        self._reader.start()

    def send(self, type_: str, **fields: Any) -> bool:
        sock = self._sock
        if sock is None or self._closed.is_set():
            return False
        data = encode(message(type_, **fields))
        with self._send_lock:
            try:
                sock.sendall(data)
                return True
            except OSError:
                self._mark_closed("Соединение с сервером потеряно")
                self._close_socket()
                return False

    def close(self) -> None:
        self._mark_closed(None)
        self._close_socket()

    def _mark_closed(self, reason: str | None) -> None:
        with self._state_lock:
            already = self._closed.is_set()
            self._closed.set()
        if reason and not already:
            self.events.put({"type": "_disconnected", "reason": reason})

    def _close_socket(self) -> None:
        sock, self._sock = self._sock, None
        if sock is None:
            return
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            sock.close()
        except OSError:
            pass

    def _read_loop(self) -> None:
        sock = self._sock
        if sock is None:
            return
        reason = "Соединение с сервером потеряно"
        try:
            stream = sock.makefile("rb")
            while not self._closed.is_set():
                raw = stream.readline(MAX_MESSAGE_BYTES + 1)
                if not raw:
                    break
                if len(raw) > MAX_MESSAGE_BYTES:
                    reason = "Сервер прислал слишком большое сообщение"
                    break
                try:
                    event = decode(raw)
                except ProtocolError:
                    continue
                if event.get("type") == "hello_ok":
                    self.player_id = event.get("player_id")
                self.events.put(event)
        except OSError:
            pass
        finally:
            self._close_socket()
            self._mark_closed(reason)
