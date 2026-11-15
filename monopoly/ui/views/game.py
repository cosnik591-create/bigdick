"""Игровой экран: поле, фишки, кубики и журнал."""

from __future__ import annotations

import math
import random
from typing import Any

import arcade

from ...board import BOARD, Tile
from .. import drawing, theme
from ..widgets import make_button, style_button
from .base import BaseView
from .game_modals import AuctionModal, PropertyModal, PurchaseModal

DICE_ANIM_TIME = 0.7
DICE_SHUFFLE_TIME = 0.055
STEP_ANIM_TIME = 0.14


def _tile_label(cell: Tile) -> str:
    if cell.kind == "property":
        words = cell.name.split()
        if words[0] in ("Улица", "Новый") and len(words) > 1:
            word = words[1]
        else:
            word = words[0]
        return word if len(word) <= 6 else word[:5] + "."
    if cell.kind == "railroad":
        return "Ж/Д"
    if cell.kind == "utility":
        return "ЭЛЕКТРО" if "Электро" in cell.name else "ВОДА"
    return {
        "chance": "ШАНС",
        "chest": "КАЗНА",
        "tax": "НАЛОГ",
        "start": "СТАРТ",
        "jail": "ТЮРЬМА",
        "parking": "ПАРК.",
        "goto_jail": "АРЕСТ",
    }.get(cell.kind, cell.name[:7])


def _fit_label(label: str, tile_width: float, font_size: float) -> str:
    max_chars = max(4, int((tile_width - 7) / (font_size * 0.95)))
    if len(label) <= max_chars:
        return label
    return label[: max_chars - 1] + "…"


def _tile_rect(board_x: float, board_y: float, board_size: float, position: int) -> tuple[float, float, float, float]:
    side = 11
    size = board_size / side
    if 0 <= position <= 10:
        rect = (board_x + board_size - size * (position + 1), board_y)
    elif 11 <= position <= 20:
        rect = (board_x, board_y + size * (position - 10))
    elif 21 <= position <= 30:
        rect = (board_x + size * (position - 20), board_y + board_size - size)
    else:
        rect = (
            board_x + board_size - size,
            board_y + board_size - size * (position - 29),
        )
    return rect[0], rect[1], size, size


class GameView(BaseView):
    def __init__(self, window, game: dict[str, Any]):
        self.game = game
        self._geo: dict[str, float] = {}
        self._last_size: tuple[int, int] = (0, 0)
        self._colors: dict[str, tuple[int, int, int]] = {}
        self._anim: dict[str, Any] | None = None
        self._queued_game: dict[str, Any] | None = None
        self._dice_display: list[int] | None = None
        self._last_notice: str | None = None
        self._jail_visible = False
        self.purchase_modal: PurchaseModal | None = None
        self.auction_modal: AuctionModal | None = None
        self.property_modal: PropertyModal | None = None
        self._assign_colors()
        super().__init__(window)
        self.build()
        self.refresh()
        self.layout()
        self._sync_modals()

    def _assign_colors(self) -> None:
        for index, player in enumerate(self.game.get("players", [])):
            player_id = str(player.get("id"))
            self._colors[player_id] = theme.AVATAR_COLORS[index % len(theme.AVATAR_COLORS)]

    # ------------------------------------------------------------------
    def build(self) -> None:
        self.ui.remove(self.root)
        self.roll_btn = make_button("Бросить кубики", 300, 54, "primary")
        self.leave_btn = make_button("Покинуть партию", 300, 38, "ghost")
        self.jail_pay_btn = make_button("Заплатить 50 ₽", 240, 32, "secondary")
        self.jail_card_btn = make_button("Карта выхода", 240, 32, "secondary")
        self.ui.add(self.roll_btn)
        self.ui.add(self.leave_btn)
        self.ui.add(self.jail_pay_btn)
        self.ui.add(self.jail_card_btn)
        self.jail_pay_btn.visible = False
        self.jail_card_btn.visible = False

        @self.roll_btn.event("on_click")
        def _roll(_event: object) -> None:
            self._roll()

        @self.leave_btn.event("on_click")
        def _leave(_event: object) -> None:
            self._request_leave()

        @self.jail_pay_btn.event("on_click")
        def _pay_jail(_event: object) -> None:
            if self.window.client is not None:
                self.window.client.send("pay_jail")

        @self.jail_card_btn.event("on_click")
        def _jail_card(_event: object) -> None:
            if self.window.client is not None:
                self.window.client.send("use_jail_card")

    def layout(self) -> None:
        width, height = self.window.width, self.window.height
        margin = 24
        header_height = 84
        content_top = height - header_height - 14
        content_bottom = 24
        available_h = content_top - content_bottom

        # Панель игроков сознательно узкая: поле — главный элемент экрана.
        side_width = min(330, max(280, width * 0.25))
        gap = 20
        max_board_width = width - margin * 2 - gap - side_width
        board_size = min(available_h, max_board_width)
        group_width = board_size + gap + side_width
        board_x = max(margin, (width - group_width) / 2)
        board_y = content_bottom + (available_h - board_size) / 2
        right_x = board_x + board_size + gap

        self._geo = {
            "margin": margin,
            "header_height": header_height,
            "board_x": board_x,
            "board_y": board_y,
            "board_size": board_size,
            "right_x": right_x,
            "right_y": board_y,
            "right_w": side_width,
            "right_h": board_size,
            "height": height,
        }
        self._last_size = (width, height)

        self.roll_btn.rect = arcade.LBWH(
            right_x + 14, board_y + 14, side_width - 28, 50
        )
        self.leave_btn.rect = arcade.LBWH(
            right_x + 14, board_y + 72, side_width - 28, 32
        )
        self.jail_pay_btn.rect = arcade.LBWH(
            right_x + 14, board_y + 110, side_width - 28, 32
        )
        self.jail_card_btn.rect = arcade.LBWH(
            right_x + 14, board_y + 148, side_width - 28, 32
        )
        self.ui.trigger_render()

    def on_update_view(self, delta_time: float) -> None:
        if (self.window.width, self.window.height) != self._last_size:
            self.layout()
        self._update_animation(delta_time)

    # ------------------------------------------------------------------
    def refresh(self) -> None:
        my_turn = self.game.get("turn_player_id") == self.window.player_id
        finished = bool(self.game.get("finished"))
        phase = self.game.get("phase")
        animating = self._anim is not None
        me = next(
            (
                player
                for player in self.game.get("players", [])
                if player.get("id") == self.window.player_id
            ),
            None,
        )

        style_button(
            self.roll_btn,
            "primary",
            enabled=my_turn and phase == "await_roll" and not finished and not animating,
        )
        if not animating:
            if my_turn and me is not None and me.get("in_jail"):
                self.roll_btn.text = "Бросить кубики в тюрьме"
            else:
                self.roll_btn.text = "Бросить кубики"
        style_button(self.leave_btn, "ghost", enabled=True)

        jail_active = bool(
            my_turn
            and phase == "await_roll"
            and me is not None
            and me.get("in_jail")
            and not finished
            and not animating
        )
        self.jail_pay_btn.visible = jail_active
        self.jail_card_btn.visible = jail_active
        if me is not None:
            cards = int(me.get("jail_cards") or 0)
            self.jail_card_btn.text = f"Карта выхода ({cards})"
            style_button(
                self.jail_pay_btn,
                "secondary",
                enabled=jail_active and int(me.get("money", 0)) >= 50,
            )
            style_button(
                self.jail_card_btn,
                "secondary",
                enabled=jail_active and cards > 0,
            )
        if jail_active != self._jail_visible:
            self._jail_visible = jail_active
            if self._geo:
                self.layout()

    def _roll(self) -> None:
        if self.window.client is None or self._anim is not None:
            return
        self.roll_btn.disabled = True
        self.window.client.send("roll_dice")

    def _request_leave(self) -> None:
        self.ask_confirm(
            "Покинуть партию?",
            "Вы вернётесь в главное меню. Если игроков станет меньше двух, партия завершится.",
            self.window.leave_lobby_to_menu,
            confirm_text="Покинуть",
        )

    # ------------------------------------------------------------------
    # Модальные окна
    # ------------------------------------------------------------------
    def _sync_modals(self) -> None:
        phase = self.game.get("phase")
        my_turn = self.game.get("turn_player_id") == self.window.player_id
        position = self.game.get("pending_position")

        if phase == "purchase" and my_turn and position is not None:
            if (
                self.purchase_modal is None
                or self.purchase_modal.position != int(position)
            ):
                self._close_purchase_modal()
                self.purchase_modal = PurchaseModal(self, self.game)
            else:
                self.purchase_modal.refresh(self.game)
        else:
            self._close_purchase_modal()

        if phase == "auction" and self.game.get("auction"):
            if self.auction_modal is None:
                self.auction_modal = AuctionModal(self, self.game)
            else:
                self.auction_modal.refresh(self.game)
        else:
            self._close_auction_modal()

        if self.property_modal is not None:
            if phase == "await_roll":
                self.property_modal.refresh(self.game)
            else:
                self.close_property_modal()

    def _close_purchase_modal(self) -> None:
        if self.purchase_modal is not None:
            self.purchase_modal.close()
            self.purchase_modal = None

    def _close_auction_modal(self) -> None:
        if self.auction_modal is not None:
            self.auction_modal.close()
            self.auction_modal = None

    def close_property_modal(self) -> None:
        if self.property_modal is not None:
            self.property_modal.close()
            self.property_modal = None

    def _open_property_modal(self, position: int) -> None:
        self.close_property_modal()
        self.property_modal = PropertyModal(self, position)

    # ------------------------------------------------------------------
    # Анимации
    # ------------------------------------------------------------------
    def _apply_game(self, game: dict[str, Any]) -> None:
        old_players = {str(p.get("id")) for p in self.game.get("players", [])}
        self.game = game
        new_players = {str(p.get("id")) for p in game.get("players", [])}
        if old_players != new_players:
            self._assign_colors()
        self._dice_display = None
        self.refresh()
        self._sync_modals()
        notice = game.get("notice")
        if (
            isinstance(notice, str)
            and notice
            and notice != self._last_notice
            and game.get("phase") not in ("purchase", "auction")
        ):
            self.show_toast(notice, seconds=4.5)
        self._last_notice = notice if isinstance(notice, str) else None

    def _on_game_update(self, game: dict[str, Any]) -> None:
        if self._anim is not None:
            # Пока идёт анимация, держим только самое свежее состояние.
            self._queued_game = game
            return
        old_roll = int(self.game.get("roll_id") or 0)
        new_roll = int(game.get("roll_id") or 0)
        if new_roll != old_roll and self._start_move_animation(self.game, game):
            return
        self._apply_game(game)

    def _start_move_animation(
        self, old_game: dict[str, Any], new_game: dict[str, Any]
    ) -> bool:
        roller_id = old_game.get("turn_player_id")
        new_dice = new_game.get("dice")
        if not roller_id or not isinstance(new_dice, list) or len(new_dice) != 2:
            return False

        old_player = next(
            (p for p in old_game.get("players", []) if p.get("id") == roller_id),
            None,
        )
        new_player = next(
            (p for p in new_game.get("players", []) if p.get("id") == roller_id),
            None,
        )
        if old_player is None or new_player is None:
            return False

        old_pos = int(old_player.get("position", 0))
        new_pos = int(new_player.get("position", 0))
        steps = (new_pos - old_pos) % 40
        if 1 <= steps <= 12:
            path = [(old_pos + step) % 40 for step in range(steps + 1)]
        else:
            # Телепорт/неудачный бросок в тюрьме: анимируем кубики без прохода.
            path = [old_pos]
        faces = [random.randint(1, 6), random.randint(1, 6)]
        self._anim = {
            "new_game": new_game,
            "roller_id": roller_id,
            "roller_name": new_player.get("name") or "Игрок",
            "path": path,
            "dice": [int(new_dice[0]), int(new_dice[1])],
            "faces": faces,
            "phase": "dice",
            "elapsed": 0.0,
            "shuffle": 0.0,
        }
        self._dice_display = list(faces)
        self.roll_btn.text = "Бросаем кубики…"
        self.roll_btn.disabled = True
        return True

    def _finish_animation(self) -> None:
        anim = self._anim
        if anim is None:
            return
        self._anim = None
        self._apply_game(anim["new_game"])

        queued = self._queued_game
        self._queued_game = None
        if queued is not None:
            if not self._start_move_animation(self.game, queued):
                self._apply_game(queued)

    def _update_animation(self, delta_time: float) -> None:
        anim = self._anim
        if anim is None:
            return
        anim["elapsed"] += delta_time

        if anim["phase"] == "dice":
            anim["shuffle"] += delta_time
            if anim["shuffle"] >= DICE_SHUFFLE_TIME:
                anim["shuffle"] = 0.0
                anim["faces"] = [random.randint(1, 6), random.randint(1, 6)]
                self._dice_display = list(anim["faces"])
            if anim["elapsed"] >= DICE_ANIM_TIME:
                anim["elapsed"] = 0.0
                self._dice_display = list(anim["dice"])
                if len(anim["path"]) > 1:
                    anim["phase"] = "move"
                    self.roll_btn.text = "Фишка идёт…"
                else:
                    anim["phase"] = "settle"
                    self.roll_btn.text = "Завершаем ход…"
        elif anim["phase"] == "move":
            steps = len(anim["path"]) - 1
            if anim["elapsed"] >= steps * STEP_ANIM_TIME:
                self._finish_animation()
        elif anim["phase"] == "settle":
            if anim["elapsed"] >= 0.35:
                self._finish_animation()

    def _display_dice(self) -> list[int | None]:
        if self._dice_display is not None:
            return list(self._dice_display)
        dice = self.game.get("dice")
        return list(dice) if isinstance(dice, list) else [None, None]

    def _moving_chip_center(self) -> tuple[float, float]:
        anim = self._anim
        assert anim is not None
        path = anim["path"]
        steps = len(path) - 1
        if anim["phase"] == "dice":
            index, fraction = 0, 0.0
        else:
            moved = min(float(steps), anim["elapsed"] / STEP_ANIM_TIME)
            index = min(int(moved), max(0, steps - 1))
            fraction = moved - index

        x1, y1 = self._chip_anchor(
            self._geo["board_x"],
            self._geo["board_y"],
            self._geo["board_size"],
            path[index],
        )
        x2, y2 = self._chip_anchor(
            self._geo["board_x"],
            self._geo["board_y"],
            self._geo["board_size"],
            path[min(index + 1, steps)],
        )
        x = x1 + (x2 - x1) * fraction
        y = y1 + (y2 - y1) * fraction
        if 0.0 < fraction < 1.0:
            y += math.sin(fraction * math.pi) * 5
        return x, y

    @staticmethod
    def _chip_anchor(
        board_x: float, board_y: float, board_size: float, position: int
    ) -> tuple[float, float]:
        x, y, tw, th = _tile_rect(board_x, board_y, board_size, position)
        if position <= 10:
            return x + tw / 2, y + th * 0.70
        if position <= 20:
            return x + tw * 0.70, y + th / 2
        if position <= 30:
            return x + tw / 2, y + th * 0.30
        return x + tw * 0.30, y + th / 2

    def handle_event(self, event: dict[str, Any]) -> None:
        event_type = event.get("type")
        if event_type == "game_started":
            game = event.get("game")
            if isinstance(game, dict):
                self._anim = None
                self._queued_game = None
                self._apply_game(game)
        elif event_type == "game_update":
            game = event.get("game")
            if isinstance(game, dict):
                self._on_game_update(game)
        elif event_type == "error":
            self.show_toast(str(event.get("message") or "Ошибка"), error=True)
            self.refresh()

    def on_key_press(self, symbol: int, modifiers: int) -> bool | None:
        if symbol == arcade.key.SPACE and self._anim is not None:
            self._finish_animation()
            return True
        if symbol == arcade.key.ESCAPE:
            if self.dialog is not None:
                return super().on_key_press(symbol, modifiers)
            if self.property_modal is not None:
                self.close_property_modal()
                return True
            if self.purchase_modal is not None or self.auction_modal is not None:
                return True
            self._request_leave()
            return True
        return super().on_key_press(symbol, modifiers)

    def on_escape(self) -> bool:
        self._request_leave()
        return True

    def _position_at(self, x: float, y: float) -> int | None:
        board_x = self._geo.get("board_x", 0)
        board_y = self._geo.get("board_y", 0)
        board_size = self._geo.get("board_size", 0)
        if board_size <= 0 or not (
            board_x <= x <= board_x + board_size
            and board_y <= y <= board_y + board_size
        ):
            return None
        side = board_size / 11
        col = int((x - board_x) / side)
        row = int((y - board_y) / side)
        col = max(0, min(10, col))
        row = max(0, min(10, row))
        if row == 0:
            return 10 - col
        if col == 0:
            return 10 + row
        if row == 10:
            return 20 + col
        if col == 10:
            return 30 + (10 - row)
        return None

    def on_mouse_press(self, x: int, y: int, button: int, modifiers: int) -> bool | None:
        if button != arcade.MOUSE_BUTTON_LEFT:
            return None
        if self.dialog is not None or self.modals:
            return None
        if self._anim is not None:
            self._finish_animation()
            return True
        position = self._position_at(x, y)
        if position is None:
            return None
        if any(
            prop.get("position") == position
            for prop in self.game.get("properties", [])
        ):
            self._open_property_modal(position)
            return True
        return None

    # ------------------------------------------------------------------
    def on_draw(self) -> None:
        self.clear(theme.BG)
        width, height = self.window.width, self.window.height
        drawing.draw_background(width, height)
        drawing.draw_header_background(width, height, self._geo["header_height"])

        drawing.draw_text(
            "Партия",
            self._geo["board_x"],
            height - 20,
            size=24,
            color=theme.TEXT,
            bold=True,
        )
        players = self.game.get("players", [])
        turn_id = self.game.get("turn_player_id")
        finished = bool(self.game.get("finished"))
        phase = self.game.get("phase")
        my_turn = turn_id == self.window.player_id
        me = next((p for p in players if p.get("id") == self.window.player_id), None)

        if finished:
            winner = next(
                (p for p in players if p.get("id") == self.game.get("winner_id")),
                None,
            )
            status = f"Партия завершена. Победитель: {winner['name']}" if winner else "Партия завершена"
            status_color = theme.SUCCESS
        elif phase == "purchase":
            turn_name = next((p["name"] for p in players if p.get("id") == turn_id), "—")
            position = self.game.get("pending_position")
            prop = next(
                (
                    item
                    for item in self.game.get("properties", [])
                    if item.get("position") == position
                ),
                None,
            )
            prop_name = f"«{prop['name']}»" if prop else "собственность"
            status = f"{turn_name} решает: купить {prop_name} или аукцион"
            status_color = theme.ACCENT
        elif phase == "auction":
            auction = self.game.get("auction") or {}
            bid = int(auction.get("highest_bid") or 0)
            status = f"Аукцион: «{auction.get('name', '')}»"
            if bid > 0:
                status += f" · ставка {bid} ₽"
            status_color = theme.ACCENT
        elif my_turn:
            if me is not None and me.get("in_jail"):
                status = "Вы в тюрьме: дубль, залог или карта"
            else:
                status = "Ваш ход — бросайте кубики"
            status_color = theme.ACCENT
        else:
            turn_name = next((p["name"] for p in players if p.get("id") == turn_id), "—")
            status = f"Ход: {turn_name}"
            if turn_name != "—":
                turn_player = next((p for p in players if p.get("id") == turn_id), None)
                if turn_player is not None and turn_player.get("in_jail"):
                    status += " (в тюрьме)"
            status_color = theme.MUTED
        drawing.draw_text(
            status,
            self._geo["right_x"] + self._geo["right_w"],
            height - 40,
            size=14,
            color=status_color,
            anchor_x="right",
            anchor_y="center",
        )

        self._draw_board()
        self._draw_sidebar()
        self.finish_draw()

    def _draw_toast(self) -> None:
        # В игре уведомление показываем внутри поля, чтобы не закрывать шапку.
        if not self._toast_text:
            return
        board_size = self._geo.get("board_size", 0)
        side = board_size / 11 if board_size else 0
        width = min(560, max(320, board_size - side * 2 - 24))
        inner_width = int(width - 40)
        measure = drawing.text_object(
            self._toast_text,
            0,
            0,
            size=14,
            width=inner_width,
            align="center",
        )
        height = max(44, measure.content_height + 18)
        x = self._geo.get("board_x", 0) + (board_size - width) / 2
        y = (
            self._geo.get("board_y", 0)
            + board_size
            - side
            - 10
            - height
        )
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

    def _draw_board(self) -> None:
        board_x = self._geo["board_x"]
        board_y = self._geo["board_y"]
        board_size = self._geo["board_size"]
        side = board_size / 11

        arcade.draw_rect_filled(
            arcade.LBWH(board_x, board_y, board_size, board_size), theme.BG_DARK
        )
        property_map = {
            int(prop["position"]): prop for prop in self.game.get("properties", [])
        }

        for position, cell in enumerate(BOARD):
            x, y, tw, th = _tile_rect(board_x, board_y, board_size, position)
            if cell.kind == "property":
                fill = (23, 64, 50)
            elif cell.kind in ("railroad", "utility"):
                fill = (30, 55, 48)
            elif cell.kind in ("chance", "chest"):
                fill = (31, 65, 50)
            else:
                fill = (18, 49, 39)
            arcade.draw_rect_filled(arcade.LBWH(x, y, tw, th), fill)
            arcade.draw_rect_outline(arcade.LBWH(x, y, tw, th), theme.BORDER, 1)

            if cell.group:
                strip = max(5, tw * 0.14)
                if position <= 10:
                    strip_rect = (x, y + th - strip, tw, strip)
                elif position <= 20:
                    strip_rect = (x + tw - strip, y, strip, th)
                elif position <= 30:
                    strip_rect = (x, y, tw, strip)
                else:
                    strip_rect = (x, y, strip, th)
                arcade.draw_rect_filled(
                    arcade.LBWH(*strip_rect),
                    theme.GROUP_COLORS.get(cell.group, theme.MUTED),
                )

            prop = property_map.get(position)
            owner_id = prop.get("owner_id") if prop else None
            if owner_id:
                owner_color = self._colors.get(str(owner_id), theme.MUTED)
                arcade.draw_rect_outline(
                    arcade.LBWH(x + 1, y + 1, tw - 2, th - 2), owner_color, 2
                )
                if prop.get("mortgaged"):
                    arcade.draw_line(
                        x + 4,
                        y + 4,
                        x + tw - 4,
                        y + th - 4,
                        theme.DANGER,
                        2,
                    )
                houses = int(prop.get("houses") or 0)
                if houses > 0:
                    house_color = theme.DANGER if houses == 5 else theme.SUCCESS
                    if position <= 10:
                        base_x, base_y = x + tw / 2, y + th - 13
                    elif position <= 20:
                        base_x, base_y = x + tw - 13, y + th / 2
                    elif position <= 30:
                        base_x, base_y = x + tw / 2, y + 13
                    else:
                        base_x, base_y = x + 13, y + th / 2

                    if houses == 5:
                        if position <= 10 or position >= 31:
                            rect_w, rect_h = 14, 7
                        else:
                            rect_w, rect_h = 7, 14
                        arcade.draw_rect_filled(
                            arcade.LBWH(
                                base_x - rect_w / 2,
                                base_y - rect_h / 2,
                                rect_w,
                                rect_h,
                            ),
                            house_color,
                        )
                    else:
                        size_sq = 5
                        spacing = 7
                        for index in range(houses):
                            offset = (index - (houses - 1) / 2) * spacing
                            if position <= 10 or (21 <= position <= 30):
                                hx = base_x + offset
                                hy = base_y
                            else:
                                hx = base_x
                                hy = base_y + offset
                            arcade.draw_rect_filled(
                                arcade.LBWH(
                                    hx - size_sq / 2, hy - size_sq / 2, size_sq, size_sq
                                ),
                                house_color,
                            )

            font_size = max(5.8, min(7.0, tw * 0.125))
            label = _fit_label(_tile_label(cell), tw, font_size)
            if position <= 10:
                label_x, label_y = x + tw / 2, y + th * 0.30
            elif position <= 20:
                label_x, label_y = x + tw * 0.31, y + th / 2
            elif position <= 30:
                label_x, label_y = x + tw / 2, y + th * 0.70
            else:
                label_x, label_y = x + tw * 0.69, y + th / 2
            drawing.draw_text(
                label,
                label_x,
                label_y,
                size=font_size,
                color=theme.TEXT if cell.kind == "property" else theme.MUTED,
                bold=cell.kind in ("start", "jail", "parking", "goto_jail"),
                anchor_x="center",
                anchor_y="center",
            )

        # Фишки игроков
        moving_id = self._anim["roller_id"] if self._anim is not None else None
        grouped: dict[int, list[dict[str, Any]]] = {}
        index_by_id = {
            str(player.get("id")): index + 1
            for index, player in enumerate(self.game.get("players", []))
        }
        for player in self.game.get("players", []):
            if not player.get("connected", True) or player.get("bankrupt"):
                continue
            if moving_id is not None and player.get("id") == moving_id:
                continue
            grouped.setdefault(int(player.get("position", 0)), []).append(player)

        radius = max(6, min(9, (board_size / 11) * 0.15))
        for position, group in grouped.items():
            chip_x, chip_y = self._chip_anchor(board_x, board_y, board_size, position)
            columns = min(3, len(group))
            rows = (len(group) + columns - 1) // columns
            for index, player in enumerate(group):
                col = index % columns
                row = index // columns
                offset_x = (col - (columns - 1) / 2) * (radius * 2 + 2)
                offset_y = (row - (rows - 1) / 2) * (radius * 2 + 2)
                cx, cy = chip_x + offset_x, chip_y + offset_y
                color = self._colors.get(str(player.get("id")), theme.ACCENT)
                if player.get("is_current"):
                    arcade.draw_circle_filled(cx, cy, radius + 3, theme.WHITE)
                arcade.draw_circle_filled(cx, cy, radius, color)
                arcade.draw_circle_outline(cx, cy, radius, theme.BG_DARK, 2)
                drawing.draw_text(
                    str(index_by_id.get(str(player.get("id")), "")),
                    cx,
                    cy,
                    size=max(6, radius),
                    color=theme.ACCENT_TEXT,
                    bold=True,
                    anchor_x="center",
                    anchor_y="center",
                )

        if moving_id is not None:
            cx, cy = self._moving_chip_center()
            color = self._colors.get(str(moving_id), theme.ACCENT)
            arcade.draw_circle_filled(cx, cy, radius + 3, theme.WHITE)
            arcade.draw_circle_filled(cx, cy, radius, color)
            arcade.draw_circle_outline(cx, cy, radius, theme.BG_DARK, 2)
            drawing.draw_text(
                str(index_by_id.get(str(moving_id), "")),
                cx,
                cy,
                size=max(6, radius),
                color=theme.ACCENT_TEXT,
                bold=True,
                anchor_x="center",
                anchor_y="center",
            )

        # Центр поля
        inner_x = board_x + side
        inner_y = board_y + side
        inner_size = board_size - side * 2
        arcade.draw_rect_filled(
            arcade.LBWH(inner_x, inner_y, inner_size, inner_size), (10, 32, 24)
        )
        arcade.draw_rect_outline(
            arcade.LBWH(inner_x, inner_y, inner_size, inner_size), theme.BORDER, 1
        )

        center_x = board_x + board_size / 2
        center_y = board_y + board_size / 2
        drawing.draw_text(
            "МОНОПОЛИЯ",
            center_x,
            center_y + inner_size * 0.24,
            size=max(26, inner_size * 0.085),
            color=theme.ACCENT,
            bold=True,
            anchor_x="center",
            anchor_y="center",
        )
        drawing.draw_text(
            "СЕТЕВАЯ НАСТОЛЬНАЯ ИГРА",
            center_x,
            center_y + inner_size * 0.13,
            size=max(9, inner_size * 0.027),
            color=theme.MUTED,
            bold=True,
            anchor_x="center",
            anchor_y="center",
        )

        dice = self._display_dice()
        die_size = max(38, inner_size * 0.105)
        gap = die_size * 0.25
        dice_animating = self._anim is not None and self._anim["phase"] == "dice"
        for index, value in enumerate(dice):
            dx = center_x - die_size - gap / 2 + index * (die_size + gap)
            dy = center_y - inner_size * 0.14
            if dice_animating and self._anim is not None:
                dy += abs(math.sin(self._anim["elapsed"] * 22 + index)) * 6
            arcade.draw_rect_filled(
                arcade.LBWH(dx, dy, die_size, die_size), theme.SURFACE_ALT
            )
            arcade.draw_rect_outline(
                arcade.LBWH(dx, dy, die_size, die_size), theme.ACCENT, 2
            )
            drawing.draw_text(
                str(value) if value else "–",
                dx + die_size / 2,
                dy + die_size / 2,
                size=die_size * 0.46,
                color=theme.ACCENT,
                bold=True,
                anchor_x="center",
                anchor_y="center",
            )

        turn_player = next(
            (p for p in self.game.get("players", []) if p.get("id") == self.game.get("turn_player_id")),
            None,
        )
        if self._anim is not None:
            phase = self._anim["phase"]
            if phase == "dice":
                hint = f"{self._anim['roller_name']} бросает кубики…"
            else:
                hint = f"{self._anim['roller_name']} делает ход"
            hint_color = theme.ACCENT
        elif self.game.get("finished"):
            hint = "Игра завершена"
            hint_color = theme.SUCCESS
        elif self.game.get("phase") == "purchase":
            hint = "Решаем судьбу собственности"
            hint_color = theme.ACCENT
        elif self.game.get("phase") == "auction":
            hint = "Идёт аукцион"
            hint_color = theme.ACCENT
        elif turn_player and turn_player.get("id") == self.window.player_id:
            hint = "Вы в тюрьме" if turn_player.get("in_jail") else "Ваш ход"
            hint_color = theme.DANGER if turn_player.get("in_jail") else theme.SUCCESS
        elif turn_player:
            hint = f"Ход: {turn_player.get('name')}"
            hint_color = theme.MUTED
        else:
            hint = "Ожидание"
            hint_color = theme.MUTED
        drawing.draw_text(
            hint,
            center_x,
            center_y - inner_size * 0.32,
            size=max(12, inner_size * 0.032),
            color=hint_color,
            bold=True,
            anchor_x="center",
            anchor_y="center",
        )
        if self._anim is None and not self.game.get("finished"):
            drawing.draw_text(
                "Клик по клетке — карточка собственности",
                center_x,
                center_y - inner_size * 0.385,
                size=max(9, inner_size * 0.021),
                color=theme.MUTED,
                anchor_x="center",
                anchor_y="center",
            )

    def _draw_sidebar(self) -> None:
        right_x = self._geo["right_x"]
        right_y = self._geo["right_y"]
        right_w = self._geo["right_w"]
        panel_h = self._geo["right_h"]
        inner_x = right_x + 14
        inner_w = right_w - 28

        drawing.draw_panel(right_x, right_y, right_w, panel_h)
        drawing.draw_text(
            "ИГРОКИ",
            inner_x,
            right_y + panel_h - 18,
            size=11,
            color=theme.MUTED,
            bold=True,
        )
        drawing.draw_text(
            f"{len(self.game.get('players', []))}",
            right_x + right_w - 14,
            right_y + panel_h - 18,
            size=11,
            color=theme.MUTED,
            anchor_x="right",
        )

        players = self.game.get("players", [])
        count = max(1, len(players))
        reserved = 280 + (80 if self._jail_visible else 0)
        row_h = max(38, min(52, (panel_h - reserved) / count))
        gap = 5
        rows_top = right_y + panel_h - 36

        for index, player in enumerate(players):
            row_y = rows_top - (index + 1) * (row_h + gap)
            bankrupt = bool(player.get("bankrupt"))
            connected_player = bool(player.get("connected", True))
            is_current = (
                player.get("id") == self.game.get("turn_player_id")
                and not bankrupt
            )
            fill = theme.SURFACE_ALT if is_current else (22, 62, 49)
            arcade.draw_rect_filled(
                arcade.LBWH(inner_x, row_y, inner_w, row_h), fill
            )
            arcade.draw_rect_outline(
                arcade.LBWH(inner_x, row_y, inner_w, row_h),
                theme.BORDER,
                1,
            )
            color = (
                (70, 82, 76)
                if bankrupt
                else self._colors.get(str(player.get("id")), theme.ACCENT)
            )
            if is_current:
                arcade.draw_rect_filled(
                    arcade.LBWH(inner_x, row_y, 3, row_h), theme.ACCENT
                )

            radius = min(13, row_h * 0.29)
            cx = inner_x + 24
            cy = row_y + row_h / 2
            arcade.draw_circle_filled(cx, cy, radius, color)
            arcade.draw_circle_outline(cx, cy, radius, theme.BG_DARK, 2)
            drawing.draw_text(
                str(index + 1),
                cx,
                cy,
                size=max(8, radius - 2),
                color=theme.ACCENT_TEXT,
                bold=True,
                anchor_x="center",
                anchor_y="center",
            )

            name = str(player.get("name") or "Игрок")
            if len(name) > 20:
                name = name[:19] + "…"
            if player.get("id") == self.window.player_id:
                name += " · вы"
            drawing.draw_text(
                name,
                inner_x + 42,
                cy + 9,
                size=13,
                color=theme.TEXT if connected_player and not bankrupt else theme.MUTED,
                bold=player.get("id") == self.window.player_id,
                anchor_y="center",
            )

            if bankrupt:
                subtitle = "банкрот"
                subtitle_color = theme.DANGER
            elif not connected_player:
                subtitle = "нет связи"
                subtitle_color = theme.DANGER
            elif player.get("in_jail"):
                subtitle = (
                    f"тюрьма · попытка {int(player.get('jail_turns') or 0)}/3"
                )
                subtitle_color = theme.DANGER
            else:
                subtitle = str(player.get("position_name", ""))
                subtitle_color = theme.MUTED
            max_chars = max(6, int((inner_w - 42 - 95) / 7.0))
            if len(subtitle) > max_chars:
                subtitle = subtitle[: max_chars - 1] + "…"
            drawing.draw_text(
                subtitle,
                inner_x + 42,
                cy - 9,
                size=9,
                color=subtitle_color,
                anchor_y="center",
            )
            drawing.draw_text(
                drawing.format_money(int(player.get("money", 0))),
                right_x + right_w - 14,
                cy - 9,
                size=11,
                color=theme.MUTED if bankrupt else theme.ACCENT,
                bold=not bankrupt,
                anchor_x="right",
                anchor_y="center",
            )

        buttons_top = right_y + (188 if self._jail_visible else 112)
        log_header_y = rows_top - count * (row_h + gap) - 18
        if log_header_y - 22 - buttons_top >= 30:
            drawing.draw_text(
                "ЖУРНАЛ",
                inner_x,
                log_header_y,
                size=11,
                color=theme.MUTED,
                bold=True,
            )
            self._draw_log(
                inner_x,
                int(inner_w),
                log_header_y - 22,
                buttons_top,
            )

    def _draw_log(self, x: float, width: int, top: float, bottom: float) -> None:
        available = top - bottom
        if available < 12:
            return
        selected: list[tuple[arcade.Text, float]] = []
        used = 0.0
        for message in reversed(self.game.get("log", [])):
            label = arcade.Text(
                text=str(message),
                x=x,
                y=0,
                color=theme.MUTED,
                font_size=11,
                font_name=theme.FONT,
                width=width,
                multiline=True,
                anchor_y="top",
            )
            height = max(16, label.content_height) + 5
            if used + height > available:
                break
            selected.append((label, height))
            used += height

        y = top
        for label, height in reversed(selected):
            label.y = y
            label.draw()
            y -= height
