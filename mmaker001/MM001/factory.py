from __future__ import annotations

from . import config
from .bot import ClobOrderBookSource, MM001Bot, SimulatedOrderBookSource


def _is_market_enabled() -> bool:
    market_type = (config.CURRENT_MARKET_CATEGORY or "").strip().lower()
    allowed = set(config.MARKET_INCLUDE_ONLY)
    if allowed and market_type and market_type not in allowed:
        return False
    slug = (config.CURRENT_MARKET_SLUG or "").strip().lower()
    if slug and any(slug.startswith(prefix.lower()) for prefix in config.MARKET_EXCLUDED_PREFIXES):
        return False
    return True


def build_bot(db_path: str | None = None) -> MM001Bot:
    """Factory contract used by launcher. db_path kept for compatibility."""
    _ = db_path
    if config.ORDERBOOK_SOURCE == "simulated":
        return MM001Bot(data_source=SimulatedOrderBookSource())
    if not _is_market_enabled():
        raise ValueError("MM001 api mode requires CURRENT_MARKET_CATEGORY/CURRENT_MARKET_SLUG enabled by filters")
    if not config.YES_TOKEN_ID or not config.NO_TOKEN_ID:
        raise ValueError("MM001 api mode requires MM001_YES_TOKEN_ID and MM001_NO_TOKEN_ID")
    return MM001Bot(
        data_source=ClobOrderBookSource(
            host=config.CLOB_HOST,
            yes_token_id=config.YES_TOKEN_ID,
            no_token_id=config.NO_TOKEN_ID,
        )
    )
