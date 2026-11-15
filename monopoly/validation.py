"""Проверка и нормализация пользовательского ввода."""

from __future__ import annotations

from typing import Any

from .config import MAX_CHAT_LENGTH, MAX_LOBBY_NAME_LENGTH, MAX_NAME_LENGTH


def _normalize(value: Any) -> str:
    """Схлопывает пробелы и убирает управляющие символы."""
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())


def clean_player_name(value: Any) -> str:
    name = _normalize(value)
    if not name:
        raise ValueError("Введите имя игрока")
    if len(name) > MAX_NAME_LENGTH:
        raise ValueError(f"Имя должно быть не длиннее {MAX_NAME_LENGTH} символов")
    return name


def clean_lobby_name(value: Any, host_name: str) -> str:
    name = _normalize(value)
    if not name:
        return f"Лобби {host_name}"
    return name[:MAX_LOBBY_NAME_LENGTH]


def clean_chat(value: Any) -> str:
    text = _normalize(value)
    if not text:
        raise ValueError("Сообщение не может быть пустым")
    return text[:MAX_CHAT_LENGTH]
