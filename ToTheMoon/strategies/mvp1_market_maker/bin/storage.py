from __future__ import annotations

import sqlite3
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict

from ..contracts import MarketCandidate, MarketResult, MarketStateSnapshot, PaperOrder, QuoteDecision
from .paper_engine import PaperFillEvent


class TradeStore:
    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        with self._connect() as conn:
            cur = conn.cursor()
            cur.executescript(
                """
                CREATE TABLE IF NOT EXISTS markets (
                    market_id TEXT PRIMARY KEY,
                    event_id TEXT,
                    asset_symbol TEXT,
                    market_open_ts TEXT,
                    market_close_ts TEXT,
                    status TEXT,
                    duration_sec INTEGER,
                    fees_enabled INTEGER,
                    tick_size REAL
                );
                CREATE TABLE IF NOT EXISTS market_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    market_id TEXT,
                    ts TEXT,
                    best_bid REAL,
                    best_ask REAL,
                    midpoint REAL,
                    last_trade_price REAL,
                    spread_ticks INTEGER,
                    bid_size_top REAL,
                    ask_size_top REAL,
                    book_update_count INTEGER
                );
                CREATE TABLE IF NOT EXISTS quote_decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    market_id TEXT,
                    ts TEXT,
                    quote_allowed INTEGER,
                    seed_fair_value REAL,
                    yes_quote_price REAL,
                    no_quote_price REAL,
                    decision_reason TEXT
                );
                CREATE TABLE IF NOT EXISTS paper_orders (
                    order_id TEXT PRIMARY KEY,
                    market_id TEXT,
                    side TEXT,
                    price REAL,
                    size REAL,
                    status TEXT,
                    created_ts TEXT,
                    cancelled_ts TEXT,
                    filled_ts TEXT,
                    cancel_reason TEXT
                );
                CREATE TABLE IF NOT EXISTS paper_fills (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id TEXT,
                    market_id TEXT,
                    side TEXT,
                    fill_price REAL,
                    fill_ts TEXT
                );
                CREATE TABLE IF NOT EXISTS market_results (
                    market_id TEXT PRIMARY KEY,
                    resolved_outcome TEXT,
                    resolution_ts TEXT,
                    gross_pnl REAL,
                    fees REAL,
                    rebates REAL,
                    net_pnl REAL
                );
                """
            )
            conn.commit()

    def upsert_market(self, market: MarketCandidate) -> None:
        payload = asdict(market)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO markets VALUES (:market_id, :event_id, :asset_symbol, :market_open_ts,
                                            :market_close_ts, :status, :duration_sec, :fees_enabled, :tick_size)
                ON CONFLICT(market_id) DO UPDATE SET
                    status=excluded.status
                """,
                payload,
            )
            conn.commit()

    def save_snapshot(self, snapshot: MarketStateSnapshot) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO market_snapshots (market_id, ts, best_bid, best_ask, midpoint, last_trade_price,
                                              spread_ticks, bid_size_top, ask_size_top, book_update_count)
                VALUES (:market_id, :ts, :best_bid, :best_ask, :midpoint, :last_trade_price,
                        :spread_ticks, :bid_size_top, :ask_size_top, :book_update_count)
                """,
                asdict(snapshot),
            )
            conn.commit()

    def save_quote_decision(self, decision: QuoteDecision) -> None:
        payload = asdict(decision)
        payload["quote_allowed"] = 1 if decision.quote_allowed else 0
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO quote_decisions (market_id, ts, quote_allowed, seed_fair_value,
                                             yes_quote_price, no_quote_price, decision_reason)
                VALUES (:market_id, :ts, :quote_allowed, :seed_fair_value,
                        :yes_quote_price, :no_quote_price, :decision_reason)
                """,
                payload,
            )
            conn.commit()

    def save_order(self, order: PaperOrder) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO paper_orders (order_id, market_id, side, price, size, status,
                                                     created_ts, cancelled_ts, filled_ts, cancel_reason)
                VALUES (:order_id, :market_id, :side, :price, :size, :status,
                        :created_ts, :cancelled_ts, :filled_ts, :cancel_reason)
                """,
                {
                    "order_id": order.order_id,
                    "market_id": order.market_id,
                    "side": order.side,
                    "price": order.price,
                    "size": order.size,
                    "status": order.status.value,
                    "created_ts": order.created_ts,
                    "cancelled_ts": order.cancelled_ts,
                    "filled_ts": order.filled_ts,
                    "cancel_reason": order.cancel_reason,
                },
            )
            conn.commit()

    def save_fill(self, fill: PaperFillEvent) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO paper_fills (order_id, market_id, side, fill_price, fill_ts)
                VALUES (?, ?, ?, ?, ?)
                """,
                (fill.order_id, fill.market_id, fill.side, fill.fill_price, fill.fill_ts),
            )
            conn.commit()

    def save_market_result(self, result: MarketResult) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO market_results VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.market_id,
                    result.resolved_outcome,
                    result.resolution_ts,
                    result.gross_pnl,
                    result.fees,
                    result.rebates,
                    result.net_pnl,
                ),
            )
            conn.commit()

    def daily_summary(self) -> Dict[str, Any]:
        with self._connect() as conn:
            cur = conn.cursor()
            markets_seen = cur.execute("SELECT COUNT(*) FROM markets").fetchone()[0]
            markets_quoted = cur.execute(
                "SELECT COUNT(DISTINCT market_id) FROM quote_decisions WHERE quote_allowed=1"
            ).fetchone()[0]
            markets_filled = cur.execute("SELECT COUNT(DISTINCT market_id) FROM paper_fills").fetchone()[0]
            net_pnl = cur.execute("SELECT COALESCE(SUM(net_pnl), 0) FROM market_results").fetchone()[0]
            return {
                "markets_seen": markets_seen,
                "markets_quoted": markets_quoted,
                "markets_filled": markets_filled,
                "net_pnl": round(float(net_pnl), 6),
            }
