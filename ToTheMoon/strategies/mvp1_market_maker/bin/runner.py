from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional

from ..contracts import Mvp1Config, PaperPosition
from .paper_engine import PaperExecutionEngine
from .services import (
    InventoryRiskManager,
    MarketDiscoveryService,
    MarketStateService,
    SignalEngine,
    UnderlyingPriceService,
)
from .storage import TradeStore


@dataclass
class Mvp1MarketMakerBot:
    config: Mvp1Config
    store: TradeStore
    discovery_service: MarketDiscoveryService = field(init=False)
    market_state_service: MarketStateService = field(init=False)
    underlying_service: UnderlyingPriceService = field(init=False)
    signal_engine: SignalEngine = field(init=False)
    risk_manager: InventoryRiskManager = field(init=False)
    paper_engine: PaperExecutionEngine = field(init=False)
    positions: dict[str, PaperPosition] = field(default_factory=dict)
    global_inventory: float = 0.0

    def __post_init__(self) -> None:
        self.discovery_service = MarketDiscoveryService(self.config)
        self.market_state_service = MarketStateService(self.config)
        self.underlying_service = UnderlyingPriceService(self.config)
        self.signal_engine = SignalEngine(self.config)
        self.risk_manager = InventoryRiskManager(self.config)
        self.paper_engine = PaperExecutionEngine()

    def run_cycle(self, raw_markets: Iterable[Dict[str, Any]], books: Dict[str, Dict[str, Any]], spot_prices: Dict[str, float]) -> dict[str, Any]:
        for market in self.discovery_service.discover_eligible_markets(raw_markets):
            self.store.upsert_market(market)
            snapshot = self.market_state_service.build_snapshot(market.market_id, books.get(market.market_id, {}))
            self.store.save_snapshot(snapshot)

            position = self.positions.setdefault(market.market_id, PaperPosition(market_id=market.market_id))
            anchor = position.avg_yes_price if position.yes_size > 0 else None
            underlying_snapshot = self.underlying_service.build_snapshot(
                asset_symbol=market.asset_symbol,
                price=spot_prices.get(market.asset_symbol),
                anchor_price=anchor,
            )

            seconds_since_open = max(0, _seconds_between(_utc_now(), market.market_open_ts))
            seconds_to_resolution = max(0, _seconds_between(market.market_close_ts, _utc_now()))
            inventory_open = position.net_exposure

            decision = self.signal_engine.decide(
                market=market,
                market_state=snapshot,
                underlying_state=underlying_snapshot,
                seconds_since_open=seconds_since_open,
                seconds_to_resolution=seconds_to_resolution,
                inventory_open=inventory_open,
            )
            self.store.save_quote_decision(decision)
            if not decision.quote_allowed:
                continue

            for side, price in (("YES", decision.yes_quote_price), ("NO", decision.no_quote_price)):
                if price is None:
                    continue

                fill_count = position.fill_count_yes if side == "YES" else position.fill_count_no
                risk_gate = self.risk_manager.check(position.net_exposure, self.global_inventory, fill_count)
                if not risk_gate.allow:
                    continue

                order = self.paper_engine.place_order(
                    market_id=market.market_id,
                    side=side,
                    price=price,
                    size=1.0,
                )
                self.store.save_order(order)

                if self.paper_engine.should_fill(order, snapshot):
                    fill = self.paper_engine.fill_order(order, fill_price=price)
                    self.store.save_fill(fill)
                    self.paper_engine.apply_fill(position, fill, size=order.size)
                    self.store.save_order(order)
                    self.global_inventory += order.size

        return self.store.daily_summary()

    def resolve_market(self, market_id: str, outcome: str) -> Optional[float]:
        position = self.positions.get(market_id)
        if position is None:
            return None
        result = self.paper_engine.resolve_market(position=position, outcome=outcome, market_id=market_id)
        self.store.save_market_result(result)
        self.global_inventory = max(0.0, self.global_inventory - position.net_exposure)
        return result.net_pnl


def run_demo_cycle(db_path: str = "ToTheMoon/strategies/mvp1_market_maker/mvp1_demo.sqlite3") -> dict[str, Any]:
    config = Mvp1Config(stabilization_delay_sec=0, min_book_updates=1)
    bot = Mvp1MarketMakerBot(config=config, store=TradeStore(db_path=db_path))
    raw_markets = [
        {
            "market_id": "mkt_btc_001",
            "event_id": "evt_1",
            "asset_symbol": "BTC",
            "market_open_ts": "2026-03-24T00:00:00+00:00",
            "market_close_ts": "2026-03-24T00:05:00+00:00",
            "status": "active",
            "duration_sec": 300,
            "fees_enabled": False,
            "tick_size": 0.01,
            "market_type": "crypto",
            "accepting_orders": True,
            "resolved": False,
        }
    ]
    books = {
        "mkt_btc_001": {
            "best_bid": 0.47,
            "best_ask": 0.53,
            "last_trade_price": 0.49,
            "bid_size_top": 25,
            "ask_size_top": 20,
            "book_update_count": 2,
            "tick_size": 0.01,
        }
    }
    prices = {"BTC": 62000.0}
    return bot.run_cycle(raw_markets=raw_markets, books=books, spot_prices=prices)


def _parse_ts(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


def _seconds_between(later_ts: str, earlier_ts: str) -> int:
    return int((_parse_ts(later_ts) - _parse_ts(earlier_ts)).total_seconds())


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
