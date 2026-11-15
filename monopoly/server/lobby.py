"""Модель игрока и лобби (комнаты ожидания)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .game import GameSession


@dataclass
class Player:
    id: str
    name: str
    is_host: bool = False
    ready: bool = False
    connected: bool = True


@dataclass
class Lobby:
    code: str
    name: str
    host_id: str
    max_players: int
    players: dict[str, Player] = field(default_factory=dict)
    phase: str = "lobby"  # lobby | in_game
    game: GameSession | None = None

    @property
    def can_start(self) -> bool:
        if self.phase != "lobby":
            return False
        if len(self.players) < 2:
            return False
        return all(player.is_host or player.ready for player in self.players.values())

    def view(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "name": self.name,
            "host_id": self.host_id,
            "max_players": self.max_players,
            "phase": self.phase,
            "can_start": self.can_start,
            "players": [
                {
                    "id": player.id,
                    "name": player.name,
                    "is_host": player.is_host,
                    "ready": player.ready,
                    "connected": player.connected,
                }
                for player in self.players.values()
            ],
        }
