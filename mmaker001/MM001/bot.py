from __future__ import annotations

import csv
import asyncio
import contextlib
import json
import random
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from tenacity import retry, stop_after_attempt, wait_fixed

from . import config
from .models import BotMetrics, Fill, Inventory, MarketTick
from .strategy import build_quotes, fee_equivalent
from py_clob_client.client import ClobClient
from py_clob_client.exceptions import PolyApiException

try:
    import websockets
except Exception:  # pragma: no cover
    websockets = None


class MarketDataSource(Protocol):
    def next_tick(self, cycle: int, previous_mid: float, rng: random.Random) -> MarketTick: ...


@dataclass
class SimulatedOrderBookSource:
    def next_tick(self, cycle: int, previous_mid: float, rng: random.Random) -> MarketTick:
        shock = rng.uniform(-config.SIMULATION_VOLATILITY, config.SIMULATION_VOLATILITY)
        mid = max(0.05, min(0.95, previous_mid + shock))
        return MarketTick(cycle=cycle, yes_mid=mid, no_mid=1.0 - mid, spread=0.01, market_id="SIMULATED_MM001")


@dataclass
class ClobOrderBookSource:
    host: str
    yes_token_id: str
    no_token_id: str
    market_ws_url: str = config.MARKET_WS_URL

    def __post_init__(self) -> None:
        self._client = ClobClient(host=self.host)
        self._latest_yes_mid: float | None = None
        self._latest_no_mid: float | None = None
        self._last_refresh_ts = 0.0
        self._stream_thread: threading.Thread | None = None
        self._stream_stop = threading.Event()
        self._stream_lock = threading.Lock()

    def _extract_mid_from_message(self, message: dict) -> tuple[str | None, float | None]:
        token_id = (
            message.get("asset_id")
            or message.get("token_id")
            or message.get("market")
            or message.get("id")
        )
        bids = message.get("bids") or []
        asks = message.get("asks") or []
        best_bid = max((float(level.get("price")) for level in bids if level.get("price") is not None), default=None)
        best_ask = min((float(level.get("price")) for level in asks if level.get("price") is not None), default=None)
        if best_bid is not None and best_ask is not None:
            return token_id, (best_bid + best_ask) / 2.0
        if best_bid is not None:
            return token_id, best_bid
        if best_ask is not None:
            return token_id, best_ask
        return token_id, None

    async def _ws_loop(self) -> None:
        if not self.market_ws_url or websockets is None:
            return
        subscribe_payload = {
            "type": "subscribe",
            "channel": "market",
            "assets_ids": [self.yes_token_id, self.no_token_id],
        }
        while not self._stream_stop.is_set():
            try:
                async with websockets.connect(self.market_ws_url, ping_interval=15, ping_timeout=15) as ws:
                    await ws.send(json.dumps(subscribe_payload))
                    while not self._stream_stop.is_set():
                        raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
                        payload = json.loads(raw)
                        if isinstance(payload, list):
                            for item in payload:
                                self._apply_ws_message(item)
                        elif isinstance(payload, dict):
                            self._apply_ws_message(payload)
            except Exception:
                await asyncio.sleep(1.0)

    def _apply_ws_message(self, payload: dict) -> None:
        token_id, mid = self._extract_mid_from_message(payload)
        if token_id is None or mid is None:
            return
        with self._stream_lock:
            if token_id == self.yes_token_id:
                self._latest_yes_mid = mid
                self._last_refresh_ts = time.monotonic()
            elif token_id == self.no_token_id:
                self._latest_no_mid = mid
                self._last_refresh_ts = time.monotonic()

    def _ensure_ws_thread(self) -> None:
        if self._stream_thread is not None and self._stream_thread.is_alive():
            return
        if not self.market_ws_url or websockets is None:
            return

        def _runner() -> None:
            asyncio.run(self._ws_loop())

        self._stream_stop.clear()
        self._stream_thread = threading.Thread(target=_runner, daemon=True)
        self._stream_thread.start()

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(0.5), reraise=True)
    def _get_order_book(self, token_id: str):
        return self._client.get_order_book(token_id)

    async def _fetch_pair_async(self) -> tuple[float, float]:
        yes_task = asyncio.to_thread(self._book_mid, self.yes_token_id)
        no_task = asyncio.to_thread(self._book_mid, self.no_token_id)
        yes_mid, no_mid = await asyncio.gather(yes_task, no_task)
        return yes_mid, no_mid

    def refresh_cache(self) -> None:
        self._ensure_ws_thread()
        with self._stream_lock:
            has_hot_state = self._latest_yes_mid is not None and self._latest_no_mid is not None
            is_fresh = (time.monotonic() - self._last_refresh_ts) < 2.0
        if has_hot_state and is_fresh:
            return
        yes_mid, no_mid = asyncio.run(self._fetch_pair_async())
        with self._stream_lock:
            self._latest_yes_mid = yes_mid
            self._latest_no_mid = no_mid
            self._last_refresh_ts = time.monotonic()

    def _book_mid(self, token_id: str) -> float:
        orderbook = self._get_order_book(token_id)
        best_bid = max((float(level.price) for level in (orderbook.bids or [])), default=None)
        best_ask = min((float(level.price) for level in (orderbook.asks or [])), default=None)
        if best_bid is not None and best_ask is not None:
            return (best_bid + best_ask) / 2.0
        if best_bid is not None:
            return best_bid
        if best_ask is not None:
            return best_ask
        raise ValueError(f"orderbook vacío para token {token_id}")

    def next_tick(self, cycle: int, previous_mid: float, rng: random.Random) -> MarketTick:
        _ = previous_mid, rng
        self.refresh_cache()
        with self._stream_lock:
            yes_mid = self._latest_yes_mid
            no_mid = self._latest_no_mid
        if yes_mid is None:
            yes_mid = self._book_mid(self.yes_token_id)
        if no_mid is None:
            no_mid = self._book_mid(self.no_token_id)
        return MarketTick(
            cycle=cycle,
            yes_mid=yes_mid,
            no_mid=no_mid,
            spread=max(0.0, yes_mid + no_mid - 1.0),
            market_id=f"{self.yes_token_id}:{self.no_token_id}",
        )

    def close(self) -> None:
        self._stream_stop.set()
        if self._stream_thread is not None:
            self._stream_thread.join(timeout=1.0)

    def __del__(self) -> None:
        with contextlib.suppress(Exception):
            self.close()


@dataclass
class MultiClobOrderBookSource:
    sources: list[ClobOrderBookSource]
    _cursor: int = 0

    @staticmethod
    def _is_missing_orderbook_error(exc: Exception) -> bool:
        if not isinstance(exc, PolyApiException):
            return False
        if exc.status_code == 404:
            return True
        message = str(getattr(exc, "error_msg", "")).lower()
        return "no orderbook exists for the requested token id" in message

    def _remove_source_at(self, index: int) -> None:
        self.sources.pop(index)
        if not self.sources:
            self._cursor = 0
            return
        self._cursor %= len(self.sources)

    def refresh_cache(self) -> None:
        index = 0
        while index < len(self.sources):
            source = self.sources[index]
            try:
                source.refresh_cache()
                index += 1
            except Exception as exc:
                if self._is_missing_orderbook_error(exc):
                    self._remove_source_at(index)
                    continue
                raise

    def next_tick(self, cycle: int, previous_mid: float, rng: random.Random) -> MarketTick:
        if not self.sources:
            raise ValueError("no hay orderbooks configurados")
        attempts = len(self.sources)
        while attempts > 0 and self.sources:
            index = self._cursor % len(self.sources)
            source = self.sources[index]
            self._cursor += 1
            try:
                return source.next_tick(cycle=cycle, previous_mid=previous_mid, rng=rng)
            except Exception as exc:
                if self._is_missing_orderbook_error(exc):
                    self._remove_source_at(index)
                    attempts -= 1
                    continue
                raise
        raise ValueError("no hay orderbooks configurados")

    def close(self) -> None:
        for source in self.sources:
            source.close()

    def __del__(self) -> None:
        with contextlib.suppress(Exception):
            self.close()


@dataclass
class MM001Bot:
    cycles: int = config.SIMULATION_CYCLES
    inventory: Inventory = field(default_factory=Inventory)
    metrics: BotMetrics = field(default_factory=BotMetrics)
    data_source: MarketDataSource = field(default_factory=SimulatedOrderBookSource)
    market_open_orders: dict[str, int] = field(default_factory=dict)
    market_canceled_orders: dict[str, int] = field(default_factory=dict)
    market_closed_orders: dict[str, int] = field(default_factory=dict)
    market_executed_orders: dict[str, int] = field(default_factory=dict)

    def run_all(self, output_dir: Path) -> dict[str, float]:
        rng = random.Random(config.SIMULATION_RANDOM_SEED)
        output_dir.mkdir(parents=True, exist_ok=True)
        ticks_file = output_dir / "ticks.csv"
        with ticks_file.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(
                [
                    "cycle",
                    "yes_mid",
                    "no_mid",
                    "yes_bid",
                    "yes_ask",
                    "no_bid",
                    "no_ask",
                    "net_yes",
                    "taker_trade",
                    "spread_pnl_cum",
                    "merge_pnl_cum",
                    "split_sell_pnl_cum",
                    "taker_fees_cum",
                    "total_realized_cum",
                ]
            )
            mid = config.SIMULATION_BASE_PRICE
            for cycle in range(1, self.cycles + 1):
                cycle_realized_before = self.metrics.total_realized
                tick = self.data_source.next_tick(cycle=cycle, previous_mid=mid, rng=rng)
                mid = tick.yes_mid
                market_id = tick.market_id
                quotes = build_quotes(tick, self.inventory)
                taker_trade = self._simulate_fill_and_pnl(tick, quotes, rng, market_id=market_id)
                cycle_realized_after = self.metrics.total_realized
                cycle_realized_delta = cycle_realized_after - cycle_realized_before
                self.metrics.closed_cycle_count += 1
                if cycle_realized_delta > 0:
                    self.metrics.winning_cycle_count += 1
                    self.metrics.winning_cycle_pnl_sum += cycle_realized_delta
                elif cycle_realized_delta < 0:
                    self.metrics.losing_cycle_count += 1
                    self.metrics.losing_cycle_pnl_sum += cycle_realized_delta
                else:
                    self.metrics.breakeven_cycle_count += 1
                writer.writerow(
                    [
                        cycle,
                        round(tick.yes_mid, 6),
                        round(tick.no_mid, 6),
                        round(quotes.yes_bid, 6),
                        round(quotes.yes_ask, 6),
                        round(quotes.no_bid, 6),
                        round(quotes.no_ask, 6),
                        round(self.inventory.net_yes, 6),
                        int(taker_trade),
                        round(self.metrics.spread_pnl, 6),
                        round(self.metrics.merge_pnl, 6),
                        round(self.metrics.split_sell_pnl, 6),
                        round(self.metrics.taker_fees, 6),
                        round(self.metrics.total_realized, 6),
                    ]
                )

        self.metrics.directional_mtm = self.inventory.net_yes * (mid - config.SIMULATION_BASE_PRICE)
        settled_cycles = self.metrics.winning_cycle_count + self.metrics.losing_cycle_count
        win_rate = (self.metrics.winning_cycle_count / settled_cycles) if settled_cycles else 0.0
        average_pnl_per_cycle = self.metrics.total_realized / max(self.metrics.closed_cycle_count, 1)
        average_win_pnl = (
            self.metrics.winning_cycle_pnl_sum / self.metrics.winning_cycle_count
            if self.metrics.winning_cycle_count
            else 0.0
        )
        average_loss_pnl = (
            self.metrics.losing_cycle_pnl_sum / self.metrics.losing_cycle_count
            if self.metrics.losing_cycle_count
            else 0.0
        )
        paired_qty_total = min(self.inventory.yes, self.inventory.no)
        unpaired_yes_qty_total = max(0.0, self.inventory.yes - self.inventory.no)
        unpaired_no_qty_total = max(0.0, self.inventory.no - self.inventory.yes)
        largest_unpaired_qty = max(unpaired_yes_qty_total, unpaired_no_qty_total)
        maker_notional = self.metrics.executed_notional
        net_capture_per_unit_notional = self.metrics.total_realized / maker_notional if maker_notional else 0.0
        reward_to_fee_ratio = (
            (self.metrics.rebate_income + self.metrics.reward_income) / self.metrics.taker_fees
            if self.metrics.taker_fees > 0
            else 0.0
        )
        adverse_taker_ratio = self.metrics.taker_trades / max(self.metrics.fill_count, 1)
        inventory_utilization_ratio = largest_unpaired_qty / max(config.MAX_ABS_INVENTORY, 1.0)
        return {
            "spread_pnl": round(self.metrics.spread_pnl, 4),
            "merge_pnl": round(self.metrics.merge_pnl, 4),
            "split_sell_pnl": round(self.metrics.split_sell_pnl, 4),
            "taker_fees": round(self.metrics.taker_fees, 4),
            "rebate_income": round(self.metrics.rebate_income, 4),
            "reward_income": round(self.metrics.reward_income, 4),
            "directional_mtm": round(self.metrics.directional_mtm, 4),
            "total_realized": round(self.metrics.total_realized, 4),
            "net_yes_inventory": round(self.inventory.net_yes, 4),
            "taker_trades": int(self.metrics.taker_trades),
            "cumulative_realized_pnl_net": round(self.metrics.total_realized, 4),
            "win_rate": round(win_rate, 4),
            "average_pnl_per_cycle": round(average_pnl_per_cycle, 4),
            "average_win_pnl": round(average_win_pnl, 4),
            "average_loss_pnl": round(average_loss_pnl, 4),
            "fill_count": int(self.metrics.fill_count),
            "maker_notional": round(maker_notional, 4),
            "net_capture_per_unit_notional": round(net_capture_per_unit_notional, 6),
            "reward_to_fee_ratio": round(reward_to_fee_ratio, 6),
            "adverse_taker_ratio": round(adverse_taker_ratio, 6),
            "inventory_utilization_ratio": round(inventory_utilization_ratio, 6),
            "redeem_count": int(self.metrics.redeem_count),
            "current_inventory_state": {
                "cash_free_usdc": round(self.inventory.cash + self.metrics.total_realized, 4),
                "paired_qty_total": round(paired_qty_total, 4),
                "unpaired_yes_qty_total": round(unpaired_yes_qty_total, 4),
                "unpaired_no_qty_total": round(unpaired_no_qty_total, 4),
                "open_cycle_count": int(self.metrics.closed_cycle_count),
                "closed_cycle_count": int(self.metrics.closed_cycle_count),
            },
            "largest_inventory_stuck_market": {
                "market_id": "SIMULATED_MM001" if largest_unpaired_qty > 0 else "n/a",
                "unpaired_qty": round(largest_unpaired_qty, 4),
            },
            "market_orderbooks": self._market_orderbook_summary(),
        }

    def _simulate_fill_and_pnl(self, tick: MarketTick, quotes, rng: random.Random, market_id: str) -> bool:
        self.market_open_orders[market_id] = self.market_open_orders.get(market_id, 0) + 2
        qty = config.SIMULATION_SIZE
        maker_buy = Fill(side="YES", qty=qty, price=quotes.yes_bid, maker=True)
        maker_sell = Fill(side="YES", qty=qty, price=quotes.yes_ask, maker=True)
        self.metrics.fill_count += 2
        self.metrics.executed_notional += qty * (maker_buy.price + maker_sell.price)
        self.market_executed_orders[market_id] = self.market_executed_orders.get(market_id, 0) + 2

        self.metrics.spread_pnl += qty * (maker_sell.price - maker_buy.price)
        self.metrics.rebate_income += fee_equivalent(qty, tick.yes_mid, config.FEE_RATE_BPS) * 0.10
        self.metrics.reward_income += fee_equivalent(qty, tick.yes_mid, config.FEE_RATE_BPS) * 0.08

        took_taker = False
        if rng.random() < config.TAKER_FRACTION:
            took_taker = True
            self.metrics.taker_trades += 1
            self.metrics.fill_count += 1
            self.metrics.taker_fees += fee_equivalent(qty, tick.yes_mid, config.FEE_RATE_BPS)
            self.metrics.executed_notional += qty * tick.yes_mid
            self.market_canceled_orders[market_id] = self.market_canceled_orders.get(market_id, 0) + 1

        if config.ENABLE_PAIR_MERGE:
            yes_buy = quotes.yes_bid
            no_buy = quotes.no_bid
            edge = 1.0 - yes_buy - no_buy
            if edge >= config.MERGE_EDGE_MIN:
                self.metrics.merge_pnl += qty * edge
                self.metrics.redeem_count += 1
                self.market_closed_orders[market_id] = self.market_closed_orders.get(market_id, 0) + 1

        if config.ENABLE_SPLIT_SELL:
            yes_sell = quotes.yes_ask
            no_sell = quotes.no_ask
            edge = yes_sell + no_sell - 1.0
            if edge >= config.SPLIT_SELL_EDGE_MIN:
                self.metrics.split_sell_pnl += qty * edge
        return took_taker

    def _market_orderbook_summary(self) -> dict[str, dict[str, int]]:
        market_ids = (
            set(self.market_open_orders)
            | set(self.market_canceled_orders)
            | set(self.market_closed_orders)
            | set(self.market_executed_orders)
        )
        return {
            market_id: {
                "open_orders": int(self.market_open_orders.get(market_id, 0)),
                "executed_orders": int(self.market_executed_orders.get(market_id, 0)),
                "canceled_orders": int(self.market_canceled_orders.get(market_id, 0)),
                "closed_orders": int(self.market_closed_orders.get(market_id, 0)),
            }
            for market_id in sorted(market_ids)
        }
