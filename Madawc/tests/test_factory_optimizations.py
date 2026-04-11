"""Pruebas de regresión para optimizaciones de API y memoria en Madawc."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from Madawc_v2.factory import PublicClobClient, PublicGammaClient
from Madawc_v2.signal import SignalConfig, SignalEngine


def test_public_gamma_client_deduplicates_market_id_across_pages(monkeypatch):
    class DummyResponse:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    calls = {"count": 0}

    def fake_get(url, params=None, timeout=20.0):  # noqa: ARG001
        if "events/slug/" in url:
            return DummyResponse({"markets": []})
        calls["count"] += 1
        if calls["count"] <= 2:
            return DummyResponse(
                {
                    "data": [
                        {
                            "markets": [
                                {
                                    "id": "mdup",
                                    "slug": "btc-updown-5m",
                                    "question": "Will BTC move in 5m?",
                                    "endDate": "2026-03-31T12:00:00Z",
                                    "active": True,
                                    "closed": False,
                                    "acceptingOrders": True,
                                    "enableOrderBook": True,
                                    "clobTokenIds": '["t1","t2"]',
                                }
                            ]
                        }
                    ]
                }
            )
        return DummyResponse({"data": []})

    monkeypatch.setattr("Madawc_v2.factory.httpx.get", fake_get)
    client = PublicGammaClient(page_limit=1, max_pages=3, seed_event_slug="")
    markets = client._fetch_active_markets()

    assert len(markets) == 1
    assert markets[0].market_id == "mdup"
    assert client.last_fetch_stats["markets_raw"] == 1


def test_public_clob_get_orderbook_does_not_call_server_time():
    class DummyLevel:
        def __init__(self, price: float, size: float):
            self.price = price
            self.size = size

    class DummyBook:
        bids = [DummyLevel(0.5, 12.0)]
        asks = [DummyLevel(0.6, 11.0)]

    calls = {"server_time": 0}

    class DummyInnerClient:
        def get_order_book(self, _token_id: str):
            return DummyBook()

        def get_server_time(self):
            calls["server_time"] += 1
            return {"timestamp": 123}

    client = PublicClobClient()
    client._client = DummyInnerClient()
    snapshot = asyncio.run(client.get_orderbook("tok-1"))

    assert snapshot.token_id == "tok-1"
    assert len(snapshot.bids) == 1
    assert len(snapshot.asks) == 1
    assert snapshot.ts_ms > 0
    assert calls["server_time"] == 0


def test_signal_engine_prunes_and_caps_dedupe():
    engine = SignalEngine(SignalConfig())
    engine.max_dedupe_entries = 2
    engine.dedupe = {"m1:yes", "m2:yes", "m3:yes"}

    engine.prune_to_active_markets({"m1", "m3"})

    assert "m2:yes" not in engine.dedupe
    assert len(engine.dedupe) <= 2
