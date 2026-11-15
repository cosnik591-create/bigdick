"""Экран создания лобби."""

from __future__ import annotations

import time

import arcade
from arcade.gui import UIBoxLayout, UISpace

from ...config import DEFAULT_MAX_PLAYERS, DEFAULT_PORT
from ...netutil import parse_port
from .. import drawing, theme
from ..errors import UiError
from ..widgets import make_button, make_divider, make_field, make_input, make_label
from .base import BaseView


class HostSetupView(BaseView):
    def __init__(self, window, port: int = DEFAULT_PORT):
        super().__init__(window)
        self.default_port = port
        self._pending = False
        self._pending_until = 0.0
        self.build()

    def build(self) -> None:
        back_btn = make_button("← Назад", 130, 42, "ghost")
        self.root.add(back_btn, anchor_x="left", anchor_y="top", align_x=32, align_y=-28)

        @back_btn.event("on_click")
        def _back(_event: object) -> None:
            self._go_back()

        outer = UIBoxLayout(
            vertical=True, align="center", space_between=6, size_hint=(0, 0)
        )
        self.root.add(outer, anchor_x="center", anchor_y="center")

        outer.add(make_label("Создание лобби", 34, theme.TEXT, bold=True, width=640, align="center"))
        outer.add(
            make_label(
                "Ваш компьютер станет сервером партии",
                14,
                theme.MUTED,
                width=640,
                align="center",
            )
        )
        outer.add(UISpace(width=1, height=16, color=theme.BG))

        card = (
            UIBoxLayout(
                vertical=True,
                align="left",
                space_between=14,
                size_hint=(0, 0),
            )
            .with_background(color=theme.SURFACE)
            .with_border(width=1, color=theme.BORDER)
            .with_padding(all=30)
        )
        outer.add(card)

        self.lobby_input = make_input(440, text=f"Лобби {self.window.nickname}".strip())
        card.add(make_field("Название лобби", self.lobby_input, label_width=440))

        row = UIBoxLayout(vertical=False, align="bottom", space_between=16, size_hint=(0, 0))
        self.port_input = make_input(170, text=str(self.default_port))
        self.players_input = make_input(120, text=str(DEFAULT_MAX_PLAYERS))
        row.add(make_field("Порт", self.port_input, hint="обычно 8765", label_width=170))
        row.add(
            make_field(
                "Игроков",
                self.players_input,
                hint="от 2 до 6",
                label_width=120,
            )
        )
        card.add(row)

        self.error_label = make_label("", 13, theme.DANGER, width=440)
        self.status_label = make_label("", 13, theme.MUTED, width=440)
        card.add(self.error_label)
        card.add(self.status_label)

        self.create_btn = make_button("Создать лобби", 440, 50, "primary")
        card.add(self.create_btn)

        @self.create_btn.event("on_click")
        def _create(_event: object) -> None:
            self._create_lobby()

        card.add(make_divider(440))
        card.add(
            make_label(
                "После создания покажите друзьям адрес и код лобби. "
                "Они появятся на следующем экране.",
                11,
                theme.MUTED,
                width=440,
            )
        )

    # ------------------------------------------------------------------
    def _go_back(self) -> None:
        if self._pending:
            self.window.abort_pending_connection()
            self._pending = False
        self.window.show_main_menu()

    def _create_lobby(self) -> None:
        if self._pending:
            return
        try:
            port = parse_port(self.port_input.text, DEFAULT_PORT)
        except ValueError as exc:
            self.error_label.text = str(exc)
            return
        try:
            max_players = int(self.players_input.text.strip())
            if not 2 <= max_players <= 6:
                raise ValueError
        except (TypeError, ValueError):
            self.error_label.text = "Число игроков должно быть от 2 до 6"
            return

        self.error_label.text = ""
        self._pending = True
        self._pending_until = time.monotonic() + 8.0
        self.create_btn.disabled = True
        self.status_label.text = "Запускаем сервер…"

        try:
            self.window.start_hosting(
                port,
                self.lobby_input.text.strip(),
                max_players,
            )
        except UiError as exc:
            self._fail(str(exc))
            return
        self.status_label.text = "Создаём лобби…"

    def _fail(self, message: str) -> None:
        self._pending = False
        self.window.abort_pending_connection()
        self.status_label.text = ""
        self.error_label.text = message
        self.create_btn.disabled = False

    def handle_event(self, event: dict) -> None:
        event_type = event.get("type")
        if event_type == "lobby_state":
            self._pending = False
            lobby = event.get("lobby")
            if isinstance(lobby, dict):
                self.window.show_lobby(lobby)
        elif event_type == "error":
            self._fail(str(event.get("message") or "Не удалось создать лобби"))

    def on_update_view(self, delta_time: float) -> None:
        if self._pending and time.monotonic() > self._pending_until:
            self._fail("Сервер не ответил. Проверьте, свободен ли порт, и попробуйте снова.")

    def on_key_press(self, symbol: int, modifiers: int) -> bool | None:
        if symbol in (arcade.key.ENTER, arcade.key.RETURN):
            self._create_lobby()
            return True
        return super().on_key_press(symbol, modifiers)

    def on_escape(self) -> bool:
        self._go_back()
        return True

    def on_draw(self) -> None:
        self.clear(theme.BG)
        drawing.draw_background(self.window.width, self.window.height)
        self.finish_draw()
