from __future__ import annotations

import argparse
import asyncio
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "KORLIC_v2"))

from Korlic_v2.bot import KorlicBot
from Korlic_v2.factory import PublicGammaClient
from Korlic_v2.launcher import _run_all
from Korlic_v2.models import BookLevel, ClassificationStatus, ClassifiedMarket, MarketRecord, OrderBookSnapshot
from Korlic_v2.signal import SignalConfig, SignalEngine
from Korlic_v2.runtime import TimeSync
from Korlic_v2.storage import KorlicStorage


def test_run_all_keep_running_skips_run_once(monkeypatch, tmp_path: Path):
    called = {"run_once": 0, "loop": 0}

    class DummyBot:
        pass

    monkeypatch.setattr("Korlic_v2.launcher._setup_logger", lambda *_: object())
    monkeypatch.setattr("Korlic_v2.launcher._load_bot", lambda *_, **__: DummyBot())

    async def fake_run_once(*_, **__):
        called["run_once"] += 1

    async def fake_run_loop(*_, **__):
        called["loop"] += 1

    monkeypatch.setattr("Korlic_v2.launcher._run_once", fake_run_once)
    monkeypatch.setattr("Korlic_v2.launcher._run_loop_with_trade_log", fake_run_loop)

    args = argparse.Namespace(
        db_path=str(tmp_path / "db.sqlite"),
        log_file=str(tmp_path / "launcher.log"),
        output_dir=str(tmp_path / "reports"),
        lines=5,
        keep_running=True,
        factory="Korlic_v2.factory:build_bot",
        trades_log_file=str(tmp_path / "trades.log"),
        interval_seconds=60.0,
    )

    rc = _run_all(args)
    assert rc == 0
    assert called["run_once"] == 0
    assert called["loop"] == 1


def test_public_gamma_client_paginates_and_keeps_non_btc_active_open(monkeypatch):
    calls = []

    class DummyResponse:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    def fake_get(url, params=None, timeout=20.0):
        if "events/slug/" in url:
            return DummyResponse({"markets": []})
        calls.append(dict(params or {}))
        if len(calls) == 1:
            return DummyResponse(
                {
                    "data": [
                        {
                            "markets": [
                                {
                                    "id": "m1",
                                    "slug": "sports-5m",
                                    "question": "Sports market?",
                                    "endDate": "2026-03-31T12:00:00Z",
                                    "active": True,
                                    "closed": False,
                                    "acceptingOrders": True,
                                    "enableOrderBook": True,
                                    "clobTokenIds": '["t1","t2"]',
                                },
                                {
                                    "id": "m2",
                                    "slug": "closed-market",
                                    "question": "Closed market",
                                    "endDate": "2026-03-31T12:00:00Z",
                                    "active": True,
                                    "closed": True,
                                    "clobTokenIds": '["t3","t4"]',
                                },
                            ]
                        }
                    ]
                }
            )
        return DummyResponse({"data": []})

    monkeypatch.setattr("Korlic_v2.factory.httpx.get", fake_get)
    client = PublicGammaClient(page_limit=2, max_pages=3, seed_event_slug="")
    markets = client._fetch_active_markets()

    assert calls[0] == {"active": "true", "closed": "false", "limit": "2", "offset": "0"}
    assert calls[1] == {"active": "true", "closed": "false", "limit": "2", "offset": "2"}
    assert [m.market_id for m in markets] == ["m1"]


class DummyGamma:
    def __init__(self, markets):
        self.markets = markets

    async def get_active_markets(self):
        return self.markets


class DummyClob:
    def __init__(self, books):
        self.books = books

    async def get_server_time_ms(self):
        return int(datetime.now(timezone.utc).timestamp() * 1000)

    async def get_orderbook(self, token_id: str):
        return self.books[token_id]


class DummyWs:
    async def subscribe(self, _asset_ids):
        return None

    async def is_healthy(self):
        return True


def test_bot_evaluates_non_crypto_operable_markets(tmp_path: Path):
    market = MarketRecord(
        market_id="m1",
        event_id="e1",
        question="Will Team A win?",
        slug="sports-5m-test",
        token_ids=("yes", "no"),
        end_time=datetime.now(timezone.utc) + timedelta(seconds=50),
        active=True,
        closed=False,
        accepting_orders=True,
        enable_order_book=True,
        tags=("sports",),
        category="sports",
        cadence_hint="5m",
    )
    books = {
        "yes": OrderBookSnapshot(token_id="yes", bids=(), asks=(BookLevel(0.95, 20.0),), ts_ms=1),
        "no": OrderBookSnapshot(token_id="no", bids=(), asks=(BookLevel(0.95, 20.0),), ts_ms=1),
    }
    storage = KorlicStorage(str(tmp_path / "korlic.sqlite"))
    bot = KorlicBot(gamma=DummyGamma([market]), clob=DummyClob(books), ws=DummyWs(), storage=storage)

    asyncio.run(bot.run_cycle())

    with sqlite3.connect(storage.db_path) as conn:
        rows = conn.execute(
            "SELECT COUNT(*) FROM events WHERE market_id='m1' AND event_type IN ('SIGNAL_DETECTED', 'NO_TRADE')"
        ).fetchone()[0]
    assert rows > 0


def test_signal_uses_per_trade_budget_instead_of_full_cash():
    market = MarketRecord(
        market_id="m-budget",
        event_id="e-budget",
        question="Budget control",
        slug="btc-updown-5m-budget",
        token_ids=("yes", "no"),
        end_time=datetime.now(timezone.utc) + timedelta(seconds=180),
        active=True,
        closed=False,
        accepting_orders=True,
        enable_order_book=True,
    )
    book = OrderBookSnapshot(
        token_id="yes",
        bids=(),
        asks=(BookLevel(0.6, 1_000.0),),
        ts_ms=int(datetime.now(timezone.utc).timestamp() * 1000),
    )
    engine = SignalEngine(
        SignalConfig(
            entry_price=0.6,
            entry_seconds_threshold=600,
            min_operational_size=10.0,
            min_order_size=5.0,
            max_stake_per_trade=30.0,
        )
    )
    sync = TimeSync()
    sync.sync(int(datetime.now(timezone.utc).timestamp() * 1000))

    signal, reason = engine.evaluate(
        market=ClassifiedMarket(
            market=market,
            status=ClassificationStatus.CANDIDATE_5M,
            confidence=1.0,
            method="test",
        ),
        token_id="yes",
        book=book,
        end_epoch_ms=int(market.end_time.timestamp() * 1000),
        time_sync=sync,
        available_cash=1_000.0,
    )

    assert reason == "signal_candidate"
    assert signal is not None
    assert signal.size == 50.0


def test_signal_treats_60c_as_0_60_not_60():
    market = MarketRecord(
        market_id="m-price-units",
        event_id="e-price-units",
        question="Price units",
        slug="btc-updown-5m-price-units",
        token_ids=("yes", "no"),
        end_time=datetime.now(timezone.utc) + timedelta(seconds=120),
        active=True,
        closed=False,
        accepting_orders=True,
        enable_order_book=True,
    )
    engine = SignalEngine(
        SignalConfig(
            entry_price=0.6,
            entry_seconds_threshold=600,
            min_operational_size=10.0,
            min_order_size=5.0,
            max_stake_per_trade=30.0,
        )
    )
    sync = TimeSync()
    sync.sync(int(datetime.now(timezone.utc).timestamp() * 1000))

    signal_ok, reason_ok = engine.evaluate(
        market=ClassifiedMarket(
            market=market,
            status=ClassificationStatus.CANDIDATE_5M,
            confidence=1.0,
            method="test",
        ),
        token_id="yes",
        book=OrderBookSnapshot(token_id="yes", bids=(), asks=(BookLevel(0.6, 100.0),), ts_ms=1),
        end_epoch_ms=int(market.end_time.timestamp() * 1000),
        time_sync=sync,
        available_cash=100.0,
    )
    assert signal_ok is not None
    assert reason_ok == "signal_candidate"

    signal_bad, reason_bad = engine.evaluate(
        market=ClassifiedMarket(
            market=MarketRecord(
                market_id="m-price-units-2",
                event_id="e-price-units-2",
                question="Price units 2",
                slug="btc-updown-5m-price-units-2",
                token_ids=("yes", "no"),
                end_time=datetime.now(timezone.utc) + timedelta(seconds=120),
                active=True,
                closed=False,
                accepting_orders=True,
                enable_order_book=True,
            ),
            status=ClassificationStatus.CANDIDATE_5M,
            confidence=1.0,
            method="test",
        ),
        token_id="yes",
        book=OrderBookSnapshot(token_id="yes", bids=(), asks=(BookLevel(60.0, 100.0),), ts_ms=1),
        end_epoch_ms=int((datetime.now(timezone.utc) + timedelta(seconds=120)).timestamp() * 1000),
        time_sync=sync,
        available_cash=100.0,
    )
    assert signal_bad is None
    assert reason_bad == "skipped_price_above_entry_threshold"
