"""Базовый экран: сеть, уведомления, модальные окна."""

from __future__ import annotations

import queue
import time
from typing import Any, TYPE_CHECKING

import arcade
from arcade.gui import UIAnchorLayout, UIManager

from ...config import HEARTBEAT_INTERVAL
from .. import drawing, theme
from ..widgets import ConfirmDialog

if TYPE_CHECKING:
    from .app import MonopolyWindow


class BaseView(arcade.View):
    def __init__(self, window: "MonopolyWindow", notice: str | None = None):
        super().__init__(window)
        self.window: "MonopolyWindow" = window
        self.ui = UIManager(window=window)
        self.root = UIAnchorLayout()
        self.ui.add(self.root)
        self.dialog: ConfirmDialog | None = None
        self.modals: list[object] = []

        self._toast_text = ""
        self._toast_error = False
        self._toast_until = 0.0
        self._heartbeat_timer = 0.0

        if notice:
            self.show_toast(notice, error=True, seconds=6.0)

    # ------------------------------------------------------------------
    # Жизненный цикл
    # ------------------------------------------------------------------
    def on_show_view(self) -> None:
        self.window.active_view = self
        self.ui.enable()
        self.on_show()

    def on_hide_view(self) -> None:
        self.ui.disable()

    def on_show(self) -> None:
        pass

    def on_update(self, delta_time: float) -> None:
        self._poll_network()
        if self.window.active_view is not self:
            return
        self._heartbeat_timer += delta_time
        if self._heartbeat_timer >= HEARTBEAT_INTERVAL:
            self._heartbeat_timer = 0.0
            if self.window.client is not None:
                self.window.client.send("ping")
        if self._toast_text and time.monotonic() > self._toast_until:
            self._toast_text = ""
        self.on_update_view(delta_time)

    def on_update_view(self, delta_time: float) -> None:
        pass

    def on_key_press(self, symbol: int, modifiers: int) -> bool | None:
        if symbol == arcade.key.ESCAPE:
            if self.dialog is not None:
                self.dialog.close()
                return True
            return self.on_escape()
        return None

    def on_escape(self) -> bool:
        return False

    # ------------------------------------------------------------------
    # Сеть
    # ------------------------------------------------------------------
    def _poll_network(self) -> None:
        if self.window._closing:
            return
        client = self.window.client
        if client is None:
            return
        while True:
            try:
                event = client.events.get_nowait()
            except queue.Empty:
                break
            if self.window.client is not client:
                return
            if self.window.handle_global_event(event):
                if self.window.active_view is not self:
                    return
                continue
            self.handle_event(event)
            if self.window.active_view is not self:
                return

    def handle_event(self, event: dict[str, Any]) -> None:
        pass

    # ------------------------------------------------------------------
    # Уведомления и подтверждения
    # ------------------------------------------------------------------
    def show_toast(self, text: str, *, error: bool = False, seconds: float = 4.0) -> None:
        self._toast_text = text
        self._toast_error = error
        self._toast_until = time.monotonic() + seconds

    def ask_confirm(
        self,
        title: str,
        message: str,
        on_confirm: Any,
        *,
        confirm_text: str = "Да",
        danger: bool = True,
    ) -> None:
        if self.dialog is not None:
            return
        self.dialog = ConfirmDialog(
            self,
            title,
            message,
            on_confirm,
            confirm_text=confirm_text,
            danger=danger,
        )

    def finish_draw(self) -> None:
        if self.dialog is not None or self.modals:
            arcade.draw_rect_filled(
                arcade.LBWH(0, 0, self.window.width, self.window.height),
                (4, 15, 11, 200),
            )
        self.ui.draw()
        self._draw_toast()

    def _draw_toast(self) -> None:
        if not self._toast_text:
            return
        width = min(620, self.window.width - 80)
        inner_width = int(width - 40)
        measure = drawing.text_object(
            self._toast_text,
            0,
            0,
            size=14,
            width=inner_width,
            align="center",
        )
        height = max(48, measure.content_height + 22)
        x = (self.window.width - width) / 2
        y = self.window.height - 30 - height
        fill = theme.DANGER_DARK if self._toast_error else theme.SURFACE_ALT
        border = theme.DANGER if self._toast_error else theme.ACCENT
        drawing.draw_panel(x, y, width, height, fill=fill, border=border)
        drawing.draw_text(
            self._toast_text,
            x + width / 2,
            y + height / 2,
            size=14,
            color=theme.TEXT,
            anchor_x="center",
            anchor_y="center",
            width=inner_width,
            align="center",
        )
