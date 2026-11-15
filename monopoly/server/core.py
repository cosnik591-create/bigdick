"""Серверная логика: подключения, лобби, чат и старт партии."""

from __future__ import annotations

import logging
import secrets
import threading
import time
import traceback
from typing import Any, Callable

from ..config import BOARD_SIZE, MIN_PLAYERS
from ..protocol import message
from ..validation import clean_chat, clean_lobby_name, clean_player_name
from .connection import Connection
from .game import GameError, GameSession
from .lobby import Lobby, Player

log = logging.getLogger("monopoly.server")

LOBBY_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
LOBBY_CODE_LENGTH = 4


class ServerError(Exception):
    def __init__(self, code: str, text: str):
        super().__init__(text)
        self.code = code
        self.text = text


class ServerCore:
    """Всё состояние сервера. Потокобезопасен: один RLock на операции."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._connections: dict[str, Connection] = {}
        self._lobbies: dict[str, Lobby] = {}
        self._stopped = False
        self._handlers: dict[str, Callable[[Connection, dict[str, Any]], None]] = {
            "ping": self._handle_ping,
            "create_lobby": self._handle_create_lobby,
            "join_lobby": self._handle_join_lobby,
            "leave_lobby": self._handle_leave_lobby,
            "set_ready": self._handle_set_ready,
            "start_game": self._handle_start_game,
            "kick_player": self._handle_kick_player,
            "chat": self._handle_chat,
            "roll_dice": self._handle_roll_dice,
            "buy_property": self._handle_buy_property,
            "decline_property": self._handle_decline_property,
            "auction_bid": self._handle_auction_bid,
            "auction_pass": self._handle_auction_pass,
            "build": self._handle_build,
            "sell_building": self._handle_sell_building,
            "mortgage": self._handle_mortgage,
            "unmortgage": self._handle_unmortgage,
            "pay_jail": self._handle_pay_jail,
            "use_jail_card": self._handle_use_jail_card,
        }

    # ------------------------------------------------------------------
    # Подключения
    # ------------------------------------------------------------------
    @property
    def stopped(self) -> bool:
        return self._stopped

    @staticmethod
    def new_connection_id() -> str:
        return "p" + secrets.token_hex(4)

    def register(self, conn: Connection) -> None:
        with self._lock:
            self._connections[conn.id] = conn

    def unregister(self, conn: Connection) -> None:
        with self._lock:
            existed = self._connections.pop(conn.id, None)
            code = conn.lobby_code
            conn.lobby_code = None
            if existed is None or not code:
                return
            lobby = self._lobbies.get(code)
            if lobby is None or conn.id not in lobby.players:
                return
            name = lobby.players[conn.id].name
            self._depart(lobby, conn.id, f"{name} отключился")

    def handle_message(self, conn: Connection, raw_message: dict[str, Any]) -> None:
        with self._lock:
            if self._stopped:
                return
            conn.last_seen = time.monotonic()
            msg_type = raw_message.get("type")
            handler = self._handlers.get(str(msg_type))
            if handler is None:
                conn.send(
                    message(
                        "error",
                        code="unknown_message",
                        message=f"Неизвестный тип сообщения: {msg_type}",
                    )
                )
                return
            try:
                handler(conn, raw_message)
            except ServerError as exc:
                conn.send(message("error", code=exc.code, message=exc.text))
            except Exception:  # pragma: no cover - защита от неожиданных ошибок
                log.error("Ошибка при обработке %s:\n%s", msg_type, traceback.format_exc())
                conn.send(
                    message(
                        "error",
                        code="internal_error",
                        message="Внутренняя ошибка сервера",
                    )
                )

    def sweep_stale(self, timeout: float) -> None:
        """Закрывает соединения, от которых давно не было ни одного пакета."""
        now = time.monotonic()
        with self._lock:
            stale = [
                conn
                for conn in self._connections.values()
                if now - conn.last_seen > timeout
            ]
        for conn in stale:
            conn.close()
            self.unregister(conn)

    def shutdown(self) -> None:
        with self._lock:
            if self._stopped:
                return
            self._stopped = True
            for lobby in list(self._lobbies.values()):
                self._broadcast_lobby(
                    lobby,
                    message("lobby_closed", reason="Хост закрыл лобби"),
                )
            self._lobbies.clear()
            connections = list(self._connections.values())
            self._connections.clear()
        for conn in connections:
            conn.close()

    # ------------------------------------------------------------------
    # Обработчики сообщений
    # ------------------------------------------------------------------
    def _handle_ping(self, conn: Connection, _msg: dict[str, Any]) -> None:
        conn.send(message("pong"))

    def _handle_create_lobby(self, conn: Connection, msg: dict[str, Any]) -> None:
        if conn.lobby_code:
            raise ServerError("already_in_lobby", "Вы уже находитесь в лобби")
        try:
            name = clean_player_name(msg.get("name"))
        except ValueError as exc:
            raise ServerError("bad_name", str(exc)) from exc

        conn.name = name
        lobby_name = clean_lobby_name(msg.get("lobby_name"), name)
        max_players = self._clamp_max_players(msg.get("max_players"))
        code = self._new_lobby_code()

        lobby = Lobby(
            code=code,
            name=lobby_name,
            host_id=conn.id,
            max_players=max_players,
        )
        lobby.players[conn.id] = Player(id=conn.id, name=name, is_host=True)
        self._lobbies[code] = lobby
        conn.lobby_code = code
        conn.send(self._lobby_state_message(lobby))

    def _handle_join_lobby(self, conn: Connection, msg: dict[str, Any]) -> None:
        if conn.lobby_code:
            raise ServerError("already_in_lobby", "Вы уже находитесь в лобби")
        try:
            name = clean_player_name(msg.get("name"))
        except ValueError as exc:
            raise ServerError("bad_name", str(exc)) from exc

        code = str(msg.get("code") or "").strip().upper()
        if not code:
            raise ServerError("bad_code", "Укажите код лобби")
        lobby = self._lobbies.get(code)
        if lobby is None:
            raise ServerError("lobby_not_found", "Лобби с таким кодом не найдено")
        if lobby.phase != "lobby":
            raise ServerError("lobby_in_game", "В этом лобби уже началась игра")
        if len(lobby.players) >= lobby.max_players:
            raise ServerError("lobby_full", "Лобби заполнено")
        if any(player.name.casefold() == name.casefold() for player in lobby.players.values()):
            raise ServerError("name_taken", "Это имя уже занято в лобби")

        conn.name = name
        conn.lobby_code = lobby.code
        lobby.players[conn.id] = Player(id=conn.id, name=name)
        self._broadcast_lobby_state(lobby)
        self._system_chat(lobby, f"{name} присоединился к лобби")

    def _handle_leave_lobby(self, conn: Connection, _msg: dict[str, Any]) -> None:
        lobby = self._require_lobby(conn)
        conn.lobby_code = None
        self._depart(lobby, conn.id, f"{conn.name or 'Игрок'} покинул лобби")
        conn.send(message("left_lobby"))

    def _handle_set_ready(self, conn: Connection, msg: dict[str, Any]) -> None:
        lobby = self._require_lobby(conn)
        if lobby.phase != "lobby":
            raise ServerError("bad_phase", "Игра уже началась")
        player = lobby.players.get(conn.id)
        if player is None:
            raise ServerError("not_in_lobby", "Вы не находитесь в лобби")
        player.ready = bool(msg.get("ready"))
        self._broadcast_lobby_state(lobby)

    def _handle_start_game(self, conn: Connection, _msg: dict[str, Any]) -> None:
        lobby = self._require_lobby(conn)
        if conn.id != lobby.host_id:
            raise ServerError("not_host", "Только хост может начать игру")
        if lobby.phase != "lobby":
            raise ServerError("bad_phase", "Игра уже началась")
        if len(lobby.players) < MIN_PLAYERS:
            raise ServerError("not_enough_players", "Нужно минимум 2 игрока")
        if not lobby.can_start:
            raise ServerError("not_ready", "Не все игроки готовы")

        lobby.game = GameSession(lobby.players.values())
        lobby.phase = "in_game"
        self._broadcast_lobby_state(lobby)
        self._broadcast_lobby(lobby, message("game_started", game=lobby.game.view()))

    def _handle_kick_player(self, conn: Connection, msg: dict[str, Any]) -> None:
        lobby = self._require_lobby(conn)
        if conn.id != lobby.host_id:
            raise ServerError("not_host", "Только хост может исключать игроков")
        if lobby.phase != "lobby":
            raise ServerError("bad_phase", "Нельзя исключать игроков во время игры")
        target_id = str(msg.get("player_id") or "")
        if target_id == conn.id:
            raise ServerError("bad_target", "Нельзя исключить самого себя")
        target = lobby.players.get(target_id)
        if target is None:
            raise ServerError("player_not_found", "Игрок не найден")

        target_conn = self._connections.get(target_id)
        if target_conn is not None:
            target_conn.lobby_code = None
        lobby.players.pop(target_id, None)
        if target_conn is not None:
            target_conn.send(
                message("kicked", by=conn.name, reason="Хост исключил вас из лобби")
            )
        self._broadcast_lobby_state(lobby)
        self._system_chat(lobby, f"{target.name} исключён хостом")

    def _handle_chat(self, conn: Connection, msg: dict[str, Any]) -> None:
        lobby = self._require_lobby(conn)
        try:
            text = clean_chat(msg.get("text"))
        except ValueError as exc:
            raise ServerError("bad_chat", str(exc)) from exc
        self._broadcast_lobby(
            lobby,
            message(
                "chat_message",
                player_id=conn.id,
                name=conn.name or "Игрок",
                text=text,
                ts=time.time(),
            ),
        )

    def _handle_roll_dice(self, conn: Connection, _msg: dict[str, Any]) -> None:
        self._run_game_action(conn, lambda game: game.roll(conn.id))

    def _handle_buy_property(self, conn: Connection, _msg: dict[str, Any]) -> None:
        self._run_game_action(conn, lambda game: game.buy_property(conn.id))

    def _handle_decline_property(self, conn: Connection, _msg: dict[str, Any]) -> None:
        self._run_game_action(conn, lambda game: game.decline_property(conn.id))

    def _handle_auction_bid(self, conn: Connection, msg: dict[str, Any]) -> None:
        self._run_game_action(
            conn, lambda game: game.auction_bid(conn.id, msg.get("amount"))
        )

    def _handle_auction_pass(self, conn: Connection, _msg: dict[str, Any]) -> None:
        self._run_game_action(conn, lambda game: game.auction_pass(conn.id))

    def _handle_build(self, conn: Connection, msg: dict[str, Any]) -> None:
        position = self._read_position(msg)
        self._run_game_action(conn, lambda game: game.build(conn.id, position))

    def _handle_sell_building(self, conn: Connection, msg: dict[str, Any]) -> None:
        position = self._read_position(msg)
        self._run_game_action(conn, lambda game: game.sell_building(conn.id, position))

    def _handle_mortgage(self, conn: Connection, msg: dict[str, Any]) -> None:
        position = self._read_position(msg)
        self._run_game_action(conn, lambda game: game.mortgage(conn.id, position))

    def _handle_unmortgage(self, conn: Connection, msg: dict[str, Any]) -> None:
        position = self._read_position(msg)
        self._run_game_action(conn, lambda game: game.unmortgage(conn.id, position))

    @staticmethod
    def _read_position(msg: dict[str, Any]) -> int:
        try:
            position = int(msg.get("position"))
        except (TypeError, ValueError) as exc:
            raise ServerError("bad_position", "Некорректная клетка") from exc
        if not 0 <= position < BOARD_SIZE:
            raise ServerError("bad_position", "Некорректная клетка")
        return position

    def _handle_pay_jail(self, conn: Connection, _msg: dict[str, Any]) -> None:
        self._run_game_action(conn, lambda game: game.pay_jail(conn.id))

    def _handle_use_jail_card(self, conn: Connection, _msg: dict[str, Any]) -> None:
        self._run_game_action(conn, lambda game: game.use_jail_card(conn.id))

    def _run_game_action(
        self, conn: Connection, action: Callable[[GameSession], None]
    ) -> None:
        lobby = self._require_lobby(conn)
        if lobby.phase != "in_game" or lobby.game is None:
            raise ServerError("not_in_game", "Игра ещё не началась")
        try:
            action(lobby.game)
        except (GameError, ValueError, TypeError) as exc:
            raise ServerError("game_error", str(exc)) from exc
        self._broadcast_lobby(
            lobby,
            message("game_update", game=lobby.game.view()),
        )

    # ------------------------------------------------------------------
    # Внутренние помощники
    # ------------------------------------------------------------------
    def _require_lobby(self, conn: Connection) -> Lobby:
        if not conn.lobby_code:
            raise ServerError("not_in_lobby", "Вы не находитесь в лобби")
        lobby = self._lobbies.get(conn.lobby_code)
        if lobby is None:
            conn.lobby_code = None
            raise ServerError("lobby_not_found", "Лобби больше не существует")
        return lobby

    def _depart(self, lobby: Lobby, player_id: str, notice: str) -> None:
        """Убирает игрока из лобби и рассылает всем новое состояние."""
        removed = lobby.players.pop(player_id, None)
        if removed is None:
            return
        if not lobby.players:
            self._lobbies.pop(lobby.code, None)
            return

        if lobby.host_id == player_id:
            new_host = next(iter(lobby.players.values()))
            new_host.is_host = True
            lobby.host_id = new_host.id
            self._system_chat(lobby, f"Новый хост лобби — {new_host.name}")

        aborted = False
        if lobby.phase == "in_game" and lobby.game is not None:
            aborted = lobby.game.remove_player(player_id)
            if aborted:
                lobby.phase = "lobby"
                lobby.game = None
                for player in lobby.players.values():
                    player.ready = False

        self._broadcast_lobby_state(lobby)
        if aborted:
            self._broadcast_lobby(
                lobby,
                message("game_aborted", reason="В игре осталось меньше двух игроков"),
            )
        elif lobby.phase == "in_game" and lobby.game is not None:
            self._broadcast_lobby(
                lobby,
                message("game_update", game=lobby.game.view()),
            )
        self._system_chat(lobby, notice)

    def _broadcast_lobby(self, lobby: Lobby, msg: dict[str, Any]) -> None:
        for player_id in list(lobby.players):
            conn = self._connections.get(player_id)
            if conn is not None:
                conn.send(msg)

    def _broadcast_lobby_state(self, lobby: Lobby) -> None:
        self._broadcast_lobby(lobby, self._lobby_state_message(lobby))

    def _system_chat(self, lobby: Lobby, text: str) -> None:
        self._broadcast_lobby(
            lobby,
            message(
                "chat_message",
                player_id=None,
                name="Система",
                text=text,
                ts=time.time(),
            ),
        )

    @staticmethod
    def _lobby_state_message(lobby: Lobby) -> dict[str, Any]:
        return message("lobby_state", lobby=lobby.view())

    @staticmethod
    def _clamp_max_players(value: Any) -> int:
        try:
            players = int(value)
        except (TypeError, ValueError):
            return 4
        return max(2, min(6, players))

    def _new_lobby_code(self) -> str:
        while True:
            code = "".join(
                secrets.choice(LOBBY_CODE_ALPHABET) for _ in range(LOBBY_CODE_LENGTH)
            )
            if code not in self._lobbies:
                return code
