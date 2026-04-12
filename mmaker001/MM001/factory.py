from __future__ import annotations

from . import config
from .bot import ClobOrderBookSource, MM001Bot, SimulatedOrderBookSource


def build_bot(db_path: str | None = None) -> MM001Bot:
    """Factory contract used by launcher. db_path kept for compatibility."""
    _ = db_path
    if config.ORDERBOOK_SOURCE == "simulated":
        return MM001Bot(data_source=SimulatedOrderBookSource())
    if not config.YES_TOKEN_ID or not config.NO_TOKEN_ID:
        return MM001Bot(data_source=SimulatedOrderBookSource())
    return MM001Bot(
        data_source=ClobOrderBookSource(
            host=config.CLOB_HOST,
            yes_token_id=config.YES_TOKEN_ID,
            no_token_id=config.NO_TOKEN_ID,
        )
    )
