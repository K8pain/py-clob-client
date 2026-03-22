from __future__ import annotations

from .config import StrategyConfig
from .models import FeatureCandidate, PositionSide, Signal, SignalKind


def build_signal(candidate: FeatureCandidate, config: StrategyConfig) -> Signal | None:
    if candidate.time_to_resolution_seconds < config.min_time_to_resolution_seconds:
        return None
    if candidate.strategy_name == "incoherence" and candidate.gap < config.incoherence_threshold:
        return None
    if candidate.strategy_name == "tail" and candidate.score < config.tail_threshold:
        return None
    side = PositionSide.NO if candidate.side.upper() == "NO" else PositionSide.YES
    kind = SignalKind.INCOHERENCE if candidate.strategy_name == "incoherence" else SignalKind.TAIL
    return Signal(kind=kind, token_id=candidate.token_id, market_id=candidate.market_id, side=side, reason=candidate.reason, score=candidate.score)
