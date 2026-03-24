from __future__ import annotations

from collections import deque
from typing import Iterable


def enforce_position_cap(requested_position_size: float, max_position_size: float, mode: str = "reduce") -> float:
    if max_position_size <= 0:
        raise ValueError("max_position_size must be positive")
    if requested_position_size <= max_position_size:
        return requested_position_size
    if mode == "reduce":
        return max_position_size
    if mode == "reject":
        raise ValueError("requested position exceeds max position size")
    raise ValueError("mode must be 'reduce' or 'reject'")


def enforce_drawdown_limits(rolling_drawdown: float, max_daily_loss: float) -> bool:
    return rolling_drawdown >= -abs(max_daily_loss)


def check_circuit_breaker(
    consecutive_losses: int,
    max_consecutive_losses: int,
    rolling_drawdown: float,
    max_drawdown: float,
    last_n_trade_results: Iterable[float],
    max_losses_in_window: int,
    window_size: int,
) -> bool:
    if consecutive_losses >= max_consecutive_losses:
        return True
    if rolling_drawdown <= -abs(max_drawdown):
        return True

    recent = deque(last_n_trade_results, maxlen=window_size)
    losses = sum(1 for result in recent if result < 0)
    return losses >= max_losses_in_window


def enforce_capital_guards(
    requested_position_size: float,
    max_position_size: float,
    max_open_trades: int,
    current_open_trades: int,
    total_exposure: float,
    max_total_exposure: float,
) -> bool:
    if requested_position_size > max_position_size:
        return False
    if current_open_trades >= max_open_trades:
        return False
    if total_exposure > max_total_exposure:
        return False
    return True
