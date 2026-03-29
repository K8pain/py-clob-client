from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


from Korlic.bot import KorlicBot
from Korlic.discovery import DiscoveryEngine, MarketClassifier
from Korlic.models import BookLevel, Ledger, MarketRecord, OrderBookSnapshot
from Korlic.paper import PaperExecutionEngine
from Korlic.signal import SignalConfig, SignalEngine
from Korlic.storage import KorlicStorage


class DummyGamma:
    def __init__(self, markets):
        self.markets = markets

    async def get_active_markets(self):
        return self.markets


class DummyClob:
    def __init__(self, book):
        self.book = book

    async def get_server_time_ms(self):
        return int(datetime.now(timezone.utc).timestamp() * 1000)

    async def get_orderbook(self, token_id: str):
        return self.book[token_id]


class DummyWs:
    def __init__(self):
        self.calls = 0

    async def subscribe(self, asset_ids):
        self.calls += 1

    async def is_healthy(self):
        return True


def _market(minutes: int = 5) -> MarketRecord:
    return MarketRecord(
        market_id="m1",
        event_id="e1",
        question="BTC 5m above 100k?",
        slug="btc-5m-above",
        token_ids=("t_yes", "t_no"),
        end_time=datetime.now(timezone.utc) + timedelta(minutes=minutes),
        active=True,
        closed=False,
        accepting_orders=True,
        enable_order_book=True,
        tags=("crypto",),
        category="crypto",
        cadence_hint="5m",
    )


def test_discovery_filters_and_classifies_5m():
    engine = DiscoveryEngine(MarketClassifier())
    state = engine.build_universe([_market()])
    assert "m1" in state.markets


def test_signal_rejects_duplicate_and_depth():
    engine = SignalEngine(SignalConfig(min_operational_size=10, min_order_size=5))
    m = MarketClassifier().classify(_market())
    book = OrderBookSnapshot(token_id="t_yes", bids=(), asks=(BookLevel(0.60, 20),), ts_ms=1)

    class T:
        def seconds_to(self, _):
            return 30

    signal, reason = engine.evaluate(m, "t_yes", book, 0, T(), 100)
    assert signal is not None and reason == "signal_candidate"

    signal2, reason2 = engine.evaluate(m, "t_yes", book, 0, T(), 100)
    assert signal2 is None and reason2 == "skipped_duplicate_signal"


def test_paper_fill_and_settlement():
    ledger = Ledger(cash_available=100)
    paper = PaperExecutionEngine(ledger)
    signal, _ = SignalEngine(SignalConfig()).evaluate(
        market=MarketClassifier().classify(_market()),
        token_id="t_yes",
        book=OrderBookSnapshot(token_id="t_yes", bids=(), asks=(BookLevel(0.60, 50),), ts_ms=1),
        end_epoch_ms=10,
        time_sync=type("T", (), {"seconds_to": lambda *_: 10})(),
        available_cash=100,
    )
    order = paper.create_order(signal)
    assert order is not None

    filled = paper.try_fill(order, OrderBookSnapshot(token_id="t_yes", bids=(), asks=(BookLevel(0.60, 50),), ts_ms=1))
    assert filled > 0
    pos = paper.settle_market("m1", "t_yes")
    assert pos is not None
    assert pos.status == pos.status.WON


def test_bot_cycle_persists_state(tmp_path):
    market = _market(minutes=1)
    book = {
        "t_yes": OrderBookSnapshot(token_id="t_yes", bids=(), asks=(BookLevel(0.60, 30),), ts_ms=1),
        "t_no": OrderBookSnapshot(token_id="t_no", bids=(), asks=(BookLevel(0.60, 30),), ts_ms=1),
    }
    storage = KorlicStorage(str(tmp_path / "korlic.sqlite"))
    bot = KorlicBot(gamma=DummyGamma([market]), clob=DummyClob(book), ws=DummyWs(), storage=storage)
    import asyncio
    asyncio.run(bot.run_cycle())
    assert storage.load_runtime_state() is not None
