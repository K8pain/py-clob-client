from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class StrategyName(str, Enum):
    TAIL = "TAIL"
    BONDING = "BONDING"
    SPREAD = "SPREAD"


class SignalDirection(str, Enum):
    YES = "YES"
    NO = "NO"


@dataclass(slots=True, frozen=True)
class MarketSnapshot:
    market_id: str
    question: str
    yes_price: float
    no_price: float
    volume_24h: float
    news_score: float

    @property
    def yes_probability(self) -> float:
        return self.yes_price

    @property
    def implied_spread(self) -> float:
        return self.yes_price + self.no_price


@dataclass(slots=True, frozen=True)
class TradeSignal:
    strategy: StrategyName
    market_id: str
    direction: SignalDirection
    confidence: float
    rationale: str


@dataclass(slots=True, frozen=True)
class PortfolioSnapshot:
    cash: float
    marked_value: float
    open_positions: int
    closed_trades: int
    win_rate: float


@dataclass(slots=True, frozen=True)
class Position:
    market_id: str
    side: SignalDirection
    quantity: float
    average_entry_price: float
    strategy: StrategyName
    opened_at: datetime


@dataclass(slots=True, frozen=True)
class ExecutedTrade:
    market_id: str
    strategy: StrategyName
    side: SignalDirection
    action: str
    quantity: float
    price: float
    pnl: float
    rationale: str
    executed_at: datetime
