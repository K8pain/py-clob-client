import json
from pathlib import Path
import sys

import logging

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
KORLIC_ROOT = REPO_ROOT / "KORLIC_v2"
if str(KORLIC_ROOT) not in sys.path:
    sys.path.insert(0, str(KORLIC_ROOT))

from Korlic_v2.launcher import (
    _append_trade_log,
    _build_parser,
    _load_bot,
    _query_event_diagnostics,
    _query_events,
    _query_trade_counters,
    _setup_logger,
    _tail_file,
)
from Korlic_v2.models import StructuredEvent
from Korlic_v2.storage import KorlicStorage


def test_query_events_filters_by_type(tmp_path: Path):
    db_path = tmp_path / "korlic.sqlite"
    storage = KorlicStorage(str(db_path))
    storage.save_event(
        StructuredEvent(
            run_id="r1",
            strategy_version="korlic-v1",
            market_id="m1",
            token_id="t1",
            event_type="SIGNAL_DETECTED",
            decision="signaled",
            reason_code="eligible",
            latency_ms=10,
            payload={"k": 1},
        )
    )
    storage.save_event(
        StructuredEvent(
            run_id="r1",
            strategy_version="korlic-v1",
            market_id="m1",
            token_id="t1",
            event_type="NO_TRADE",
            decision="ignored",
            reason_code="insufficient_depth",
            latency_ms=11,
            payload={"k": 2},
        )
    )

    rows = _query_events(db_path, limit=10, event_type="SIGNAL_DETECTED")
    assert len(rows) == 1
    assert rows[0]["event_type"] == "SIGNAL_DETECTED"
    assert rows[0]["payload"]["payload"]["k"] == 1


def test_tail_file_returns_1_if_missing(tmp_path: Path):
    rc = _tail_file(tmp_path / "missing.log", lines=20, follow=False)
    assert rc == 1


def test_tail_file_prints_last_lines(tmp_path: Path, capsys):
    log_file = tmp_path / "launcher.log"
    log_file.write_text("uno\ndos\ntres\n", encoding="utf-8")

    rc = _tail_file(log_file, lines=2, follow=False)
    out = capsys.readouterr().out

    assert rc == 0
    assert out == "dos\ntres\n"


def test_query_trade_counters(tmp_path: Path):
    db_path = tmp_path / "korlic.sqlite"
    storage = KorlicStorage(str(db_path))
    storage.save_pseudo_trade(
        {
            "pseudo_trade_id": "pt1",
            "pseudo_order_id": "po1",
            "run_id": "r1",
            "strategy_version": "korlic-v1",
            "market_id": "m1",
            "token_id": "t1",
            "side": "BUY",
            "outcome": "YES",
            "signal_timestamp_utc": "2026-01-01T00:00:00+00:00",
            "fill_timestamp_utc": "2026-01-01T00:00:01+00:00",
            "settlement_timestamp_utc": "2026-01-01T00:05:00+00:00",
            "seconds_to_end_at_signal": 300,
            "signal_price": 0.99,
            "average_fill_price": 0.99,
            "requested_size": 10.0,
            "filled_size": 10.0,
            "gross_stake": 9.9,
            "gross_payoff": 10.0,
            "net_pnl": 0.1,
            "roi_percent": 1.0,
            "result_class": "WON",
            "trade_duration_seconds": 300,
            "partial_fill": 0,
        }
    )

    counters = _query_trade_counters(db_path)
    assert counters["total_trades"] == 1
    assert counters["won_trades"] == 1
    assert counters["lost_trades"] == 0
    assert counters["net_pnl"] == 0.1


def test_load_bot_from_builtin_factory(tmp_path: Path):
    db_path = tmp_path / "korlic.sqlite"
    bot = _load_bot("Korlic_v2.factory:build_bot", db_path)
    assert str(bot.storage.db_path) == str(db_path)


def test_query_event_diagnostics(tmp_path: Path):
    db_path = tmp_path / "korlic.sqlite"
    storage = KorlicStorage(str(db_path))
    storage.save_event(
        StructuredEvent(
            run_id="r1",
            strategy_version="korlic-v1",
            market_id="m1",
            token_id="t1",
            event_type="NO_TRADE",
            decision="ignored",
            reason_code="skipped_outside_entry_window",
            latency_ms=10,
            payload={},
        )
    )
    storage.save_event(
        StructuredEvent(
            run_id="r1",
            strategy_version="korlic-v1",
            market_id="m1",
            token_id="t1",
            event_type="NO_TRADE",
            decision="ignored",
            reason_code="skipped_outside_entry_window",
            latency_ms=10,
            payload={},
        )
    )
    storage.save_event(
        StructuredEvent(
            run_id="r1",
            strategy_version="korlic-v1",
            market_id="m2",
            token_id="t2",
            event_type="SIGNAL_DETECTED",
            decision="signaled",
            reason_code="signal_candidate",
            latency_ms=12,
            payload={},
        )
    )
    storage.save_event(
        StructuredEvent(
            run_id="r1",
            strategy_version="korlic-v1",
            market_id="m2",
            token_id="t2",
            event_type="PSEUDO_ORDER_OPENED",
            decision="pseudo-traded",
            reason_code="accepted_by_paper_engine",
            latency_ms=15,
            payload={},
        )
    )

    diagnostics = _query_event_diagnostics(db_path)
    assert diagnostics["evaluations"] == 3
    assert diagnostics["signals"] == 1
    assert diagnostics["opened_orders"] == 1
    assert diagnostics["fills"] == 0
    assert diagnostics["top_no_trade_reasons"] == [{"reason_code": "skipped_outside_entry_window", "count": 2}]


def test_append_trade_log_writes_incremental_rows(tmp_path: Path):
    db_path = tmp_path / "korlic.sqlite"
    trade_log = tmp_path / "korlic-trades.log"
    storage = KorlicStorage(str(db_path))
    storage.save_event(
        StructuredEvent(
            run_id="r1",
            strategy_version="korlic-v1",
            market_id="m1",
            token_id="t1",
            event_type="NO_TRADE",
            decision="ignored",
            reason_code="skipped_price_above_entry_threshold",
            latency_ms=8,
            payload={},
        )
    )
    storage.save_event(
        StructuredEvent(
            run_id="r1",
            strategy_version="korlic-v1",
            market_id="m1",
            token_id="t1",
            event_type="PSEUDO_ORDER_OPENED",
            decision="pseudo-traded",
            reason_code="accepted_by_paper_engine",
            latency_ms=10,
            payload={},
        )
    )
    last_id = _append_trade_log(db_path, trade_log, since_id=0)
    text = trade_log.read_text(encoding="utf-8")
    assert "NO_TRADE" in text
    assert "PSEUDO_ORDER_OPENED" in text
    assert last_id > 0

    second = _append_trade_log(db_path, trade_log, since_id=last_id)
    assert second == last_id


def test_parser_supports_tail_trades_command():
    parser = _build_parser()
    args = parser.parse_args(["tail-trades", "--follow"])
    assert args.command == "tail-trades"
    assert args.follow is True


def test_setup_logger_enables_debug_for_launcher_bot_and_factory(tmp_path: Path):
    logger = _setup_logger(tmp_path / "launcher.log")
    bot_logger = logging.getLogger("korlic-bot")
    factory_logger = logging.getLogger("korlic-factory")
    assert logger.level == logging.INFO
    assert bot_logger.level == logging.INFO
    assert factory_logger.level == logging.INFO
