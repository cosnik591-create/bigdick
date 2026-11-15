"""Клиентская часть сетевого взаимодействия."""

from .network import NetworkClient, NetworkError

__all__ = ["NetworkClient", "NetworkError"]
