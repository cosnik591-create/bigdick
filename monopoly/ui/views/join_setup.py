"""Экран подключения к чужому лобби."""

from __future__ import annotations

import time

import arcade
from arcade.gui import UIBoxLayout, UISpace

from ...netutil import parse_address
from .. import drawing, theme
from ..errors import UiError
from ..widgets import make_button, make_divider, make_field, make_input, make_label
from .base import BaseView


class JoinSetupView(BaseView):
    def __init__(self, window, address: str = ""):
        super().__init__(window)
        self.default_address = address
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

        outer.add(
            make_label(
                "Подключение к лобби",
                34,
                theme.TEXT,
                bold=True,
                width=640,
                align="center",
            )
        )
        outer.add(
            make_label(
                "Введите адрес хоста и код комнаты",
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

        self.address_input = make_input(440, text=self.default_address)
        card.add(
            make_field(
                "Адрес сервера",
                self.address_input,
                hint="например, 192.168.0.5:8765",
                label_width=440,
            )
        )

        self.code_input = make_input(200, text="")
        card.add(
            make_field(
                "Код лобби",
                self.code_input,
                hint="4 символа, например AB3D",
                label_width=440,
            )
        )

        self.error_label = make_label("", 13, theme.DANGER, width=440)
        self.status_label = make_label("", 13, theme.MUTED, width=440)
        card.add(self.error_label)
        card.add(self.status_label)

        self.join_btn = make_button("Войти в лобби", 440, 50, "primary")
        card.add(self.join_btn)

        @self.join_btn.event("on_click")
        def _join(_event: object) -> None:
            self._join_lobby()

        card.add(make_divider(440))
        card.add(
            make_label(
                "Адрес и код лобби сообщает хост. "
                "Убедитесь, что вы в одной сети или порт открыт в интернет.",
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

    def _join_lobby(self) -> None:
        if self._pending:
            return
        try:
            host, port = parse_address(self.address_input.text)
        except ValueError as exc:
            self.error_label.text = str(exc)
            return
        code = self.code_input.text.strip().upper()
        if not code:
            self.error_label.text = "Введите код лобби"
            return
        if not self.window.nickname:
            self.error_label.text = "Вернитесь в меню и укажите имя"
            return

        self.error_label.text = ""
        self._pending = True
        self._pending_until = time.monotonic() + 8.0
        self.join_btn.disabled = True
        self.status_label.text = "Подключаемся…"

        try:
            self.window.connect_to_game(host, port)
        except UiError as exc:
            self._fail(str(exc))
            return

        assert self.window.client is not None
        self.window.client.send(
            "join_lobby",
            name=self.window.nickname,
            code=code,
        )
        self.status_label.text = "Проверяем лобби…"

    def _fail(self, message: str) -> None:
        self._pending = False
        self.window.abort_pending_connection()
        self.status_label.text = ""
        self.error_label.text = message
        self.join_btn.disabled = False

    def handle_event(self, event: dict) -> None:
        event_type = event.get("type")
        if event_type == "lobby_state":
            self._pending = False
            lobby = event.get("lobby")
            if isinstance(lobby, dict):
                self.window.show_lobby(lobby)
        elif event_type == "error":
            self._fail(str(event.get("message") or "Не удалось войти в лобби"))

    def on_update_view(self, delta_time: float) -> None:
        if self._pending and time.monotonic() > self._pending_until:
            self._fail("Сервер не ответил. Проверьте адрес и код лобби.")

    def on_key_press(self, symbol: int, modifiers: int) -> bool | None:
        if symbol in (arcade.key.ENTER, arcade.key.RETURN):
            self._join_lobby()
            return True
        return super().on_key_press(symbol, modifiers)

    def on_escape(self) -> bool:
        self._go_back()
        return True

    def on_draw(self) -> None:
        self.clear(theme.BG)
        drawing.draw_background(self.window.width, self.window.height)
        self.finish_draw()
