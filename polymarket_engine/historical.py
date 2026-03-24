from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Iterable

import httpx

from .models import PricePoint, TokenCatalogEntry
from .storage import CsvStore


class HistoricalDownloader:
    def __init__(
        self,
        base_url: str,
        history_path: str,
        store: CsvStore,
        fetch_json: Callable[[str, dict[str, Any]], Any] | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.history_path = history_path
        self.store = store
        self._fetch_json = fetch_json or self._default_fetch_json

    def download_for_tokens(self, tokens: Iterable[TokenCatalogEntry], interval: str = "1h") -> list[PricePoint]:
        collected: list[PricePoint] = []
        for token in tokens:
            payload = self._fetch_json(
                f"{self.base_url}{self.history_path}",
                {"market": token.token_id, "interval": interval},
            )
            points = parse_price_history(token.token_id, interval, payload)
            relative_path = f"historical/{interval}/{token.token_id}.csv"
            self.store.append_rows(relative_path, [point.to_row() for point in points], unique_by=("token_id", "ts", "interval"))
            collected.extend(points)
        return collected

    @staticmethod
    def _default_fetch_json(url: str, params: dict[str, Any]) -> Any:
        response = httpx.get(url, params=params, timeout=30.0)
        response.raise_for_status()
        return response.json()


def parse_price_history(token_id: str, interval: str, payload: Any) -> list[PricePoint]:
    entries = payload.get("history") if isinstance(payload, dict) else payload
    fetched_at = datetime.now(timezone.utc).isoformat()
    points: list[PricePoint] = []
    for item in entries or []:
        ts = int(item.get("t") or item.get("timestamp") or item.get("ts") or 0)
        price = float(item.get("p") or item.get("price") or 0.0)
        if ts <= 0:
            continue
        points.append(PricePoint(token_id=token_id, ts=ts, price=price, interval=interval, fetched_at=fetched_at))
    return points
