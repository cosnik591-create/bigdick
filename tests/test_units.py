from __future__ import annotations

import unittest

from monopoly.netutil import format_address, parse_address, parse_port
from monopoly.protocol import ProtocolError, decode, encode, message
from monopoly.validation import clean_chat, clean_lobby_name, clean_player_name


class ProtocolTests(unittest.TestCase):
    def test_roundtrip(self) -> None:
        original = message("chat", text="Привет, мир!", ts=123)
        self.assertEqual(decode(encode(original)), original)

    def test_rejects_broken_json(self) -> None:
        with self.assertRaises(ProtocolError):
            decode(b"{not json}\n")

    def test_rejects_non_object(self) -> None:
        with self.assertRaises(ProtocolError):
            decode(b"[1, 2, 3]\n")

    def test_rejects_missing_type(self) -> None:
        with self.assertRaises(ProtocolError):
            decode(b'{"text": "hi"}\n')


class NameTests(unittest.TestCase):
    def test_name_is_normalized(self) -> None:
        self.assertEqual(clean_player_name("  Анна   Мария "), "Анна Мария")

    def test_empty_name_rejected(self) -> None:
        with self.assertRaises(ValueError):
            clean_player_name("   ")

    def test_long_name_rejected(self) -> None:
        with self.assertRaises(ValueError):
            clean_player_name("я" * 20)

    def test_default_lobby_name(self) -> None:
        self.assertEqual(clean_lobby_name("", "Аня"), "Лобби Аня")

    def test_chat_is_limited(self) -> None:
        self.assertEqual(len(clean_chat("а" * 500)), 300)

    def test_chat_rejects_empty(self) -> None:
        with self.assertRaises(ValueError):
            clean_chat(" \n ")


class AddressTests(unittest.TestCase):
    def test_parse_with_port(self) -> None:
        self.assertEqual(parse_address("192.168.0.5:9000"), ("192.168.0.5", 9000))

    def test_parse_without_port(self) -> None:
        self.assertEqual(parse_address("10.0.0.2"), ("10.0.0.2", 8765))

    def test_parse_empty(self) -> None:
        with self.assertRaises(ValueError):
            parse_address("")

    def test_invalid_port(self) -> None:
        with self.assertRaises(ValueError):
            parse_port("70000")

    def test_format(self) -> None:
        self.assertEqual(format_address("localhost", 8765), "localhost:8765")


if __name__ == "__main__":
    unittest.main()
