"""Fábrica de dependencias para construir una instancia lista del bot."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
import threading
import time

import httpx

from py_clob_client.client import ClobClient

from .bot import KorlicBot, KorlicConfig
from .config import (
    KORLIC_CLOB_HOST,
    KORLIC_CLOB_MIN_INTERVAL_SECONDS,
    KORLIC_CYCLE_STEP_SLEEP_SECONDS,
    KORLIC_GAMMA_BASE_URL,
    KORLIC_GAMMA_MAX_PAGES,
    KORLIC_GAMMA_MIN_INTERVAL_SECONDS,
    KORLIC_GAMMA_PAGE_LIMIT,
    KORLIC_GAMMA_SEED_EVENT_SLUG,
    KORLIC_MARKET_NEAR_EXPIRY_SECONDS,
    KORLIC_MAX_TRADES_PER_MARKET,
    KORLIC_SIGNAL_ENTRY_PRICE,
    KORLIC_SIGNAL_ENTRY_SECONDS,
    KORLIC_SIGNAL_MAX_STAKE,
    KORLIC_SIGNAL_MIN_DEPTH,
    KORLIC_SIGNAL_MIN_SIZE,
    KORLIC_SKIPPED_MARKET_PREFIXES,
)
from .models import BookLevel, MarketRecord, OrderBookSnapshot
from .signal import SignalConfig, SignalEngine
from .storage import KorlicStorage

logger = logging.getLogger("korlic-factory")


@dataclass
class PublicGammaClient:
    base_url: str = "https://gamma-api.polymarket.com"
    timeout_seconds: float = 20.0
    min_interval_seconds: float = 0.25

    def __post_init__(self) -> None:
        self._rate_limiter = _IntervalRateLimiter(min_interval_seconds=self.min_interval_seconds)

    page_limit: int = 100
    max_pages: int = 0
    seed_event_slug: str = "btc-updown-5m-1774854300"
    last_fetch_stats: dict[str, int | bool] = field(default_factory=dict)

    async def get_active_markets(self) -> list[MarketRecord]:
        return await asyncio.to_thread(self._fetch_active_markets)

    def _fetch_active_markets(self) -> list[MarketRecord]:
        # Descarga paginada de eventos/markets para construir el universo operable.
        url = f"{self.base_url.rstrip('/')}/events"
        offset = 0
        pages_fetched = 0
        records_by_market_id: dict[str, MarketRecord] = {}

        def _collect_records(items: list[dict]) -> None:
            for item in items:
                record = _to_market_record(item)
                if record is None or not record.active or record.closed:
                    continue
                records_by_market_id[record.market_id] = record

        seed_markets = self._fetch_seed_event_markets()
        if seed_markets:
            _collect_records(seed_markets)
            logger.debug("gamma.fetch seed_event_markets=%s slug=%s", len(seed_markets), self.seed_event_slug)

        page = 1
        while True:
            if self.max_pages > 0 and page > self.max_pages:
                logger.debug(
                    "gamma.fetch reached_configured_page_cap=true pages=%s max_pages=%s offset=%s",
                    pages_fetched,
                    self.max_pages,
                    offset,
                )
                break
            self._rate_limiter.wait_turn()
            params = {"active": "true", "closed": "false", "limit": str(self.page_limit), "offset": str(offset)}
            logger.debug("gamma.fetch.page_request page=%s offset=%s limit=%s", page, offset, self.page_limit)
            response = httpx.get(url, params=params, timeout=self.timeout_seconds)
            response.raise_for_status()
            payload = response.json()
            candidate = _extract_market_items(payload)
            self._debug_payload_shape(payload, candidate, params)
            page_markets = _flatten_event_markets(candidate)
            pages_fetched += 1
            if not page_markets:
                logger.debug("gamma.fetch page=%s offset=%s empty_page=true", page, offset)
                break

            # Segunda capa de filtro para quedarnos con mercados aún activos/abiertos.
            page_active_tradeable = [
                item
                for item in page_markets
                if _parse_bool(item.get("active"), default=True)
                and not _parse_bool(item.get("closed"), default=False)
            ]
            logger.debug(
                "gamma.fetch page=%s offset=%s page_markets=%s active_open_markets=%s",
                page,
                offset,
                len(page_markets),
                len(page_active_tradeable),
            )
            _collect_records(page_active_tradeable)
            if len(page_markets) < self.page_limit:
                logger.debug(
                    "gamma.fetch page=%s offset=%s reached_last_page=true page_markets=%s page_limit=%s",
                    page,
                    offset,
                    len(page_markets),
                    self.page_limit,
                )
                break
            offset += self.page_limit
            page += 1

        logger.debug(
            "gamma.fetch aggregated pages=%s markets=%s page_limit=%s max_pages=%s final_offset=%s",
            pages_fetched,
            len(records_by_market_id),
            self.page_limit,
            self.max_pages,
            offset,
        )
        self.last_fetch_stats = {
            "pages_fetched": pages_fetched,
            "markets_raw": len(records_by_market_id),
            "final_offset": offset,
            "page_limit": self.page_limit,
            "max_pages": self.max_pages,
        }

        records = list(records_by_market_id.values())
        logger.debug("gamma.fetch records_normalized=%s", len(records))
        return records

    def _fetch_seed_event_markets(self) -> list[dict]:
        if not self.seed_event_slug:
            return []
        self._rate_limiter.wait_turn()
        url = f"{self.base_url.rstrip('/')}/events/slug/{self.seed_event_slug}"
        response = httpx.get(url, timeout=self.timeout_seconds)
        response.raise_for_status()
        payload = response.json()
        items = _extract_market_items(payload)
        return _flatten_event_markets(items)

    @staticmethod
    def _debug_payload_shape(payload: object, candidate: object, params: dict[str, str]) -> None:
        if not logger.isEnabledFor(logging.DEBUG):
            return
        payload_type = type(payload).__name__
        payload_keys = list(payload.keys())[:8] if isinstance(payload, dict) else []
        candidate_count = len(candidate) if isinstance(candidate, list) else 0
        head: dict[str, object] = {}
        if isinstance(candidate, list) and candidate and isinstance(candidate[0], dict):
            first = candidate[0]
            for key in ("id", "conditionId", "question", "slug", "endDate", "endDateIso", "clobTokenIds", "active", "closed"):
                if key in first:
                    head[key] = first[key]
        logger.debug(
            "gamma.payload params=%s payload_type=%s payload_keys=%s candidate_count=%s head=%s",
            params or "none",
            payload_type,
            payload_keys,
            candidate_count,
            head,
        )


@dataclass
class PublicClobClient:
    host: str = "https://clob.polymarket.com"
    min_interval_seconds: float = 0.05

    def __post_init__(self) -> None:
        self._client = ClobClient(host=self.host)
        self._rate_limiter = _IntervalRateLimiter(min_interval_seconds=self.min_interval_seconds)

    async def get_server_time_ms(self) -> int:
        self._rate_limiter.wait_turn()
        server_time = await asyncio.to_thread(self._client.get_server_time)
        if isinstance(server_time, dict):
            timestamp = server_time.get("timestamp")
            if timestamp is not None:
                return int(timestamp)
        elif isinstance(server_time, (int, float, str)):
            parsed = _parse_epoch_value(server_time)
            if parsed is not None:
                return parsed
        # Fallback defensivo: tiempo UTC local si la respuesta no trae timestamp parseable.
        return int(datetime.now(timezone.utc).timestamp() * 1000)

    async def get_orderbook(self, token_id: str) -> OrderBookSnapshot:
        self._rate_limiter.wait_turn()
        ob = await asyncio.to_thread(self._client.get_order_book, token_id)
        bids = tuple(BookLevel(price=float(level.price), size=float(level.size)) for level in (ob.bids or []))
        asks = tuple(BookLevel(price=float(level.price), size=float(level.size)) for level in (ob.asks or []))
        ts_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        return OrderBookSnapshot(token_id=token_id, bids=bids, asks=asks, ts_ms=ts_ms)

    async def get_market_resolution(self, market_id: str) -> tuple[bool, str | None]:
        self._rate_limiter.wait_turn()
        payload = await asyncio.to_thread(self._client.get_market, market_id)
        return _extract_resolution(payload)

    async def get_market_status(self, market_id: str) -> dict[str, str | bool | None]:
        self._rate_limiter.wait_turn()
        payload = await asyncio.to_thread(self._client.get_market, market_id)
        return _extract_market_status(payload)


@dataclass
class EmptyWsClient:
    async def subscribe(self, asset_ids: list[str]) -> None:
        return None

    async def is_healthy(self) -> bool:
        return True


def build_bot(db_path: str) -> KorlicBot:
    # Punto único de ensamblado de dependencias para ejecución local/CLI.
    storage = KorlicStorage(db_path)
    return KorlicBot(
        gamma=PublicGammaClient(
            base_url=KORLIC_GAMMA_BASE_URL,
            min_interval_seconds=KORLIC_GAMMA_MIN_INTERVAL_SECONDS,
            page_limit=KORLIC_GAMMA_PAGE_LIMIT,
            max_pages=KORLIC_GAMMA_MAX_PAGES,
            seed_event_slug=KORLIC_GAMMA_SEED_EVENT_SLUG,
        ),
        clob=PublicClobClient(host=KORLIC_CLOB_HOST, min_interval_seconds=KORLIC_CLOB_MIN_INTERVAL_SECONDS),
        ws=EmptyWsClient(),
        storage=storage,
        config=KorlicConfig(
            watch_window_seconds=KORLIC_MARKET_NEAR_EXPIRY_SECONDS,
            max_trades_per_market=KORLIC_MAX_TRADES_PER_MARKET,
            cycle_step_sleep_seconds=KORLIC_CYCLE_STEP_SLEEP_SECONDS,
            skipped_market_prefixes=KORLIC_SKIPPED_MARKET_PREFIXES,
        ),
        signal_engine=SignalEngine(
            SignalConfig(
                entry_price=KORLIC_SIGNAL_ENTRY_PRICE,
                entry_seconds_threshold=KORLIC_SIGNAL_ENTRY_SECONDS,
                min_operational_size=KORLIC_SIGNAL_MIN_DEPTH,
                min_order_size=KORLIC_SIGNAL_MIN_SIZE,
                max_stake_per_trade=KORLIC_SIGNAL_MAX_STAKE,
            )
        ),
    )


@dataclass
class _IntervalRateLimiter:
    min_interval_seconds: float

    def __post_init__(self) -> None:
        self._lock = threading.Lock()
        self._last_call_at = 0.0

    def wait_turn(self) -> None:
        # Rate limiter simple por intervalo mínimo entre llamadas.
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_call_at
            sleep_for = self.min_interval_seconds - elapsed
            if sleep_for > 0:
                time.sleep(sleep_for)
            self._last_call_at = time.monotonic()


def _to_market_record(item: dict) -> MarketRecord | None:
    if not isinstance(item, dict):
        return None

    end_time_raw = item.get("end_date_iso") or item.get("endDate") or item.get("end_date") or item.get("endDateIso")
    end_time = _parse_end_time(end_time_raw)
    if end_time is None:
        return None

    tokens = item.get("tokens") or []
    if not tokens:
        tokens = item.get("outcomes") or []
    token_ids = tuple(str(t.get("token_id") or t.get("id") or "") for t in tokens if isinstance(t, dict))
    if not token_ids:
        token_ids = tuple(str(t.get("tokenId") or "") for t in tokens if isinstance(t, dict))
    if not token_ids:
        token_ids = _parse_token_ids_from_clob_ids(item.get("clobTokenIds"))
    token_ids = tuple(t for t in token_ids if t)
    if not token_ids:
        return None

    market_id = str(item.get("condition_id") or item.get("conditionId") or item.get("id") or item.get("market_id") or "")
    if not market_id:
        return None

    tags = item.get("tags") or []
    normalized_tags = []
    for tag in tags:
        if isinstance(tag, dict):
            normalized_tags.append(str(tag.get("slug") or tag.get("label") or "").strip())
        else:
            normalized_tags.append(str(tag).strip())

    return MarketRecord(
        market_id=market_id,
        event_id=str(item.get("event_id") or item.get("eventId") or ""),
        question=str(item.get("question") or ""),
        slug=str(item.get("market_slug") or item.get("slug") or ""),
        token_ids=token_ids,
        end_time=end_time,
        active=_parse_bool(item.get("active"), default=True),
        closed=_parse_bool(item.get("closed"), default=False),
        accepting_orders=_parse_bool(item.get("accepting_orders", item.get("acceptingOrders")), default=True),
        enable_order_book=_parse_bool(item.get("enable_order_book", item.get("enableOrderBook")), default=True),
        tags=tuple(tag for tag in normalized_tags if tag),
        category=str(item.get("category")) if item.get("category") is not None else None,
        cadence_hint=str(item.get("cadence_hint")) if item.get("cadence_hint") is not None else None,
    )


def _parse_end_time(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _extract_market_items(payload: object) -> object:
    if not isinstance(payload, dict):
        return payload
    for key in ("data", "markets", "results"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
    return payload


def _flatten_event_markets(payload_items: object) -> list[dict]:
    if not isinstance(payload_items, list):
        return []
    flat_markets: list[dict] = []
    for item in payload_items:
        if not isinstance(item, dict):
            continue
        event_markets = item.get("markets")
        if isinstance(event_markets, list):
            for market in event_markets:
                if isinstance(market, dict):
                    flat_markets.append(market)
            continue
        flat_markets.append(item)
    return flat_markets


def _parse_token_ids_from_clob_ids(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, list):
        return tuple(str(v) for v in value if str(v).strip())
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return ()
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return ()
        if isinstance(parsed, list):
            return tuple(str(v) for v in parsed if str(v).strip())
    return ()


def _extract_resolution(payload: object) -> tuple[bool, str | None]:
    if not isinstance(payload, dict):
        return (False, None)
    resolved = _parse_bool(payload.get("market_resolved"), default=False) or _parse_bool(payload.get("resolved"), default=False)
    winner_token_id: str | None = None
    tokens = payload.get("tokens") or []
    for token in tokens:
        if not isinstance(token, dict):
            continue
        is_winner = _parse_bool(token.get("winner"), default=False) or _parse_bool(token.get("is_winner"), default=False)
        if is_winner:
            winner_token_id = str(token.get("token_id") or token.get("tokenId") or token.get("id") or "")
            winner_token_id = winner_token_id or None
            resolved = True
            break
    if winner_token_id is None:
        inferred_winner = _infer_winner_token_id(tokens=tokens, outcome_prices=payload.get("outcomePrices"))
        if inferred_winner is not None:
            winner_token_id = inferred_winner
            resolved = True
    return (resolved, winner_token_id)


def _extract_market_status(payload: object) -> dict[str, str | bool | None]:
    if not isinstance(payload, dict):
        return {}
    return {
        "closed": _parse_bool(payload.get("closed"), default=False),
        "resolved": _parse_bool(payload.get("market_resolved"), default=False) or _parse_bool(payload.get("resolved"), default=False),
        "closed_time": str(payload.get("closedTime") or payload.get("closed_time") or "") or None,
        "resolved_by": str(payload.get("resolvedBy") or payload.get("resolved_by") or "") or None,
        "uma_resolution_status": str(payload.get("umaResolutionStatus") or payload.get("uma_resolution_status") or "").strip().lower() or None,
    }


def _infer_winner_token_id(tokens: list[object], outcome_prices: object) -> str | None:
    if not isinstance(tokens, list):
        return None
    parsed_prices = _parse_outcome_prices(outcome_prices)
    if not parsed_prices:
        return None
    for index, price in enumerate(parsed_prices):
        if abs(price - 1.0) > 1e-9:
            continue
        if index >= len(tokens):
            continue
        token = tokens[index]
        if not isinstance(token, dict):
            continue
        token_id = str(token.get("token_id") or token.get("tokenId") or token.get("id") or "").strip()
        if token_id:
            return token_id
    return None


def _parse_outcome_prices(value: object) -> list[float]:
    if value is None:
        return []
    raw_values: list[object]
    if isinstance(value, list):
        raw_values = value
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return []
        if not isinstance(parsed, list):
            return []
        raw_values = parsed
    else:
        return []
    parsed_prices: list[float] = []
    for raw in raw_values:
        try:
            parsed_prices.append(float(raw))
        except (TypeError, ValueError):
            return []
    return parsed_prices


def _parse_epoch_value(value: int | float | str) -> int | None:
    try:
        as_float = float(value)
    except (TypeError, ValueError):
        return None
    as_int = int(as_float)
    # Heurística mínima: segundos UNIX => convertir a ms; ms UNIX => usar directo.
    if as_int < 10_000_000_000:
        return as_int * 1000
    return as_int


def _parse_bool(value: object, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y"}:
            return True
        if normalized in {"false", "0", "no", "n"}:
            return False
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    return default
