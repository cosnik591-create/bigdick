"""Стилизованные элементы интерфейса на базе arcade.gui."""

from __future__ import annotations

from typing import Callable

import arcade
from arcade.gui import (
    UIAnchorLayout,
    UIBoxLayout,
    UIFlatButton,
    UIInputText,
    UILabel,
    UIMouseEvent,
)

from . import theme


def button_style(variant: str = "primary") -> dict[str, UIFlatButton.UIStyle]:
    if variant == "primary":
        normal_bg, normal_fg = theme.ACCENT, theme.ACCENT_TEXT
        hover_bg, press_bg = theme.ACCENT_HOVER, theme.ACCENT_PRESS
        border = None
    elif variant == "secondary":
        normal_bg, normal_fg = theme.SURFACE_ALT, theme.TEXT
        hover_bg, press_bg = theme.SURFACE_HOVER, theme.BORDER
        border = theme.BORDER
    elif variant == "danger":
        normal_bg, normal_fg = theme.SURFACE_ALT, theme.DANGER
        hover_bg, press_bg = theme.DANGER_DARK, theme.DANGER_DARK
        border = theme.DANGER_DARK
    else:  # ghost
        normal_bg, normal_fg = theme.SURFACE, theme.MUTED
        hover_bg, press_bg = theme.SURFACE_ALT, theme.SURFACE_HOVER
        border = theme.BORDER

    return {
        "normal": UIFlatButton.UIStyle(
            font_name=theme.FONT,
            font_size=16,
            font_color=normal_fg,
            bg=normal_bg,
            border=border,
            border_width=1 if border else 0,
        ),
        "hover": UIFlatButton.UIStyle(
            font_name=theme.FONT,
            font_size=16,
            font_color=theme.ACCENT_TEXT if variant == "primary" else normal_fg,
            bg=hover_bg,
            border=border,
            border_width=1 if border else 0,
        ),
        "press": UIFlatButton.UIStyle(
            font_name=theme.FONT,
            font_size=16,
            font_color=theme.ACCENT_TEXT if variant == "primary" else normal_fg,
            bg=press_bg,
            border=border,
            border_width=1 if border else 0,
        ),
        "disabled": UIFlatButton.UIStyle(
            font_name=theme.FONT,
            font_size=16,
            font_color=theme.MUTED,
            bg=theme.SURFACE,
            border=theme.BORDER,
            border_width=1,
        ),
    }


def make_button(
    text: str,
    width: float,
    height: float = 48,
    variant: str = "primary",
) -> UIFlatButton:
    return UIFlatButton(
        text=text,
        width=width,
        height=height,
        style=button_style(variant),
    )


def style_button(button: UIFlatButton, variant: str, enabled: bool = True) -> None:
    button.style = button_style(variant)
    button.disabled = not enabled
    button.trigger_render()


def input_style() -> dict[str, UIInputText.UIStyle]:
    return {
        "normal": UIInputText.UIStyle(
            bg=theme.SURFACE_ALT, border=theme.BORDER, border_width=2
        ),
        "hover": UIInputText.UIStyle(
            bg=theme.SURFACE_HOVER, border=theme.BORDER_LIGHT, border_width=2
        ),
        "press": UIInputText.UIStyle(
            bg=theme.SURFACE_ALT, border=theme.ACCENT, border_width=2
        ),
        "disabled": UIInputText.UIStyle(
            bg=theme.SURFACE, border=theme.BORDER, border_width=2
        ),
    }


def make_input(
    width: float,
    height: float = 46,
    text: str = "",
    font_size: float = 16,
) -> UIInputText:
    return UIInputText(
        width=width,
        height=height,
        text=text,
        font_name=theme.FONT,
        font_size=font_size,
        text_color=theme.TEXT,
        caret_color=theme.ACCENT,
        style=input_style(),
    )


def make_label(
    text: str,
    size: float = 15,
    color: tuple[int, int, int] = theme.TEXT,
    *,
    bold: bool = False,
    width: float | None = None,
    align: str = "left",
) -> UILabel:
    return UILabel(
        text=text,
        font_name=theme.FONT,
        font_size=size,
        text_color=color,
        bold=bold,
        width=width,
        align=align,
        multiline=width is not None,
    )


def make_field(
    label: str,
    widget: arcade.gui.UIWidget,
    *,
    hint: str | None = None,
    label_width: float | None = None,
) -> UIBoxLayout:
    box = UIBoxLayout(vertical=True, align="left", space_between=7, size_hint=(0, 0))
    box.add(make_label(label, 13, theme.MUTED, width=label_width))
    box.add(widget)
    if hint:
        box.add(make_label(hint, 11, theme.MUTED, width=label_width))
    return box


def make_divider(width: float) -> arcade.gui.UISpace:
    return arcade.gui.UISpace(width=width, height=1, color=theme.BORDER)


class OverlayPanel:
    """Карточка-модалка поверх экрана с произвольным содержимым."""

    def __init__(self, view: arcade.View, width: float = 520, padding: int = 28):
        self.view = view
        self.layer = ModalLayer()
        view.ui.add(self.layer)
        self.box = (
            UIBoxLayout(
                vertical=True,
                align="left",
                space_between=12,
                size_hint=(0, 0),
            )
            .with_background(color=theme.SURFACE)
            .with_border(width=1, color=theme.BORDER)
            .with_padding(all=padding)
        )
        self.layer.add(self.box, anchor_x="center", anchor_y="center")
        view.modals.append(self)
        self.closed = False
        self.width = width

    def add(self, widget: arcade.gui.UIWidget) -> arcade.gui.UIWidget:
        return self.box.add(widget)

    def clear(self) -> None:
        for child in list(self.box.children):
            self.box.remove(child)
        self.view.ui.trigger_render()

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        self.view.ui.remove(self.layer)
        if self in self.view.modals:
            self.view.modals.remove(self)
        if getattr(self.view, "dialog", None) is self:
            self.view.dialog = None


class ModalLayer(UIAnchorLayout):
    """Полноэкранный слой, перехватывающий клики под диалогом."""

    def on_event(self, event: object) -> bool | None:
        result = super().on_event(event)
        if result:
            return result
        if isinstance(event, UIMouseEvent) and self.rect.point_in_rect(event.pos):
            return True
        return None


class ConfirmDialog:
    """Модальное подтверждение действия."""

    def __init__(
        self,
        view: arcade.View,
        title: str,
        message: str,
        on_confirm: Callable[[], None],
        *,
        confirm_text: str = "Да",
        danger: bool = True,
    ):
        self.view = view
        self._on_confirm = on_confirm
        self.layer = ModalLayer()
        view.ui.add(self.layer)

        box = (
            UIBoxLayout(
                vertical=True,
                align="center",
                space_between=18,
                size_hint=(0, 0),
            )
            .with_background(color=theme.SURFACE)
            .with_border(width=1, color=theme.BORDER)
            .with_padding(all=30)
        )
        self.layer.add(box, anchor_x="center", anchor_y="center")

        box.add(make_label(title, 22, theme.TEXT, bold=True))
        box.add(
            make_label(
                message,
                15,
                theme.MUTED,
                width=440,
                align="center",
            )
        )

        row = UIBoxLayout(vertical=False, align="center", space_between=12, size_hint=(0, 0))
        cancel = make_button("Отмена", 190, 44, "secondary")
        confirm = make_button(confirm_text, 190, 44, "danger" if danger else "primary")

        @cancel.event("on_click")
        def _cancel(_event: object) -> None:
            self.close()

        @confirm.event("on_click")
        def _confirm(_event: object) -> None:
            self.close()
            on_confirm()

        row.add(cancel)
        row.add(confirm)
        box.add(row)

    def close(self) -> None:
        self.view.ui.remove(self.layer)
        if getattr(self.view, "dialog", None) is self:
            self.view.dialog = None
