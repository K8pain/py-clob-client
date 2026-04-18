from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Side = Literal["YES", "NO"]


@dataclass
class MarketTick:
    cycle: int
    yes_mid: float
    no_mid: float
    spread: float
    market_id: str = "SIMULATED_MM001"


@dataclass
class Inventory:
    yes: float = 0.0
    no: float = 0.0
    cash: float = 10_000.0

    @property
    def net_yes(self) -> float:
        return self.yes - self.no


@dataclass
class Fill:
    side: Side
    qty: float
    price: float
    maker: bool


@dataclass
class BotMetrics:
    spread_pnl: float = 0.0
    merge_pnl: float = 0.0
    split_sell_pnl: float = 0.0
    taker_fees: float = 0.0
    rebate_income: float = 0.0
    reward_income: float = 0.0
    directional_mtm: float = 0.0
    taker_trades: int = 0
    fill_count: int = 0
    executed_notional: float = 0.0
    closed_cycle_count: int = 0
    winning_cycle_count: int = 0
    losing_cycle_count: int = 0
    breakeven_cycle_count: int = 0
    winning_cycle_pnl_sum: float = 0.0
    losing_cycle_pnl_sum: float = 0.0
    redeem_count: int = 0
    events: list[str] = field(default_factory=list)

    @property
    def total_realized(self) -> float:
        return self.spread_pnl + self.merge_pnl + self.split_sell_pnl - self.taker_fees + self.rebate_income + self.reward_income
