from __future__ import annotations

from conftest import load_helper_module

execution = load_helper_module("execution_guard")


def test_validate_trade_request_blocks_when_circuit_breaker_active():
    allowed, reason = execution.validate_trade_request(1, 2, 3, 0, True)
    assert not allowed
    assert reason == "circuit_breaker_active"


def test_should_open_trade_requires_all_conditions():
    assert not execution.should_open_trade(True, True, True)
    assert execution.should_open_trade(True, True, False)


def test_track_skip_reason_counts_reasons():
    counts = execution.track_skip_reason({}, "weak_trend")
    counts = execution.track_skip_reason(counts, "weak_trend")
    assert counts["weak_trend"] == 2
