from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import mmaker001.MM001.factory as factory_module
from py_clob_client.exceptions import PolyApiException


def _not_found_error() -> PolyApiException:
    exc = PolyApiException(error_msg={"error": "No orderbook exists for the requested token id"})
    exc.status_code = 404
    return exc


def test_token_has_orderbook_returns_false_for_404() -> None:
    class DummyClient:
        def get_order_book(self, token_id: str):
            if token_id == "missing":
                raise _not_found_error()
            return object()

    assert factory_module._token_has_orderbook(DummyClient(), "yes") is True
    assert factory_module._token_has_orderbook(DummyClient(), "missing") is False


def test_resolve_token_ids_from_remote_market_skips_pairs_without_orderbook(monkeypatch) -> None:
    class DummyClient:
        def __init__(self, host: str) -> None:
            self.host = host

        def get_simplified_markets(self, next_cursor: str = "MA=="):
            return {
                "data": [
                    {
                        "category": "crypto",
                        "market_slug": "btc-up",
                        "tokens": [
                            {"outcome": "Yes", "token_id": "yes-missing"},
                            {"outcome": "No", "token_id": "no-missing"},
                        ],
                    },
                    {
                        "category": "crypto",
                        "market_slug": "eth-up",
                        "tokens": [
                            {"outcome": "Yes", "token_id": "yes-ok"},
                            {"outcome": "No", "token_id": "no-ok"},
                        ],
                    },
                ],
                "next_cursor": "LTE=",
            }

        def get_order_book(self, token_id: str):
            if token_id.endswith("missing"):
                raise _not_found_error()
            return object()

    monkeypatch.setattr(factory_module, "ClobClient", DummyClient)
    monkeypatch.setattr(factory_module.config, "MARKET_INCLUDE_ONLY", ("crypto",))
    monkeypatch.setattr(factory_module.config, "MARKET_EXCLUDED_PREFIXES", ())

    pairs = factory_module._resolve_token_ids_from_remote_market(slug="", max_markets=2)

    assert pairs == [("yes-ok", "no-ok")]
