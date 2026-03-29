from __future__ import annotations

from datetime import timezone

from Korlic.factory import PublicGammaClient, _IntervalRateLimiter, _parse_end_time, _to_market_record


def test_parse_end_time_supports_z_suffix():
    parsed = _parse_end_time("2026-03-29T21:20:47.138Z")
    assert parsed is not None
    assert parsed.tzinfo == timezone.utc


def test_to_market_record_parses_gamma_market_shape():
    raw = {
        "id": "123",
        "event_id": "evt-1",
        "question": "BTC 5m above 100k?",
        "slug": "btc-5m-above-100k",
        "tokens": [{"token_id": "tok-yes"}, {"token_id": "tok-no"}],
        "end_date_iso": "2026-03-29T21:20:47.138Z",
        "active": True,
        "closed": False,
        "accepting_orders": True,
        "enable_order_book": True,
        "tags": [{"slug": "crypto"}],
        "category": "crypto",
    }
    market = _to_market_record(raw)
    assert market is not None
    assert market.market_id == "123"
    assert market.token_ids == ("tok-yes", "tok-no")
    assert market.tags == ("crypto",)


def test_interval_rate_limiter_sleeps_when_called_too_fast(monkeypatch):
    calls: list[float] = []
    now = {"v": 10.0}

    def fake_monotonic():
        return now["v"]

    def fake_sleep(seconds: float):
        calls.append(seconds)
        now["v"] += seconds

    monkeypatch.setattr("Korlic.factory.time.monotonic", fake_monotonic)
    monkeypatch.setattr("Korlic.factory.time.sleep", fake_sleep)

    limiter = _IntervalRateLimiter(min_interval_seconds=0.25)
    limiter.wait_turn()
    limiter.wait_turn()
    assert calls == [0.25]


def test_public_gamma_client_tries_filtered_params_first(monkeypatch):
    calls: list[dict] = []

    class DummyResponse:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    market_payload = [
        {
            "id": "123",
            "event_id": "evt-1",
            "question": "BTC 5m above 100k?",
            "slug": "btc-5m-above-100k",
            "tokens": [{"token_id": "tok-yes"}, {"token_id": "tok-no"}],
            "end_date_iso": "2026-03-29T21:20:47.138Z",
            "active": True,
            "closed": False,
            "accepting_orders": True,
            "enable_order_book": True,
            "tags": [{"slug": "crypto"}],
            "category": "crypto",
        }
    ]

    def fake_get(url, params=None, timeout=20.0):
        calls.append(params or {})
        if params and params.get("accepting_orders") == "true":
            return DummyResponse(market_payload)
        return DummyResponse([])

    monkeypatch.setattr("Korlic.factory.httpx.get", fake_get)

    client = PublicGammaClient()
    markets = client._fetch_active_markets()

    assert len(markets) == 1
    assert calls[0] == {"active": "true", "closed": "false", "accepting_orders": "true", "limit": "500"}
