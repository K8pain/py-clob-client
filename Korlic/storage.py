from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
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
