"""Pruebas del ciclo del bot para validar selección, señales y ejecución."""

from __future__ import annotations

import sys
import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from Korlic_v2.bot import KorlicBot, KorlicConfig
from Korlic_v2.models import BookLevel, MarketRecord, OrderBookSnapshot, StructuredEvent


class InMemoryStorage:
    def __init__(self) -> None:
        self.events: list[StructuredEvent] = []

    def save_event(self, event: StructuredEvent) -> None:
        self.events.append(event)

    def save_runtime_state(self, ledger, orders, positions, dedupe) -> None:  # noqa: ANN001
        return None

    def load_runtime_state(self):
        return None

    def save_pseudo_trade(self, row):  # noqa: ANN001
        return None

    def export_csv_reports(self, output_dir: str):  # noqa: ARG002
        return {}

    def trade_counters(self) -> dict[str, float | int]:
        return {
            "total_trades": 0,
            "won_trades": 0,
            "lost_trades": 0,
            "open_trades": 0,
            "net_pnl": 0.0,
        }


class StubGamma:
    def __init__(self, markets_per_cycle: list[list[MarketRecord]]) -> None:
        self._markets_per_cycle = markets_per_cycle

    async def get_active_markets(self) -> list[MarketRecord]:
        if self._markets_per_cycle:
            return self._markets_per_cycle.pop(0)
        return []


class StubClob:
    def __init__(self, server_times_ms: list[int], orderbook: OrderBookSnapshot) -> None:
        self._server_times_ms = server_times_ms
        self._orderbook = orderbook

    async def get_server_time_ms(self) -> int:
        return self._server_times_ms.pop(0)

    async def get_orderbook(self, token_id: str) -> OrderBookSnapshot:  # noqa: ARG002
        return self._orderbook

    async def get_market_resolution(self, market_id: str) -> tuple[bool, str | None]:  # noqa: ARG002
        return False, None


class StubWs:
    async def subscribe(self, asset_ids: list[str]) -> None:  # noqa: ARG002
        return None

    async def is_healthy(self) -> bool:
        return True


def test_run_cycle_emits_business_log_each_cycle(monkeypatch: pytest.MonkeyPatch) -> None:
    now = datetime.now(timezone.utc)
    market = MarketRecord(
        market_id="m-1",
        event_id="e-1",
        question="BTC up or down",
        slug="btc-updown-5m",
        token_ids=("tok-1",),
        end_time=now + timedelta(minutes=2),
        active=True,
        closed=False,
        accepting_orders=True,
        enable_order_book=True,
    )
    orderbook = OrderBookSnapshot(
        token_id="tok-1",
        bids=(BookLevel(price=0.59, size=30.0),),
        asks=(BookLevel(price=0.59, size=30.0),),
        ts_ms=0,
    )
    storage = InMemoryStorage()
    bot = KorlicBot(
        gamma=StubGamma([[market], [market]]),
        clob=StubClob(
            server_times_ms=[int(now.timestamp() * 1000), int(now.timestamp() * 1000) + 1_000],
            orderbook=orderbook,
        ),
        ws=StubWs(),
        storage=storage,  # type: ignore[arg-type]
    )
    calls: list[str] = []

    def fake_info(message: str, payload: str) -> None:
        calls.append(f"{message}\n{payload}")

    monkeypatch.setattr("Korlic_v2.bot.business_logger.info", fake_info)

    asyncio.run(bot.run_cycle())
    asyncio.run(bot.run_cycle())

    assert len(calls) == 3
    assert any("business.pnl.update" in item for item in calls)
    assert any("business.trade.entered" in item for item in calls)


def test_run_cycle_can_open_orders_after_first_cycle() -> None:
    now = datetime.now(timezone.utc)
    market_1 = MarketRecord(
        market_id="m-1",
        event_id="e-1",
        question="BTC up or down",
        slug="btc-updown-5m",
        token_ids=("tok-1",),
        end_time=now + timedelta(minutes=2),
        active=True,
        closed=False,
        accepting_orders=True,
        enable_order_book=True,
    )
    market_2 = MarketRecord(
        market_id="m-2",
        event_id="e-2",
        question="ETH up or down",
        slug="eth-updown-5m",
        token_ids=("tok-2",),
        end_time=now + timedelta(minutes=2),
        active=True,
        closed=False,
        accepting_orders=True,
        enable_order_book=True,
    )
    orderbook = OrderBookSnapshot(
        token_id="tok-1",
        bids=(BookLevel(price=0.59, size=30.0),),
        asks=(BookLevel(price=0.59, size=30.0),),
        ts_ms=0,
    )
    storage = InMemoryStorage()
    bot = KorlicBot(
        gamma=StubGamma([[market_1], [market_2]]),
        clob=StubClob(
            server_times_ms=[int(now.timestamp() * 1000), int(now.timestamp() * 1000) + 1_000],
            orderbook=orderbook,
        ),
        ws=StubWs(),
        storage=storage,  # type: ignore[arg-type]
    )

    asyncio.run(bot.run_cycle())
    asyncio.run(bot.run_cycle())

    opened_events = [event for event in storage.events if event.event_type == "PSEUDO_ORDER_OPENED"]
    assert len(opened_events) == 2


def test_run_cycle_filters_markets_beyond_near_expiry_window() -> None:
    now = datetime.now(timezone.utc)
    future_market = MarketRecord(
        market_id="m-future",
        event_id="e-future",
        question="BTC up or down in 6h",
        slug="btc-updown-6h",
        token_ids=("tok-future",),
        end_time=now + timedelta(hours=6),
        active=True,
        closed=False,
        accepting_orders=True,
        enable_order_book=True,
    )
    orderbook = OrderBookSnapshot(
        token_id="tok-future",
        bids=(BookLevel(price=0.59, size=30.0),),
        asks=(BookLevel(price=0.59, size=30.0),),
        ts_ms=0,
    )
    storage = InMemoryStorage()
    bot = KorlicBot(
        gamma=StubGamma([[future_market]]),
        clob=StubClob(server_times_ms=[int(now.timestamp() * 1000)], orderbook=orderbook),
        ws=StubWs(),
        storage=storage,  # type: ignore[arg-type]
        config=KorlicConfig(watch_window_seconds=7200),
    )

    asyncio.run(bot.run_cycle())

    opened_events = [event for event in storage.events if event.event_type == "PSEUDO_ORDER_OPENED"]
    assert opened_events == []
