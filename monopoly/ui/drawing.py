"""Помощники для немедленной отрисовки: текст, панели, фон."""

from __future__ import annotations

from typing import Any

import arcade

from . import theme

_TEXT_CACHE: dict[tuple[Any, ...], arcade.Text] = {}
_MAX_CACHE = 600


def text_object(
    content: str,
    x: float,
    y: float,
    *,
    size: float = 15,
    color: tuple[int, int, int] | tuple[int, int, int, int] = theme.TEXT,
    bold: bool = False,
    anchor_x: str = "left",
    anchor_y: str = "top",
    width: int | None = None,
    align: str = "left",
    font: tuple[str, ...] = theme.FONT,
) -> arcade.Text:
    key = (content, x, y, size, color, bold, anchor_x, anchor_y, width, align, font)
    cached = _TEXT_CACHE.get(key)
    if cached is None:
        if len(_TEXT_CACHE) > _MAX_CACHE:
            _TEXT_CACHE.clear()
        cached = arcade.Text(
            text=content,
            x=x,
            y=y,
            color=color,
            font_size=size,
            font_name=font,
            bold=bold,
            anchor_x=anchor_x,
            anchor_y=anchor_y,
            width=width,
            align=align,
            multiline=width is not None,
        )
        _TEXT_CACHE[key] = cached
    return cached


def draw_text(content: str, x: float, y: float, **kwargs: Any) -> None:
    text_object(content, x, y, **kwargs).draw()


def clear_text_cache() -> None:
    _TEXT_CACHE.clear()


def draw_panel(
    x: float,
    y: float,
    width: float,
    height: float,
    *,
    fill: tuple[int, int, int] = theme.SURFACE,
    border: tuple[int, int, int] = theme.BORDER,
    accent: bool = False,
) -> None:
    arcade.draw_rect_filled(arcade.LBWH(x, y, width, height), fill)
    arcade.draw_rect_outline(arcade.LBWH(x, y, width, height), border, 1)
    if accent:
        arcade.draw_rect_filled(arcade.LBWH(x, y + height - 2, width, 2), theme.ACCENT)


def draw_chip(
    x: float,
    y: float,
    width: float,
    height: float,
    label: str,
    *,
    fill: tuple[int, int, int] = theme.SURFACE_ALT,
    text_color: tuple[int, int, int] = theme.MUTED,
    font_size: float = 11,
) -> None:
    arcade.draw_rect_filled(arcade.LBWH(x, y, width, height), fill)
    draw_text(
        label,
        x + width / 2,
        y + height / 2,
        size=font_size,
        color=text_color,
        bold=True,
        anchor_x="center",
        anchor_y="center",
    )


def draw_background(width: float, height: float) -> None:
    arcade.draw_rect_filled(arcade.LBWH(0, 0, width, height), theme.BG)

    # Декоративные окружности в правом верхнем углу.
    center_x = width * 0.86
    center_y = height * 0.82
    for radius in (150, 260, 390):
        arcade.draw_circle_outline(center_x, center_y, radius, (27, 67, 52), 2)

    # Крупная полупрозрачная монограмма на фоне.
    draw_text(
        "M",
        width - 24,
        -80,
        size=300,
        color=(15, 45, 35),
        bold=True,
        anchor_x="right",
        anchor_y="bottom",
    )

    # Тонкая линия снизу.
    arcade.draw_rect_filled(arcade.LBWH(0, 0, width, 3), (29, 70, 55))


def draw_header_background(width: float, height: float, header_height: float = 150) -> None:
    arcade.draw_rect_filled(
        arcade.LBWH(0, height - header_height, width, header_height), theme.BG_DARK
    )
    arcade.draw_rect_filled(
        arcade.LBWH(0, height - header_height - 1, width, 1), theme.BORDER
    )


def format_money(amount: int) -> str:
    return f"{amount:,}".replace(",", " ") + " ₽"
