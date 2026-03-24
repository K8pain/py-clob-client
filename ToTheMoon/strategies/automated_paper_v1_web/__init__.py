"""Automated paper trading strategy bundle v1 (web-oriented)."""

from .mean_reversion import MeanReversionPaperStrategy, StrategyConfig

__all__ = ["MeanReversionPaperStrategy", "StrategyConfig"]
