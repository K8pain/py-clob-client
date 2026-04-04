"""Reglas de señal para decidir cuándo abrir una operación en paper trading."""

from __future__ import annotations

from dataclasses import dataclass, field

from .config import (
    DEFAULT_SIGNAL_ENTRY_PRICE,
    DEFAULT_SIGNAL_ENTRY_SECONDS,
    DEFAULT_SIGNAL_MAX_STAKE,
    DEFAULT_SIGNAL_MIN_DEPTH,
    DEFAULT_SIGNAL_MIN_SIZE,
)
from .models import ClassifiedMarket, OrderBookSnapshot, SignalCandidate
from .runtime import TimeSync


@dataclass
class SignalConfig:
    entry_price: float = DEFAULT_SIGNAL_ENTRY_PRICE
    entry_seconds_threshold: int = DEFAULT_SIGNAL_ENTRY_SECONDS
    min_operational_size: float = DEFAULT_SIGNAL_MIN_DEPTH
    min_order_size: float = DEFAULT_SIGNAL_MIN_SIZE
    max_stake_per_trade: float = DEFAULT_SIGNAL_MAX_STAKE


@dataclass
class SignalEngine:
    config: SignalConfig
    dedupe: set[str] = field(default_factory=set)

    def evaluate(
        self,
        market: ClassifiedMarket,
        token_id: str,
        book: OrderBookSnapshot,
        end_epoch_ms: int,
        time_sync: TimeSync,
        available_cash: float,
    ) -> tuple[SignalCandidate | None, str]:
        # 1) Guardrail temporal: solo operar cerca del vencimiento.
        seconds_to_end = time_sync.seconds_to(end_epoch_ms)
        if seconds_to_end > self.config.entry_seconds_threshold:
            return None, "skipped_outside_entry_window"

        # 2) Se publica una limit order fija a 5c sin condicionar al best ask actual.
        budget_for_trade = self.config.max_stake_per_trade
        size_by_cash = budget_for_trade / self.config.entry_price
        if size_by_cash < self.config.min_order_size:
            return None, "skipped_insufficient_funds"

        # 3) Dedupe estricto: una sola orden por token en cada mercado.
        dedupe_key = f"{market.market.market_id}:{token_id}"
        if dedupe_key in self.dedupe:
            return None, "skipped_duplicate_signal"

        self.dedupe.add(dedupe_key)
        return (
            SignalCandidate(
                market_id=market.market.market_id,
                token_id=token_id,
                price=self.config.entry_price,
                size=size_by_cash,
                seconds_to_end=seconds_to_end,
            ),
            "signal_candidate",
        )
