"""Утилиты для работы с адресами и портами."""

from __future__ import annotations

import socket

from .config import DEFAULT_PORT


def local_ip() -> str:
    """Возвращает IP-адрес машины в локальной сети."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Подключение к внешнему адресу не отправляет пакетов, но заставляет
        # ядро выбрать исходящий интерфейс.
        sock.connect(("8.8.8.8", 80))
        return str(sock.getsockname()[0])
    except OSError:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return "127.0.0.1"
    finally:
        sock.close()


def parse_port(value: object, default: int = DEFAULT_PORT) -> int:
    raw = str(value).strip()
    if not raw:
        return default
    try:
        port = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("Порт должен быть числом") from exc
    if not 1 <= port <= 65535:
        raise ValueError("Порт должен быть в диапазоне 1–65535")
    return port


def parse_address(value: object, default_port: int = DEFAULT_PORT) -> tuple[str, int]:
    """Разбирает строку вида ``192.168.0.5:8765`` или ``192.168.0.5``."""
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("Укажите адрес сервера")
    if raw.count(":") > 1:
        raise ValueError("IPv6-адреса пока не поддерживаются")
    if ":" in raw:
        host, port_text = raw.rsplit(":", 1)
    else:
        host, port_text = raw, str(default_port)
    host = host.strip()
    if not host:
        raise ValueError("Укажите адрес сервера")
    return host, parse_port(port_text, default_port)


def format_address(host: str, port: int) -> str:
    return f"{host}:{port}"
