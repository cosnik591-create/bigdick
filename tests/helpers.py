"""Вспомогательные классы для интеграционных тестов."""

from __future__ import annotations

import socket
from typing import Any

from monopoly.protocol import decode, encode, message


class TestClient:
    def __init__(self, port: int):
        self.sock = socket.create_connection(("127.0.0.1", port), timeout=3)
        self.stream = self.sock.makefile("rb")
        self.hello = self.read()
        assert self.hello["type"] == "hello_ok", self.hello

    @property
    def id(self) -> str:
        return str(self.hello["player_id"])

    def send(self, type_: str, **fields: Any) -> None:
        self.sock.sendall(encode(message(type_, **fields)))

    def read(self) -> dict[str, Any]:
        raw = self.stream.readline()
        if not raw:
            raise AssertionError("Сервер закрыл соединение")
        return decode(raw)

    def read_until(self, type_: str, limit: int = 40) -> dict[str, Any]:
        seen: list[str] = []
        for _ in range(limit):
            event = self.read()
            if event["type"] == type_:
                return event
            seen.append(event["type"])
        raise AssertionError(f"Не дождались {type_!r}; получено: {seen}")

    def read_chat_from(self, name: str, limit: int = 40) -> dict[str, Any]:
        for _ in range(limit):
            event = self.read()
            if event["type"] == "chat_message" and event.get("name") == name:
                return event
        raise AssertionError(f"Не дождались сообщения от {name!r}")

    def close(self) -> None:
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass
