from __future__ import annotations

import unittest
from unittest.mock import patch

from monopoly.server import game as game_module
from monopoly.server.game import GameError, GameSession


class PlayerStub:
    def __init__(self, player_id: str, name: str):
        self.id = player_id
        self.name = name


class ScriptedRng:
    def __init__(self, *values: int):
        self.values = list(values)

    def randint(self, start: int, end: int) -> int:
        return self.values.pop(0)

    def randrange(self, stop: int) -> int:
        return self.values.pop(0)


def make_game(*names: str) -> GameSession:
    return GameSession([PlayerStub(f"p{i + 1}", name) for i, name in enumerate(names)])


def roll(game: GameSession, player_id: str, *dice: int) -> None:
    with patch.object(game_module, "_rng", ScriptedRng(*dice)):
        game.roll(player_id)


class PurchaseAndAuctionTests(unittest.TestCase):
    def test_buy_property(self) -> None:
        game = make_game("Аня", "Боря")
        roll(game, "p1", 1, 2)
        self.assertEqual(game.players["p1"].position, 3)
        self.assertEqual(game.phase, "purchase")
        self.assertEqual(game.pending_position, 3)

        game.buy_property("p1")
        self.assertEqual(game.properties[3].owner_id, "p1")
        self.assertEqual(game.players["p1"].money, 1500 - 60)
        self.assertEqual(game.phase, "await_roll")
        self.assertEqual(game.current.id, "p2")

    def test_decline_starts_auction_and_bids(self) -> None:
        game = make_game("Аня", "Боря")
        roll(game, "p1", 1, 2)
        game.decline_property("p1")
        self.assertEqual(game.phase, "auction")
        self.assertIsNotNone(game.auction)
        self.assertEqual(game.auction.turn_id, "p1")

        game.auction_bid("p1", 70)
        self.assertEqual(game.auction.highest_bid, 70)
        self.assertEqual(game.auction.turn_id, "p2")

        game.auction_bid("p2", 80)
        game.auction_pass("p1")
        self.assertIsNone(game.auction)
        self.assertEqual(game.properties[3].owner_id, "p2")
        self.assertEqual(game.players["p2"].money, 1500 - 80)
        self.assertEqual(game.current.id, "p2")

    def test_auction_without_bids_leaves_property(self) -> None:
        game = make_game("Аня", "Боря")
        roll(game, "p1", 1, 2)
        game.decline_property("p1")
        game.auction_pass("p1")
        game.auction_pass("p2")
        self.assertIsNone(game.auction)
        self.assertIsNone(game.properties[3].owner_id)
        self.assertEqual(game.current.id, "p2")

    def test_current_player_disconnects_during_auction(self) -> None:
        game = make_game("Аня", "Боря", "Вика")
        game.players["p1"].position = 5
        roll(game, "p1", 2, 2)
        self.assertEqual(game.phase, "purchase")
        self.assertTrue(game.extra_roll)
        game.decline_property("p1")
        game.remove_player("p1")

        game.auction_bid("p2", 10)
        game.auction_bid("p3", 20)
        game.auction_pass("p2")
        self.assertIsNone(game.auction)
        self.assertEqual(game.phase, "await_roll")
        self.assertEqual(game.current.id, "p2")

    def test_bid_cannot_exceed_money(self) -> None:
        game = make_game("Аня", "Боря")
        game.players["p1"].money = 20
        roll(game, "p1", 1, 2)
        game.decline_property("p1")
        with self.assertRaises(GameError):
            game.auction_bid("p1", 30)


class MovementTests(unittest.TestCase):
    def test_passing_start_gives_salary(self) -> None:
        game = make_game("Аня", "Боря")
        game.players["p1"].position = 38
        roll(game, "p1", 1, 2)
        self.assertEqual(game.players["p1"].position, 1)
        self.assertEqual(game.players["p1"].money, 1700)

    def test_three_doubles_send_to_jail(self) -> None:
        game = make_game("Аня", "Боря")
        game._chest = [{"text": "Тест", "money": 1}]
        roll(game, "p1", 2, 2)
        self.assertEqual(game.players["p1"].position, 4)
        self.assertEqual(game.current.id, "p1")

        roll(game, "p1", 2, 2)
        self.assertEqual(game.phase, "purchase")
        game.buy_property("p1")
        self.assertEqual(game.current.id, "p1")

        roll(game, "p1", 2, 2)
        self.assertTrue(game.players["p1"].in_jail)
        self.assertEqual(game.players["p1"].position, 10)
        self.assertEqual(game.current.id, "p2")


class RentTests(unittest.TestCase):
    def test_base_rent(self) -> None:
        game = make_game("Аня", "Боря")
        game.properties[6].owner_id = "p2"
        game.players["p1"].position = 3
        roll(game, "p1", 1, 2)
        self.assertEqual(game.players["p1"].money, 1500 - 6)
        self.assertEqual(game.players["p2"].money, 1500 + 6)

    def test_double_rent_with_full_group(self) -> None:
        game = make_game("Аня", "Боря")
        for position in (6, 8, 9):
            game.properties[position].owner_id = "p2"
        game.players["p1"].position = 3
        roll(game, "p1", 1, 2)
        self.assertEqual(game.players["p1"].money, 1500 - 12)

    def test_railroad_rent_by_count(self) -> None:
        game = make_game("Аня", "Боря")
        game.properties[5].owner_id = "p2"
        game.properties[15].owner_id = "p2"
        game.players["p1"].position = 12
        roll(game, "p1", 1, 2)
        self.assertEqual(game.players["p1"].money, 1500 - 50)

    def test_utility_rent(self) -> None:
        game = make_game("Аня", "Боря")
        game.properties[12].owner_id = "p2"
        game.properties[28].owner_id = "p2"
        game.players["p1"].position = 9
        roll(game, "p1", 1, 2)
        self.assertEqual(game.players["p1"].money, 1500 - 30)

    def test_mortgaged_property_has_no_rent(self) -> None:
        game = make_game("Аня", "Боря")
        game.properties[6].owner_id = "p2"
        game.properties[6].mortgaged = True
        game.players["p1"].position = 3
        roll(game, "p1", 1, 2)
        self.assertEqual(game.players["p1"].money, 1500)


class BuildingAndMortgageTests(unittest.TestCase):
    def _own_brown(self, game: GameSession) -> None:
        game.properties[1].owner_id = "p1"
        game.properties[3].owner_id = "p1"

    def test_build_requires_monopoly_and_even_build(self) -> None:
        game = make_game("Аня", "Боря")
        with self.assertRaises(GameError):
            game.build("p1", 1)

        self._own_brown(game)
        game.build("p1", 1)
        self.assertEqual(game.properties[1].houses, 1)
        self.assertEqual(game.bank_houses, 31)
        self.assertEqual(game.players["p1"].money, 1450)

        with self.assertRaises(GameError):
            game.build("p1", 1)

        game.build("p1", 3)
        game.build("p1", 1)
        self.assertEqual(game.properties[1].houses, 2)

    def test_hotel_and_sell(self) -> None:
        game = make_game("Аня", "Боря")
        self._own_brown(game)
        game.properties[1].houses = 4
        game.properties[3].houses = 4
        game.bank_houses = 24
        game.players["p1"].money = 1000

        game.build("p1", 1)
        self.assertEqual(game.properties[1].houses, 5)
        self.assertEqual(game.bank_hotels, 11)
        self.assertEqual(game.bank_houses, 28)
        self.assertEqual(game.players["p1"].money, 950)

        game.sell_building("p1", 1)
        self.assertEqual(game.properties[1].houses, 4)
        self.assertEqual(game.bank_hotels, 12)
        self.assertEqual(game.bank_houses, 24)
        self.assertEqual(game.players["p1"].money, 975)

    def test_mortgage_and_unmortgage(self) -> None:
        game = make_game("Аня", "Боря")
        self._own_brown(game)
        game.mortgage("p1", 1)
        self.assertTrue(game.properties[1].mortgaged)
        self.assertEqual(game.players["p1"].money, 1530)

        game.unmortgage("p1", 1)
        self.assertFalse(game.properties[1].mortgaged)
        self.assertEqual(game.players["p1"].money, 1530 - 33)

    def test_cannot_mortgage_developed_group(self) -> None:
        game = make_game("Аня", "Боря")
        self._own_brown(game)
        game.properties[1].houses = 1
        with self.assertRaises(GameError):
            game.mortgage("p1", 3)


class JailTests(unittest.TestCase):
    def test_goto_jail_and_pay(self) -> None:
        game = make_game("Аня", "Боря")
        game.players["p1"].position = 27
        roll(game, "p1", 1, 2)
        self.assertEqual(game.players["p1"].position, 10)
        self.assertTrue(game.players["p1"].in_jail)
        self.assertEqual(game.current.id, "p2")

        game.turn_index = 0
        game.phase = "await_roll"
        game.pay_jail("p1")
        self.assertFalse(game.players["p1"].in_jail)
        self.assertEqual(game.players["p1"].money, 1450)

    def test_doubles_leave_jail(self) -> None:
        game = make_game("Аня", "Боря")
        player = game.players["p1"]
        player.position = 10
        player.in_jail = True
        roll(game, "p1", 3, 3)
        self.assertFalse(player.in_jail)
        self.assertEqual(player.position, 16)
        self.assertEqual(game.phase, "purchase")

    def test_third_failure_pays_and_moves(self) -> None:
        game = make_game("Аня", "Боря")
        player = game.players["p1"]
        player.position = 10
        player.in_jail = True
        player.jail_turns = 2
        roll(game, "p1", 1, 2)
        self.assertFalse(player.in_jail)
        self.assertEqual(player.money, 1450)
        self.assertEqual(player.position, 13)

    def test_jail_card(self) -> None:
        game = make_game("Аня", "Боря")
        player = game.players["p1"]
        player.position = 10
        player.in_jail = True
        player.jail_cards = 1
        game.use_jail_card("p1")
        self.assertFalse(player.in_jail)
        self.assertEqual(player.jail_cards, 0)


class CardsAndMoneyTests(unittest.TestCase):
    def test_income_tax(self) -> None:
        game = make_game("Аня", "Боря")
        game.players["p1"].position = 1
        roll(game, "p1", 1, 2)
        self.assertEqual(game.players["p1"].money, 1300)

    def test_chance_card_money(self) -> None:
        game = make_game("Аня", "Боря")
        game._chance = [{"text": "Банк платит 50 ₽.", "money": 50}]
        game.players["p1"].position = 4
        roll(game, "p1", 1, 2)
        self.assertEqual(game.players["p1"].money, 1550)

    def test_chance_zero_money(self) -> None:
        game = make_game("Аня", "Боря")
        game.players["p1"].money = 800
        game._chance = [{"text": "Сбор.", "zero_money": True}]
        game.players["p1"].position = 4
        roll(game, "p1", 1, 2)
        self.assertEqual(game.players["p1"].money, 0)

    def test_chance_lose_random_property(self) -> None:
        game = make_game("Аня", "Боря")
        game.properties[1].owner_id = "p1"
        game.properties[1].houses = 2
        game.bank_houses = 30
        game._chance = [{"text": "Расселение.", "lose_property": True}]
        game.players["p1"].position = 4
        with patch.object(game_module, "_rng", ScriptedRng(1, 2, 0)):
            game.roll("p1")
        self.assertIsNone(game.properties[1].owner_id)
        self.assertEqual(game.properties[1].houses, 0)
        self.assertEqual(game.bank_houses, 32)

    def test_chance_grandma_debt(self) -> None:
        game = make_game("Аня", "Боря")
        game.players["p1"].money = 1000
        game._chance = [{"text": "Долг.", "grandma_debt": True}]
        game.players["p1"].position = 4
        with patch.object(game_module, "_rng", ScriptedRng(1, 2, 600)):
            game.roll("p1")
        self.assertEqual(game.players["p1"].money, 400)
        self.assertEqual(game.current.id, "p2")

    def test_chance_card_to_jail(self) -> None:
        game = make_game("Аня", "Боря")
        game._chance = [{"text": "В тюрьму.", "jail": True}]
        game.players["p1"].position = 4
        roll(game, "p1", 1, 2)
        self.assertTrue(game.players["p1"].in_jail)
        self.assertEqual(game.current.id, "p2")

    def test_bankruptcy_transfers_assets(self) -> None:
        game = make_game("Аня", "Боря")
        game.properties[1].owner_id = "p1"
        game.properties[3].owner_id = "p2"
        game.players["p1"].money = 1
        game.players["p1"].position = 0
        roll(game, "p1", 1, 2)
        self.assertTrue(game.players["p1"].bankrupt)
        self.assertTrue(game.finished)
        self.assertEqual(game.winner_id, "p2")
        self.assertEqual(game.properties[1].owner_id, "p2")
        self.assertEqual(game.phase, "game_over")


if __name__ == "__main__":
    unittest.main()
