"""Orquestador principal del ciclo de mercado, señal y ejecución del bot."""

from __future__ import annotations

import asyncio
import json
import logging
import random
import time
import uuid
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Protocol

from .discovery import DiscoveryEngine, DiscoveryState, MarketClassifier
from .models import (
    ClassificationStatus,
    ClassifiedMarket,
    Ledger,
    MarketRecord,
    OrderBookSnapshot,
    PaperOrder,
    PaperPosition,
    PositionStatus,
    StructuredEvent,
)
from .paper import PaperExecutionEngine
from .runtime import TimeSync
from .signal import SignalConfig, SignalEngine
from .storage import KorlicStorage

logger = logging.getLogger("korlic-bot")
business_logger = logging.getLogger("korlic-business")


class GammaClient(Protocol):
    async def get_active_markets(self) -> list[MarketRecord]: ...


class ClobClient(Protocol):
    async def get_server_time_ms(self) -> int: ...

    async def get_orderbook(self, token_id: str) -> OrderBookSnapshot: ...

    async def get_market_resolution(self, market_id: str) -> tuple[bool, str | None]: ...

    async def get_market_status(self, market_id: str) -> dict[str, str | bool | None]: ...


class WsClient(Protocol):
    async def subscribe(self, asset_ids: list[str]) -> None: ...

    async def is_healthy(self) -> bool: ...


@dataclass
class KorlicConfig:
    watch_window_seconds: int = 600
    retry_max: int = 4
    retry_base_ms: int = 100
    retry_jitter_ms: int = 250
    strategy_version: str = "korlic-v1"
    order_expiry_seconds: int = 5


@dataclass
class KorlicBot:
    gamma: GammaClient
    clob: ClobClient
    ws: WsClient
    storage: KorlicStorage
    config: KorlicConfig = field(default_factory=KorlicConfig)
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    classifier: MarketClassifier = field(default_factory=MarketClassifier)
    time_sync: TimeSync = field(default_factory=TimeSync)
    signal_engine: SignalEngine = field(default_factory=lambda: SignalEngine(SignalConfig()))
    ledger: Ledger = field(default_factory=lambda: Ledger(cash_available=1000.0))
    cycle_number: int = 0
    last_logged_cumulative_realized_pnl: float | None = None

    def __post_init__(self) -> None:
        self.discovery = DiscoveryEngine(classifier=self.classifier, parser_version="korlic-v1")
        self.paper = PaperExecutionEngine(ledger=self.ledger)
        self.universe = DiscoveryState(markets={}, parser_version="korlic-v1", discovered_at=datetime.utcnow().isoformat())

    async def run_cycle(self) -> None:
        # Ciclo principal: sincroniza tiempo, descubre universo, evalúa señales y ejecuta paper trading.
        self.cycle_number += 1
        started = time.perf_counter()
        logger.debug("cycle.start run_id=%s cycle_number=%s", self.run_id, self.cycle_number)
        server_time = await self._retry(self.clob.get_server_time_ms, "degraded_clob_rest")
        if server_time is not None:
            self.time_sync.sync(server_time)
            logger.debug("cycle.time_sync server_time_ms=%s", server_time)

        markets = await self._retry(self.gamma.get_active_markets, "degraded_gamma")
        if markets is None:
            logger.debug("cycle.discovery skipped markets_fetch_failed")
            return

        logger.debug("cycle.discovery active_markets=%s", len(markets))
        gamma_fetch_stats = getattr(self.gamma, "last_fetch_stats", None)
        if isinstance(gamma_fetch_stats, dict) and gamma_fetch_stats:
            logger.debug(
                "cycle.discovery.pagination pages_fetched=%s markets_raw=%s page_limit=%s max_pages=%s final_offset=%s",
                gamma_fetch_stats.get("pages_fetched", 0),
                gamma_fetch_stats.get("markets_raw", 0),
                gamma_fetch_stats.get("page_limit", 0),
                gamma_fetch_stats.get("max_pages", 0),
                gamma_fetch_stats.get("final_offset", 0),
            )
        operable_markets = sum(1 for market in markets if market.is_operable)
        crypto_markets = sum(1 for market in markets if self.classifier.is_crypto(market))
        near_expiry_operable_markets = 0
        filter_stats: dict[str, int] = {
            "inactive": 0,
            "closed": 0,
            "not_accepting_orders": 0,
            "orderbook_disabled": 0,
            "non_crypto": 0,
            "outside_watch_window": 0,
            "low_confidence": 0,
        }
        candidate_pool: list[ClassifiedMarket] = []
        for market in markets:
            if not market.active:
                filter_stats["inactive"] += 1
            if market.closed:
                filter_stats["closed"] += 1
            if not market.accepting_orders:
                filter_stats["not_accepting_orders"] += 1
            if not market.enable_order_book:
                filter_stats["orderbook_disabled"] += 1
            if not market.is_operable:
                continue
            classified = self.classifier.classify(market)
            seconds_to_end = self.time_sync.seconds_to(int(market.end_time.timestamp() * 1000))
            if 0 < seconds_to_end <= self.config.watch_window_seconds:
                near_expiry_operable_markets += 1
            else:
                filter_stats["outside_watch_window"] += 1
                continue
            if classified.status.value == "candidate_5m" and classified.confidence < self.classifier.min_confidence:
                filter_stats["low_confidence"] += 1
            candidate_pool.append(
                # Se fuerza entrada al pool vigilado para no perder mercados cerca de expiración.
                ClassifiedMarket(
                    market=market,
                    status=classified.status if classified.status == ClassificationStatus.CANDIDATE_5M else ClassificationStatus.CANDIDATE_5M,
                    confidence=classified.confidence if classified.confidence > 0 else 0.01,
                    method=classified.method if classified.status == ClassificationStatus.CANDIDATE_5M else f"{classified.method}_forced_watch",
                )
            )
        logger.debug(
            "cycle.discovery.filters operable=%s crypto=%s near_expiry_operable=%s watch_window_seconds=%s inactive=%s closed=%s not_accepting_orders=%s orderbook_disabled=%s non_crypto=%s outside_watch_window=%s low_confidence=%s",
            operable_markets,
            crypto_markets,
            near_expiry_operable_markets,
            self.config.watch_window_seconds,
            filter_stats["inactive"],
            filter_stats["closed"],
            filter_stats["not_accepting_orders"],
            filter_stats["orderbook_disabled"],
            filter_stats["non_crypto"],
            filter_stats["outside_watch_window"],
            filter_stats["low_confidence"],
        )
        if operable_markets == 0:
            sample = [
                {
                    "market_id": market.market_id,
                    "active": market.active,
                    "closed": market.closed,
                    "accepting_orders": market.accepting_orders,
                    "enable_order_book": market.enable_order_book,
                    "slug": market.slug,
                }
                for market in markets[:5]
            ]
            logger.debug("cycle.discovery.no_operable sample=%s", sample)
        fresh = DiscoveryState(
            markets={item.market.market_id: item for item in candidate_pool},
            parser_version=self.discovery.parser_version,
            discovered_at=datetime.now(timezone.utc).isoformat(),
        )
        self.universe = self.discovery.refresh_universe(self.universe, fresh)
        watchlist = self._build_watchlist(list(self.universe.markets.values()))
        logger.debug("cycle.watchlist near_expiry_markets=%s", len(watchlist))
        token_ids = sorted({token for item in watchlist for token in item.market.token_ids})
        await self._ensure_subscription(token_ids)
        logger.debug("cycle.subscription token_ids=%s", len(token_ids))
        orderbook_stats: dict[str, float] = {
            "samples": 0,
            "bid_levels": 0,
            "ask_levels": 0,
            "depth_at_entry": 0.0,
        }
        signal_stats: dict[str, int] = {
            "evaluated": 0,
            "triggered": 0,
            "outside_entry_window": 0,
        }
        execution_stats: dict[str, int] = {
            "orders_opened": 0,
            "orders_filled": 0,
            "orders_partial": 0,
            "orders_expired": 0,
            "trades_taken": 0,
        }

        for market in watchlist:
            if not market.market.accepting_orders or not market.market.active or market.market.closed:
                logger.debug(
                    "cycle.market.skip market_id=%s accepting=%s active=%s closed=%s",
                    market.market.market_id,
                    market.market.accepting_orders,
                    market.market.active,
                    market.market.closed,
                )
                continue
            logger.debug("cycle.market.evaluate market_id=%s", market.market.market_id)
            for token_id in market.market.token_ids:
                end_epoch_ms = int(market.market.end_time.timestamp() * 1000)
                book = await self._retry(lambda tid=token_id: self.clob.get_orderbook(tid), "degraded_clob_rest")
                if book is None:
                    logger.debug("cycle.token.skip market_id=%s token_id=%s reason=missing_orderbook", market.market.market_id, token_id)
                    continue
                best_bid = max((b.price for b in book.bids), default=None)
                best_ask = book.best_ask()
                logger.debug(
                    "cycle.orderbook market_id=%s best_bid=%s best_ask=%s bids=%s asks=%s depth_at_entry=%s ts_ms=%s",
                    market.market.market_id,
                    best_bid,
                    best_ask,
                    len(book.bids),
                    len(book.asks),
                    book.depth_at_or_better(self.signal_engine.config.entry_price),
                    book.ts_ms,
                )
                orderbook_stats["samples"] += 1
                orderbook_stats["bid_levels"] += len(book.bids)
                orderbook_stats["ask_levels"] += len(book.asks)
                orderbook_stats["depth_at_entry"] += book.depth_at_or_better(self.signal_engine.config.entry_price)
                signal, reason = self.signal_engine.evaluate(
                    market=market,
                    token_id=token_id,
                    book=book,
                    end_epoch_ms=end_epoch_ms,
                    time_sync=self.time_sync,
                    available_cash=self.ledger.cash_available,
                )
                seconds_to_end = self.time_sync.seconds_to(end_epoch_ms)
                signal_stats["evaluated"] += 1
                if signal is not None:
                    signal_stats["triggered"] += 1
                    logger.debug(
                        "cycle.signal market_id=%s market_slug=%s seconds_to_end=%s signal=%s reason=%s",
                        market.market.market_id,
                        market.market.slug,
                        seconds_to_end,
                        True,
                        reason,
                    )
                elif reason == "skipped_outside_entry_window":
                    signal_stats["outside_entry_window"] += 1
                self._log_decision(
                    market=market,
                    token_id=token_id,
                    event_type="SIGNAL_DETECTED" if signal else "NO_TRADE",
                    decision="signaled" if signal else "ignored",
                    reason=reason,
                    started=started,
                    payload={
                        "seconds_to_end": seconds_to_end,
                        "best_bid": best_bid,
                        "best_ask": best_ask,
                        "visible_depth_at_target": book.depth_at_or_better(self.signal_engine.config.entry_price),
                        "signal_price": self.signal_engine.config.entry_price,
                        "market_slug": market.market.slug,
                        "market_title": market.market.question,
                        "side": "BUY",
                    },
                )
                if signal is None:
                    continue
                # Paper flow: crear orden pseudo-real y simular llenado contra libro visible.
                order = self.paper.create_order(signal)
                if order is None:
                    logger.debug(
                        "cycle.order.skip market_id=%s token_id=%s reason=paper_engine_rejected",
                        market.market.market_id,
                        token_id,
                    )
                    continue
                logger.debug(
                    "cycle.order.open market_id=%s market_slug=%s token_id=%s order_id=%s size=%s price=%s side=BUY",
                    market.market.market_id,
                    market.market.slug,
                    token_id,
                    order.paper_order_id,
                    order.requested_size,
                    order.limit_price,
                )
                execution_stats["orders_opened"] += 1
                execution_stats["trades_taken"] += 1
                self._log_decision(
                    market=market,
                    token_id=token_id,
                    event_type="PSEUDO_ORDER_OPENED",
                    decision="pseudo-traded",
                    reason="accepted_by_paper_engine",
                    started=started,
                    payload={
                        "pseudo_order_id": order.paper_order_id,
                        "limit_price": order.limit_price,
                        "requested_size": order.requested_size,
                        "reserved_cash": order.reserved_cash,
                        "order_open_timestamp_utc": order.opened_at_utc,
                        "rationale": "signal_candidate",
                        "side": "BUY",
                    },
                )
                before = self.paper.positions.get(market.market.market_id)
                filled = self.paper.try_fill(order, book)
                report = self.paper.last_fill_report
                if filled > 0 and report is not None:
                    logger.debug(
                        "cycle.order.fill market_id=%s market_slug=%s order_id=%s fill_size=%s avg_fill_price=%s remaining=%s state=%s",
                        market.market.market_id,
                        market.market.slug,
                        order.paper_order_id,
                        report.fill_size,
                        report.average_fill_price,
                        report.remaining_size,
                        report.state,
                    )
                    if report.state == "PSEUDO_ORDER_FILLED":
                        execution_stats["orders_filled"] += 1
                    else:
                        execution_stats["orders_partial"] += 1
                    self._log_decision(
                        market=market,
                        token_id=token_id,
                        event_type=report.state,
                        decision="filled" if report.state == "PSEUDO_ORDER_FILLED" else "partial_fill",
                        reason="visible_depth_match",
                        started=started,
                        payload={
                            "pseudo_order_id": order.paper_order_id,
                            "fill_size": report.fill_size,
                            "average_fill_price": report.average_fill_price,
                            "remaining_size": report.remaining_size,
                            "remaining_reserved_cash": report.remaining_reserved_cash,
                            "requested_size": order.requested_size,
                            "filled_size": order.filled_size,
                            "reserved_cash": order.reserved_cash,
                        },
                    )
                    self.storage.save_pseudo_trade(
                        {
                            "pseudo_trade_id": f"pt-{self.run_id[:8]}-{market.market.market_id}",
                            "pseudo_order_id": f"po-{self.run_id[:8]}-{market.market.market_id}",
                            "run_id": self.run_id,
                            "strategy_version": self.config.strategy_version,
                            "market_id": market.market.market_id,
                            "token_id": token_id,
                            "side": "BUY",
                            "outcome": "OPEN",
                            "signal_timestamp_utc": datetime.now(timezone.utc).isoformat(),
                            "fill_timestamp_utc": order.closed_at_utc or datetime.now(timezone.utc).isoformat(),
                            "settlement_timestamp_utc": order.closed_at_utc or datetime.now(timezone.utc).isoformat(),
                            "seconds_to_end_at_signal": signal.seconds_to_end,
                            "signal_price": signal.price,
                            "average_fill_price": report.average_fill_price,
                            "requested_size": order.requested_size,
                            "filled_size": order.filled_size,
                            "gross_stake": order.filled_size * report.average_fill_price,
                            "gross_payoff": 0.0,
                            "net_pnl": 0.0,
                            "roi_percent": 0.0,
                            "result_class": "OPEN",
                            "trade_duration_seconds": 0,
                            "partial_fill": 1 if report.state == "PSEUDO_ORDER_PARTIAL_FILL" else 0,
                        }
                    )
                    after = self.paper.positions.get(market.market.market_id)
                    if after is not None:
                        after.expected_end_utc = market.market.end_time.isoformat()
                        self._log_decision(
                            market=market,
                            token_id=token_id,
                            event_type="PAPER_POSITION_OPENED" if before is None else "PAPER_POSITION_UPDATED",
                            decision="position_opened" if before is None else "position_updated",
                            reason="fill_applied",
                            started=started,
                            payload={
                                "net_shares": after.size,
                                "average_entry_price": after.avg_price,
                                "gross_notional": after.size * after.avg_price,
                                "previous_size": before.size if before else 0.0,
                                "new_size": after.size,
                                "previous_average_entry": before.avg_price if before else 0.0,
                                "new_average_entry": after.avg_price,
                            },
                        )
                        if before is None:
                            business_logger.info(
                                "business.trade.entered %s",
                                json.dumps(
                                    {
                                        "run_id": self.run_id,
                                        "cycle": self.cycle_number,
                                        "market_id": after.market_id,
                                        "token_id": after.token_id,
                                        "entered_at_utc": after.opened_at_utc,
                                        "expected_end_utc": after.expected_end_utc,
                                        "entry_price": after.avg_price,
                                        "size": after.size,
                                    },
                                    separators=(",", ":"),
                                ),
                            )
                if order.status.value == "OPEN" and seconds_to_end <= self.config.order_expiry_seconds:
                    self.paper.expire_order(order.paper_order_id, cancelled=False)
                    logger.debug(
                        "cycle.order.expire market_id=%s market_slug=%s order_id=%s unfilled=%s",
                        market.market.market_id,
                        market.market.slug,
                        order.paper_order_id,
                        order.remaining,
                    )
                    execution_stats["orders_expired"] += 1
                    self._log_decision(
                        market=market,
                        token_id=token_id,
                        event_type="PSEUDO_ORDER_EXPIRED",
                        decision="expired",
                        reason="local_expiration_rule",
                        started=started,
                        payload={
                            "pseudo_order_id": order.paper_order_id,
                            "unfilled_size": order.remaining,
                            "released_reserved_cash": max(0.0, order.reserved_cash - (order.filled_size * order.limit_price)),
                            "order_close_timestamp_utc": order.closed_at_utc,
                        },
                    )

        settled_count, settled_net_pnl, pending_resolution_count, resolved_waiting_redeem_count = await self._settle_resolved_positions()
        # Persistencia al final de ciclo para permitir recuperación tras reinicios.
        self.storage.save_runtime_state(
            ledger=self.ledger,
            orders=self.paper.open_orders,
            positions=self.paper.positions,
            dedupe=self.signal_engine.dedupe,
        )
        avg_bid_levels = orderbook_stats["bid_levels"] / orderbook_stats["samples"] if orderbook_stats["samples"] else 0.0
        avg_ask_levels = orderbook_stats["ask_levels"] / orderbook_stats["samples"] if orderbook_stats["samples"] else 0.0
        avg_depth_at_entry = orderbook_stats["depth_at_entry"] / orderbook_stats["samples"] if orderbook_stats["samples"] else 0.0
        logger.debug(
            "cycle.orderbook.summary samples=%s avg_bid_levels=%.2f avg_ask_levels=%.2f avg_depth_at_entry=%.4f",
            int(orderbook_stats["samples"]),
            avg_bid_levels,
            avg_ask_levels,
            avg_depth_at_entry,
        )
        logger.debug(
            "cycle.signal.summary evaluated=%s triggered=%s trigger_rate=%.4f outside_entry_window=%s",
            signal_stats["evaluated"],
            signal_stats["triggered"],
            (signal_stats["triggered"] / signal_stats["evaluated"]) if signal_stats["evaluated"] else 0.0,
            signal_stats["outside_entry_window"],
        )
        logger.debug(
            "cycle.end run_id=%s cycle_number=%s open_orders=%s open_positions=%s cash_available=%.4f cash_reserved=%.4f",
            self.run_id,
            self.cycle_number,
            len(self.paper.open_orders),
            len(self.paper.positions),
            self.ledger.cash_available,
            self.ledger.cash_reserved,
        )
        if settled_count > 0:
            logger.debug(
                "cycle.settlement.summary settled_positions=%s cycle_realized_net_pnl=%.4f",
                settled_count,
                settled_net_pnl,
            )
        counters = self.storage.trade_counters()
        cumulative_won = int(counters["won_trades"])
        cumulative_lost = int(counters["lost_trades"])
        pending_positions = int(counters["open_trades"])
        cumulative_trades = int(counters["total_trades"])
        markets_parsed = len(markets)
        markets_in_watchlist = len(watchlist)
        cumulative_realized_pnl = float(counters["net_pnl"])
        nearest_pending_expiration_utc = self._nearest_pending_expiration_utc()
        business_logger.info(
            "business.pnl.update\n%s",
            self._format_business_pnl_table(
                cycle=self.cycle_number,
                markets_parsed=markets_parsed,
                markets_in_watchlist=markets_in_watchlist,
                tokens_evaluated=signal_stats["evaluated"],
                trades_taken_cycle=execution_stats["trades_taken"],
                cumulative_trades=cumulative_trades,
                pending_positions=pending_positions,
                settled_total=(cumulative_won + cumulative_lost),
                settled_this_cycle=settled_count,
                cumulative_won=cumulative_won,
                cumulative_lost=cumulative_lost,
                cumulative_realized_pnl=cumulative_realized_pnl,
                nearest_pending_expiration_utc=nearest_pending_expiration_utc,
                pending_resolution_count=pending_resolution_count,
                resolved_waiting_redeem_count=resolved_waiting_redeem_count,
                cash_available=self.ledger.cash_available,
                cash_reserved=self.ledger.cash_reserved,
            ),
        )
        business_logger.debug(
            "business.trade.lifecycle %s",
            self._build_trade_lifecycle_snapshot(
                settled_this_cycle=settled_count,
                cumulative_won=cumulative_won,
                cumulative_lost=cumulative_lost,
                cumulative_realized_pnl=cumulative_realized_pnl,
            ),
        )
        self.last_logged_cumulative_realized_pnl = cumulative_realized_pnl
        logger.debug(
            "cycle.trading.summary cycle=%s trades_taken=%s orders_opened=%s orders_filled=%s orders_partial=%s orders_expired=%s settled_this_cycle=%s cumulative_won=%s cumulative_lost=%s cumulative_realized_pnl=%.4f",
            self.cycle_number,
            execution_stats["trades_taken"],
            execution_stats["orders_opened"],
            execution_stats["orders_filled"],
            execution_stats["orders_partial"],
            execution_stats["orders_expired"],
            settled_count,
            cumulative_won,
            cumulative_lost,
            cumulative_realized_pnl,
        )

    def _format_business_pnl_table(
        self,
        cycle: int,
        markets_parsed: int,
        markets_in_watchlist: int,
        tokens_evaluated: int,
        trades_taken_cycle: int,
        cumulative_trades: int,
        pending_positions: int,
        settled_total: int,
        settled_this_cycle: int,
        cumulative_won: int,
        cumulative_lost: int,
        cumulative_realized_pnl: float,
        nearest_pending_expiration_utc: str | None,
        cash_available: float,
        cash_reserved: float,
        pending_resolution_count: int = 0,
        resolved_waiting_redeem_count: int = 0,
    ) -> str:
        rows = [
            ("cycle", str(cycle)),
            ("markets_parsed", str(markets_parsed)),
            ("markets_watchlist", str(markets_in_watchlist)),
            ("tokens_evaluated", str(tokens_evaluated)),
            ("trades_cycle", str(trades_taken_cycle)),
            ("trades_total", str(cumulative_trades)),
            ("positions_pending", str(pending_positions)),
            ("positions_settled_total", str(settled_total)),
            ("settled_this_cycle", str(settled_this_cycle)),
            ("cumulative_won", str(cumulative_won)),
            ("cumulative_lost", str(cumulative_lost)),
            ("cumulative_realized_pnl", f"{cumulative_realized_pnl:.4f}"),
            ("nearest_pending_expiration_utc", nearest_pending_expiration_utc or "n/a"),
            ("pending_resolution_markets", str(pending_resolution_count)),
            ("resolved_waiting_redeem", str(resolved_waiting_redeem_count)),
            ("cash_available", f"{cash_available:.4f}"),
            ("cash_reserved", f"{cash_reserved:.4f}"),
        ]
        key_width = max(len(key) for key, _ in rows)
        val_width = max(len(value) for _, value in rows)
        border = f"+-{'-' * key_width}-+-{'-' * val_width}-+"
        body = "\n".join(f"| {key:<{key_width}} | {value:>{val_width}} |" for key, value in rows)
        return f"{border}\n{body}\n{border}"

    def _build_trade_lifecycle_snapshot(
        self,
        settled_this_cycle: int,
        cumulative_won: int,
        cumulative_lost: int,
        cumulative_realized_pnl: float,
    ) -> str:
        trades = []
        for position in sorted(self.paper.positions.values(), key=lambda p: p.opened_at_utc):
            settled = position.status.value in {"WON", "LOST"}
            trades.append(
                {
                    "market_id": position.market_id,
                    "token_id": position.token_id,
                    "entered_at_utc": position.opened_at_utc,
                    "expected_end_utc": position.expected_end_utc,
                    "entry_price": position.avg_price,
                    "size": position.size,
                    "status": position.status.value,
                    "settled_at_utc": position.settled_at_utc if settled else None,
                    "outcome": "WIN" if position.status.value == "WON" else ("LOSS" if position.status.value == "LOST" else None),
                    "net_pnl": position.pnl_net if settled else None,
                }
            )
        payload = {
            "run_id": self.run_id,
            "cycle": self.cycle_number,
            "settled_this_cycle": settled_this_cycle,
            "cumulative_won": cumulative_won,
            "cumulative_lost": cumulative_lost,
            "cumulative_realized_pnl": cumulative_realized_pnl,
            "trades": trades,
        }
        return json.dumps(payload, separators=(",", ":"), sort_keys=False)

    def _log_decision(
        self,
        market: ClassifiedMarket,
        token_id: str,
        event_type: str,
        decision: str,
        reason: str,
        started: float,
        payload: dict[str, str | float | int | bool | None],
    ) -> None:
        self.storage.save_event(
            StructuredEvent(
                run_id=self.run_id,
                strategy_version=self.config.strategy_version,
                market_id=market.market.market_id,
                token_id=token_id,
                event_type=event_type,
                decision=decision,
                reason_code=reason,
                latency_ms=int((time.perf_counter() - started) * 1000),
                payload=payload,
            )
        )

    def restore(self) -> bool:
        state = self.storage.load_runtime_state()
        if not state:
            return False
        ledger = state["ledger"]
        self.ledger.cash_available = ledger["cash_available"]
        self.ledger.cash_reserved = ledger["cash_reserved"]
        self.ledger.holdings = dict(ledger.get("holdings") or {})
        self.paper.open_orders = {
            order_id: PaperOrder(**payload)
            for order_id, payload in (state.get("orders") or {}).items()
            if isinstance(payload, dict)
        }
        self.paper.positions = {
            market_id: PaperPosition(**payload)
            for market_id, payload in (state.get("positions") or {}).items()
            if isinstance(payload, dict)
        }
        self.signal_engine.dedupe = set(state.get("dedupe") or [])
        return True

    def settle_position(self, market: ClassifiedMarket, winner_token_id: str | None) -> None:
        position = self.paper.settle_market(market.market.market_id, winner_token_id)
        settlement = self.paper.last_settlement_report
        if position is None:
            return
        started = time.perf_counter()
        if settlement is None:
            self._log_decision(
                market=market,
                token_id=position.token_id,
                event_type="PAPER_POSITION_PENDING_SETTLEMENT",
                decision="pending_settlement",
                reason="awaiting_resolution_feed",
                started=started,
                payload={"elapsed_since_market_end_seconds": 0, "next_settlement_check_seconds": 30},
            )
            return
        event_type = "PAPER_POSITION_SETTLED_WIN" if settlement.result_class == "WIN" else "PAPER_POSITION_SETTLED_LOSS"
        self._log_decision(
            market=market,
            token_id=position.token_id,
            event_type=event_type,
            decision="settled",
            reason="resolved",
            started=started,
            payload={
                "realized_pnl_gross": settlement.net_pnl,
                "realized_pnl_net": settlement.net_pnl,
                "roi_percent": settlement.roi_percent,
                "holding_duration_seconds": settlement.holding_duration_seconds,
            },
        )
        self.storage.save_pseudo_trade(
            {
                "pseudo_trade_id": f"pt-{self.run_id[:8]}-{market.market.market_id}",
                "pseudo_order_id": f"po-{self.run_id[:8]}-{market.market.market_id}",
                "run_id": self.run_id,
                "strategy_version": self.config.strategy_version,
                "market_id": market.market.market_id,
                "token_id": position.token_id,
                "side": "BUY",
                "outcome": settlement.outcome,
                "signal_timestamp_utc": position.opened_at_utc,
                "fill_timestamp_utc": position.opened_at_utc,
                "settlement_timestamp_utc": position.settled_at_utc or datetime.now(timezone.utc).isoformat(),
                "seconds_to_end_at_signal": 0,
                "signal_price": position.avg_price,
                "average_fill_price": settlement.average_fill_price,
                "requested_size": settlement.filled_size,
                "filled_size": settlement.filled_size,
                "gross_stake": settlement.gross_stake,
                "gross_payoff": settlement.gross_payoff,
                "net_pnl": settlement.net_pnl,
                "roi_percent": settlement.roi_percent,
                "result_class": settlement.result_class,
                "trade_duration_seconds": settlement.holding_duration_seconds,
                "partial_fill": 1 if settlement.partial_fill else 0,
            }
        )
        business_logger.info(
            "business.trade.outcome %s",
            json.dumps(
                {
                    "run_id": self.run_id,
                    "cycle": self.cycle_number,
                    "market_id": position.market_id,
                    "token_id": position.token_id,
                    "entered_at_utc": position.opened_at_utc,
                    "entry_price": position.avg_price,
                    "size": position.size,
                    "settlement_timestamp_utc": position.settled_at_utc,
                    "outcome": settlement.outcome,
                    "result_class": settlement.result_class,
                    "net_pnl": settlement.net_pnl,
                    "roi_percent": settlement.roi_percent,
                },
                separators=(",", ":"),
            ),
        )

    def export_reports(self, output_dir: str) -> dict[str, str]:
        return self.storage.export_csv_reports(output_dir)

    def _build_watchlist(self, candidates: list[ClassifiedMarket]) -> list[ClassifiedMarket]:
        output: list[ClassifiedMarket] = []
        for market in candidates:
            seconds_to_end = self.time_sync.seconds_to(int(market.market.end_time.timestamp() * 1000))
            if 0 < seconds_to_end <= self.config.watch_window_seconds:
                output.append(market)
        return output

    def _nearest_pending_expiration_utc(self) -> str | None:
        nearest: datetime | None = None
        for position in self.paper.positions.values():
            if position.status not in {PositionStatus.OPEN, PositionStatus.PENDING_RESOLUTION}:
                continue
            if not position.expected_end_utc:
                continue
            try:
                expected_end = datetime.fromisoformat(position.expected_end_utc)
            except ValueError:
                continue
            if nearest is None or expected_end < nearest:
                nearest = expected_end
        return nearest.isoformat() if nearest is not None else None

    async def _settle_resolved_positions(self) -> tuple[int, float, int, int]:
        settled_count = 0
        settled_net_pnl = 0.0
        pending_resolution_count = 0
        resolved_waiting_redeem_count = 0
        now_ms = self.time_sync.now_ms()
        known_end_times = {market_id: int(item.market.end_time.timestamp() * 1000) for market_id, item in self.universe.markets.items()}
        # Recorre únicamente posiciones no liquidadas para evitar llamadas innecesarias.
        pending_market_ids = [
            market_id
            for market_id, position in self.paper.positions.items()
            if position.status in {PositionStatus.OPEN, PositionStatus.PENDING_RESOLUTION}
        ]
        for market_id in pending_market_ids:
            market_end_ms = known_end_times.get(market_id)
            position = self.paper.positions.get(market_id)
            if market_end_ms is None and position is not None and position.expected_end_utc:
                try:
                    market_end_ms = int(datetime.fromisoformat(position.expected_end_utc).timestamp() * 1000)
                except ValueError:
                    market_end_ms = None
            if market_end_ms is not None and now_ms < market_end_ms:
                continue
            market_status = await self._market_status(market_id)
            if market_status.get("uma_resolution_status") in {"resolved", "settled"} or market_status.get("resolved"):
                resolved_waiting_redeem_count += 1
            elif market_status.get("closed"):
                pending_resolution_count += 1
            resolved, winner_token_id = await self._retry(
                lambda m_id=market_id: self.clob.get_market_resolution(m_id),
                "degraded_clob_rest",
            ) or (False, None)
            if not resolved:
                continue
            synthetic_market = ClassifiedMarket(
                market=MarketRecord(
                    market_id=market_id,
                    event_id="",
                    question="",
                    slug="",
                    token_ids=tuple(),
                    end_time=datetime.now(timezone.utc),
                    active=False,
                    closed=True,
                    accepting_orders=False,
                    enable_order_book=False,
                ),
                status=ClassificationStatus.CANDIDATE_5M,
                confidence=1.0,
                method="resolution",
            )
            self.settle_position(synthetic_market, winner_token_id)
            if self.paper.last_settlement_report is not None:
                settled_count += 1
                settled_net_pnl += self.paper.last_settlement_report.net_pnl
        return settled_count, settled_net_pnl, pending_resolution_count, resolved_waiting_redeem_count

    async def _market_status(self, market_id: str) -> dict[str, str | bool | None]:
        get_status = getattr(self.clob, "get_market_status", None)
        if get_status is None:
            return {}
        status = await self._retry(lambda m_id=market_id: get_status(m_id), "degraded_clob_rest")
        if isinstance(status, dict):
            return status
        return {}

    async def _ensure_subscription(self, token_ids: list[str]) -> None:
        if not token_ids:
            return
        if not await self.ws.is_healthy():
            await self.ws.subscribe(token_ids)
        else:
            await self.ws.subscribe(token_ids)

    async def _retry(self, operation, degraded_reason: str):
        # Retry exponencial con jitter; si agota intentos, registra evento degraded y continúa.
        for attempt in range(self.config.retry_max):
            try:
                return await operation()
            except Exception:
                delay_ms = self.config.retry_base_ms * (2**attempt) + random.randint(0, self.config.retry_jitter_ms)
                await asyncio.sleep(delay_ms / 1000)
        self.storage.save_event(
            StructuredEvent(
                run_id=self.run_id,
                strategy_version=self.config.strategy_version,
                event_type="degraded",
                decision="continue",
                reason_code=degraded_reason,
                latency_ms=0,
            )
        )
        return None
