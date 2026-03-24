from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class CircuitBreakerState:
    triggered: bool
    reason: str


def enforce_position_cap(requested_position_size: float, max_position_size: float, reject_oversize: bool = False) -> float:
    if max_position_size <= 0:
        raise ValueError("max_position_size must be > 0")
    if requested_position_size <= max_position_size:
        return requested_position_size
    if reject_oversize:
        raise ValueError("requested position exceeds max_position_size")
    return max_position_size


def enforce_drawdown_limits(current_equity: float, peak_equity: float, max_drawdown_pct: float) -> bool:
    if peak_equity <= 0:
        return False
    drawdown = (peak_equity - current_equity) / peak_equity
    return drawdown <= max_drawdown_pct


def check_circuit_breaker(
    consecutive_losses: int,
    max_consecutive_losses: int,
    rolling_drawdown_pct: float,
    max_drawdown_pct: float,
    last_n_trade_results: Iterable[float],
    max_losses_in_window: int,
) -> CircuitBreakerState:
    if consecutive_losses >= max_consecutive_losses:
        return CircuitBreakerState(True, "max_consecutive_losses")
    if rolling_drawdown_pct >= max_drawdown_pct:
        return CircuitBreakerState(True, "max_drawdown")
    losses = sum(1 for pnl in last_n_trade_results if pnl < 0)
    if losses >= max_losses_in_window:
        return CircuitBreakerState(True, "losses_in_window")
    return CircuitBreakerState(False, "ok")
