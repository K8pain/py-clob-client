"""Reglas de señal para decidir cuándo abrir una operación en paper trading."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

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
    max_dedupe_entries: int = 4000

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

        # 2) Liquidez visible mínima al precio objetivo.
        visible_depth = book.depth_at_or_better(self.config.entry_price)
        if visible_depth < self.config.min_operational_size:
            return None, "skipped_insufficient_depth"

        # 3) Se publica una limit order fija a 5c sin condicionar al best ask actual.
        budget_for_trade = self.config.max_stake_per_trade
        size_by_cash = budget_for_trade / self.config.entry_price
        if size_by_cash < self.config.min_order_size:
            return None, "skipped_insufficient_funds"

        # 4) Dedupe estricto: una sola orden por token en cada mercado.
        dedupe_key = f"{market.market.market_id}:{token_id}"
        if dedupe_key in self.dedupe:
            return None, "skipped_duplicate_signal"

        self.dedupe.add(dedupe_key)
        self._trim_dedupe()
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

    def prune_to_active_markets(self, active_market_ids: set[str]) -> None:
        if not self.dedupe:
            return
        self.dedupe = {key for key in self.dedupe if key.split(":", 1)[0] in active_market_ids}
        self._trim_dedupe()

    def _trim_dedupe(self) -> None:
        extra = len(self.dedupe) - self.max_dedupe_entries
        if extra <= 0:
            return
        for key in sorted(self.dedupe)[:extra]:
            self.dedupe.discard(key)


class SamplingMode(str, Enum):
    IDLE = "idle"
    WATCH = "watch"
    AGGRESSIVE = "aggressive"


def sampling_mode(seconds_to_end: int, has_open_limit_order: bool) -> SamplingMode:
    # Política mínima de muestreo adaptativo basada en proximidad y estado de orden.
    if has_open_limit_order and seconds_to_end <= 30:
        return SamplingMode.AGGRESSIVE
    if seconds_to_end <= 120:
        return SamplingMode.WATCH
    return SamplingMode.IDLE
