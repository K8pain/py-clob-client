from __future__ import annotations


def validate_trade_request(
    requested_position_size: float,
    max_position_size: float,
    max_open_trades: int,
    current_open_trades: int,
    circuit_breaker_active: bool,
) -> tuple[bool, str]:
    if circuit_breaker_active:
        return False, "circuit_breaker_active"
    if requested_position_size > max_position_size:
        return False, "risk_limit_hit"
    if current_open_trades >= max_open_trades:
        return False, "max_open_trades_hit"
    return True, "ok"


def should_open_trade(regime_is_favorable: bool, risk_checks_passed: bool, circuit_breaker_active: bool) -> bool:
    return regime_is_favorable and risk_checks_passed and not circuit_breaker_active


def should_close_trade(stop_loss_hit: bool, take_profit_hit: bool, circuit_breaker_active: bool) -> bool:
    return stop_loss_hit or take_profit_hit or circuit_breaker_active


def track_skip_reason(skip_reason_counts: dict[str, int], reason: str) -> dict[str, int]:
    new_counts = dict(skip_reason_counts)
    new_counts[reason] = new_counts.get(reason, 0) + 1
    return new_counts
