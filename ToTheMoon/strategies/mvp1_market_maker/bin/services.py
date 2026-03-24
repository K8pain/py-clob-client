from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional, Protocol

from ..contracts import (
    MarketCandidate,
    MarketStateSnapshot,
    Mvp1Config,
    QuoteDecision,
    UnderlyingStateSnapshot,
)


class MarketFeedClient(Protocol):
    def fetch_markets(self) -> Iterable[Dict[str, Any]]:
        """Return raw market payloads."""


class UnderlyingFeedClient(Protocol):
    def get_price(self, asset_symbol: str) -> Optional[float]:
        """Return latest underlying spot price."""


@dataclass
class MarketDiscoveryService:
    config: Mvp1Config

    def discover_eligible_markets(self, raw_markets: Iterable[Dict[str, Any]]) -> list[MarketCandidate]:
        eligible: list[MarketCandidate] = []
        for row in raw_markets:
            if not self._is_eligible(row):
                continue
            eligible.append(
                MarketCandidate(
                    market_id=str(row["market_id"]),
                    event_id=str(row.get("event_id", "")),
                    asset_symbol=str(row.get("asset_symbol", "")).upper(),
                    market_open_ts=str(row["market_open_ts"]),
                    market_close_ts=str(row["market_close_ts"]),
                    status=str(row.get("status", "active")),
                    duration_sec=int(row.get("duration_sec", 300)),
                    fees_enabled=bool(row.get("fees_enabled", False)),
                    tick_size=float(row.get("tick_size", 0.01)),
                )
            )
        return eligible

    @staticmethod
    def _is_eligible(row: Dict[str, Any]) -> bool:
        return (
            str(row.get("market_type", "")).lower() == "crypto"
            and int(row.get("duration_sec", 0)) == 300
            and str(row.get("status", "")).lower() == "active"
            and bool(row.get("accepting_orders", False))
            and not bool(row.get("resolved", False))
        )


@dataclass
class MarketStateService:
    config: Mvp1Config

    def build_snapshot(self, market_id: str, book: Dict[str, Any]) -> MarketStateSnapshot:
        best_bid = _as_float(book.get("best_bid"))
        best_ask = _as_float(book.get("best_ask"))
        midpoint = None
        spread_ticks = None
        if best_bid is not None and best_ask is not None:
            midpoint = round((best_bid + best_ask) / 2, 6)
            spread_ticks = int(round((best_ask - best_bid) / max(float(book.get("tick_size", 0.01)), 1e-9)))

        return MarketStateSnapshot(
            market_id=market_id,
            ts=_utc_now(),
            best_bid=best_bid,
            best_ask=best_ask,
            midpoint=midpoint,
            last_trade_price=_as_float(book.get("last_trade_price")),
            spread_ticks=spread_ticks,
            bid_size_top=_as_float(book.get("bid_size_top")),
            ask_size_top=_as_float(book.get("ask_size_top")),
            book_update_count=int(book.get("book_update_count", 0)),
        )


@dataclass
class UnderlyingPriceService:
    config: Mvp1Config

    def build_snapshot(
        self,
        asset_symbol: str,
        price: Optional[float],
        anchor_price: Optional[float],
    ) -> UnderlyingStateSnapshot:
        clean_price = _as_float(price) or 0.0
        if anchor_price and anchor_price > 0:
            bps = ((clean_price - anchor_price) / anchor_price) * 10_000
        else:
            bps = 0.0

        return UnderlyingStateSnapshot(
            asset_symbol=asset_symbol,
            ts=_utc_now(),
            underlying_price=clean_price,
            underlying_return_bps_from_quote_anchor=round(bps, 4),
            data_fresh=price is not None,
        )


@dataclass
class SignalEngine:
    config: Mvp1Config

    def decide(
        self,
        market: MarketCandidate,
        market_state: MarketStateSnapshot,
        underlying_state: UnderlyingStateSnapshot,
        seconds_since_open: int,
        seconds_to_resolution: int,
        inventory_open: float,
    ) -> QuoteDecision:
        if seconds_since_open < self.config.stabilization_delay_sec:
            return self._deny(market.market_id, "stabilizing")
        if market_state.book_update_count < self.config.min_book_updates:
            return self._deny(market.market_id, "not_enough_book_updates")
        if market_state.best_bid is None or market_state.best_ask is None:
            return self._deny(market.market_id, "empty_top_of_book")
        if market_state.spread_ticks is None or market_state.spread_ticks < self.config.min_spread_ticks:
            return self._deny(market.market_id, "spread_too_tight")
        if seconds_to_resolution <= self.config.no_quote_last_sec:
            return self._deny(market.market_id, "no_quote_resolution_window")
        if inventory_open >= self.config.max_inventory_per_market:
            return self._deny(market.market_id, "inventory_limit_market")
        if not underlying_state.data_fresh:
            return self._deny(market.market_id, "underlying_stale")

        seed_fair_value = market_state.midpoint if market_state.midpoint is not None else 0.5
        offset = self.config.quote_offset_ticks * market.tick_size
        yes_quote = max(0.0, min(1.0, round(seed_fair_value - offset, 6)))
        no_quote = max(0.0, min(1.0, round((1 - seed_fair_value) - offset, 6)))

        return QuoteDecision(
            market_id=market.market_id,
            ts=_utc_now(),
            quote_allowed=True,
            seed_fair_value=round(seed_fair_value, 6),
            yes_quote_price=yes_quote,
            no_quote_price=no_quote,
            decision_reason="quote_allowed",
        )

    @staticmethod
    def _deny(market_id: str, reason: str) -> QuoteDecision:
        return QuoteDecision(
            market_id=market_id,
            ts=_utc_now(),
            quote_allowed=False,
            seed_fair_value=None,
            yes_quote_price=None,
            no_quote_price=None,
            decision_reason=reason,
        )


@dataclass
class RiskGateResult:
    allow: bool
    reason: str


@dataclass
class InventoryRiskManager:
    config: Mvp1Config

    def check(
        self,
        market_inventory: float,
        global_inventory: float,
        fill_count_side: int,
    ) -> RiskGateResult:
        if market_inventory >= self.config.max_inventory_per_market:
            return RiskGateResult(False, "market_inventory_limit")
        if global_inventory >= self.config.max_global_inventory:
            return RiskGateResult(False, "global_inventory_limit")
        if fill_count_side >= self.config.max_fills_per_side_per_market:
            return RiskGateResult(False, "fill_limit_per_side")
        return RiskGateResult(True, "risk_pass")


def _as_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
