"""Цвета, шрифты и геометрические константы интерфейса."""

from __future__ import annotations

from ..config import VERSION as _VERSION

# Тёмно-зелёная «бархатная» палитра с золотом.
BG = (12, 38, 30)
BG_DARK = (7, 25, 19)
SURFACE = (19, 55, 43)
SURFACE_ALT = (26, 72, 56)
SURFACE_HOVER = (34, 88, 69)
BORDER = (44, 98, 77)
BORDER_LIGHT = (62, 125, 99)
TEXT = (245, 240, 228)
MUTED = (156, 183, 169)
ACCENT = (232, 180, 76)
ACCENT_HOVER = (246, 204, 116)
ACCENT_PRESS = (204, 152, 54)
ACCENT_TEXT = (20, 36, 26)
SUCCESS = (121, 214, 161)
DANGER = (224, 122, 122)
DANGER_HOVER = (240, 146, 146)
DANGER_DARK = (120, 50, 45)
CHAT_BG = (10, 34, 26)
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)

FONT = ("DejaVu Sans", "Noto Sans", "Liberation Sans", "Arial", "Segoe UI")
FONT_BOLD = FONT

AVATAR_COLORS = (
    (232, 180, 76),
    (121, 214, 161),
    (126, 178, 236),
    (198, 154, 226),
    (240, 137, 118),
    (238, 202, 121),
)

GROUP_COLORS = {
    "brown": (148, 96, 62),
    "lightblue": (117, 183, 210),
    "pink": (205, 110, 145),
    "orange": (224, 148, 73),
    "red": (205, 79, 79),
    "yellow": (229, 197, 84),
    "green": (82, 158, 104),
    "darkblue": (86, 116, 190),
    "railroad": (150, 162, 160),
    "utility": (190, 203, 184),
}

VERSION_LABEL = f"v{_VERSION} · Python + Arcade"
