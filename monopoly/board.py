"""Игровое поле и экономические параметры клеток."""

from __future__ import annotations

from dataclasses import dataclass

from .config import BOARD_SIZE


@dataclass(frozen=True)
class Tile:
    name: str
    kind: str  # start | property | chance | chest | tax | railroad | utility | jail | parking | goto_jail
    group: str = ""
    price: int = 0
    rent: tuple[int, ...] = ()
    house_cost: int = 0
    tax: int = 0


BOARD: tuple[Tile, ...] = (
    Tile("СТАРТ", "start"),
    Tile("Шава у Ашота-Камшота", "property", "brown", 60, (2, 10, 30, 90, 160, 250), 50),
    Tile("Казна", "chest"),
    Tile("Халяль шавуха со свининой", "property", "brown", 60, (4, 20, 60, 180, 320, 450), 50),
    Tile("Подоходный налог", "tax", tax=200),
    Tile("Кокаиновая дорога", "railroad", "railroad", 200),
    Tile("Гей клуб 'Голубой вагон'", "property", "lightblue", 100, (6, 30, 90, 270, 400, 550), 50),
    Tile("Шанс", "chance"),
    Tile("Гей клуб 'Дырявый борт'", "property", "lightblue", 100, (6, 30, 90, 270, 400, 550), 50),
    Tile("Гей клуб 'Мастурбатор'", "property", "lightblue", 120, (8, 40, 100, 300, 450, 600), 50),
    Tile("Тюрьма", "jail"),
    Tile("Героиновый рай", "property", "pink", 140, (10, 50, 150, 450, 625, 750), 100),
    Tile("Электростанция", "utility", "utility", 150),
    Tile("Крокодиловы тропы", "property", "pink", 140, (10, 50, 150, 450, 625, 750), 100),
    Tile("Грибное чудо", "property", "pink", 160, (12, 60, 180, 500, 700, 900), 100),
    Tile("Курская железная дорога", "railroad", "railroad", 200),
    Tile("Сеть продажи людей 'Африканские дети'", "property", "orange", 180, (14, 70, 200, 550, 750, 950), 100),
    Tile("Казна", "chest"),
    Tile("Сеть продажи негров 'Негретос'", "property", "orange", 180, (14, 70, 200, 550, 750, 950), 100),
    Tile("Рабочий дом 1000 рублей в день", "property", "orange", 200, (16, 80, 220, 600, 800, 1000), 100),
    Tile("Бесплатная парковка (500 рублей / ход)", "parking"),
    Tile("Бордель 'У дырявой Анжелы'", "property", "red", 220, (18, 90, 250, 700, 875, 1050), 150),
    Tile("Шанс", "chance"),
    Tile("Секс-шоп 'Фембой уцы'", "property", "red", 220, (18, 90, 250, 700, 875, 1050), 150),
    Tile("Улица Белого Негра", "property", "red", 240, (20, 100, 300, 750, 925, 1100), 150),
    Tile("Харам", "railroad", "railroad", 200),
    Tile("Больница 'Донор спермы'", "property", "yellow", 260, (22, 110, 330, 800, 975, 1150), 150),
    Tile("Бизнес центр ООО 'ТЛИЗ'", "property", "yellow", 260, (22, 110, 330, 800, 975, 1150), 150),
    Tile("Водопровод", "utility", "utility", 150),
    Tile("Школа 'ВАЙБКУКОЛДИНГ'", "property", "yellow", 280, (24, 120, 360, 850, 1025, 1200), 150),
    Tile("Идите в тюрьму", "goto_jail"),
    Tile("Банк 'Хач'", "property", "green", 300, (26, 130, 390, 900, 1100, 1275), 200),
    Tile("Дом престарелых блядей", "property", "green", 300, (26, 130, 390, 900, 1100, 1275), 200),
    Tile("Казна", "chest"),
    Tile("Школа минета", "property", "green", 320, (28, 150, 450, 1000, 1200, 1400), 200),
    Tile("Дорога нахуй", "railroad", "railroad", 200),
    Tile("Шанс", "chance"),
    Tile("Косметология по отбеливанию ануса", "property", "darkblue", 350, (35, 175, 500, 1100, 1300, 1500), 200),
    Tile("Налог на роскошь", "tax", tax=100),
    Tile("Миграционные служба 'ХАЧУ'", "property", "darkblue", 400, (50, 200, 600, 1400, 1700, 2000), 200),
)

assert len(BOARD) == BOARD_SIZE, "Размер поля должен совпадать с BOARD_SIZE"

_groups: dict[str, list[int]] = {}
for _position, _tile in enumerate(BOARD):
    if _tile.kind == "property":
        _groups.setdefault(_tile.group, []).append(_position)
GROUP_POSITIONS: dict[str, tuple[int, ...]] = {
    group: tuple(positions) for group, positions in _groups.items()
}

PURCHASABLE_POSITIONS: tuple[int, ...] = tuple(
    position
    for position, cell in enumerate(BOARD)
    if cell.kind in ("property", "railroad", "utility")
)

RAILROAD_POSITIONS: tuple[int, ...] = tuple(
    position for position, cell in enumerate(BOARD) if cell.kind == "railroad"
)
UTILITY_POSITIONS: tuple[int, ...] = tuple(
    position for position, cell in enumerate(BOARD) if cell.kind == "utility"
)


def tile(position: int) -> Tile:
    return BOARD[position % BOARD_SIZE]


def tile_name(position: int) -> str:
    return tile(position).name


def mortgage_value(position: int) -> int:
    return tile(position).price // 2
