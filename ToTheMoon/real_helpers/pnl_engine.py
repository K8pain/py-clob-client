from dataclasses import dataclass


@dataclass(frozen=True)
class PnlBreakdown:
    gross_pnl: float
    slippage_cost: float
    fees: float
    net_pnl: float


def calculate_gross_pnl(entry_price: float, exit_price: float, position_size: float) -> float:
    return (exit_price - entry_price) * position_size


def apply_slippage(gross_pnl: float, slippage_rate: float) -> float:
    return abs(gross_pnl) * max(slippage_rate, 0.0)


def apply_fees(notional_value: float, fee_rate: float) -> float:
    return abs(notional_value) * max(fee_rate, 0.0)


def calculate_net_pnl(
    entry_price: float,
    exit_price: float,
    position_size: float,
    fee_rate: float,
    slippage_rate: float,
) -> PnlBreakdown:
    gross_pnl = calculate_gross_pnl(entry_price, exit_price, position_size)
    notional = (abs(entry_price) + abs(exit_price)) * position_size
    fees = apply_fees(notional, fee_rate)
    slippage_cost = apply_slippage(gross_pnl, slippage_rate)
    net_pnl = gross_pnl - fees - slippage_cost
    return PnlBreakdown(gross_pnl, slippage_cost, fees, net_pnl)


def update_compounded_equity(current_equity: float, net_pnl: float) -> float:
    return current_equity + net_pnl


def validate_equity_jump(previous_equity: float, new_equity: float, max_jump_pct: float = 0.5) -> bool:
    if previous_equity <= 0:
        return False
    jump = (new_equity - previous_equity) / previous_equity
    return jump <= max_jump_pct
