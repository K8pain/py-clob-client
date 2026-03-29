import json
from pathlib import Path

from Korlic.launcher import _query_events, _query_trade_counters, _tail_file
from Korlic.models import StructuredEvent
from Korlic.storage import KorlicStorage


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
