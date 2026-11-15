"""Модальные окна игрового экрана: покупка, аукцион и управление собственностью."""

from __future__ import annotations

from typing import Any

from arcade.gui import UIBoxLayout

from ...board import GROUP_POSITIONS
from .. import theme
from ..widgets import OverlayPanel, make_button, make_label


def _player(game: dict[str, Any], player_id: str | None) -> dict[str, Any] | None:
    if not player_id:
        return None
    return next(
        (player for player in game.get("players", []) if player.get("id") == player_id),
        None,
    )


def _property(game: dict[str, Any], position: int | None) -> dict[str, Any] | None:
    if position is None:
        return None
    return next(
        (
            prop
            for prop in game.get("properties", [])
            if prop.get("position") == position
        ),
        None,
    )


def _kind_title(prop: dict[str, Any]) -> str:
    return {
        "property": "Улица",
        "railroad": "Железная дорога",
        "utility": "Коммунальное предприятие",
    }.get(prop.get("kind"), "Собственность")


def rent_description(prop: dict[str, Any]) -> str:
    if prop.get("kind") == "railroad":
        return "Аренда: 25 / 50 / 100 / 200 ₽ за 1–4 вокзала."
    if prop.get("kind") == "utility":
        return "Аренда: 4× сумма кубиков за одно предприятие, 10× — за два."
    rent = prop.get("rent") or []
    if len(rent) >= 6:
        return (
            f"Аренда: {rent[0]} ₽ · 1 дом: {rent[1]} ₽ · 2 дома: {rent[2]} ₽ · "
            f"3 дома: {rent[3]} ₽ · 4 дома: {rent[4]} ₽ · отель: {rent[5]} ₽. "
            "При полной цветовой группе базовая аренда удваивается."
        )
    return "Аренда начисляется по стандартным правилам."


def _send(view: Any, message_type: str, **fields: Any) -> None:
    if view.window.client is not None:
        view.window.client.send(message_type, **fields)


class PurchaseModal(OverlayPanel):
    def __init__(self, view: Any, game: dict[str, Any]):
        super().__init__(view, width=520)
        self.position = int(game.get("pending_position") or 0)
        self.refresh(game)

    def refresh(self, game: dict[str, Any]) -> None:
        prop = _property(game, self.position)
        if prop is None:
            self.close()
            return
        me = _player(game, self.view.window.player_id)
        self.clear()

        self.add(make_label("ПОКУПКА", 11, theme.MUTED, bold=True, width=464))
        self.add(make_label(prop["name"], 26, theme.TEXT, bold=True, width=464))
        self.add(make_label(_kind_title(prop), 13, theme.MUTED, width=464))
        self.add(
            make_label(
                f"Цена: {prop['price']} ₽",
                20,
                theme.ACCENT,
                bold=True,
                width=464,
            )
        )
        self.add(make_label(rent_description(prop), 13, theme.TEXT, width=464))
        if me is not None:
            self.add(
                make_label(
                    f"У вас {me.get('money', 0)} ₽. При отказе начнётся аукцион.",
                    12,
                    theme.MUTED,
                    width=464,
                )
            )

        row = UIBoxLayout(
            vertical=False, align="center", space_between=12, size_hint=(0, 0)
        )
        buy = make_button(f"Купить за {prop['price']} ₽", 240, 46, "primary")
        if me is None or int(me.get("money", 0)) < int(prop["price"]):
            buy.disabled = True
        auction = make_button("На аукцион", 200, 46, "secondary")

        @buy.event("on_click")
        def _buy(_event: object) -> None:
            _send(self.view, "buy_property")

        @auction.event("on_click")
        def _auction(_event: object) -> None:
            _send(self.view, "decline_property")

        row.add(buy)
        row.add(auction)
        self.add(row)


class AuctionModal(OverlayPanel):
    def __init__(self, view: Any, game: dict[str, Any]):
        super().__init__(view, width=520)
        self.refresh(game)

    def refresh(self, game: dict[str, Any]) -> None:
        auction = game.get("auction")
        if not auction:
            self.close()
            return
        self.clear()
        me = _player(game, self.view.window.player_id)
        self.add(make_label("АУКЦИОН", 11, theme.ACCENT, bold=True, width=464))
        self.add(make_label(auction["name"], 26, theme.TEXT, bold=True, width=464))
        self.add(
            make_label(
                f"Цена на доске: {auction['price']} ₽",
                13,
                theme.MUTED,
                width=464,
            )
        )

        highest = int(auction.get("highest_bid") or 0)
        bidder_name = auction.get("highest_bidder_name")
        bid_text = (
            f"Текущая ставка: {highest} ₽ — {bidder_name}"
            if highest > 0
            else "Ставок пока нет"
        )
        self.add(make_label(bid_text, 18, theme.ACCENT, bold=True, width=464))

        if me is not None:
            self.add(
                make_label(
                    f"Ваши деньги: {me.get('money', 0)} ₽",
                    12,
                    theme.MUTED,
                    width=464,
                )
            )

        if auction.get("turn_player_id") == self.view.window.player_id and me is not None:
            self.add(
                make_label(
                    "Ваша очередь делать ставку.",
                    14,
                    theme.SUCCESS,
                    bold=True,
                    width=464,
                )
            )
            money = int(me.get("money", 0))
            min_bid = int(auction.get("min_bid") or 10)
            row = UIBoxLayout(
                vertical=False, align="center", space_between=10, size_hint=(0, 0)
            )
            for amount in (min_bid, min_bid + 50, min_bid + 100):
                bid_button = make_button(f"{amount} ₽", 140, 42, "secondary")
                if amount > money:
                    bid_button.disabled = True

                @bid_button.event("on_click")
                def _bid(_event: object, value: int = amount) -> None:
                    _send(self.view, "auction_bid", amount=value)

                row.add(bid_button)
            self.add(row)
            pass_button = make_button("Пас", 200, 40, "ghost")

            @pass_button.event("on_click")
            def _pass(_event: object) -> None:
                _send(self.view, "auction_pass")

            self.add(pass_button)
        else:
            turn_name = auction.get("turn_player_name") or "—"
            self.add(
                make_label(
                    f"Ждём ставку: {turn_name}",
                    15,
                    theme.TEXT,
                    bold=True,
                    width=464,
                )
            )
            self.add(
                make_label(
                    "Аукцион идёт по очереди. Пас означает выход из торгов.",
                    12,
                    theme.MUTED,
                    width=464,
                )
            )


class PropertyModal(OverlayPanel):
    def __init__(self, view: Any, position: int):
        super().__init__(view, width=540)
        self.position = position
        self.refresh(view.game)

    def refresh(self, game: dict[str, Any]) -> None:
        prop = _property(game, self.position)
        if prop is None:
            self.close()
            return
        me = _player(game, self.view.window.player_id)
        owner = _player(game, prop.get("owner_id"))
        self.clear()

        self.add(make_label("СОБСТВЕННОСТЬ", 11, theme.MUTED, bold=True, width=484))
        self.add(make_label(prop["name"], 25, theme.TEXT, bold=True, width=484))
        self.add(make_label(_kind_title(prop), 13, theme.MUTED, width=484))
        self.add(
            make_label(
                f"Цена: {prop['price']} ₽ · Залог: {prop['mortgage_value']} ₽",
                13,
                theme.MUTED,
                width=484,
            )
        )
        owner_text = owner["name"] if owner else "свободна"
        self.add(make_label(f"Владелец: {owner_text}", 15, theme.TEXT, width=484))
        self.add(make_label(rent_description(prop), 12, theme.TEXT, width=484))

        if prop.get("mortgaged"):
            self.add(make_label("Статус: заложена, аренда не начисляется.", 13, theme.DANGER, width=484))
        elif prop.get("houses") == 5:
            self.add(make_label("На участке построен отель.", 13, theme.SUCCESS, width=484))
        elif prop.get("houses"):
            self.add(
                make_label(
                    f"На участке домов: {prop['houses']}.",
                    13,
                    theme.SUCCESS,
                    width=484,
                )
            )
        else:
            self.add(make_label("Зданий нет.", 12, theme.MUTED, width=484))

        actions: list[Any] = []
        if (
            me is not None
            and prop.get("owner_id") == me.get("id")
            and game.get("phase") == "await_roll"
            and game.get("turn_player_id") == me.get("id")
        ):
            if prop.get("kind") == "property":
                group = GROUP_POSITIONS.get(prop.get("group", ""), ())
                properties = {
                    item["position"]: item for item in game.get("properties", [])
                }
                full_group = bool(group) and all(
                    properties.get(pos, {}).get("owner_id") == me.get("id")
                    for pos in group
                )
                group_mortgaged = any(
                    properties.get(pos, {}).get("mortgaged") for pos in group
                )
                houses = int(prop.get("houses") or 0)
                levels = [
                    int(properties.get(pos, {}).get("houses") or 0) for pos in group
                ]
                even_build = (
                    bool(levels) and houses + 1 <= min(levels) + 1
                )
                bank_ok = (
                    int(game.get("bank_hotels") or 0) > 0
                    if houses == 4
                    else int(game.get("bank_houses") or 0) > 0
                )
                if (
                    full_group
                    and not group_mortgaged
                    and houses < 5
                    and even_build
                    and bank_ok
                    and int(me.get("money", 0)) >= int(prop["house_cost"])
                ):
                    word = "отель" if houses == 4 else "дом"
                    build = make_button(
                        f"Построить {word} ({prop['house_cost']} ₽)",
                        484,
                        42,
                        "primary",
                    )

                    @build.event("on_click")
                    def _build(_event: object) -> None:
                        _send(self.view, "build", position=self.position)

                    actions.append(build)

                if houses > 0:
                    post_levels = list(levels)
                    post_levels[group.index(self.position)] = houses - 1
                    even_sell = max(post_levels) - min(post_levels) <= 1
                    bank_ok = (
                        int(game.get("bank_houses") or 0) >= 4
                        if houses == 5
                        else True
                    )
                    if even_sell and bank_ok:
                        sell = make_button(
                            f"Продать здание (+{int(prop['house_cost']) // 2} ₽)",
                            484,
                            42,
                            "secondary",
                        )

                        @sell.event("on_click")
                        def _sell(_event: object) -> None:
                            _send(self.view, "sell_building", position=self.position)

                        actions.append(sell)

            if prop.get("mortgaged"):
                unmortgage = make_button(
                    f"Выкупить ({prop['unmortgage_cost']} ₽)", 484, 42, "secondary"
                )
                if int(me.get("money", 0)) < int(prop["unmortgage_cost"]):
                    unmortgage.disabled = True

                @unmortgage.event("on_click")
                def _unmortgage(_event: object) -> None:
                    _send(self.view, "unmortgage", position=self.position)

                actions.append(unmortgage)
            elif int(prop.get("houses") or 0) == 0:
                group = GROUP_POSITIONS.get(prop.get("group", ""), ())
                properties = {
                    item["position"]: item for item in game.get("properties", [])
                }
                group_developed = any(
                    int(properties.get(pos, {}).get("houses") or 0) > 0
                    for pos in group
                )
                if not group_developed:
                    mortgage = make_button(
                        f"Заложить (+{prop['mortgage_value']} ₽)",
                        484,
                        42,
                        "secondary",
                    )

                    @mortgage.event("on_click")
                    def _mortgage(_event: object) -> None:
                        _send(self.view, "mortgage", position=self.position)

                    actions.append(mortgage)

        for button in actions:
            self.add(button)

        close = make_button("Закрыть", 484, 40, "ghost")

        @close.event("on_click")
        def _close(_event: object) -> None:
            self.view.close_property_modal()

        self.add(close)
