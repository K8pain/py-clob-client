from __future__ import annotations


def apply_slippage(price: float, slippage_bps: float, side: str) -> float:
    multiplier = slippage_bps / 10_000
    if side == "buy":
        return price * (1 + multiplier)
    if side == "sell":
        return price * (1 - multiplier)
    raise ValueError("side must be 'buy' or 'sell'")


def calculate_gross_pnl(entry_price: float, exit_price: float, position_size: float, side: str) -> float:
    if side == "long":
        return (exit_price - entry_price) * position_size
    if side == "short":
        return (entry_price - exit_price) * position_size
    raise ValueError("side must be 'long' or 'short'")


def apply_fees(entry_notional: float, exit_notional: float, fee_rate: float) -> float:
    return (entry_notional + exit_notional) * fee_rate


def calculate_net_pnl(
    entry_price: float,
    exit_price: float,
    position_size: float,
    side: str,
    fee_rate: float,
    slippage_bps: float,
) -> float:
    effective_entry = apply_slippage(entry_price, slippage_bps, "buy" if side == "long" else "sell")
    effective_exit = apply_slippage(exit_price, slippage_bps, "sell" if side == "long" else "buy")
    gross_pnl = calculate_gross_pnl(effective_entry, effective_exit, position_size, side)
    fees = apply_fees(effective_entry * position_size, effective_exit * position_size, fee_rate)
    return gross_pnl - fees


def update_cumulative_pnl(previous_cumulative_pnl: float, net_pnl: float) -> float:
    return previous_cumulative_pnl + net_pnl


def update_compounded_equity(
    previous_equity: float,
    net_pnl: float,
    max_single_trade_return: float = 0.5,
) -> float:
    if previous_equity <= 0:
        raise ValueError("previous_equity must be positive")

    pct_change = net_pnl / previous_equity
    if abs(pct_change) > max_single_trade_return:
        raise ValueError("unrealistic equity jump detected")

    return previous_equity + net_pnl
