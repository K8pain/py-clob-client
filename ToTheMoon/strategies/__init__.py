"""Trading strategies and strategy packages for ToTheMoon."""

from .mean_reversion import MeanReversionPaperStrategy, StrategyConfig
from .polymarket_mvp import (
    MarketDefinition,
    MarketState,
    PaperTrade,
    ResolutionRecord,
    SignalCandidate,
    StrategyThresholds,
    UnderlyingState,
    build_related_groups,
    compute_reference_probability,
    parse_market_definition,
    score_related_market_incoherence,
    score_tail_premium,
    settle_trade,
    simulate_entry,
)

__all__ = [
    "MeanReversionPaperStrategy",
    "StrategyConfig",
    "MarketDefinition",
    "MarketState",
    "PaperTrade",
    "ResolutionRecord",
    "SignalCandidate",
    "StrategyThresholds",
    "UnderlyingState",
    "build_related_groups",
    "compute_reference_probability",
    "parse_market_definition",
    "score_related_market_incoherence",
    "score_tail_premium",
    "settle_trade",
    "simulate_entry",
]
