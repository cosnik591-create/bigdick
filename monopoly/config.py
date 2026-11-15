"""Общие константы приложения и сетевого протокола."""

from __future__ import annotations

APP_NAME = "Монополия"
VERSION = "0.2.0"

# --- Сеть -----------------------------------------------------------------
PROTOCOL_VERSION = 2
DEFAULT_PORT = 8765
HOST = "0.0.0.0"
MAX_MESSAGE_BYTES = 64 * 1024
HEARTBEAT_INTERVAL = 15.0
CONNECTION_IDLE_TIMEOUT = 60.0

# --- Лобби ----------------------------------------------------------------
MIN_PLAYERS = 2
MAX_PLAYERS = 6
DEFAULT_MAX_PLAYERS = 4
MAX_NAME_LENGTH = 16
MAX_LOBBY_NAME_LENGTH = 30
MAX_CHAT_LENGTH = 300

# --- Игра -----------------------------------------------------------------
START_MONEY = 1500
GO_SALARY = 200
BOARD_SIZE = 40
