import json
from pathlib import Path

from Korlic.launcher import _append_progress_csv, _query_events, _tail_file, _trade_stats
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


def test_trade_stats_and_progress_csv(tmp_path: Path):
    db_path = tmp_path / "korlic.sqlite"
    storage = KorlicStorage(str(db_path))
    storage.save_event(
        StructuredEvent(
            run_id="r2",
            strategy_version="korlic-v1",
            market_id="m2",
            token_id="t2",
            event_type="SIGNAL_DETECTED",
            decision="signaled",
            reason_code="eligible",
            latency_ms=9,
            payload={"x": 1},
        )
    )
    storage.save_pseudo_trade(
        {
            "pseudo_trade_id": "pt-1",
            "pseudo_order_id": "po-1",
            "run_id": "r2",
            "strategy_version": "korlic-v1",
            "market_id": "m2",
            "token_id": "t2",
            "side": "BUY",
            "outcome": "YES",
            "signal_timestamp_utc": "2025-01-01T00:00:00+00:00",
            "fill_timestamp_utc": "2025-01-01T00:00:01+00:00",
            "settlement_timestamp_utc": "2025-01-01T00:05:00+00:00",
            "seconds_to_end_at_signal": 30,
            "signal_price": 0.99,
            "average_fill_price": 0.99,
            "requested_size": 10.0,
            "filled_size": 10.0,
            "gross_stake": 9.9,
            "gross_payoff": 10.0,
            "net_pnl": 0.1,
            "roi_percent": 1.01,
            "result_class": "WON",
            "trade_duration_seconds": 299,
            "partial_fill": 0,
        }
    )

    stats = _trade_stats(db_path)
    assert stats["total_trades"] == 1
    assert stats["won"] == 1
    assert stats["total_signals"] == 1

    csv_path = tmp_path / "trade_progress.csv"
    _append_progress_csv(csv_path, stats)
    content = csv_path.read_text(encoding="utf-8")
    assert "total_trades,won,lost,pending,total_pnl,total_signals" in content
    assert ",1,1,0,0,0.1,1" in content
