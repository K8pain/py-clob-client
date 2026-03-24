from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import date, datetime, time as time_of_day, timedelta
from pathlib import Path
from typing import Any

import httpx

from ToTheMoon.api import PolymarketHttpClient, RateLimitPolicy

from .models import MarketSnapshot, SignalDirection, StrategyName, TradeSignal
from .storage import PaperTradingStore

GAMMA_MARKETS_URL = "https://gamma-api.polymarket.com/markets"


@dataclass(slots=True, frozen=True)
class StrategyConfig:
    starting_capital: float = 10_000.0
    max_markets: int = 200
    tail_probability_threshold: float = 0.60
    tail_volume_spike_threshold: float = 0.25
    bonding_drop_threshold: float = -0.10
    bonding_news_threshold: float = 0.50
    spread_threshold: float = 1.05
    profit_target: float = 0.07
    summary_channel: str = "#polymarket-autopilot"
    gamma_markets_limit: int = 250
    gamma_window_seconds: float = 10.0


class PolymarketAutopilot:
    """Paper-only Polymarket strategy runner.

    Intended users: developers/operators who want a safe strategy simulator.
    Problem solved: evaluate simple market-making/trend/mean-reversion ideas
    without risking capital.
    How it works: fetch market snapshots, derive signals, store simulated
    portfolio state in SQLite, and write a morning summary log.
    """

    def __init__(
        self,
        store: PaperTradingStore,
        log_directory: Path,
        config: StrategyConfig | None = None,
        *,
        market_api_url: str = GAMMA_MARKETS_URL,
        client: httpx.Client | None = None,
    ) -> None:
        self.store = store
        self.log_directory = log_directory
        self.config = config or StrategyConfig(starting_capital=store.starting_capital)
        self.market_api_url = market_api_url
        self.client = client
        self.http_client = PolymarketHttpClient(timeout=10.0, client=client) if client is not None else PolymarketHttpClient(timeout=10.0)
        self.http_client.register_limit(RateLimitPolicy("gamma-markets", self.config.gamma_markets_limit, self.config.gamma_window_seconds))
        self.log_directory.mkdir(parents=True, exist_ok=True)

    def fetch_market_data(self) -> list[MarketSnapshot]:
        payload = self._request_market_payload()
        items = payload["data"] if isinstance(payload, dict) and "data" in payload else payload
        snapshots = [snapshot for item in items if (snapshot := _parse_market(item)) is not None]
        return snapshots[: self.config.max_markets]

    def generate_signals(self, snapshots: list[MarketSnapshot]) -> list[TradeSignal]:
        signals: list[TradeSignal] = []
        for snapshot in snapshots:
            previous = self.store.previous_snapshot(snapshot.market_id)
            signals.extend(self._tail_signals(snapshot, previous))
            signals.extend(self._bonding_signals(snapshot, previous))
            signals.extend(self._spread_signals(snapshot))
        return signals

    def run_cycle(self) -> dict[str, int]:
        snapshots = self.fetch_market_data()
        snapshot_map = {snapshot.market_id: snapshot for snapshot in snapshots}
        executed = 0
        for signal in self.generate_signals(snapshots):
            snapshot = snapshot_map.get(signal.market_id)
            if snapshot is None:
                continue
            execution_price = snapshot.yes_price if signal.direction is SignalDirection.YES else snapshot.no_price
            executed += 1 if self.store.execute_paper_trade(signal, execution_price) else 0

        closed = self.store.rebalance_take_profit(snapshot_map, self.config.profit_target)
        self.store.record_market_snapshots(snapshots)
        return {"snapshots": len(snapshots), "executed_trades": executed, "closed_positions": closed}

    def publish_daily_summary(self, as_of: date | None = None) -> Path:
        report_day = as_of or date.today()
        yesterday = report_day - timedelta(days=1)
        latest_snapshots = {snapshot.market_id: snapshot for snapshot in self.fetch_market_data()}
        trades = self.store.trades_for_day(yesterday)
        portfolio = self.store.portfolio_snapshot(latest_snapshots, yesterday)
        performance = self.store.strategy_performance(yesterday)
        output_path = self.log_directory / "polymarket-autopilot.log"

        lines = [
            f"{self.config.summary_channel} | summary for {report_day.isoformat()}",
            "",
            "Yesterday's trades (entry/exit prices, P&L):",
        ]
        if trades:
            for trade in trades:
                lines.append(
                    "- "
                    f"{trade.executed_at.isoformat()} | {trade.strategy.value} | {trade.action} {trade.side.value} | "
                    f"price={trade.price:.3f} | qty={trade.quantity:.4f} | pnl={trade.pnl:.2f} | {trade.rationale}"
                )
        else:
            lines.append("- No paper trades were recorded yesterday.")

        lines.extend(
            [
                "",
                f"Current portfolio value: ${portfolio.marked_value:,.2f}",
                f"Open positions: {portfolio.open_positions}",
                f"Win rate: {portfolio.win_rate:.2%}",
                f"Strategy performance: {json.dumps(performance, sort_keys=True)}",
                "",
                "Market insights and recommendations:",
                "- TAIL: Favor strong-conviction YES markets only when volume is accelerating.",
                "- BONDING: Review headline-driven drops before fading them in paper mode.",
                "- SPREAD: Prefer liquid markets where YES + NO remains materially above 1.05.",
                "- Safety: This automation is paper trading only and must never use real money.",
                "\n---\n",
            ]
        )

        with output_path.open("a", encoding="utf-8") as file_handle:
            file_handle.write("\n".join(lines))
        return output_path

    def run_daily_scheduler(self) -> None:
        while True:
            now = datetime.now()
            next_run = datetime.combine(now.date(), time_of_day(hour=8))
            if now >= next_run:
                next_run += timedelta(days=1)
            time.sleep(max(1, int((next_run - now).total_seconds())))
            self.publish_daily_summary()

    def _request_market_payload(self) -> Any:
        params = {"limit": self.config.max_markets, "active": "true", "closed": "false"}
        response = self.http_client.get(self.market_api_url, params=params, policy_name="gamma-markets")
        return response.json()

    def _tail_signals(
        self,
        snapshot: MarketSnapshot,
        previous: MarketSnapshot | None,
    ) -> list[TradeSignal]:
        if snapshot.yes_probability < self.config.tail_probability_threshold or previous is None:
            return []

        if previous.volume_24h <= 0:
            return []

        volume_growth = (snapshot.volume_24h - previous.volume_24h) / previous.volume_24h
        if volume_growth <= self.config.tail_volume_spike_threshold:
            return []

        return [
            TradeSignal(
                strategy=StrategyName.TAIL,
                market_id=snapshot.market_id,
                direction=SignalDirection.YES,
                confidence=min(0.10, snapshot.yes_probability / 10),
                rationale=(
                    f"Strong trend detected with probability={snapshot.yes_probability:.2f} "
                    f"and volume_growth={volume_growth:.2%}"
                ),
            )
        ]

    def _bonding_signals(
        self,
        snapshot: MarketSnapshot,
        previous: MarketSnapshot | None,
    ) -> list[TradeSignal]:
        if previous is None or previous.yes_price <= 0:
            return []

        drop = (snapshot.yes_price - previous.yes_price) / previous.yes_price
        if drop > self.config.bonding_drop_threshold or snapshot.news_score < self.config.bonding_news_threshold:
            return []

        return [
            TradeSignal(
                strategy=StrategyName.BONDING,
                market_id=snapshot.market_id,
                direction=SignalDirection.YES,
                confidence=0.08,
                rationale=(
                    f"Contrarian setup after a {drop:.2%} move with news_score={snapshot.news_score:.2f}"
                ),
            )
        ]

    def _spread_signals(self, snapshot: MarketSnapshot) -> list[TradeSignal]:
        if snapshot.implied_spread <= self.config.spread_threshold:
            return []

        cheaper_side = SignalDirection.YES if snapshot.yes_price <= snapshot.no_price else SignalDirection.NO
        return [
            TradeSignal(
                strategy=StrategyName.SPREAD,
                market_id=snapshot.market_id,
                direction=cheaper_side,
                confidence=0.05,
                rationale=f"Arbitrage candidate: YES + NO = {snapshot.implied_spread:.3f}",
            )
        ]


def _parse_market(item: dict[str, Any]) -> MarketSnapshot | None:
    market_id = str(item.get("id") or item.get("marketId") or "")
    if not market_id:
        return None

    question = str(item.get("question") or item.get("title") or market_id)
    prices = _extract_prices(item)
    if prices is None:
        return None

    yes_price, no_price = prices
    volume_24h = float(item.get("volume24hr") or item.get("volume24h") or item.get("volume") or 0.0)
    raw_news_signal = float(item.get("commentCount") or item.get("eventsCount") or 0.0)
    news_score = min(1.0, raw_news_signal / 20.0)

    return MarketSnapshot(
        market_id=market_id,
        question=question,
        yes_price=yes_price,
        no_price=no_price,
        volume_24h=volume_24h,
        news_score=news_score,
    )


def _extract_prices(item: dict[str, Any]) -> tuple[float, float] | None:
    outcome_prices = item.get("outcomePrices")
    if isinstance(outcome_prices, str):
        parsed = json.loads(outcome_prices)
        if len(parsed) >= 2:
            return float(parsed[0]), float(parsed[1])

    direct_prices = item.get("prices")
    if isinstance(direct_prices, list) and len(direct_prices) >= 2:
        return float(direct_prices[0]), float(direct_prices[1])

    yes_price = item.get("yesPrice") or item.get("bestAsk")
    if yes_price is None:
        return None

    no_price = item.get("noPrice")
    if no_price is None:
        no_price = 1 - float(yes_price)
    return float(yes_price), float(no_price)
