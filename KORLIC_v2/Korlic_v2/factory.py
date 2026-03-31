from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
import threading
import time

import httpx

from py_clob_client.client import ClobClient

from .bot import KorlicBot
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
    family_slug_prefix: str = "btc-updown-5m-"

    async def get_active_markets(self) -> list[MarketRecord]:
        return await asyncio.to_thread(self._fetch_active_markets)

    def _fetch_active_markets(self) -> list[MarketRecord]:
        url = f"{self.base_url.rstrip('/')}/events"
        offset = 0
        pages_fetched = 0
        raw_markets: list[dict] = []
        seed_markets = self._fetch_seed_event_markets()
        if seed_markets:
            raw_markets.extend(seed_markets)
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
            raw_markets.extend(page_active_tradeable)
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
            len(raw_markets),
            self.page_limit,
            self.max_pages,
            offset,
        )

        records: list[MarketRecord] = []
        for item in raw_markets:
            record = _to_market_record(item)
            if record is not None and record.active and not record.closed:
                records.append(record)
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
        return int(datetime.now(timezone.utc).timestamp() * 1000)

    async def get_orderbook(self, token_id: str) -> OrderBookSnapshot:
        self._rate_limiter.wait_turn()
        ob = await asyncio.to_thread(self._client.get_order_book, token_id)
        bids = tuple(BookLevel(price=float(level.price), size=float(level.size)) for level in (ob.bids or []))
        asks = tuple(BookLevel(price=float(level.price), size=float(level.size)) for level in (ob.asks or []))
        return OrderBookSnapshot(token_id=token_id, bids=bids, asks=asks, ts_ms=await self.get_server_time_ms())


@dataclass
class EmptyWsClient:
    async def subscribe(self, asset_ids: list[str]) -> None:
        return None

    async def is_healthy(self) -> bool:
        return True


def build_bot(db_path: str) -> KorlicBot:
    storage = KorlicStorage(db_path)
    gamma_base_url = os.getenv("KORLIC_GAMMA_BASE_URL", "https://gamma-api.polymarket.com")
    clob_host = os.getenv("KORLIC_CLOB_HOST", "https://clob.polymarket.com")
    gamma_min_interval = float(os.getenv("KORLIC_GAMMA_MIN_INTERVAL_SECONDS", "0.25"))
    clob_min_interval = float(os.getenv("KORLIC_CLOB_MIN_INTERVAL_SECONDS", "0.05"))
    gamma_page_limit = int(os.getenv("KORLIC_GAMMA_PAGE_LIMIT", "100"))
    gamma_max_pages = int(os.getenv("KORLIC_GAMMA_MAX_PAGES", "0"))
    gamma_seed_slug = os.getenv("KORLIC_GAMMA_SEED_EVENT_SLUG", "btc-updown-5m-1774854300")
    gamma_family_prefix = os.getenv("KORLIC_GAMMA_FAMILY_PREFIX", "btc-updown-5m-")
    signal_entry_price = float(os.getenv("KORLIC_SIGNAL_ENTRY_PRICE", "0.60"))
    signal_entry_seconds = int(os.getenv("KORLIC_SIGNAL_ENTRY_SECONDS", "600"))
    signal_min_depth = float(os.getenv("KORLIC_SIGNAL_MIN_DEPTH", "10.0"))
    signal_min_size = float(os.getenv("KORLIC_SIGNAL_MIN_SIZE", "5.0"))
    signal_max_stake = float(os.getenv("KORLIC_SIGNAL_MAX_STAKE", "25.0"))
    return KorlicBot(
        gamma=PublicGammaClient(
            base_url=gamma_base_url,
            min_interval_seconds=gamma_min_interval,
            page_limit=gamma_page_limit,
            max_pages=gamma_max_pages,
            seed_event_slug=gamma_seed_slug,
            family_slug_prefix=gamma_family_prefix,
        ),
        clob=PublicClobClient(host=clob_host, min_interval_seconds=clob_min_interval),
        ws=EmptyWsClient(),
        storage=storage,
        signal_engine=SignalEngine(
            SignalConfig(
                entry_price=signal_entry_price,
                entry_seconds_threshold=signal_entry_seconds,
                min_operational_size=signal_min_depth,
                min_order_size=signal_min_size,
                max_stake_per_trade=signal_max_stake,
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

    market_id = str(item.get("id") or item.get("market_id") or item.get("condition_id") or item.get("conditionId") or "")
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


def _is_bitcoin_5m_market(item: dict, family_slug_prefix: str = "btc-updown-5m-") -> bool:
    text = " ".join(
        [
            str(item.get("question") or ""),
            str(item.get("title") or ""),
            str(item.get("slug") or item.get("market_slug") or ""),
        ]
    ).lower()
    slug = str(item.get("slug") or item.get("market_slug") or "").lower()
    if family_slug_prefix and slug.startswith(family_slug_prefix.lower()):
        return True
    has_bitcoin = "bitcoin" in text or "btc" in text
    has_5m = "5m" in text or "5 min" in text or "5min" in text
    return has_bitcoin and has_5m


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
