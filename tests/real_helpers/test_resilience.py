from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import pytest

from conftest import load_helper_module

resilience = load_helper_module("resilience")


def test_api_timeout_guard_raises_on_timeout():
    def slow_op():
        time.sleep(0.05)

    with pytest.raises(TimeoutError):
        resilience.api_timeout_guard(slow_op, timeout_seconds=0.01)


def test_retry_with_backoff_retries_then_succeeds():
    attempts = {"count": 0}

    def flaky():
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise TimeoutError("temporary")
        return "ok"

    sleeps = []
    result = resilience.retry_with_backoff(
        flaky,
        retriable_exceptions=(TimeoutError,),
        max_attempts=3,
        base_delay_seconds=0.001,
        sleeper=sleeps.append,
    )
    assert result == "ok"
    assert sleeps == [0.001, 0.002]


def test_watchdog_detects_stale_process_and_restarts():
    stale = resilience.heartbeat_monitor(
        last_heartbeat=datetime.now(tz=timezone.utc) - timedelta(seconds=30),
        heartbeat_timeout_seconds=5,
        now=datetime.now(tz=timezone.utc),
    )
    events = []
    restarted = resilience.restart_stalled_worker(stale, lambda: events.append("restart"), events.append)
    assert restarted
    assert "restart" in events
