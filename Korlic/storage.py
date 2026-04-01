from __future__ import annotations

import json
import sqlite3
from csv import DictWriter
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .models import Ledger, PaperOrder, PaperPosition, StructuredEvent


class KorlicStorage:
    def __init__(self, db_path: str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts_utc TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    market_id TEXT,
                    token_id TEXT,
                    event_type TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    reason_code TEXT NOT NULL,
                    latency_ms INTEGER NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pseudo_trades (
                    pseudo_trade_id TEXT PRIMARY KEY,
                    pseudo_order_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    strategy_version TEXT NOT NULL,
                    market_id TEXT NOT NULL,
                    token_id TEXT NOT NULL,
                    side TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    signal_timestamp_utc TEXT NOT NULL,
                    fill_timestamp_utc TEXT NOT NULL,
                    settlement_timestamp_utc TEXT NOT NULL,
                    seconds_to_end_at_signal INTEGER NOT NULL,
                    signal_price REAL NOT NULL,
                    average_fill_price REAL NOT NULL,
                    requested_size REAL NOT NULL,
                    filled_size REAL NOT NULL,
                    gross_stake REAL NOT NULL,
                    gross_payoff REAL NOT NULL,
                    net_pnl REAL NOT NULL,
                    roi_percent REAL NOT NULL,
                    result_class TEXT NOT NULL,
                    trade_duration_seconds INTEGER NOT NULL,
                    partial_fill INTEGER NOT NULL
                )
                """
            )

    def save_event(self, event: StructuredEvent) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO events(ts_utc, run_id, market_id, token_id, event_type, decision, reason_code, latency_ms, payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.ts_utc,
                    event.run_id,
                    event.market_id,
                    event.token_id,
                    event.event_type,
                    event.decision,
                    event.reason_code,
                    event.latency_ms,
                    json.dumps(asdict(event)),
                ),
            )

    def save_pseudo_trade(self, row: dict[str, str | int | float]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO pseudo_trades(
                    pseudo_trade_id, pseudo_order_id, run_id, strategy_version, market_id, token_id, side, outcome,
                    signal_timestamp_utc, fill_timestamp_utc, settlement_timestamp_utc, seconds_to_end_at_signal,
                    signal_price, average_fill_price, requested_size, filled_size, gross_stake, gross_payoff,
                    net_pnl, roi_percent, result_class, trade_duration_seconds, partial_fill
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["pseudo_trade_id"],
                    row["pseudo_order_id"],
                    row["run_id"],
                    row["strategy_version"],
                    row["market_id"],
                    row["token_id"],
                    row["side"],
                    row["outcome"],
                    row["signal_timestamp_utc"],
                    row["fill_timestamp_utc"],
                    row["settlement_timestamp_utc"],
                    row["seconds_to_end_at_signal"],
                    row["signal_price"],
                    row["average_fill_price"],
                    row["requested_size"],
                    row["filled_size"],
                    row["gross_stake"],
                    row["gross_payoff"],
                    row["net_pnl"],
                    row["roi_percent"],
                    row["result_class"],
                    row["trade_duration_seconds"],
                    row["partial_fill"],
                ),
            )

    def save_runtime_state(self, ledger: Ledger, orders: dict[str, PaperOrder], positions: dict[str, PaperPosition], dedupe: set[str]) -> None:
        payload = {
            "ledger": asdict(ledger),
            "orders": {k: asdict(v) for k, v in orders.items()},
            "positions": {k: asdict(v) for k, v in positions.items()},
            "dedupe": sorted(dedupe),
        }
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO state(key, value) VALUES(?, ?)",
                ("runtime", json.dumps(payload)),
            )

    def load_runtime_state(self) -> dict | None:
        with self._connect() as conn:
            row = conn.execute("SELECT value FROM state WHERE key='runtime'").fetchone()
        if row is None:
            return None
        return json.loads(row[0])

    def get_trade_counters(self) -> dict[str, float | int]:
        with self._connect() as conn:
            total, net_pnl = conn.execute("SELECT COUNT(*), COALESCE(SUM(net_pnl), 0) FROM pseudo_trades").fetchone()
            wins = conn.execute("SELECT COUNT(*) FROM pseudo_trades WHERE result_class IN ('WIN', 'WON')").fetchone()[0]
            losses = conn.execute("SELECT COUNT(*) FROM pseudo_trades WHERE result_class IN ('LOSS', 'LOST')").fetchone()[0]
        return {
            "total_trades": int(total or 0),
            "wins": int(wins or 0),
            "losses": int(losses or 0),
            "net_pnl": float(net_pnl or 0.0),
        }

    def export_csv_reports(self, output_dir: str) -> dict[str, str]:
        report_ts = datetime.now(timezone.utc).isoformat()
        base = Path(output_dir)
        base.mkdir(parents=True, exist_ok=True)
        files = {
            "pseudo_trades": str(base / "pseudo_trades.csv"),
            "strategy_summary": str(base / "strategy_summary.csv"),
            "signal_audit": str(base / "signal_audit.csv"),
            "pseudo_orders": str(base / "pseudo_orders.csv"),
        }
        with self._connect() as conn:
            trades = conn.execute("SELECT * FROM pseudo_trades ORDER BY settlement_timestamp_utc").fetchall()
            cols = [d[0] for d in conn.execute("SELECT * FROM pseudo_trades").description]
            pseudo_rows = [dict(zip(cols, row)) for row in trades]

            events = conn.execute("SELECT payload FROM events ORDER BY id").fetchall()
            payloads = [json.loads(item[0]) for item in events]
            runtime_row = conn.execute("SELECT value FROM state WHERE key='runtime'").fetchone()

        self._write_csv(
            files["pseudo_trades"],
            [
                "report_timestamp_utc",
                "run_id",
                "strategy_version",
                "pseudo_trade_id",
                "pseudo_order_id",
                "market_id",
                "market_slug",
                "market_title",
                "token_id",
                "outcome",
                "side",
                "signal_timestamp_utc",
                "fill_timestamp_utc",
                "settlement_timestamp_utc",
                "seconds_to_end_at_signal",
                "signal_price",
                "average_fill_price",
                "requested_size",
                "filled_size",
                "gross_stake",
                "gross_payoff",
                "net_pnl",
                "roi_percent",
                "result_class",
                "trade_duration_seconds",
                "partial_fill",
            ],
            [
                {
                    "report_timestamp_utc": report_ts,
                    "market_slug": "",
                    "market_title": "",
                    **row,
                }
                for row in pseudo_rows
            ],
        )
        self._export_signal_and_orders(files["signal_audit"], files["pseudo_orders"], report_ts, payloads)
        self._export_summary(files["strategy_summary"], report_ts, pseudo_rows, payloads, runtime_row[0] if runtime_row else None)
        return files

    def _export_signal_and_orders(self, signal_path: str, orders_path: str, report_ts: str, payloads: list[dict]) -> None:
        signal_rows: list[dict] = []
        order_rows: list[dict] = []
        for payload in payloads:
            event_type = payload.get("event_type")
            if event_type in {"NO_TRADE", "SIGNAL_DETECTED"}:
                signal_rows.append(
                    {
                        "report_timestamp_utc": report_ts,
                        "run_id": payload.get("run_id", ""),
                        "strategy_version": payload.get("strategy_version", ""),
                        "market_id": payload.get("market_id", ""),
                        "market_slug": payload.get("payload", {}).get("market_slug", ""),
                        "market_title": payload.get("payload", {}).get("market_title", ""),
                        "token_id": payload.get("token_id", ""),
                        "outcome": payload.get("payload", {}).get("outcome", ""),
                        "evaluation_timestamp_utc": payload.get("ts_utc", ""),
                        "seconds_to_end": payload.get("payload", {}).get("seconds_to_end", ""),
                        "best_bid": payload.get("payload", {}).get("best_bid", ""),
                        "best_ask": payload.get("payload", {}).get("best_ask", ""),
                        "visible_depth_at_target": payload.get("payload", {}).get("visible_depth_at_target", ""),
                        "decision": payload.get("decision", ""),
                        "reason_code": payload.get("reason_code", ""),
                        "pseudo_order_id": payload.get("payload", {}).get("pseudo_order_id", ""),
                    }
                )
            if event_type.startswith("PSEUDO_ORDER_"):
                p = payload.get("payload", {})
                order_rows.append(
                    {
                        "report_timestamp_utc": report_ts,
                        "run_id": payload.get("run_id", ""),
                        "strategy_version": payload.get("strategy_version", ""),
                        "pseudo_order_id": p.get("pseudo_order_id", ""),
                        "market_id": payload.get("market_id", ""),
                        "token_id": payload.get("token_id", ""),
                        "outcome": p.get("outcome", ""),
                        "side": p.get("side", "BUY"),
                        "order_open_timestamp_utc": p.get("order_open_timestamp_utc", payload.get("ts_utc", "")),
                        "order_close_timestamp_utc": p.get("order_close_timestamp_utc", ""),
                        "limit_price": p.get("limit_price", ""),
                        "requested_size": p.get("requested_size", ""),
                        "filled_size": p.get("filled_size", 0),
                        "remaining_size": p.get("remaining_size", ""),
                        "reserved_cash": p.get("reserved_cash", ""),
                        "current_state": event_type,
                        "close_reason": payload.get("reason_code", ""),
                    }
                )
        self._write_csv(signal_path, [
            "report_timestamp_utc", "run_id", "strategy_version", "market_id", "market_slug", "market_title",
            "token_id", "outcome", "evaluation_timestamp_utc", "seconds_to_end", "best_bid", "best_ask",
            "visible_depth_at_target", "decision", "reason_code", "pseudo_order_id",
        ], signal_rows)
        self._write_csv(orders_path, [
            "report_timestamp_utc", "run_id", "strategy_version", "pseudo_order_id", "market_id", "token_id", "outcome",
            "side", "order_open_timestamp_utc", "order_close_timestamp_utc", "limit_price", "requested_size",
            "filled_size", "remaining_size", "reserved_cash", "current_state", "close_reason",
        ], order_rows)

    def _export_summary(self, path: str, report_ts: str, pseudo_rows: list[dict], payloads: list[dict], runtime_json: str | None) -> None:
        total = len(pseudo_rows)
        wins = sum(1 for row in pseudo_rows if row["result_class"] == "WIN")
        losses = sum(1 for row in pseudo_rows if row["result_class"] == "LOSS")
        net_pnl = sum(float(row["net_pnl"]) for row in pseudo_rows) if pseudo_rows else 0.0
        gross_pnl = sum(float(row["gross_payoff"]) - float(row["gross_stake"]) for row in pseudo_rows) if pseudo_rows else 0.0
        sorted_roi = sorted(float(row["roi_percent"]) for row in pseudo_rows)
        median = sorted_roi[len(sorted_roi) // 2] if sorted_roi else 0.0
        avg_roi = (sum(sorted_roi) / len(sorted_roi)) if sorted_roi else 0.0
        signals = sum(1 for p in payloads if p.get("event_type") == "SIGNAL_DETECTED")
        evaluations = sum(1 for p in payloads if p.get("event_type") in {"SIGNAL_DETECTED", "NO_TRADE"})
        orders = sum(1 for p in payloads if p.get("event_type") == "PSEUDO_ORDER_OPENED")
        fills = sum(1 for p in payloads if p.get("event_type") in {"PSEUDO_ORDER_PARTIAL_FILL", "PSEUDO_ORDER_FILLED"})
        runtime = json.loads(runtime_json) if runtime_json else {"ledger": {"cash_available": 0.0, "cash_reserved": 0.0}}
        initial_cash = 1000.0
        current_cash = float(runtime["ledger"].get("cash_available", 0.0))
        avg_seconds = [p.get("payload", {}).get("seconds_to_end") for p in payloads if p.get("event_type") == "SIGNAL_DETECTED"]
        avg_depth = [p.get("payload", {}).get("visible_depth_at_target") for p in payloads if p.get("event_type") == "SIGNAL_DETECTED"]
        row = {
            "report_timestamp_utc": report_ts,
            "run_id": pseudo_rows[-1]["run_id"] if pseudo_rows else "",
            "strategy_version": pseudo_rows[-1]["strategy_version"] if pseudo_rows else "korlic-v1",
            "initial_paper_cash": initial_cash,
            "current_paper_cash": current_cash,
            "total_markets_evaluated": evaluations,
            "total_signals": signals,
            "total_pseudo_orders": orders,
            "total_filled_orders": fills,
            "total_settled_trades": total,
            "wins": wins,
            "losses": losses,
            "win_rate": (wins / total) if total else 0.0,
            "gross_pnl": gross_pnl,
            "net_pnl": net_pnl,
            "average_roi_percent": avg_roi,
            "median_roi_percent": median,
            "cumulative_roi_percent": (net_pnl / initial_cash * 100.0) if initial_cash else 0.0,
            "capital_turnover": (sum(float(row["gross_stake"]) for row in pseudo_rows) / initial_cash) if initial_cash else 0.0,
            "reserved_cash_peak": float(runtime["ledger"].get("cash_reserved", 0.0)),
            "deployed_cash_peak": float(runtime["ledger"].get("cash_reserved", 0.0)),
            "average_seconds_to_end_at_signal": (sum(v for v in avg_seconds if isinstance(v, (int, float))) / len(avg_seconds)) if avg_seconds else 0.0,
            "average_visible_depth_at_signal": (sum(v for v in avg_depth if isinstance(v, (int, float))) / len(avg_depth)) if avg_depth else 0.0,
        }
        self._write_csv(path, list(row.keys()), [row])

    def _write_csv(self, path: str, fieldnames: list[str], rows: list[dict]) -> None:
        out = Path(path)
        tmp = out.with_suffix(out.suffix + ".tmp")
        with tmp.open("w", newline="", encoding="utf-8") as f:
            writer = DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow({k: row.get(k, "") for k in fieldnames})
        tmp.replace(out)
