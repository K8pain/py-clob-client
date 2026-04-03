"""Modelos de datos tipados usados en el flujo de trading de KORLIC v2."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class ClassificationStatus(str, Enum):
    CANDIDATE_5M = "candidate_5m"
    SKIPPED_AMBIGUOUS = "skipped_ambiguous_interval"


class OrderStatus(str, Enum):
    OPEN = "OPEN"
    FILLED = "FILLED"
    EXPIRED = "EXPIRED"
    CANCELLED_LOCAL = "CANCELLED_LOCAL"


class PositionStatus(str, Enum):
    OPEN = "OPEN"
    WON = "WON"
    LOST = "LOST"
    UNRESOLVED = "UNRESOLVED"
    PENDING_RESOLUTION = "PENDING_RESOLUTION"


@dataclass(frozen=True)
class MarketRecord:
    market_id: str
    event_id: str
    question: str
    slug: str
    token_ids: tuple[str, ...]
    end_time: datetime
    active: bool
    closed: bool
    accepting_orders: bool
    enable_order_book: bool
    volume_24h: float = 0.0
    liquidity: float = 0.0
    spread: float | None = None
    outcome_labels: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    category: str | None = None
    cadence_hint: str | None = None

    @property
    def is_operable(self) -> bool:
        # Condición mínima para intentar operar un mercado en runtime.
        return self.active and not self.closed and self.accepting_orders and self.enable_order_book


@dataclass(frozen=True)
class ClassifiedMarket:
    market: MarketRecord
    status: ClassificationStatus
    confidence: float
    method: str


@dataclass(frozen=True)
class BookLevel:
    price: float
    size: float


@dataclass(frozen=True)
class OrderBookSnapshot:
    token_id: str
    bids: tuple[BookLevel, ...]
    asks: tuple[BookLevel, ...]
    ts_ms: int

    def best_ask(self) -> float | None:
        if not self.asks:
            return None
        return min(level.price for level in self.asks)

    def depth_at_or_better(self, limit_price: float) -> float:
        # Liquidez visible disponible para compra a precio límite o mejor.
        return sum(level.size for level in self.asks if level.price <= limit_price)


@dataclass(frozen=True)
class SignalCandidate:
    market_id: str
    token_id: str
    price: float
    size: float
    seconds_to_end: int


@dataclass
class PaperOrder:
    paper_order_id: str
    market_id: str
    token_id: str
    limit_price: float
    requested_size: float
    reserved_cash: float
    filled_size: float = 0.0
    status: OrderStatus = OrderStatus.OPEN
    opened_at_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    closed_at_utc: str | None = None
    close_reason: str | None = None

    @property
    def remaining(self) -> float:
        return max(0.0, self.requested_size - self.filled_size)


@dataclass
class PaperPosition:
    market_id: str
    token_id: str
    size: float
    avg_price: float
    status: PositionStatus = PositionStatus.OPEN
    pnl_gross: float | None = None
    pnl_net: float | None = None
    return_pct: float | None = None
    opened_at_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    settled_at_utc: str | None = None


@dataclass
class Ledger:
    cash_available: float
    cash_reserved: float = 0.0
    holdings: dict[str, float] = field(default_factory=dict)

    def reserve(self, amount: float, allow_negative: bool = False) -> bool:
        # Mueve cash de disponible a reservado; opcionalmente permite sobregiro en simulación.
        if not allow_negative and amount > self.cash_available:
            return False
        self.cash_available -= amount
        self.cash_reserved += amount
        return True

    def release(self, amount: float) -> None:
        self.cash_reserved = max(0.0, self.cash_reserved - amount)
        self.cash_available += amount

    def add_holding(self, token_id: str, size: float) -> None:
        self.holdings[token_id] = self.holdings.get(token_id, 0.0) + size


@dataclass(frozen=True)
class StructuredEvent:
    run_id: str
    strategy_version: str
    event_type: str
    decision: str
    reason_code: str
    latency_ms: int
    market_id: str | None = None
    token_id: str | None = None
    payload: dict[str, str | int | float | bool | None] = field(default_factory=dict)
    retry_of_event_id: int | None = None
    ts_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass(frozen=True)
class FillReport:
    fill_size: float
    average_fill_price: float
    remaining_size: float
    remaining_reserved_cash: float
    state: str


@dataclass(frozen=True)
class SettlementReport:
    market_id: str
    token_id: str
    outcome: str
    gross_stake: float
    gross_payoff: float
    net_pnl: float
    roi_percent: float
    holding_duration_seconds: int
    result_class: str
    filled_size: float
    average_fill_price: float
    partial_fill: bool
