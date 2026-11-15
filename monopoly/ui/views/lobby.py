"""Экран лобби: игроки, готовность, чат."""

from __future__ import annotations

import time
from typing import Any

import arcade
from .. import drawing, theme
from ..widgets import make_button, make_input, style_button
from .base import BaseView

AVATARS = theme.AVATAR_COLORS


class LobbyView(BaseView):
    def __init__(self, window, lobby: dict[str, Any], notice: str | None = None):
        self.lobby = lobby
        self.messages: list[dict[str, Any]] = []
        self._geo: dict[str, float] = {}
        self._last_size: tuple[int, int] = (0, 0)
        self._kick_zones: list[tuple[float, float, float, float, str, str]] = []
        self._code_zone: tuple[float, float, float, float] = (0, 0, 0, 0)
        super().__init__(window, notice)
        self.build()
        self.refresh()
        self.layout()

    # ------------------------------------------------------------------
    # Виджеты
    # ------------------------------------------------------------------
    def build(self) -> None:
        self.ui.remove(self.root)

        self.leave_btn = make_button("Выйти", 140, 46, "ghost")
        # Одна кнопка на действие: у хоста — «Начать игру», у гостя — «Я готов».
        # Две кнопки в одном месте раньше конфликтовали при клике.
        self.action_btn = make_button("Я готов", 210, 46, "primary")
        self.chat_input = make_input(320, 44)
        self.send_btn = make_button("Отправить", 110, 44, "secondary")

        for widget in (
            self.leave_btn,
            self.action_btn,
            self.chat_input,
            self.send_btn,
        ):
            self.ui.add(widget)

        @self.leave_btn.event("on_click")
        def _leave(_event: object) -> None:
            self._request_leave()

        @self.action_btn.event("on_click")
        def _action(_event: object) -> None:
            if self.window.is_host:
                self._start_game()
            else:
                self._toggle_ready()

        @self.send_btn.event("on_click")
        def _send(_event: object) -> None:
            self._send_chat()

    # ------------------------------------------------------------------
    # Геометрия
    # ------------------------------------------------------------------
    def layout(self) -> None:
        width, height = self.window.width, self.window.height
        margin = 44
        header = 150
        bottom = 104
        content_top = height - header
        panel_height = content_top - bottom
        left_width = (width - margin * 2 - 24) * 0.47
        right_x = margin + left_width + 24
        right_width = width - margin - right_x

        self._geo = {
            "width": width,
            "height": height,
            "margin": margin,
            "content_top": content_top,
            "panel_y": bottom,
            "panel_h": panel_height,
            "left_x": margin,
            "left_w": left_width,
            "right_x": right_x,
            "right_w": right_width,
        }
        self._last_size = (width, height)

        self.leave_btn.rect = arcade.LBWH(margin, 40, 140, 46)
        action_x = margin + 156
        self.action_btn.rect = arcade.LBWH(action_x, 40, 210, 46)

        self.chat_input.rect = arcade.LBWH(
            right_x + 20, bottom + 18, right_width - 180, 44
        )
        self.send_btn.rect = arcade.LBWH(
            right_x + right_width - 150, bottom + 18, 130, 44
        )

        code_width = 220
        self._code_zone = (
            width - margin - code_width,
            height - 134,
            code_width,
            84,
        )

        self.ui.trigger_render()

    def on_update_view(self, delta_time: float) -> None:
        if (self.window.width, self.window.height) != self._last_size:
            self.layout()

    def refresh(self) -> None:
        lobby = self.window.lobby or self.lobby
        if not lobby:
            return
        self.lobby = lobby
        me = self.window.me()
        is_host = self.window.is_host
        in_lobby = lobby.get("phase") == "lobby"

        if is_host:
            self.action_btn.text = "Начать игру"
            style_button(
                self.action_btn,
                "primary",
                enabled=bool(lobby.get("can_start")) and in_lobby,
            )
        else:
            ready = bool(me.get("ready")) if me is not None else False
            self.action_btn.text = "Отменить готовность" if ready else "Я готов"
            style_button(
                self.action_btn,
                "secondary" if ready else "primary",
                enabled=in_lobby,
            )
        style_button(self.leave_btn, "ghost", enabled=True)

    # ------------------------------------------------------------------
    # Действия
    # ------------------------------------------------------------------
    def _toggle_ready(self) -> None:
        me = self.window.me()
        if me is None or self.window.client is None:
            return
        self.action_btn.disabled = True
        self.window.client.send("set_ready", ready=not bool(me.get("ready")))

    def _start_game(self) -> None:
        if self.window.client is None:
            return
        self.action_btn.disabled = True
        self.window.client.send("start_game")

    def _send_chat(self) -> None:
        text = self.chat_input.text.strip()
        if not text or self.window.client is None:
            return
        if self.window.client.send("chat", text=text):
            self.chat_input.text = ""

    def _request_leave(self) -> None:
        players = self.lobby.get("players", [])
        if self.window.is_host and len(players) > 1:
            self.ask_confirm(
                "Закрыть лобби?",
                "Вы хост. Сервер остановится, и все игроки покинут лобби.",
                self.window.leave_lobby_to_menu,
                confirm_text="Закрыть лобби",
            )
        else:
            self.window.leave_lobby_to_menu()

    def _confirm_kick(self, player_id: str, name: str) -> None:
        self.ask_confirm(
            "Исключить игрока?",
            f"Игрок {name} потеряет доступ к этому лобби.",
            lambda: self._kick(player_id),
            confirm_text="Исключить",
        )

    def _kick(self, player_id: str) -> None:
        if self.window.client is not None:
            self.window.client.send("kick_player", player_id=player_id)

    def _copy_code(self) -> None:
        code = str(self.lobby.get("code") or "")
        if code:
            self.window.set_clipboard_text(code)
            self.show_toast(f"Код {code} скопирован")

    # ------------------------------------------------------------------
    # События
    # ------------------------------------------------------------------
    def handle_event(self, event: dict[str, Any]) -> None:
        event_type = event.get("type")
        if event_type == "lobby_state":
            lobby = event.get("lobby")
            if isinstance(lobby, dict):
                self.lobby = lobby
                self.refresh()
        elif event_type == "chat_message":
            self.messages.append(event)
            if len(self.messages) > 200:
                del self.messages[:100]
        elif event_type == "game_started":
            self.window.show_game(event.get("game", {}))
        elif event_type == "error":
            self.show_toast(str(event.get("message") or "Ошибка"), error=True)
            self.refresh()

    def on_key_press(self, symbol: int, modifiers: int) -> bool | None:
        if self.dialog is None and symbol in (arcade.key.ENTER, arcade.key.RETURN):
            self._send_chat()
            return True
        return super().on_key_press(symbol, modifiers)

    def on_mouse_press(self, x: int, y: int, button: int, modifiers: int) -> bool | None:
        if self.dialog is not None or button != arcade.MOUSE_BUTTON_LEFT:
            return None

        for zone_x, zone_y, zone_w, zone_h, player_id, name in self._kick_zones:
            if zone_x <= x <= zone_x + zone_w and zone_y <= y <= zone_y + zone_h:
                self._confirm_kick(player_id, name)
                return True

        code_x, code_y, code_w, code_h = self._code_zone
        if code_x <= x <= code_x + code_w and code_y <= y <= code_y + code_h:
            self._copy_code()
            return True
        return None

    def on_escape(self) -> bool:
        self._request_leave()
        return True

    # ------------------------------------------------------------------
    # Отрисовка
    # ------------------------------------------------------------------
    def _status_text(self, players: list[dict[str, Any]]) -> tuple[str, tuple[int, int, int]]:
        if self.lobby.get("phase") != "lobby":
            return "Партия начинается…", theme.ACCENT
        if self.window.is_host:
            if len(players) < 2:
                return "Пригласите хотя бы одного игрока", theme.MUTED
            if not self.lobby.get("can_start"):
                return "Ожидаем готовности игроков", theme.MUTED
            return "Все готовы — можно начинать!", theme.SUCCESS
        me = self.window.me()
        if me is not None and me.get("ready"):
            return "Вы готовы. Ждём, когда хост начнёт игру.", theme.SUCCESS
        return "Отметьте готовность кнопкой «Я готов».", theme.MUTED

    def _player_rows(
        self, players: list[dict[str, Any]]
    ) -> list[tuple[dict[str, Any], float, float, float]]:
        panel_h = self._geo["panel_h"]
        row_h = max(44, min(64, (panel_h - 80) / 6 - 8))
        x = self._geo["left_x"] + 16
        top = self._geo["content_top"] - 58
        rows = []
        for index, player in enumerate(players):
            y = top - row_h - index * (row_h + 8)
            rows.append((player, x, y, row_h))
        return rows

    def on_draw(self) -> None:
        self.clear(theme.BG)
        width, height = self.window.width, self.window.height
        drawing.draw_background(width, height)
        drawing.draw_header_background(width, height)

        players = list(self.lobby.get("players", []))
        me_id = self.window.player_id
        is_host = self.window.is_host
        margin = self._geo["margin"]
        content_top = self._geo["content_top"]

        # Заголовок
        lobby_name = str(self.lobby.get("name") or "Лобби")
        if len(lobby_name) > 30:
            lobby_name = lobby_name[:29] + "…"
        drawing.draw_text(
            f"Лобби «{lobby_name}»",
            margin,
            height - 34,
            size=30,
            color=theme.TEXT,
            bold=True,
        )
        if self.window.host_address:
            subtitle = f"Ваш адрес для друзей: {self.window.host_address}"
        else:
            subtitle = "Вы подключены к лобби хоста"
        drawing.draw_text(subtitle, margin, height - 78, size=14, color=theme.MUTED)
        status, status_color = self._status_text(players)
        drawing.draw_text(status, margin, height - 122, size=13, color=status_color)

        # Код лобби
        code_x, code_y, code_w, code_h = self._code_zone
        drawing.draw_panel(
            code_x,
            code_y,
            code_w,
            code_h,
            fill=theme.SURFACE_ALT,
            border=theme.ACCENT,
        )
        drawing.draw_text(
            "КОД ЛОББИ · КОПИРОВАТЬ",
            code_x + code_w / 2,
            code_y + code_h - 8,
            size=10,
            color=theme.MUTED,
            bold=True,
            anchor_x="center",
        )
        drawing.draw_text(
            str(self.lobby.get("code") or "····"),
            code_x + code_w / 2,
            code_y + 42,
            size=28,
            color=theme.ACCENT,
            bold=True,
            anchor_x="center",
            anchor_y="center",
        )

        # Панель игроков
        panel_y = self._geo["panel_y"]
        panel_h = self._geo["panel_h"]
        left_x = self._geo["left_x"]
        left_w = self._geo["left_w"]
        drawing.draw_panel(left_x, panel_y, left_w, panel_h)
        drawing.draw_text(
            "ИГРОКИ",
            left_x + 20,
            content_top - 24,
            size=12,
            color=theme.MUTED,
            bold=True,
        )
        drawing.draw_text(
            f"{len(players)} / {self.lobby.get('max_players', 6)}",
            left_x + left_w - 20,
            content_top - 24,
            size=12,
            color=theme.MUTED,
            anchor_x="right",
        )

        self._kick_zones = []
        for index, (player, row_x, row_y, row_h) in enumerate(self._player_rows(players)):
            is_me = player.get("id") == me_id
            fill = theme.SURFACE_ALT if is_me else (22, 62, 49)
            arcade.draw_rect_filled(arcade.LBWH(row_x, row_y, left_w - 32, row_h), fill)
            arcade.draw_rect_outline(
                arcade.LBWH(row_x, row_y, left_w - 32, row_h), theme.BORDER, 1
            )
            if player.get("is_host"):
                arcade.draw_rect_filled(
                    arcade.LBWH(row_x, row_y, 3, row_h), theme.ACCENT
                )

            radius = min(16, row_h * 0.3)
            center_y = row_y + row_h / 2
            center_x = row_x + 32
            color = AVATARS[index % len(AVATARS)]
            arcade.draw_circle_filled(center_x, center_y, radius, color)
            arcade.draw_circle_outline(center_x, center_y, radius, theme.BG_DARK, 2)
            drawing.draw_text(
                str(player.get("name", "?"))[:1].upper(),
                center_x,
                center_y,
                size=max(10, radius - 2),
                color=theme.ACCENT_TEXT,
                bold=True,
                anchor_x="center",
                anchor_y="center",
            )

            name = str(player.get("name") or "Игрок")
            name_label = name + ("  ·  вы" if is_me else "")
            drawing.draw_text(
                name_label,
                row_x + 58,
                row_y + row_h / 2,
                size=16 if row_h >= 54 else 14,
                color=theme.TEXT,
                bold=is_me,
                anchor_y="center",
            )

            kickable = is_host and not is_me and self.lobby.get("phase") == "lobby"
            kick_size = 28
            kick_x = row_x + (left_w - 32) - kick_size - 8
            if kickable:
                self._kick_zones.append(
                    (kick_x, center_y - kick_size / 2, kick_size, kick_size, player.get("id", ""), name)
                )
                drawing.draw_text(
                    "✕",
                    kick_x + kick_size / 2,
                    center_y,
                    size=15,
                    color=theme.DANGER,
                    bold=True,
                    anchor_x="center",
                    anchor_y="center",
                )

            chip_w, chip_h = 88, 22
            chip_right = kick_x - 6 if kickable else row_x + (left_w - 32) - 14
            chip_x = chip_right - chip_w
            if player.get("is_host"):
                chip_fill, chip_text, label = (66, 50, 22), theme.ACCENT, "ХОСТ"
            elif player.get("ready"):
                chip_fill, chip_text, label = (26, 66, 47), theme.SUCCESS, "ГОТОВ"
            else:
                chip_fill, chip_text, label = theme.SURFACE, theme.MUTED, "ЖДЁТ"
            drawing.draw_chip(
                chip_x,
                center_y - chip_h / 2,
                chip_w,
                chip_h,
                label,
                fill=chip_fill,
                text_color=chip_text,
                font_size=10,
            )

        # Чат
        right_x = self._geo["right_x"]
        right_w = self._geo["right_w"]
        drawing.draw_panel(right_x, panel_y, right_w, panel_h)
        drawing.draw_text(
            "ЧАТ",
            right_x + 20,
            content_top - 24,
            size=12,
            color=theme.MUTED,
            bold=True,
        )
        drawing.draw_text(
            "Enter — отправить",
            right_x + right_w - 20,
            content_top - 24,
            size=10,
            color=theme.MUTED,
            anchor_x="right",
        )
        if not self.chat_input.text:
            drawing.draw_text(
                "Сообщение",
                right_x + 22,
                panel_y + 74,
                size=10,
                color=theme.MUTED,
            )
        self._draw_chat(right_x, right_w, content_top, panel_y)

        self.finish_draw()

    def _draw_chat(
        self, right_x: float, right_w: float, content_top: float, panel_y: float
    ) -> None:
        x = right_x + 20
        width = int(right_w - 40)
        top = content_top - 52
        bottom = panel_y + 80
        if not self.messages:
            drawing.draw_text(
                "Пока ни одного сообщения.\nПоздоровайтесь с остальными!",
                x,
                top - 8,
                size=13,
                color=theme.MUTED,
                width=width,
            )
            return

        y = bottom
        for message in reversed(self.messages):
            ts = message.get("ts")
            try:
                stamp = time.strftime("%H:%M", time.localtime(float(ts)))
            except (TypeError, ValueError, OSError):
                stamp = "--:--"
            player_id = message.get("player_id")
            if player_id is None:
                content = f"{stamp}  {message.get('text', '')}"
                color = theme.MUTED
            else:
                content = f"{stamp}  {message.get('name', 'Игрок')}: {message.get('text', '')}"
                color = theme.ACCENT if player_id == self.window.player_id else theme.TEXT

            label = arcade.Text(
                text=content,
                x=x,
                y=0,
                color=color,
                font_size=13,
                font_name=theme.FONT,
                width=width,
                multiline=True,
                anchor_y="top",
            )
            height = max(18, label.content_height) + 6
            if y + height > top:
                break
            y += height
            label.y = y - 4
            label.draw()
