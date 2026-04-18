from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from Madawc_v2.launcher import _build_ascii_line_chart, _print_cycle_charts


def test_build_ascii_line_chart_handles_empty_points():
    text = _build_ascii_line_chart([], "demo", "{:.2f}")
    assert text == "[demo] sin datos"


def test_print_cycle_charts_prints_both_series(tmp_path: Path, capsys):
    aggregate_file = tmp_path / "cycle_aggregates.jsonl"
    aggregate_file.write_text(
        "\n".join(
            [
                '{"timestamp_utc":"2026-01-01T00:00:00Z","trades":{"net_pnl":0.0,"win_rate_percent":0.0}}',
                '{"timestamp_utc":"2026-01-01T00:01:00Z","trades":{"net_pnl":3.75,"win_rate_percent":100.0}}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    _print_cycle_charts(aggregate_file, limit=20)
    output = capsys.readouterr().out
    assert "cumulative realized PNL vs time" in output
    assert "cumulative winrate vs time" in output
