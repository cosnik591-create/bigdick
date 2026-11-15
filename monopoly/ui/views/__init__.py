"""Экраны приложения."""

from .game import GameView
from .host_setup import HostSetupView
from .join_setup import JoinSetupView
from .lobby import LobbyView
from .main_menu import MainMenuView

__all__ = [
    "MainMenuView",
    "HostSetupView",
    "JoinSetupView",
    "LobbyView",
    "GameView",
]
