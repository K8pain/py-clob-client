from __future__ import annotations

import json

from . import config
from .bot import ClobOrderBookSource, MM001Bot, MultiClobOrderBookSource
from py_clob_client.client import ClobClient
from py_clob_client.exceptions import PolyApiException


def _is_market_enabled() -> bool:
    market_type = (config.CURRENT_MARKET_CATEGORY or "").strip().lower()
    allowed = set(config.MARKET_INCLUDE_ONLY)
    if allowed and market_type and market_type not in allowed:
        return False
    slug = (config.CURRENT_MARKET_SLUG or "").strip().lower()
    if slug and any(slug.startswith(prefix.lower()) for prefix in config.MARKET_EXCLUDED_PREFIXES):
        return False
    return True


def _extract_yes_no_token_ids(market: dict) -> tuple[str, str] | None:
    tokens = market.get("tokens") or []
    yes_token_id = ""
    no_token_id = ""
    for token in tokens:
        outcome = str(token.get("outcome") or token.get("name") or "").strip().lower()
        token_id = str(token.get("token_id") or token.get("tokenId") or "").strip()
        if not token_id:
            continue
        if outcome == "yes":
            yes_token_id = token_id
        elif outcome == "no":
            no_token_id = token_id
    if yes_token_id and no_token_id:
        return yes_token_id, no_token_id
    parsed_token_ids = _parse_clob_token_ids(market.get("clobTokenIds"))
    if len(parsed_token_ids) >= 2:
        return parsed_token_ids[0], parsed_token_ids[1]
    return None


def _parse_clob_token_ids(value: object) -> tuple[str, ...]:
    if isinstance(value, list):
        return tuple(str(item).strip() for item in value if str(item).strip())
    if not isinstance(value, str) or not value.strip():
        return ()
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return ()
    return tuple(str(item).strip() for item in parsed) if isinstance(parsed, list) else ()


def _is_remote_market_enabled(market: dict) -> bool:
    market_category = str(market.get("category") or "").strip().lower()
    allowed = set(config.MARKET_INCLUDE_ONLY)
    if allowed and market_category and market_category not in allowed:
        return False
    market_slug = str(market.get("market_slug") or market.get("slug") or "").strip().lower()
    if market_slug and any(market_slug.startswith(prefix.lower()) for prefix in config.MARKET_EXCLUDED_PREFIXES):
        return False
    return True


def _resolve_token_ids_from_remote_market(slug: str, max_markets: int) -> list[tuple[str, str]]:
    client = ClobClient(host=config.CLOB_HOST)
    next_cursor = "MA=="
    target_slug = slug.strip().lower()
    resolved_pairs: list[tuple[str, str]] = []
    while next_cursor:
        payload = client.get_simplified_markets(next_cursor=next_cursor)
        markets = payload.get("data") or []
        for market in markets:
            market_slug = str(market.get("market_slug") or market.get("slug") or "").strip().lower()
            if target_slug:
                if market_slug != target_slug:
                    continue
                resolved = _extract_yes_no_token_ids(market)
                if resolved is None:
                    return []
                return [resolved] if _pair_has_orderbooks(client, *resolved) else []
            if not _is_remote_market_enabled(market):
                continue
            resolved = _extract_yes_no_token_ids(market)
            if resolved is not None and _pair_has_orderbooks(client, *resolved):
                resolved_pairs.append(resolved)
                if len(resolved_pairs) >= max_markets:
                    return resolved_pairs
        next_cursor = payload.get("next_cursor")
        if not next_cursor or next_cursor == "LTE=":
            break
    return resolved_pairs


def _pair_has_orderbooks(client: ClobClient, yes_token_id: str, no_token_id: str) -> bool:
    return _token_has_orderbook(client, yes_token_id) and _token_has_orderbook(client, no_token_id)


def _token_has_orderbook(client: ClobClient, token_id: str) -> bool:
    try:
        client.get_order_book(token_id)
        return True
    except PolyApiException as exc:
        if exc.status_code == 404:
            return False
        if _is_transient_orderbook_check_error(exc):
            return False
        raise


def _is_transient_orderbook_check_error(exc: PolyApiException) -> bool:
    if exc.status_code is not None:
        return False
    message = str(exc)
    return any(
        marker in message
        for marker in ("ReadTimeout", "ConnectTimeout", "RemoteProtocolError", "Request exception!")
    )


def build_bot(db_path: str | None = None) -> MM001Bot:
    """Factory contract used by launcher. db_path kept for compatibility."""
    _ = db_path
    if config.ORDERBOOK_SOURCE != "api":
        raise ValueError("MM001 only supports real API orderbook data; simulated orderbook source is disabled")
    yes_token_id = config.YES_TOKEN_ID
    no_token_id = config.NO_TOKEN_ID

    client = ClobClient(host=config.CLOB_HOST)
    has_configured_pair = bool(yes_token_id and no_token_id)
    configured_pair_is_live = has_configured_pair and _pair_has_orderbooks(client, yes_token_id, no_token_id)

    if configured_pair_is_live:
        return MM001Bot(
            data_source=ClobOrderBookSource(
                host=config.CLOB_HOST,
                yes_token_id=yes_token_id,
                no_token_id=no_token_id,
            )
        )

    target_slug = config.CURRENT_MARKET_SLUG if _is_market_enabled() else ""
    resolved_pairs = _resolve_token_ids_from_remote_market(target_slug, max_markets=config.MAX_SIMULTANEOUS_OB)
    if not resolved_pairs:
        if has_configured_pair:
            raise ValueError(
                "MM001 configured token IDs have no orderbook; update MM001_YES_TOKEN_ID/MM001_NO_TOKEN_ID"
            )
        raise ValueError("MM001 api mode requires MM001_YES_TOKEN_ID and MM001_NO_TOKEN_ID")
    if len(resolved_pairs) == 1:
        resolved_yes_token_id, resolved_no_token_id = resolved_pairs[0]
        return MM001Bot(
            data_source=ClobOrderBookSource(
                host=config.CLOB_HOST,
                yes_token_id=resolved_yes_token_id,
                no_token_id=resolved_no_token_id,
            )
        )
    return MM001Bot(
        data_source=MultiClobOrderBookSource(
            sources=[
                ClobOrderBookSource(
                    host=config.CLOB_HOST,
                    yes_token_id=resolved_yes_token_id,
                    no_token_id=resolved_no_token_id,
                )
                for resolved_yes_token_id, resolved_no_token_id in resolved_pairs
            ]
        )
    )
