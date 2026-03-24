from __future__ import annotations

import sqlite3
from collections import defaultdict
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Iterator

from .models import ExecutedTrade, MarketSnapshot, PortfolioSnapshot, Position, SignalDirection, StrategyName, TradeSignal

DEFAULT_CAPITAL = 10_000.0


class PaperTradingStore:
    """SQLite-backed store for paper-trading state only."""

    def __init__(self, db_path: Path, starting_capital: float = DEFAULT_CAPITAL) -> None:
        self.db_path = db_path
        self.starting_capital = starting_capital
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS portfolio (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    cash REAL NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS positions (
                    market_id TEXT NOT NULL,
                    side TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    average_entry_price REAL NOT NULL,
                    strategy TEXT NOT NULL,
                    opened_at TEXT NOT NULL,
                    PRIMARY KEY (market_id, side)
                );

                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    market_id TEXT NOT NULL,
                    strategy TEXT NOT NULL,
                    side TEXT NOT NULL,
                    action TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    price REAL NOT NULL,
                    pnl REAL NOT NULL,
                    rationale TEXT NOT NULL,
                    executed_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS market_history (
                    market_id TEXT NOT NULL,
                    yes_price REAL NOT NULL,
                    no_price REAL NOT NULL,
                    volume_24h REAL NOT NULL,
                    news_score REAL NOT NULL,
                    captured_at TEXT NOT NULL
                );
                """
            )
            existing = connection.execute("SELECT 1 FROM portfolio WHERE id = 1").fetchone()
            if existing is None:
                connection.execute(
                    "INSERT INTO portfolio (id, cash, updated_at) VALUES (1, ?, ?)",
                    (self.starting_capital, _now_iso()),
                )

    def record_market_snapshots(self, snapshots: list[MarketSnapshot]) -> None:
        captured_at = _now_iso()
        rows = [
            (snapshot.market_id, snapshot.yes_price, snapshot.no_price, snapshot.volume_24h, snapshot.news_score, captured_at)
            for snapshot in snapshots
        ]
        with self._connection() as connection:
            connection.executemany(
                """
                INSERT INTO market_history (market_id, yes_price, no_price, volume_24h, news_score, captured_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                rows,
            )

    def previous_snapshot(self, market_id: str) -> MarketSnapshot | None:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT market_id, yes_price, no_price, volume_24h, news_score
                FROM market_history
                WHERE market_id = ?
                ORDER BY captured_at DESC
                LIMIT 1
                """,
                (market_id,),
            ).fetchone()
        if row is None:
            return None
        return MarketSnapshot(
            market_id=row["market_id"],
            question=row["market_id"],
            yes_price=float(row["yes_price"]),
            no_price=float(row["no_price"]),
            volume_24h=float(row["volume_24h"]),
            news_score=float(row["news_score"]),
        )

    def available_cash(self) -> float:
        with self._connection() as connection:
            row = connection.execute("SELECT cash FROM portfolio WHERE id = 1").fetchone()
        return float(row["cash"])

    def execute_paper_trade(self, signal: TradeSignal, execution_price: float) -> bool:
        allocation = self.available_cash() * min(max(signal.confidence, 0.0), 0.10)
        if allocation < 25:
            return False

        quantity = round(allocation / max(execution_price, 0.01), 4)
        cost = quantity * execution_price
        if quantity <= 0 or cost <= 0:
            return False

        with self._connection() as connection:
            cash = float(connection.execute("SELECT cash FROM portfolio WHERE id = 1").fetchone()["cash"])
            if cost > cash:
                return False

            existing = connection.execute(
                "SELECT quantity, average_entry_price FROM positions WHERE market_id = ? AND side = ?",
                (signal.market_id, signal.direction.value),
            ).fetchone()
            if existing is None:
                connection.execute(
                    """
                    INSERT INTO positions (market_id, side, quantity, average_entry_price, strategy, opened_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        signal.market_id,
                        signal.direction.value,
                        quantity,
                        execution_price,
                        signal.strategy.value,
                        _now_iso(),
                    ),
                )
            else:
                existing_quantity = float(existing["quantity"])
                new_quantity = existing_quantity + quantity
                average_price = ((existing_quantity * float(existing["average_entry_price"])) + cost) / new_quantity
                connection.execute(
                    """
                    UPDATE positions
                    SET quantity = ?, average_entry_price = ?
                    WHERE market_id = ? AND side = ?
                    """,
                    (new_quantity, average_price, signal.market_id, signal.direction.value),
                )

            connection.execute(
                "UPDATE portfolio SET cash = cash - ?, updated_at = ? WHERE id = 1",
                (cost, _now_iso()),
            )
            connection.execute(
                """
                INSERT INTO trades (market_id, strategy, side, action, quantity, price, pnl, rationale, executed_at)
                VALUES (?, ?, ?, 'BUY', ?, ?, 0, ?, ?)
                """,
                (
                    signal.market_id,
                    signal.strategy.value,
                    signal.direction.value,
                    quantity,
                    execution_price,
                    signal.rationale,
                    _now_iso(),
                ),
            )
        return True

    def rebalance_take_profit(self, latest_snapshots: dict[str, MarketSnapshot], profit_target: float) -> int:
        closed_positions = 0
        with self._connection() as connection:
            positions = connection.execute("SELECT * FROM positions ORDER BY opened_at ASC").fetchall()
            for row in positions:
                snapshot = latest_snapshots.get(str(row["market_id"]))
                if snapshot is None:
                    continue

                side = SignalDirection(row["side"])
                mark_price = snapshot.yes_price if side is SignalDirection.YES else snapshot.no_price
                entry = float(row["average_entry_price"])
                pnl_ratio = (mark_price - entry) / max(entry, 0.01)
                if pnl_ratio < profit_target:
                    continue

                quantity = float(row["quantity"])
                realized_pnl = quantity * (mark_price - entry)
                proceeds = quantity * mark_price
                connection.execute(
                    "DELETE FROM positions WHERE market_id = ? AND side = ?",
                    (row["market_id"], row["side"]),
                )
                connection.execute(
                    "UPDATE portfolio SET cash = cash + ?, updated_at = ? WHERE id = 1",
                    (proceeds, _now_iso()),
                )
                connection.execute(
                    """
                    INSERT INTO trades (market_id, strategy, side, action, quantity, price, pnl, rationale, executed_at)
                    VALUES (?, ?, ?, 'SELL', ?, ?, ?, ?, ?)
                    """,
                    (
                        row["market_id"],
                        row["strategy"],
                        row["side"],
                        quantity,
                        mark_price,
                        realized_pnl,
                        f"Take-profit triggered at {profit_target:.0%}",
                        _now_iso(),
                    ),
                )
                closed_positions += 1
        return closed_positions

    def list_open_positions(self) -> list[Position]:
        with self._connection() as connection:
            rows = connection.execute("SELECT * FROM positions ORDER BY opened_at ASC").fetchall()
        return [
            Position(
                market_id=str(row["market_id"]),
                side=SignalDirection(row["side"]),
                quantity=float(row["quantity"]),
                average_entry_price=float(row["average_entry_price"]),
                strategy=StrategyName(row["strategy"]),
                opened_at=datetime.fromisoformat(str(row["opened_at"])),
            )
            for row in rows
        ]

    def trades_for_day(self, target_day: date) -> list[ExecutedTrade]:
        start = datetime.combine(target_day, time.min, tzinfo=timezone.utc)
        end = start + timedelta(days=1)
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT market_id, strategy, side, action, quantity, price, pnl, rationale, executed_at
                FROM trades
                WHERE executed_at >= ? AND executed_at < ?
                ORDER BY executed_at ASC
                """,
                (start.isoformat(), end.isoformat()),
            ).fetchall()
        return [
            ExecutedTrade(
                market_id=str(row["market_id"]),
                strategy=StrategyName(row["strategy"]),
                side=SignalDirection(row["side"]),
                action=str(row["action"]),
                quantity=float(row["quantity"]),
                price=float(row["price"]),
                pnl=float(row["pnl"]),
                rationale=str(row["rationale"]),
                executed_at=datetime.fromisoformat(str(row["executed_at"])),
            )
            for row in rows
        ]

    def strategy_performance(self, target_day: date) -> dict[str, float]:
        performance: dict[str, float] = defaultdict(float)
        for trade in self.trades_for_day(target_day):
            performance[trade.strategy.value] += trade.pnl
        return dict(performance)


    def trades_between(self, start_day: date, end_day: date) -> list[ExecutedTrade]:
        start = datetime.combine(start_day, time.min, tzinfo=timezone.utc)
        end = datetime.combine(end_day + timedelta(days=1), time.min, tzinfo=timezone.utc)
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT market_id, strategy, side, action, quantity, price, pnl, rationale, executed_at
                FROM trades
                WHERE executed_at >= ? AND executed_at < ?
                ORDER BY executed_at ASC
                """,
                (start.isoformat(), end.isoformat()),
            ).fetchall()
        return [
            ExecutedTrade(
                market_id=str(row["market_id"]),
                strategy=StrategyName(row["strategy"]),
                side=SignalDirection(row["side"]),
                action=str(row["action"]),
                quantity=float(row["quantity"]),
                price=float(row["price"]),
                pnl=float(row["pnl"]),
                rationale=str(row["rationale"]),
                executed_at=datetime.fromisoformat(str(row["executed_at"])),
            )
            for row in rows
        ]

    def strategy_performance_between(self, start_day: date, end_day: date) -> dict[str, float]:
        performance: dict[str, float] = defaultdict(float)
        for trade in self.trades_between(start_day, end_day):
            performance[trade.strategy.value] += trade.pnl
        return dict(performance)

    def portfolio_snapshot(self, latest_snapshots: dict[str, MarketSnapshot], target_day: date) -> PortfolioSnapshot:
        open_positions = self.list_open_positions()
        marked_value = self.available_cash()
        for position in open_positions:
            snapshot = latest_snapshots.get(position.market_id)
            if snapshot is None:
                continue
            mark_price = snapshot.yes_price if position.side is SignalDirection.YES else snapshot.no_price
            marked_value += position.quantity * mark_price

        closed_trades = [trade for trade in self.trades_for_day(target_day) if trade.action == "SELL"]
        wins = sum(1 for trade in closed_trades if trade.pnl > 0)
        win_rate = wins / len(closed_trades) if closed_trades else 0.0
        return PortfolioSnapshot(
            cash=self.available_cash(),
            marked_value=marked_value,
            open_positions=len(open_positions),
            closed_trades=len(closed_trades),
            win_rate=win_rate,
        )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
