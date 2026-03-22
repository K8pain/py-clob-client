from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class MarketLifecycleState(str, Enum):
    NEW = "NEW"
    STABILIZING = "STABILIZING"
    READY_TO_QUOTE = "READY_TO_QUOTE"
    QUOTING = "QUOTING"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    NO_QUOTE_WINDOW = "NO_QUOTE_WINDOW"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


class SystemState(str, Enum):
    RUNNING = "RUNNING"
    DEGRADED = "DEGRADED"
    RECONNECTING = "RECONNECTING"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"


class PaperOrderStatus(str, Enum):
    RESTING = "RESTING"
    CANCELLED = "CANCELLED"
    FILLED = "FILLED"
    EXPIRED = "EXPIRED"


@dataclass(frozen=True)
class Mvp1Config:
    stabilization_delay_sec: int = 20
    min_book_updates: int = 3
    quote_offset_ticks: int = 1
    min_spread_ticks: int = 2
    no_quote_last_sec: int = 30
    cancel_on_move_bps: int = 10
    max_inventory_per_market: float = 1.0
    max_global_inventory: float = 5.0
    max_fills_per_side_per_market: int = 1
    paper_slippage_mode: str = "conservative"
    fill_assumption_mode: str = "conservative_fill_mode"
    fee_model_enabled: bool = False
    maker_rebate_enabled: bool = False
    log_level: str = "INFO"
    persist_book_snapshots: bool = True
    persist_quote_events: bool = True
    persist_fill_events: bool = True


@dataclass(frozen=True)
class MarketCandidate:
    market_id: str
    event_id: str
    asset_symbol: str
    market_open_ts: str
    market_close_ts: str
    status: str
    duration_sec: int
    fees_enabled: bool
    tick_size: float


@dataclass(frozen=True)
class MarketStateSnapshot:
    market_id: str
    ts: str
    best_bid: Optional[float]
    best_ask: Optional[float]
    midpoint: Optional[float]
    last_trade_price: Optional[float]
    spread_ticks: Optional[int]
    bid_size_top: Optional[float]
    ask_size_top: Optional[float]
    book_update_count: int


@dataclass(frozen=True)
class UnderlyingStateSnapshot:
    asset_symbol: str
    ts: str
    underlying_price: float
    underlying_return_bps_from_quote_anchor: float
    data_fresh: bool


@dataclass(frozen=True)
class QuoteDecision:
    market_id: str
    ts: str
    quote_allowed: bool
    seed_fair_value: Optional[float]
    yes_quote_price: Optional[float]
    no_quote_price: Optional[float]
    decision_reason: str


@dataclass
class PaperOrder:
    order_id: str
    market_id: str
    side: str
    price: float
    size: float
    status: PaperOrderStatus
    created_ts: str
    cancelled_ts: Optional[str] = None
    filled_ts: Optional[str] = None
    cancel_reason: Optional[str] = None


@dataclass
class PaperPosition:
    market_id: str
    yes_size: float = 0.0
    no_size: float = 0.0
    avg_yes_price: float = 0.0
    avg_no_price: float = 0.0
    net_exposure: float = 0.0
    resolved_pnl: float = 0.0
    status: MarketLifecycleState = MarketLifecycleState.NEW
    fill_count_yes: int = 0
    fill_count_no: int = 0
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class MarketResult:
    market_id: str
    resolved_outcome: str
    resolution_ts: str
    gross_pnl: float
    fees: float
    rebates: float
    net_pnl: float
