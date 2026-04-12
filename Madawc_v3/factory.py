from __future__ import annotations

from .bot import MadawcV3Bot


def build_bot(db_path: str | None = None) -> MadawcV3Bot:
    """Factory contract used by launcher. db_path kept for compatibility."""
    _ = db_path
    return MadawcV3Bot()
