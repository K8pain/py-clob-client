from __future__ import annotations

from .bot import MM001Bot


def build_bot(db_path: str | None = None) -> MM001Bot:
    """Factory contract used by launcher. db_path kept for compatibility."""
    _ = db_path
    return MM001Bot()
