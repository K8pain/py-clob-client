from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import httpx

from ToTheMoon.api import RateLimitPolicy

from .models import MarketCatalogEntry, TokenCatalogEntry


@dataclass
class DiscoveryResult:
    markets: list[MarketCatalogEntry]
    tokens: list[TokenCatalogEntry]


class GammaDiscoveryClient:
    def __init__(
        self,
        base_url: str,
        get_json: Callable[[str], Any] | None = None,
        http_client: Any | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self._get_json = get_json or self._default_get_json
        self._http_client = http_client
        if self._http_client is not None:
            self._http_client.register_limit(RateLimitPolicy("gamma-markets", 250, 10.0))

    def fetch_markets(self, path: str = "/markets") -> list[dict[str, Any]]:
        if self._http_client is not None:
            payload = self._http_client.get(f"{self.base_url}{path}", policy_name="gamma-markets").json()
        else:
            payload = self._get_json(f"{self.base_url}{path}")
        if isinstance(payload, dict) and "data" in payload:
            return list(payload["data"])
        return list(payload)

    @staticmethod
    def _default_get_json(url: str) -> Any:
        response = httpx.get(url, timeout=30.0)
        response.raise_for_status()
        return response.json()


def discover_catalog(raw_markets: list[dict[str, Any]]) -> DiscoveryResult:
    market_rows: list[MarketCatalogEntry] = []
    token_rows: list[TokenCatalogEntry] = []

    for market in raw_markets:
        if not market.get("active", True):
            continue
        market_id = str(market.get("id") or market.get("market_id") or market.get("condition_id") or "")
        event_id = str(market.get("event_id") or market.get("eventId") or "")
        slug = str(market.get("market_slug") or market.get("slug") or "")
        end_date = str(market.get("end_date_iso") or market.get("endDate") or market.get("end_date") or "")
        status = "closed" if market.get("closed") else "active"
        tag = _extract_tag(market)
        if not market_id or not event_id or not slug:
            continue
        market_rows.append(MarketCatalogEntry(market_id, event_id, slug, end_date, status, tag))
        for token in market.get("tokens", []):
            token_id = str(token.get("token_id") or token.get("id") or "")
            outcome = str(token.get("outcome") or "")
            if not token_id or not outcome:
                continue
            token_rows.append(
                TokenCatalogEntry(
                    token_id=token_id,
                    market_id=market_id,
                    event_id=event_id,
                    outcome=outcome,
                    yes_no_side=outcome.upper(),
                    end_date=end_date,
                    active=True,
                )
            )

    return DiscoveryResult(markets=_unique_by_market(market_rows), tokens=_unique_by_token(token_rows))


def _extract_tag(market: dict[str, Any]) -> str:
    tags = market.get("tags") or []
    if isinstance(tags, list) and tags:
        first = tags[0]
        if isinstance(first, dict):
            return str(first.get("slug") or first.get("label") or "")
        return str(first)
    return ""


def _unique_by_market(rows: list[MarketCatalogEntry]) -> list[MarketCatalogEntry]:
    unique: dict[str, MarketCatalogEntry] = {}
    for row in rows:
        unique[row.market_id] = row
    return list(unique.values())


def _unique_by_token(rows: list[TokenCatalogEntry]) -> list[TokenCatalogEntry]:
    unique: dict[str, TokenCatalogEntry] = {}
    for row in rows:
        unique[row.token_id] = row
    return list(unique.values())
