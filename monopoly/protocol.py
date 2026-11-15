"""Текстовый протокол поверх TCP.

Каждое сообщение — JSON-объект с полем ``type``, закодированный в UTF-8
и завершённый переводом строки. Такой формат легко читать глазами и
отлаживать через ``nc``/telnet.
"""

from __future__ import annotations

import json
from typing import Any

from .config import MAX_MESSAGE_BYTES


class ProtocolError(Exception):
    """Сообщение не соответствует протоколу."""


def encode(message: dict[str, Any]) -> bytes:
    payload = json.dumps(message, ensure_ascii=False, separators=(",", ":"))
    return payload.encode("utf-8") + b"\n"


def decode(raw: bytes | str) -> dict[str, Any]:
    if isinstance(raw, bytes):
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ProtocolError("Сообщение пришло не в кодировке UTF-8") from exc
    else:
        text = raw

    text = text.strip()
    if not text:
        raise ProtocolError("Пустое сообщение")
    if len(text.encode("utf-8")) > MAX_MESSAGE_BYTES:
        raise ProtocolError("Сообщение слишком большое")
    try:
        message = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProtocolError("Некорректный JSON") from exc
    if not isinstance(message, dict):
        raise ProtocolError("Сообщение должно быть JSON-объектом")
    if not isinstance(message.get("type"), str) or not message["type"]:
        raise ProtocolError("В сообщении отсутствует поле type")
    return message


def message(type_: str, **fields: Any) -> dict[str, Any]:
    return {"type": type_, **fields}
