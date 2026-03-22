"""Trading strategies for the ToTheMoon paper-trading prototype."""

from .mean_reversion import MeanReversionPaperStrategy, StrategyConfig

__all__ = ["MeanReversionPaperStrategy", "StrategyConfig"]
