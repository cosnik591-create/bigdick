"""Игровая сессия: полный базовый набор правил «Монополии».

Сервер авторитетно рассчитывает покупки, аренду, аукционы, строительство,
залог, тюрьму, налоги, карточки и банкротство. Клиент только отправляет
действия и рисует полученное состояние.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from random import SystemRandom
from typing import Any, Iterable, Protocol

from ..board import (
    BOARD,
    BOARD_SIZE,
    GROUP_POSITIONS,
    PURCHASABLE_POSITIONS,
    RAILROAD_POSITIONS,
    UTILITY_POSITIONS,
    Tile,
)
from ..config import GO_SALARY, START_MONEY

_rng = SystemRandom()

GO_POSITION = 0
JAIL_POSITION = 10
JAIL_FINE = 50
MAX_HOUSES = 32
MAX_HOTELS = 12
MIN_AUCTION_BID = 10


class NamedPlayer(Protocol):
    """Всё, что нужно игровой сессии от игрока лобби."""

    id: str
    name: str


class GameError(Exception):
    """Ход невозможен по правилам игры."""


@dataclass
class GamePlayer:
    id: str
    name: str
    money: int = START_MONEY
    position: int = 0
    connected: bool = True
    in_jail: bool = False
    jail_turns: int = 0
    jail_cards: int = 0
    bankrupt: bool = False


@dataclass
class PropertyState:
    owner_id: str | None = None
    houses: int = 0  # 0..4 дома, 5 — отель
    mortgaged: bool = False


@dataclass
class Auction:
    position: int
    order: list[str]
    active: list[str]
    turn_id: str | None = None
    highest_bid: int = 0
    highest_bidder: str | None = None


CHANCE_CARDS: tuple[dict[str, Any], ...] = (
    {"text": "Вперёд к СТАРТу. Получите 200 ₽.", "advance_to": GO_POSITION},
    {"text": "Банк выплачивает дивиденды. Получите 50 ₽.", "money": 50},
    {"text": "Идите в тюрьму. Не проходите СТАРТ.", "jail": True},
    {"text": "Карта освобождения из тюрьмы. Сохраните её.", "jail_card": True},
    {"text": "Оплатите дорожный налог 15 ₽.", "money": -15},
    {"text": "Ваш строительный заём погашен. Получите 150 ₽.", "money": 150},
    {"text": "Вернитесь на 3 клетки назад.", "move_relative": -3},
    {"text": "Отправляйтесь на Смоленскую улицу.", "advance_to": 23},
    {"text": "Отправляйтесь на Рижскую железную дорогу.", "advance_to": 5},
    {"text": "Вы выиграли конкурс. Получите 100 ₽.", "money": 100},
    {
        "text": "Срочный благотворительный сбор. Ваш счёт обнуляется.",
        "zero_money": True,
    },
    {
        "text": "Городская программа расселения: вы теряете случайную собственность.",
        "lose_property": True,
    },
    {
        "text": "Кредит бабушки: банк требует срочно погасить долг.",
        "grandma_debt": True,
    },
)

CHEST_CARDS: tuple[dict[str, Any], ...] = (
    {"text": "Вперёд к СТАРТу. Получите 200 ₽.", "advance_to": GO_POSITION},
    {"text": "Банковская ошибка в вашу пользу. Получите 200 ₽.", "money": 200},
    {"text": "Визит к врачу. Заплатите 50 ₽.", "money": -50},
    {"text": "Идите в тюрьму. Не проходите СТАРТ.", "jail": True},
    {"text": "Карта освобождения из тюрьмы. Сохраните её.", "jail_card": True},
    {"text": "Продажа акций. Получите 50 ₽.", "money": 50},
    {"text": "Наследство. Получите 100 ₽.", "money": 100},
    {"text": "Школьные сборы. Заплатите 150 ₽.", "money": -150},
    {"text": "Вы заняли второе место на конкурсе красоты. Получите 10 ₽.", "money": 10},
    {"text": "Вернитесь на 3 клетки назад.", "move_relative": -3},
)


class GameSession:
    MAX_LOG = 80

    def __init__(self, players: Iterable[NamedPlayer]):
        player_list = list(players)
        self.order: list[str] = [player.id for player in player_list]
        self.players: dict[str, GamePlayer] = {
            player.id: GamePlayer(id=player.id, name=player.name) for player in player_list
        }
        self.properties: dict[int, PropertyState] = {
            position: PropertyState() for position in PURCHASABLE_POSITIONS
        }
        self.turn_index = 0
        self.phase = "await_roll"  # await_roll | purchase | auction | game_over
        self.pending_position: int | None = None
        self.auction: Auction | None = None
        self.dice: tuple[int, int] | None = None
        self.roll_id = 0
        self.extra_roll = False
        self.doubles_count = 0
        self.finished = False
        self.winner_id: str | None = None
        self.bank_houses = MAX_HOUSES
        self.bank_hotels = MAX_HOTELS
        self.notice: str | None = None
        self.log: list[str] = []

        self._chance: list[dict[str, Any]] = list(CHANCE_CARDS)
        self._chest: list[dict[str, Any]] = list(CHEST_CARDS)
        random.shuffle(self._chance)
        random.shuffle(self._chest)
        self._chance_index = 0
        self._chest_index = 0

        current = self.current
        if current is not None:
            self._log(f"Игра началась. Первым ходит {current.name}.")
        else:
            self._log("Игра началась.")

    # ------------------------------------------------------------------
    # Базовые свойства состояния
    # ------------------------------------------------------------------
    @property
    def current(self) -> GamePlayer | None:
        if not self.order:
            return None
        return self.players.get(self.order[self.turn_index])

    def _active_connected(self) -> list[GamePlayer]:
        return [
            player
            for player in self.players.values()
            if player.connected and not player.bankrupt
        ]

    def _log(self, text: str) -> None:
        self.log.append(text)
        if len(self.log) > self.MAX_LOG:
            del self.log[: len(self.log) - self.MAX_LOG]

    def _set_notice(self, text: str) -> None:
        self.notice = text
        self._log(text)

    def _require_turn(self, player_id: str) -> GamePlayer:
        if self.finished:
            raise GameError("Игра уже завершена")
        player = self.players.get(player_id)
        if player is None or player.bankrupt:
            raise GameError("Вы не участвуете в игре")
        current = self.current
        if current is None or current.id != player_id:
            raise GameError("Сейчас не ваш ход")
        return player

    def _property(self, position: int) -> PropertyState:
        return self.properties[position]

    def _owner(self, position: int) -> GamePlayer | None:
        owner_id = self.properties[position].owner_id
        return self.players.get(owner_id) if owner_id else None

    # ------------------------------------------------------------------
    # Бросок кубиков и перемещение
    # ------------------------------------------------------------------
    def roll(self, player_id: str) -> None:
        player = self._require_turn(player_id)
        if self.phase != "await_roll":
            raise GameError("Сначала завершите текущее действие")

        self.roll_id += 1
        d1, d2 = _rng.randint(1, 6), _rng.randint(1, 6)
        total = d1 + d2
        doubles = d1 == d2
        self.dice = (d1, d2)
        self._log(f"{player.name}: {d1} + {d2} = {total}.")

        if player.in_jail:
            self._roll_in_jail(player, doubles, total)
            return

        if doubles:
            self.doubles_count += 1
        else:
            self.doubles_count = 0

        if self.doubles_count >= 3:
            self._set_notice("Три дубля подряд — отправляемся в тюрьму.")
            self._send_to_jail(player)
            self._end_turn()
            return

        self.extra_roll = doubles
        self._advance_player(player, total)
        self._resolve_landing(player, total)

    def _roll_in_jail(self, player: GamePlayer, doubles: bool, total: int) -> None:
        if doubles:
            player.in_jail = False
            player.jail_turns = 0
            self._set_notice(f"{player.name} выбрасывает дубль и выходит из тюрьмы.")
            self.extra_roll = False
            self._advance_player(player, total)
            self._resolve_landing(player, total)
            return

        player.jail_turns += 1
        if player.jail_turns >= 3:
            self._set_notice("Третья неудачная попытка — штраф 50 ₽.")
            if not self._pay(player, None, JAIL_FINE, "штраф за тюрьму"):
                self._after_bankruptcy(player)
                return
            player.in_jail = False
            player.jail_turns = 0
            self.extra_roll = False
            self._advance_player(player, total)
            self._resolve_landing(player, total)
            return

        self._log(f"{player.name} остаётся в тюрьме (попытка {player.jail_turns}/3).")
        self._end_turn()

    def _advance_player(self, player: GamePlayer, steps: int) -> None:
        for _ in range(steps):
            player.position = (player.position + 1) % BOARD_SIZE
            if player.position == GO_POSITION:
                player.money += GO_SALARY
                self._log(f"{player.name} проходит СТАРТ и получает {GO_SALARY} ₽.")

    def _resolve_landing(self, player: GamePlayer, dice_total: int) -> None:
        if self.finished:
            return
        position = player.position
        cell = BOARD[position]
        self._log(f"{player.name} останавливается на «{cell.name}».")

        if cell.kind in ("property", "railroad", "utility"):
            self._resolve_property(player, position, cell, dice_total)
        elif cell.kind == "tax":
            self._set_notice(f"{cell.name}: {cell.tax} ₽.")
            if not self._pay(player, None, cell.tax, cell.name):
                self._after_bankruptcy(player)
                return
            self._after_action()
        elif cell.kind == "goto_jail":
            self._set_notice("Идите в тюрьму. Не проходите СТАРТ.")
            self._send_to_jail(player)
            self._end_turn()
        elif cell.kind == "chance":
            self._draw_card(player, "chance", dice_total)
        elif cell.kind == "chest":
            self._draw_card(player, "chest", dice_total)
        elif cell.kind == "parking":
            self._log("Бесплатная парковка: ничего не происходит.")
            self._after_action()
        elif cell.kind == "jail":
            self._log("Вы просто посещаете тюрьму.")
            self._after_action()
        else:
            self._after_action()

    def _resolve_property(
        self, player: GamePlayer, position: int, cell: Tile, dice_total: int
    ) -> None:
        state = self._property(position)
        if state.owner_id is None:
            self.pending_position = position
            self.phase = "purchase"
            self._set_notice(
                f"«{cell.name}» не куплена. Можно купить за {cell.price} ₽ или отправить на аукцион."
            )
            return

        if state.owner_id == player.id:
            self._log(f"«{cell.name}» уже ваша.")
            self._after_action()
            return

        owner = self.players.get(state.owner_id)
        if owner is None or state.mortgaged:
            self._log(f"«{cell.name}» заложена — аренда не взимается.")
            self._after_action()
            return

        rent = self._rent_for(position, dice_total)
        self._set_notice(f"Аренда «{cell.name}»: {rent} ₽ → {owner.name}.")
        if not self._pay(player, owner, rent, f"аренда за «{cell.name}»"):
            self._after_bankruptcy(player)
            return
        self._after_action()

    def _rent_for(self, position: int, dice_total: int) -> int:
        cell = BOARD[position]
        state = self._property(position)
        if state.owner_id is None or state.mortgaged:
            return 0
        owner_id = state.owner_id

        if cell.kind == "property":
            if state.houses > 0:
                return cell.rent[state.houses]
            rent = cell.rent[0]
            group = GROUP_POSITIONS.get(cell.group, ())
            if group and all(
                self._property(pos).owner_id == owner_id
                and not self._property(pos).mortgaged
                for pos in group
            ):
                rent *= 2
            return rent

        if cell.kind == "railroad":
            count = sum(
                1
                for pos in RAILROAD_POSITIONS
                if self._property(pos).owner_id == owner_id
                and not self._property(pos).mortgaged
            )
            return {1: 25, 2: 50, 3: 100, 4: 200}.get(count, 0)

        if cell.kind == "utility":
            count = sum(
                1
                for pos in UTILITY_POSITIONS
                if self._property(pos).owner_id == owner_id
                and not self._property(pos).mortgaged
            )
            if count == 0:
                return 0
            return dice_total * (10 if count >= 2 else 4)
        return 0

    # ------------------------------------------------------------------
    # Покупка и аукцион
    # ------------------------------------------------------------------
    def buy_property(self, player_id: str) -> None:
        player = self._require_turn(player_id)
        if self.phase != "purchase" or self.pending_position is None:
            raise GameError("Сейчас нечего покупать")
        position = self.pending_position
        cell = BOARD[position]
        state = self._property(position)
        if state.owner_id is not None:
            raise GameError("Эта клетка уже куплена")
        if player.money < cell.price:
            raise GameError("Недостаточно денег для покупки")

        player.money -= cell.price
        state.owner_id = player.id
        self._set_notice(f"{player.name} покупает «{cell.name}» за {cell.price} ₽.")
        self._after_action()

    def decline_property(self, player_id: str) -> None:
        player = self._require_turn(player_id)
        if self.phase != "purchase" or self.pending_position is None:
            raise GameError("Сейчас нечего выставлять на аукцион")
        position = self.pending_position
        cell = BOARD[position]
        self.pending_position = None
        self._set_notice(
            f"{player.name} отказывается от покупки «{cell.name}». Начинается аукцион."
        )
        self._start_auction(position)

    def _start_auction(self, position: int) -> None:
        participants = [
            player.id
            for player in self.players.values()
            if player.connected and not player.bankrupt
        ]
        if not participants:
            self._set_notice("Аукцион невозможен: нет активных игроков.")
            self.phase = "await_roll"
            self._end_turn()
            return

        current_id = self.current.id if self.current else participants[0]
        start = self.order.index(current_id) if current_id in self.order else 0
        ordered = [
            self.order[(start + offset) % len(self.order)]
            for offset in range(len(self.order))
            if self.order[(start + offset) % len(self.order)] in participants
        ]
        self.auction = Auction(
            position=position,
            order=ordered,
            active=list(ordered),
            turn_id=ordered[0],
        )
        self.phase = "auction"
        self._set_notice("Аукцион начался. Ставки принимаются по очереди.")

    def auction_bid(self, player_id: str, amount: int) -> None:
        auction = self.auction
        if self.phase != "auction" or auction is None:
            raise GameError("Аукцион не идёт")
        if auction.turn_id != player_id:
            raise GameError("Сейчас не ваша очередь делать ставку")
        player = self.players.get(player_id)
        if player is None or player.bankrupt:
            raise GameError("Вы не участвуете в игре")
        try:
            bid = int(amount)
        except (TypeError, ValueError) as exc:
            raise GameError("Некорректная ставка") from exc
        if bid < MIN_AUCTION_BID:
            raise GameError(f"Минимальная ставка — {MIN_AUCTION_BID} ₽")
        if bid <= auction.highest_bid:
            raise GameError("Ставка должна быть выше текущей")
        if bid > player.money:
            raise GameError("Ставка не может превышать ваши деньги")

        auction.highest_bid = bid
        auction.highest_bidder = player_id
        self._set_notice(
            f"{player.name} предлагает {bid} ₽ за «{BOARD[auction.position].name}»."
        )
        self._auction_step()

    def auction_pass(self, player_id: str) -> None:
        auction = self.auction
        if self.phase != "auction" or auction is None:
            raise GameError("Аукцион не идёт")
        if auction.turn_id != player_id:
            raise GameError("Сейчас не ваша очередь делать ставку")
        if player_id in auction.active:
            auction.active.remove(player_id)
        player = self.players.get(player_id)
        name = player.name if player else "Игрок"
        self._log(f"{name} пасует на аукционе.")
        self._auction_step()

    def _auction_step(self) -> None:
        auction = self.auction
        if auction is None:
            return

        auction.active = [
            player_id
            for player_id in auction.active
            if (player := self.players.get(player_id)) is not None
            and player.connected
            and not player.bankrupt
        ]

        if not auction.active:
            winner = auction.highest_bidder
            price = auction.highest_bid
            self._finish_auction(winner, price)
            return

        if len(auction.active) == 1 and auction.highest_bidder == auction.active[0]:
            self._finish_auction(auction.active[0], auction.highest_bid)
            return

        if auction.turn_id not in auction.active:
            auction.turn_id = auction.active[0]
            return
        self._set_next_auction_turn()

    def _set_next_auction_turn(self) -> None:
        auction = self.auction
        if auction is None or not auction.active:
            return
        current = auction.turn_id
        start = auction.order.index(current) if current in auction.order else -1
        for offset in range(1, len(auction.order) + 1):
            candidate = auction.order[(start + offset) % len(auction.order)]
            if candidate in auction.active:
                auction.turn_id = candidate
                return
        auction.turn_id = auction.active[0]

    def _finish_auction(self, winner_id: str | None, price: int) -> None:
        auction = self.auction
        if auction is None:
            return
        self.auction = None
        self.phase = "await_roll"
        position = auction.position
        cell = BOARD[position]
        winner = self.players.get(winner_id) if winner_id else None

        if winner is not None and price > 0:
            if winner.money < price:
                self._log(f"{winner.name} не может оплатить ставку — лот не продан.")
            else:
                winner.money -= price
                self._property(position).owner_id = winner.id
                self._set_notice(
                    f"{winner.name} выигрывает аукцион: «{cell.name}» за {price} ₽."
                )
        else:
            self._log(f"Лот «{cell.name}» остался некупленным.")
        self._after_action()

    # ------------------------------------------------------------------
    # Строительство и залог
    # ------------------------------------------------------------------
    def build(self, player_id: str, position: int) -> None:
        player = self._require_turn(player_id)
        if self.phase != "await_roll":
            raise GameError("Строить можно только перед броском кубиков")
        cell = BOARD[position]
        state = self._property(position)
        if cell.kind != "property":
            raise GameError("На этой клетке нельзя строить")
        if state.owner_id != player.id:
            raise GameError("Это не ваша улица")
        group = GROUP_POSITIONS.get(cell.group, ())
        if not group or not all(self._property(pos).owner_id == player.id for pos in group):
            raise GameError("Нужна полная монополия по цветовой группе")
        if any(self._property(pos).mortgaged for pos in group):
            raise GameError("Нельзя строить, пока в группе есть заложенные улицы")
        if state.houses >= 5:
            raise GameError("На этой улице уже отель")

        target = state.houses + 1
        levels = [self._property(pos).houses for pos in group]
        levels[group.index(position)] = target
        if max(levels) - min(levels) > 1:
            raise GameError("Строить нужно равномерно по всей группе")

        cost = cell.house_cost
        if player.money < cost:
            raise GameError("Недостаточно денег для строительства")

        if target == 5:
            if self.bank_hotels < 1:
                raise GameError("В банке закончились отели")
            self.bank_hotels -= 1
            self.bank_houses += 4
            word = "отель"
        else:
            if self.bank_houses < 1:
                raise GameError("В банке закончились дома")
            self.bank_houses -= 1
            word = "дом"

        player.money -= cost
        state.houses = target
        self._set_notice(
            f"{player.name} строит {word} на «{cell.name}» за {cost} ₽."
        )

    def sell_building(self, player_id: str, position: int) -> None:
        player = self._require_turn(player_id)
        if self.phase != "await_roll":
            raise GameError("Продавать здания можно только перед броском кубиков")
        cell = BOARD[position]
        state = self._property(position)
        if cell.kind != "property" or state.owner_id != player.id:
            raise GameError("Это не ваша улица")
        if state.houses <= 0:
            raise GameError("На этой улице нет зданий")

        group = GROUP_POSITIONS.get(cell.group, ())
        target = state.houses - 1
        levels = [self._property(pos).houses for pos in group]
        levels[group.index(position)] = target
        if max(levels) - min(levels) > 1:
            raise GameError("Продавать здания нужно равномерно по группе")

        refund = cell.house_cost // 2
        if state.houses == 5:
            if self.bank_houses < 4:
                raise GameError("В банке не хватает домов для обмена отеля")
            self.bank_hotels += 1
            self.bank_houses -= 4
        else:
            self.bank_houses += 1

        state.houses = target
        player.money += refund
        self._set_notice(
            f"{player.name} продаёт здание на «{cell.name}» и получает {refund} ₽."
        )

    def mortgage(self, player_id: str, position: int) -> None:
        player = self._require_turn(player_id)
        if self.phase != "await_roll":
            raise GameError("Закладывать можно только перед броском кубиков")
        cell = BOARD[position]
        state = self._property(position)
        if cell.kind not in ("property", "railroad", "utility"):
            raise GameError("Эту клетку нельзя заложить")
        if state.owner_id != player.id:
            raise GameError("Это не ваша собственность")
        if state.mortgaged:
            raise GameError("Клетка уже заложена")
        group = GROUP_POSITIONS.get(cell.group, (position,))
        if any(self._property(pos).houses > 0 for pos in group):
            raise GameError("Сначала продайте здания в этой группе")

        value = cell.price // 2
        state.mortgaged = True
        player.money += value
        self._set_notice(f"{player.name} закладывает «{cell.name}» за {value} ₽.")

    def unmortgage(self, player_id: str, position: int) -> None:
        player = self._require_turn(player_id)
        if self.phase != "await_roll":
            raise GameError("Выкупать можно только перед броском кубиков")
        cell = BOARD[position]
        state = self._property(position)
        if state.owner_id != player.id:
            raise GameError("Это не ваша собственность")
        if not state.mortgaged:
            raise GameError("Клетка не заложена")
        cost = int(cell.price * 0.55)
        if player.money < cost:
            raise GameError("Недостаточно денег для выкупа")
        player.money -= cost
        state.mortgaged = False
        self._set_notice(f"{player.name} выкупает «{cell.name}» за {cost} ₽.")

    # ------------------------------------------------------------------
    # Тюрьма
    # ------------------------------------------------------------------
    def pay_jail(self, player_id: str) -> None:
        player = self._require_turn(player_id)
        if self.phase != "await_roll":
            raise GameError("Сначала завершите текущее действие")
        if not player.in_jail:
            raise GameError("Вы не в тюрьме")
        if not self._pay(player, None, JAIL_FINE, "залог за тюрьму"):
            self._after_bankruptcy(player)
            return
        player.in_jail = False
        player.jail_turns = 0
        self._set_notice(f"{player.name} платит 50 ₽ и выходит из тюрьмы.")

    def use_jail_card(self, player_id: str) -> None:
        player = self._require_turn(player_id)
        if self.phase != "await_roll":
            raise GameError("Сначала завершите текущее действие")
        if not player.in_jail:
            raise GameError("Вы не в тюрьме")
        if player.jail_cards < 1:
            raise GameError("У вас нет карты освобождения")
        player.jail_cards -= 1
        player.in_jail = False
        player.jail_turns = 0
        self._set_notice(f"{player.name} использует карту освобождения из тюрьмы.")

    def _send_to_jail(self, player: GamePlayer) -> None:
        player.position = JAIL_POSITION
        player.in_jail = True
        player.jail_turns = 0
        self.doubles_count = 0

    # ------------------------------------------------------------------
    # Карточки
    # ------------------------------------------------------------------
    def _draw_card(self, player: GamePlayer, deck_name: str, dice_total: int) -> None:
        if deck_name == "chance":
            deck = self._chance
            index = self._chance_index
        else:
            deck = self._chest
            index = self._chest_index
        card = deck[index % len(deck)]
        if deck_name == "chance":
            self._chance_index = (index + 1) % len(deck)
        else:
            self._chest_index = (index + 1) % len(deck)

        deck_title = "Шанс" if deck_name == "chance" else "Казна"
        self._set_notice(f"{player.name}: «{deck_title}» — {card['text']}")

        if card.get("jail"):
            self._send_to_jail(player)
            self._end_turn()
            return

        if card.get("jail_card"):
            player.jail_cards += 1
            self._after_action()
            return

        if card.get("zero_money"):
            lost = player.money
            player.money = 0
            self._set_notice(
                f"{player.name}: счёт обнулён, списано {lost} ₽."
            )
            self._after_action()
            return

        if card.get("lose_property"):
            self._lose_random_property(player)
            self._after_action()
            return

        if card.get("grandma_debt"):
            money = max(0, player.money)
            low = int(money * 0.5)
            high = max(low, int(money * 2))
            debt = _rng.randint(low, high)
            self._set_notice(
                f"{player.name}: кредит бабушки — срочно оплатите {debt} ₽."
            )
            if not self._pay(player, None, debt, "кредит бабушки"):
                self._after_bankruptcy(player)
                return
            self._after_action()
            return

        if "money" in card:
            amount = int(card["money"])
            if amount >= 0:
                player.money += amount
            else:
                if not self._pay(player, None, -amount, "карточка"):
                    self._after_bankruptcy(player)
                    return
            self._after_action()
            return

        if "advance_to" in card:
            target = int(card["advance_to"]) % BOARD_SIZE
            old = player.position
            if target == GO_POSITION or target < old:
                player.money += GO_SALARY
                self._log(f"{player.name} проходит СТАРТ и получает {GO_SALARY} ₽.")
            player.position = target
            self._resolve_landing(player, dice_total)
            return

        if "move_relative" in card:
            player.position = (player.position + int(card["move_relative"])) % BOARD_SIZE
            self._resolve_landing(player, dice_total)
            return

        self._after_action()

    def _lose_random_property(self, player: GamePlayer) -> None:
        owned = [
            position
            for position, state in self.properties.items()
            if state.owner_id == player.id
        ]
        if not owned:
            self._log(f"У {player.name} нет собственности — карта не сработала.")
            return
        position = owned[_rng.randrange(len(owned))]
        state = self._property(position)
        if state.houses == 5:
            self.bank_hotels += 1
        elif state.houses > 0:
            self.bank_houses += state.houses
        state.houses = 0
        state.owner_id = None
        state.mortgaged = False
        self._set_notice(
            f"{player.name} теряет «{BOARD[position].name}» — объект возвращён банку."
        )

    # ------------------------------------------------------------------
    # Деньги и банкротство
    # ------------------------------------------------------------------
    def _pay(
        self,
        payer: GamePlayer,
        recipient: GamePlayer | None,
        amount: int,
        reason: str,
    ) -> bool:
        if amount <= 0:
            return True
        if payer.money >= amount:
            payer.money -= amount
            if recipient is not None:
                recipient.money += amount
                self._log(
                    f"{payer.name} платит {amount} ₽ ({reason}) игроку {recipient.name}."
                )
            else:
                self._log(f"{payer.name} платит {amount} ₽ ({reason}) банку.")
            return True

        self._bankrupt(payer, recipient)
        return False

    def _bankrupt(self, player: GamePlayer, creditor: GamePlayer | None) -> None:
        if player.bankrupt:
            return
        proceeds = 0
        for position, state in self.properties.items():
            if state.owner_id != player.id:
                continue
            if state.houses > 0:
                proceeds += state.houses * BOARD[position].house_cost // 2
                if state.houses == 5:
                    self.bank_hotels += 1
                else:
                    self.bank_houses += state.houses
                state.houses = 0
            if creditor is not None and not creditor.bankrupt:
                state.owner_id = creditor.id
            else:
                state.owner_id = None
                state.mortgaged = False

        player.money += proceeds
        if creditor is not None and not creditor.bankrupt:
            creditor.money += player.money
            self._set_notice(
                f"{player.name} обанкротился. Имущество переходит к {creditor.name}."
            )
        else:
            self._set_notice(f"{player.name} обанкротился. Имущество возвращено банку.")
        player.money = 0
        player.bankrupt = True
        player.in_jail = False
        player.jail_cards = 0
        self._check_game_over()

    def _check_game_over(self) -> None:
        active = self._active_connected()
        if len(active) <= 1:
            self.finished = True
            self.phase = "game_over"
            self.auction = None
            self.pending_position = None
            if active:
                self.winner_id = active[0].id
                self._log(f"Игра завершена. Победитель: {active[0].name}.")
            else:
                self.winner_id = None
                self._log("Игра завершена. Победителей нет.")

    def _after_bankruptcy(self, player: GamePlayer) -> None:
        if self.finished:
            return
        if self.current is player:
            self._end_turn()
        else:
            self._after_action()

    # ------------------------------------------------------------------
    # Завершение действия и хода
    # ------------------------------------------------------------------
    def _after_action(self) -> None:
        if self.finished:
            return
        self.pending_position = None
        self.phase = "await_roll"
        current = self.current
        if (
            self.extra_roll
            and current is not None
            and current.connected
            and not current.bankrupt
            and not current.in_jail
        ):
            self.extra_roll = False
            self._set_notice("Дубль! Бросайте кубики ещё раз.")
            return
        self._end_turn()

    def _end_turn(self) -> None:
        if self.finished:
            return
        self.extra_roll = False
        self.pending_position = None
        self.phase = "await_roll"
        self.doubles_count = 0
        self._advance_turn()

    def _advance_turn(self) -> None:
        if not self.order:
            self._check_game_over()
            return
        for _ in range(len(self.order)):
            self.turn_index = (self.turn_index + 1) % len(self.order)
            player = self.players.get(self.order[self.turn_index])
            if player is not None and player.connected and not player.bankrupt:
                break
        self._check_game_over()
        if not self.finished:
            current = self.current
            if current is not None and current.in_jail:
                self._log(f"Ход переходит к {current.name}. Он в тюрьме.")

    # ------------------------------------------------------------------
    # Отключение игрока
    # ------------------------------------------------------------------
    def remove_player(self, player_id: str) -> bool:
        player = self.players.get(player_id)
        if player is None or not player.connected:
            return False
        player.connected = False
        self._log(f"{player.name} покинул игру.")

        if self.auction is not None:
            auction = self.auction
            if player_id in auction.active:
                auction.active.remove(player_id)
            if auction.highest_bidder == player_id:
                auction.highest_bidder = None
                auction.highest_bid = 0
                self._log("Ставка выбывшего игрока аннулирована.")
            self._auction_step()

        if self.finished:
            return False

        if self._active_connected():
            if len(self._active_connected()) < 2:
                return True

            if self.phase == "purchase" and self.current and self.current.id == player_id:
                self.pending_position = None
                self._log("Игрок вышел — лот остался некупленным.")
                self._end_turn()
            elif self.phase == "await_roll" and self.current and self.current.id == player_id:
                self._end_turn()
            elif self.phase == "game_over":
                pass
            return False
        return True

    # ------------------------------------------------------------------
    # Состояние для клиента
    # ------------------------------------------------------------------
    def view(self) -> dict[str, Any]:
        current = self.current
        return {
            "players": [
                {
                    "id": player.id,
                    "name": player.name,
                    "money": player.money,
                    "position": player.position,
                    "position_name": BOARD[player.position].name,
                    "connected": player.connected,
                    "bankrupt": player.bankrupt,
                    "in_jail": player.in_jail,
                    "jail_turns": player.jail_turns,
                    "jail_cards": player.jail_cards,
                    "properties": sum(
                        1
                        for state in self.properties.values()
                        if state.owner_id == player.id
                    ),
                    "is_current": current is not None and current.id == player.id,
                }
                for player in self.players.values()
            ],
            "turn_player_id": current.id if current else None,
            "dice": list(self.dice) if self.dice else None,
            "roll_id": self.roll_id,
            "log": list(self.log),
            "finished": self.finished,
            "winner_id": self.winner_id,
            "phase": self.phase,
            "pending_position": self.pending_position,
            "properties": [
                self._property_view(position) for position in PURCHASABLE_POSITIONS
            ],
            "auction": self._auction_view(),
            "bank_houses": self.bank_houses,
            "bank_hotels": self.bank_hotels,
            "notice": self.notice,
        }

    def _property_view(self, position: int) -> dict[str, Any]:
        cell = BOARD[position]
        state = self._property(position)
        owner = self.players.get(state.owner_id) if state.owner_id else None
        rent = list(cell.rent)
        if cell.kind == "railroad":
            rent = [25, 50, 100, 200]
        elif cell.kind == "utility":
            rent = [0]
        return {
            "position": position,
            "name": cell.name,
            "kind": cell.kind,
            "group": cell.group,
            "price": cell.price,
            "house_cost": cell.house_cost,
            "rent": rent,
            "owner_id": state.owner_id,
            "owner_name": owner.name if owner else None,
            "houses": state.houses,
            "mortgaged": state.mortgaged,
            "mortgage_value": cell.price // 2,
            "unmortgage_cost": int(cell.price * 0.55),
        }

    def _auction_view(self) -> dict[str, Any] | None:
        auction = self.auction
        if auction is None:
            return None
        cell = BOARD[auction.position]
        bidder = (
            self.players.get(auction.highest_bidder)
            if auction.highest_bidder
            else None
        )
        turn_player = self.players.get(auction.turn_id) if auction.turn_id else None
        return {
            "position": auction.position,
            "name": cell.name,
            "price": cell.price,
            "highest_bid": auction.highest_bid,
            "highest_bidder_id": auction.highest_bidder,
            "highest_bidder_name": bidder.name if bidder else None,
            "turn_player_id": auction.turn_id,
            "turn_player_name": turn_player.name if turn_player else None,
            "active_ids": list(auction.active),
            "min_bid": max(MIN_AUCTION_BID, auction.highest_bid + 10),
        }
