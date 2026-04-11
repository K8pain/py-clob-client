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

        best_ask = book.best_ask()
        if best_ask is None:
            return None, "skipped_missing_book"

        # CLOB binary markets are quoted in probability dollars [0.00, 1.00].
        # Example: 60c is represented as 0.60 (not 60).
        # 2) Guardrail de precio: solo toma entradas <= precio objetivo.
        normalized = round(best_ask, 2)
        if normalized > self.config.entry_price:
            return None, "skipped_price_above_entry_threshold"

        # 3) Guardrails de tamaño y liquidez visible.
        budget_for_trade = self.config.max_stake_per_trade
        size_by_cash = budget_for_trade / self.config.entry_price
        if size_by_cash < self.config.min_order_size:
            return None, "skipped_insufficient_funds"

        visible_depth = book.depth_at_or_better(self.config.entry_price)
        if visible_depth < self.config.min_operational_size:
            return None, "skipped_insufficient_depth"

        # 4) Dedupe por bucket temporal para evitar repetir señal sobre el mismo mercado/token.
        dedupe_key = f"{market.market.market_id}:{token_id}:{seconds_to_end // self.config.entry_seconds_threshold}"
        if dedupe_key in self.dedupe:
            return None, "skipped_duplicate_signal"

        self.dedupe.add(dedupe_key)
        self._trim_dedupe()
        size = min(visible_depth, size_by_cash)
        return (
            SignalCandidate(
                market_id=market.market.market_id,
                token_id=token_id,
                price=self.config.entry_price,
                size=size,
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
