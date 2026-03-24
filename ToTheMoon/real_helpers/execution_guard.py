from typing import Any


def validate_trade_request(requested_position_size: float, max_position_size: float, regime_allowed: bool, circuit_breaker_active: bool) -> tuple[bool, str]:
    if circuit_breaker_active:
        return False, "circuit_breaker_active"
    if requested_position_size > max_position_size:
        return False, "risk_limit_hit"
    if not regime_allowed:
        return False, "unfavorable_regime"
    return True, "ok"


def should_open_trade(regime_allowed: bool, pretrade_checks: dict[str, bool]) -> bool:
    return regime_allowed and all(pretrade_checks.values())


def should_close_trade(current_pnl: float, stop_loss: float, take_profit: float) -> bool:
    return current_pnl <= stop_loss or current_pnl >= take_profit


def build_skip_log(reason: str, context: dict[str, Any]) -> dict[str, Any]:
    return {"event": "trade_skipped", "reason": reason, **context}
