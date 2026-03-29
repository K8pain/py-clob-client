from __future__ import annotations

import asyncio
import random
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from .discovery import DiscoveryEngine, DiscoveryState, MarketClassifier
from .models import (
    ClassifiedMarket,
    Ledger,
    MarketRecord,
    OrderBookSnapshot,
    StructuredEvent,
)
from .paper import PaperExecutionEngine
from .runtime import TimeSync
from .signal import SignalConfig, SignalEngine
from .storage import KorlicStorage


class GammaClient(Protocol):
    async def get_active_markets(self) -> list[MarketRecord]: ...


class ClobClient(Protocol):
    async def get_server_time_ms(self) -> int: ...

    async def get_orderbook(self, token_id: str) -> OrderBookSnapshot: ...


class WsClient(Protocol):
    async def subscribe(self, asset_ids: list[str]) -> None: ...

    async def is_healthy(self) -> bool: ...


@dataclass
class KorlicConfig:
    watch_window_seconds: int = 600
    retry_max: int = 4
    retry_base_ms: int = 100
    retry_jitter_ms: int = 250


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

    def __post_init__(self) -> None:
        self.discovery = DiscoveryEngine(classifier=self.classifier, parser_version="korlic-v1")
        self.paper = PaperExecutionEngine(ledger=self.ledger)
        self.universe = DiscoveryState(markets={}, parser_version="korlic-v1", discovered_at=datetime.utcnow().isoformat())

    async def run_cycle(self) -> None:
        started = time.perf_counter()
        server_time = await self._retry(self.clob.get_server_time_ms, "degraded_clob_rest")
        if server_time is not None:
            self.time_sync.sync(server_time)

        markets = await self._retry(self.gamma.get_active_markets, "degraded_gamma")
        if markets is None:
            return

        fresh = self.discovery.build_universe(markets)
        self.universe = self.discovery.refresh_universe(self.universe, fresh)
        watchlist = self._build_watchlist(list(self.universe.markets.values()))
        token_ids = sorted({token for item in watchlist for token in item.market.token_ids})
        await self._ensure_subscription(token_ids)

        for market in watchlist:
            if not market.market.accepting_orders or not market.market.active or market.market.closed:
                continue
            for token_id in market.market.token_ids:
                book = await self._retry(lambda tid=token_id: self.clob.get_orderbook(tid), "degraded_clob_rest")
                if book is None:
                    continue
                signal, reason = self.signal_engine.evaluate(
                    market=market,
                    token_id=token_id,
                    book=book,
                    end_epoch_ms=int(market.market.end_time.timestamp() * 1000),
                    time_sync=self.time_sync,
                    available_cash=self.ledger.cash_available,
                )
                self.storage.save_event(
                    StructuredEvent(
                        run_id=self.run_id,
                        market_id=market.market.market_id,
                        token_id=token_id,
                        event_type="signal",
                        decision="accepted" if signal else "rejected",
                        reason_code=reason,
                        latency_ms=int((time.perf_counter() - started) * 1000),
                    )
                )
                if signal is None:
                    continue
                order = self.paper.create_order(signal)
                if order is None:
                    continue
                self.paper.try_fill(order, book)

        self.storage.save_runtime_state(
            ledger=self.ledger,
            orders=self.paper.open_orders,
            positions=self.paper.positions,
            dedupe=self.signal_engine.dedupe,
        )

    def restore(self) -> bool:
        state = self.storage.load_runtime_state()
        if not state:
            return False
        ledger = state["ledger"]
        self.ledger.cash_available = ledger["cash_available"]
        self.ledger.cash_reserved = ledger["cash_reserved"]
        self.ledger.holdings = dict(ledger.get("holdings") or {})
        self.signal_engine.dedupe = set(state.get("dedupe") or [])
        return True

    def _build_watchlist(self, candidates: list[ClassifiedMarket]) -> list[ClassifiedMarket]:
        output: list[ClassifiedMarket] = []
        for market in candidates:
            seconds_to_end = self.time_sync.seconds_to(int(market.market.end_time.timestamp() * 1000))
            if 0 < seconds_to_end <= self.config.watch_window_seconds:
                output.append(market)
        return output

    async def _ensure_subscription(self, token_ids: list[str]) -> None:
        if not token_ids:
            return
        if not await self.ws.is_healthy():
            await self.ws.subscribe(token_ids)
        else:
            await self.ws.subscribe(token_ids)

    async def _retry(self, operation, degraded_reason: str):
        for attempt in range(self.config.retry_max):
            try:
                return await operation()
            except Exception:
                delay_ms = self.config.retry_base_ms * (2**attempt) + random.randint(0, self.config.retry_jitter_ms)
                await asyncio.sleep(delay_ms / 1000)
        self.storage.save_event(
            StructuredEvent(
                run_id=self.run_id,
                event_type="degraded",
                decision="continue",
                reason_code=degraded_reason,
                latency_ms=0,
            )
        )
        return None
