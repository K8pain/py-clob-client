from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any


class SignalKind(str, Enum):
    INCOHERENCE = "incoherence"
    TAIL = "tail"


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class PositionSide(str, Enum):
    YES = "YES"
    NO = "NO"


class ExecutionMode(str, Enum):
    PAPER = "paper"
    REAL = "real"


@dataclass(frozen=True)
class MarketCatalogEntry:
    market_id: str
    event_id: str
    slug: str
    end_date: str
    market_status: str
    tag: str = ""

    def to_row(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TokenCatalogEntry:
    token_id: str
    market_id: str
    event_id: str
    outcome: str
    yes_no_side: str
    end_date: str
    active: bool = True

    def to_row(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PricePoint:
    token_id: str
    ts: int
    price: float
    interval: str
    fetched_at: str

    def to_row(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MarketSnapshot:
    token_id: str
    best_bid: float
    best_ask: float
    midpoint: float
    spread: float
    last_trade: float
    ts: int
    stale: bool = False


@dataclass(frozen=True)
class FeatureCandidate:
    strategy_name: str
    token_id: str
    market_id: str
    side: str
    score: float
    gap: float
    reason: str
    time_to_resolution_seconds: int


@dataclass(frozen=True)
class Signal:
    kind: SignalKind
    token_id: str
    market_id: str
    side: PositionSide
    reason: str
    score: float


@dataclass(frozen=True)
class RiskDecision:
    approved: bool
    reason: str


@dataclass(frozen=True)
class OrderRequest:
    token_id: str
    side: OrderSide
    price: float
    size: float
    market_id: str
    strategy_name: str
    signal_reason: str


@dataclass(frozen=True)
class OrderEvent:
    order_id: str
    token_id: str
    market_id: str
    status: str
    side: str
    price: float
    size: float
    created_at: str
    reason: str

    def to_row(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FillRecord:
    fill_id: str
    order_id: str
    token_id: str
    price: float
    size: float
    fee: float
    ts: str

    def to_row(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Position:
    token_id: str
    market_id: str
    side: PositionSide
    net_qty: float = 0.0
    avg_cost: float = 0.0
    realized_pnl: float = 0.0

    def to_row(self) -> dict[str, Any]:
        return asdict(self)
