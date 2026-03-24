from __future__ import annotations

from dataclasses import replace
from time import time

from .models import MarketCatalogEntry, MarketSnapshot, TokenCatalogEntry


REQUIRED_MARKET_FIELDS = ("market_id", "event_id", "slug", "end_date", "market_status")
REQUIRED_TOKEN_FIELDS = ("token_id", "market_id", "event_id", "outcome", "yes_no_side", "end_date")


def validate_catalog(markets: list[MarketCatalogEntry], tokens: list[TokenCatalogEntry]) -> None:
    _validate_required(markets, REQUIRED_MARKET_FIELDS)
    _validate_required(tokens, REQUIRED_TOKEN_FIELDS)
    _validate_unique([market.market_id for market in markets], "market_id")
    _validate_unique([token.token_id for token in tokens], "token_id")


def normalize_market_snapshot(snapshot: MarketSnapshot, stale_after_seconds: int) -> MarketSnapshot:
    is_stale = (time() - snapshot.ts) > stale_after_seconds
    midpoint = round((snapshot.best_bid + snapshot.best_ask) / 2, 6) if snapshot.best_bid and snapshot.best_ask else snapshot.midpoint
    spread = round(snapshot.best_ask - snapshot.best_bid, 6)
    return replace(snapshot, midpoint=midpoint, spread=spread, stale=is_stale)


def _validate_required(rows: list[object], required_fields: tuple[str, ...]) -> None:
    for row in rows:
        for field in required_fields:
            value = getattr(row, field)
            if value is None or value == "":
                raise ValueError(f"Missing required field: {field}")


def _validate_unique(values: list[str], field_name: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"Duplicated {field_name} detected")
