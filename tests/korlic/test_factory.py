from __future__ import annotations

from datetime import timezone

from Korlic.factory import (
    PublicClobClient,
    PublicGammaClient,
    _IntervalRateLimiter,
    _extract_market_items,
    _parse_end_time,
    _parse_epoch_value,
    _parse_token_ids_from_clob_ids,
    _to_market_record,
)


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


def test_public_gamma_client_tries_limit_first(monkeypatch):
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
        if params and params.get("limit") == "500":
            return DummyResponse(market_payload)
        return DummyResponse([])

    monkeypatch.setattr("Korlic.factory.httpx.get", fake_get)

    client = PublicGammaClient()
    markets = client._fetch_active_markets()

    assert len(markets) == 1
    assert calls[0] == {"limit": "500"}


def test_public_gamma_client_accepts_markets_payload_shape(monkeypatch):
    class DummyResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "markets": [
                    {
                        "id": "123",
                        "event_id": "evt-1",
                        "question": "BTC 5m above 100k?",
                        "slug": "btc-5m-above-100k",
                        "tokens": [{"token_id": "tok-yes"}, {"token_id": "tok-no"}],
                        "end_date_iso": "2026-03-29T21:20:47.138Z",
                    }
                ]
            }

    monkeypatch.setattr("Korlic.factory.httpx.get", lambda *args, **kwargs: DummyResponse())
    markets = PublicGammaClient()._fetch_active_markets()
    assert len(markets) == 1


def test_to_market_record_parses_camel_case_market_shape():
    raw = {
        "conditionId": "cond-123",
        "event_id": "evt-1",
        "question": "BTC 5m above 100k?",
        "slug": "btc-5m-above-100k",
        "clobTokenIds": "[\"tok-yes\", \"tok-no\"]",
        "endDateIso": "2026-03-29T21:20:47.138Z",
        "acceptingOrders": True,
        "enableOrderBook": True,
        "closed": False,
        "active": True,
    }
    market = _to_market_record(raw)
    assert market is not None
    assert market.market_id == "cond-123"
    assert market.token_ids == ("tok-yes", "tok-no")
    assert market.accepting_orders is True
    assert market.enable_order_book is True


def test_extract_market_items_handles_common_wrappers():
    assert _extract_market_items({"data": [1]}) == [1]
    assert _extract_market_items({"markets": [2]}) == [2]
    assert _extract_market_items({"results": [3]}) == [3]


def test_parse_token_ids_from_clob_ids_handles_json_string():
    assert _parse_token_ids_from_clob_ids("[\"1\",\"2\"]") == ("1", "2")


def test_to_market_record_parses_real_gamma_shape_with_clob_token_ids_string():
    raw = {
        "id": "531202",
        "question": "BitBoy convicted?",
        "conditionId": "0xb48621f7eba07b0a3eeabc6afb09ae42490239903997b9d412b0f69aeb040c8b",
        "slug": "bitboy-convicted",
        "endDate": "2026-03-31T12:00:00Z",
        "active": True,
        "closed": False,
        "acceptingOrders": True,
        "enableOrderBook": True,
        "clobTokenIds": "[\"75467129615908319583031474642658885479135630431889036121812713428992454630178\", \"3842963720267267286970642336860752782302644680156535061700039388405652129691\"]",
    }
    market = _to_market_record(raw)
    assert market is not None
    assert market.market_id == "531202"
    assert market.token_ids == (
        "75467129615908319583031474642658885479135630431889036121812713428992454630178",
        "3842963720267267286970642336860752782302644680156535061700039388405652129691",
    )
    assert market.accepting_orders is True
    assert market.closed is False


def test_public_clob_client_get_server_time_ms_accepts_scalar_time(monkeypatch):
    client = PublicClobClient()
    monkeypatch.setattr(client._rate_limiter, "wait_turn", lambda: None)
    monkeypatch.setattr(client._client, "get_server_time", lambda: 1774823321)
    result = __import__("asyncio").run(client.get_server_time_ms())
    assert result == 1774823321000


def test_parse_epoch_value_supports_seconds_and_millis():
    assert _parse_epoch_value(1774823321) == 1774823321000
    assert _parse_epoch_value("1774823321000") == 1774823321000
