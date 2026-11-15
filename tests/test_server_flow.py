from __future__ import annotations

import unittest
from unittest.mock import patch

from monopoly.server import MonopolyServer

from tests.helpers import TestClient


class SequenceRng:
    def __init__(self, *values: int):
        self.values = list(values)

    def randint(self, start: int, end: int) -> int:
        return self.values.pop(0)


class ServerFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.server = MonopolyServer(("127.0.0.1", 0))
        self.server.start()
        self.port = self.server.port
        self.clients: list[TestClient] = []

    def tearDown(self) -> None:
        for client in self.clients:
            client.close()
        self.server.stop()

    def client(self) -> TestClient:
        client = TestClient(self.port)
        self.clients.append(client)
        return client

    def test_full_flow(self) -> None:
        host = self.client()
        host.send("create_lobby", name="Аня", lobby_name="Тестовое лобби", max_players=4)
        state = host.read_until("lobby_state")
        lobby = state["lobby"]
        self.assertEqual(lobby["name"], "Тестовое лобби")
        self.assertEqual(lobby["host_id"], host.id)
        self.assertEqual(len(lobby["players"]), 1)
        self.assertFalse(lobby["can_start"])
        code = lobby["code"]
        self.assertEqual(len(code), 4)

        guest = self.client()
        guest.send("join_lobby", name="Боря", code=code.lower())
        host_state = host.read_until("lobby_state")
        guest_state = guest.read_until("lobby_state")
        self.assertEqual(len(host_state["lobby"]["players"]), 2)
        self.assertEqual(len(guest_state["lobby"]["players"]), 2)
        self.assertFalse(guest_state["lobby"]["can_start"])

        guest.send("set_ready", ready=True)
        guest_ready = guest.read_until("lobby_state")
        self.assertTrue(guest_ready["lobby"]["can_start"])

        host.send("start_game")
        host_game = host.read_until("game_started")["game"]
        guest.read_until("game_started")
        self.assertEqual(len(host_game["players"]), 2)
        self.assertFalse(host_game["finished"])
        self.assertEqual(host_game["turn_player_id"], host_game["players"][0]["id"])

        first = host_game["players"][0]["id"]
        roller = host if first == host.id else guest
        with patch("monopoly.server.game._rng", SequenceRng(1, 2)):
            roller.send("roll_dice")
            update = host.read_until("game_update")["game"]
            guest.read_until("game_update")
        self.assertIsNotNone(update["dice"])
        self.assertEqual(update["players"][0]["position"], 3)
        self.assertEqual(update["phase"], "purchase")

        roller.send("buy_property")
        update = host.read_until("game_update")["game"]
        guest.read_until("game_update")
        brown = next(p for p in update["properties"] if p["position"] == 3)
        self.assertEqual(brown["owner_id"], first)
        self.assertNotEqual(update["turn_player_id"], first)

    def _start_two_player_game(self) -> tuple[TestClient, TestClient]:
        host = self.client()
        host.send("create_lobby", name="Аня", lobby_name="Тест", max_players=4)
        code = host.read_until("lobby_state")["lobby"]["code"]
        guest = self.client()
        guest.send("join_lobby", name="Боря", code=code)
        host.read_until("lobby_state")
        guest.read_until("lobby_state")
        guest.send("set_ready", ready=True)
        host.read_until("lobby_state")
        guest.read_until("lobby_state")
        host.send("start_game")
        host.read_until("game_started")
        guest.read_until("game_started")
        return host, guest

    def test_auction_over_network(self) -> None:
        host, guest = self._start_two_player_game()
        with patch("monopoly.server.game._rng", SequenceRng(1, 2)):
            host.send("roll_dice")
            update = host.read_until("game_update")["game"]
            guest.read_until("game_update")
        self.assertEqual(update["phase"], "purchase")
        self.assertEqual(update["pending_position"], 3)

        host.send("decline_property")
        update = host.read_until("game_update")["game"]
        guest.read_until("game_update")
        self.assertEqual(update["phase"], "auction")
        self.assertEqual(update["auction"]["turn_player_id"], host.id)

        host.send("auction_bid", amount=10)
        host.read_until("game_update")
        guest.read_until("game_update")

        guest.send("auction_bid", amount=20)
        host.read_until("game_update")
        guest.read_until("game_update")

        host.send("auction_pass")
        final = host.read_until("game_update")["game"]
        guest.read_until("game_update")
        brown = next(p for p in final["properties"] if p["position"] == 3)
        self.assertEqual(brown["owner_id"], guest.id)
        self.assertEqual(final["phase"], "await_roll")
        self.assertEqual(final["turn_player_id"], guest.id)

    def test_join_unknown_lobby(self) -> None:
        client = self.client()
        client.send("join_lobby", name="Гость", code="ZZZZ")
        error = client.read_until("error")
        self.assertEqual(error["code"], "lobby_not_found")

    def test_duplicate_name_rejected(self) -> None:
        host = self.client()
        host.send("create_lobby", name="Аня")
        code = host.read_until("lobby_state")["lobby"]["code"]

        guest = self.client()
        guest.send("join_lobby", name="Аня", code=code)
        error = guest.read_until("error")
        self.assertEqual(error["code"], "name_taken")

    def test_kick_player(self) -> None:
        host = self.client()
        host.send("create_lobby", name="Аня")
        code = host.read_until("lobby_state")["lobby"]["code"]

        guest = self.client()
        guest.send("join_lobby", name="Боря", code=code)
        host.read_until("lobby_state")
        guest.read_until("lobby_state")

        host.send("kick_player", player_id=guest.id)
        kicked = guest.read_until("kicked")
        self.assertEqual(kicked["by"], "Аня")
        state = host.read_until("lobby_state")
        self.assertEqual(len(state["lobby"]["players"]), 1)

    def test_disconnect_removes_player(self) -> None:
        host = self.client()
        host.send("create_lobby", name="Аня")
        code = host.read_until("lobby_state")["lobby"]["code"]

        guest = self.client()
        guest.send("join_lobby", name="Боря", code=code)
        host.read_until("lobby_state")
        guest.read_until("lobby_state")

        guest.close()
        self.clients.remove(guest)
        state = host.read_until("lobby_state")
        self.assertEqual(len(state["lobby"]["players"]), 1)
        self.assertEqual(state["lobby"]["host_id"], host.id)

    def test_host_transfer_on_disconnect(self) -> None:
        host = self.client()
        host.send("create_lobby", name="Аня")
        code = host.read_until("lobby_state")["lobby"]["code"]

        guest = self.client()
        guest.send("join_lobby", name="Боря", code=code)
        host.read_until("lobby_state")
        guest.read_until("lobby_state")

        host.close()
        self.clients.remove(host)
        state = guest.read_until("lobby_state")
        self.assertEqual(state["lobby"]["host_id"], guest.id)
        self.assertTrue(state["lobby"]["players"][0]["is_host"])

    def test_ready_required_to_start(self) -> None:
        host = self.client()
        host.send("create_lobby", name="Аня")
        code = host.read_until("lobby_state")["lobby"]["code"]

        guest = self.client()
        guest.send("join_lobby", name="Боря", code=code)
        host.read_until("lobby_state")
        guest.read_until("lobby_state")

        host.send("start_game")
        error = host.read_until("error")
        self.assertEqual(error["code"], "not_ready")

    def test_chat_broadcast(self) -> None:
        host = self.client()
        host.send("create_lobby", name="Аня")
        code = host.read_until("lobby_state")["lobby"]["code"]

        guest = self.client()
        guest.send("join_lobby", name="Боря", code=code)
        host.read_until("lobby_state")
        guest.read_until("lobby_state")

        guest.send("chat", text="Привет!")
        message = host.read_chat_from("Боря")
        self.assertEqual(message["text"], "Привет!")


if __name__ == "__main__":
    unittest.main()
