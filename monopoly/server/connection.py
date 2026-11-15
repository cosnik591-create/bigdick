"""Обёртка над сокетом одного подключённого клиента."""

from __future__ import annotations

import socket
import threading
import time
from typing import Any

from ..protocol import encode


class Connection:
    def __init__(self, sock: socket.socket, address: tuple[str, int], connection_id: str):
        self.sock = sock
        self.address = address
        self.id = connection_id
        self.name: str | None = None
        self.lobby_code: str | None = None
        self.last_seen = time.monotonic()
        self.closed = False
        self._send_lock = threading.Lock()

    def send(self, message: dict[str, Any]) -> bool:
        data = encode(message)
        with self._send_lock:
            if self.closed:
                return False
            try:
                self.sock.sendall(data)
                return True
            except OSError:
                self.closed = True
                return False

    def close(self) -> None:
        self.closed = True
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass
