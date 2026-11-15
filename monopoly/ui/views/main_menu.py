"""Главное меню."""

from __future__ import annotations

import arcade
from arcade.gui import UIBoxLayout, UISpace

from ...config import DEFAULT_PORT
from ...netutil import local_ip
from ...settings import save_settings
from ...validation import clean_player_name
from .. import drawing, theme
from ..widgets import make_button, make_field, make_input, make_label
from .base import BaseView


class MainMenuView(BaseView):
    def __init__(self, window, notice: str | None = None):
        super().__init__(window, notice)
        self.build()

    def build(self) -> None:
        outer = UIBoxLayout(
            vertical=True, align="center", space_between=6, size_hint=(0, 0)
        )
        self.root.add(outer, anchor_x="center", anchor_y="center", align_y=10)

        outer.add(
            make_label(
                "МОНОПОЛИЯ",
                56,
                theme.ACCENT,
                bold=True,
                width=560,
                align="center",
            )
        )
        outer.add(UISpace(width=90, height=3, color=theme.ACCENT))
        outer.add(
            make_label(
                "СЕТЕВАЯ НАСТОЛЬНАЯ ИГРА",
                13,
                theme.MUTED,
                width=560,
                align="center",
            )
        )
        outer.add(UISpace(width=1, height=18, color=theme.BG))

        card = (
            UIBoxLayout(
                vertical=True,
                align="left",
                space_between=12,
                size_hint=(0, 0),
            )
            .with_background(color=theme.SURFACE)
            .with_border(width=1, color=theme.BORDER)
            .with_padding(all=28)
        )
        outer.add(card)

        self.name_input = make_input(364, text=self.window.nickname or "Игрок")
        card.add(make_field("Ваше имя", self.name_input, label_width=364))

        self.error_label = make_label("", 13, theme.DANGER, width=364)
        card.add(self.error_label)

        create_btn = make_button("Создать лобби", 364, 50, "primary")
        join_btn = make_button("Подключиться", 364, 50, "secondary")
        quit_btn = make_button("Выйти", 364, 42, "ghost")
        card.add(create_btn)
        card.add(join_btn)
        card.add(quit_btn)

        @create_btn.event("on_click")
        def _create(_event: object) -> None:
            self._go_host()

        @join_btn.event("on_click")
        def _join(_event: object) -> None:
            self._go_join()

        @quit_btn.event("on_click")
        def _quit(_event: object) -> None:
            self.window.close()

        card.add(make_label("", 8, theme.MUTED, width=364))
        card.add(
            make_label(
                f"Ваш IP: {local_ip()}\nПорт по умолчанию: {DEFAULT_PORT}",
                11,
                theme.MUTED,
                width=364,
                align="center",
            )
        )

        outer.add(UISpace(width=1, height=8, color=theme.BG))
        outer.add(make_label(theme.VERSION_LABEL, 11, theme.MUTED, width=560, align="center"))

    # ------------------------------------------------------------------
    def _apply_name(self) -> bool:
        try:
            name = clean_player_name(self.name_input.text)
        except ValueError as exc:
            self.error_label.text = str(exc)
            return False
        self.name_input.text = name
        self.window.nickname = name
        self.error_label.text = ""
        save_settings({"name": name})
        return True

    def _go_host(self) -> None:
        if self._apply_name():
            self.window.show_host_setup()

    def _go_join(self) -> None:
        if self._apply_name():
            self.window.show_join_setup()

    def on_key_press(self, symbol: int, modifiers: int) -> bool | None:
        if symbol in (arcade.key.ENTER, arcade.key.RETURN):
            self._go_host()
            return True
        return super().on_key_press(symbol, modifiers)

    def on_draw(self) -> None:
        self.clear(theme.BG)
        drawing.draw_background(self.window.width, self.window.height)
        self.finish_draw()
