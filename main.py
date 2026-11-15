"""Точка входа в игру."""

from __future__ import annotations

import logging

import arcade

from monopoly.ui.app import MonopolyWindow


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    window = MonopolyWindow()
    try:
        arcade.run()
    finally:
        window.close()


if __name__ == "__main__":
    main()
