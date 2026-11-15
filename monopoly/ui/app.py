"""Окно приложения: состояние сети и переключение экранов."""

from __future__ import annotations

import logging
from typing import Any

import arcade

from ..client import NetworkClient, NetworkError
from ..config import APP_NAME, DEFAULT_PORT, PROTOCOL_VERSION
from ..netutil import format_address, local_ip
from ..server import MonopolyServer
from ..settings import load_settings, save_settings
from .errors import UiError
from .views.game import GameView
from .views.host_setup import HostSetupView
from .views.join_setup import JoinSetupView
from .views.lobby import LobbyView
from .views.main_menu import MainMenuView

log = logging.getLogger("monopoly.ui")


class MonopolyWindow(arcade.Window):
    def __init__(self) -> None:
        super().__init__(
            1280,
            800,
            f"{APP_NAME} — сетевая игра",
            resizable=True,
            center_window=True,
            antialiasing=True,
            samples=4,
        )
        self.set_minimum_size(1000, 680)

        self.settings = load_settings()
        self.nickname = str(self.settings.get("name") or "")
        self.default_port = self._settings_port()

        self.client: NetworkClient | None = None
        self.server: MonopolyServer | None = None
        self.player_id: str | None = None
        self.lobby: dict[str, Any] | None = None
        self.host_address: str | None = None

        self.active_view: Any = None
        self._closing = False

        self.show_main_menu()

    def _settings_port(self) -> int:
        try:
            port = int(self.settings.get("port") or DEFAULT_PORT)
        except (TypeError, ValueError):
            return DEFAULT_PORT
        return port if 1 <= port <= 65535 else DEFAULT_PORT

    # ------------------------------------------------------------------
    # Переключение экранов
    # ------------------------------------------------------------------
    def show_main_menu(self, notice: str | None = None) -> None:
        self.show_view(MainMenuView(self, notice=notice))

    def show_host_setup(self) -> None:
        self.show_view(HostSetupView(self, port=self.default_port))

    def show_join_setup(self) -> None:
        address = str(self.settings.get("last_address") or "")
        self.show_view(JoinSetupView(self, address=address))

    def show_lobby(self, lobby: dict[str, Any], notice: str | None = None) -> None:
        self.lobby = lobby
        self.show_view(LobbyView(self, lobby=lobby, notice=notice))

    def show_game(self, game: dict[str, Any]) -> None:
        self.show_view(GameView(self, game=game))

    # ------------------------------------------------------------------
    # Сетевое состояние
    # ------------------------------------------------------------------
    @property
    def is_host(self) -> bool:
        return bool(
            self.lobby
            and self.player_id
            and self.lobby.get("host_id") == self.player_id
        )

    def me(self) -> dict[str, Any] | None:
        if not self.lobby or not self.player_id:
            return None
        for player in self.lobby.get("players", []):
            if player.get("id") == self.player_id:
                return player
        return None

    def _open_client(self, host: str, port: int) -> None:
        client = NetworkClient()
        client.connect(host, port)
        self.client = client

    def start_hosting(self, port: int, lobby_name: str, max_players: int) -> None:
        self.shutdown_networking()
        try:
            server = MonopolyServer(("0.0.0.0", port))
        except OSError as exc:
            reason = exc.strerror or str(exc)
            raise UiError(f"Не удалось открыть порт {port}: {reason}") from exc

        server.start()
        self.server = server
        try:
            self._open_client("127.0.0.1", port)
        except NetworkError as exc:
            self.shutdown_networking()
            raise UiError(str(exc)) from exc

        self.host_address = format_address(local_ip(), port)
        self.default_port = port
        self.settings["port"] = port
        assert self.client is not None
        self.client.send(
            "create_lobby",
            name=self.nickname,
            lobby_name=lobby_name,
            max_players=max_players,
        )
        save_settings({"name": self.nickname, "port": port})

    def connect_to_game(self, host: str, port: int) -> None:
        self.shutdown_networking()
        try:
            self._open_client(host, port)
        except NetworkError as exc:
            self.shutdown_networking()
            raise UiError(str(exc)) from exc
        address = format_address(host, port)
        self.settings["last_address"] = address
        save_settings({"name": self.nickname, "last_address": address})

    def abort_pending_connection(self) -> None:
        self.shutdown_networking()

    def leave_lobby_to_menu(self) -> None:
        self.shutdown_networking(send_leave=True)
        self.show_main_menu()

    def disconnect_to_menu(self, notice: str) -> None:
        self.shutdown_networking()
        self.show_main_menu(notice=notice)

    def shutdown_networking(self, *, send_leave: bool = False) -> None:
        client, self.client = self.client, None
        if client is not None:
            if send_leave and client.connected:
                client.send("leave_lobby")
            client.close()

        server, self.server = self.server, None
        if server is not None:
            try:
                server.stop()
            except Exception:  # pragma: no cover - при выходе важно не упасть
                log.exception("Ошибка при остановке сервера")

        self.player_id = None
        self.lobby = None
        self.host_address = None

    # ------------------------------------------------------------------
    # События, важные для всех экранов
    # ------------------------------------------------------------------
    def handle_global_event(self, event: dict[str, Any]) -> bool:
        if self._closing:
            return True
        event_type = event.get("type")

        if event_type == "_disconnected":
            if self._closing:
                return True
            reason = str(event.get("reason") or "Соединение с сервером потеряно")
            self.shutdown_networking()
            self.show_main_menu(notice=reason)
            return True

        if event_type == "hello_ok":
            self.player_id = event.get("player_id")
            if event.get("version") != PROTOCOL_VERSION:
                self.shutdown_networking()
                self.show_main_menu(
                    notice="Версия игры не совпадает с версией сервера. Обновите игру."
                )
            return True

        if event_type == "pong":
            return True

        if event_type == "lobby_state":
            lobby = event.get("lobby")
            if isinstance(lobby, dict):
                self.lobby = lobby
            return False

        if event_type == "kicked":
            reason = str(event.get("reason") or "Вас исключили из лобби")
            self.shutdown_networking()
            self.show_main_menu(notice=reason)
            return True

        if event_type == "lobby_closed":
            reason = str(event.get("reason") or "Лобби закрыто")
            self.shutdown_networking()
            self.show_main_menu(notice=reason)
            return True

        if event_type == "game_aborted":
            reason = str(event.get("reason") or "Партия прервана")
            if self.lobby is not None:
                self.show_lobby(self.lobby, notice=reason)
            else:
                self.shutdown_networking()
                self.show_main_menu(notice=reason)
            return True

        return False

    # ------------------------------------------------------------------
    # Завершение работы
    # ------------------------------------------------------------------
    def close(self) -> None:
        self._closing = True
        self.shutdown_networking()
        super().close()

    def on_close(self) -> None:
        self._closing = True
        self.shutdown_networking()
        super().on_close()
