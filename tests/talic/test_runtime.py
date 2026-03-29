import pytest

from Talic.runtime.degradation import apply_recovery, update_state_for_error
from Talic.runtime.engine import process_events
from Talic.runtime.errors import InternalError, TransientError
from Talic.runtime.idempotency import OperationLedger, run_idempotent
from Talic.runtime.mode import ModeState, transition_to


class _Logger:
    def info(self, *args, **kwargs):
        return None

    def warning(self, *args, **kwargs):
        return None

    def error(self, *args, **kwargs):
        return None


class _Metrics:
    def __init__(self):
        self.counts = {}

    def increment(self, key):
        self.counts[key] = self.counts.get(key, 0) + 1


def test_mode_transitions_reject_invalid():
    assert transition_to(ModeState.NORMAL, ModeState.RETRYING) == ModeState.RETRYING
    try:
        transition_to(ModeState.IDLE_SAFE, ModeState.READ_ONLY)
        assert False, "expected invalid transition"
    except ValueError:
        assert True


def test_idempotent_replay_returns_prior_result():
    ledger = OperationLedger()
    calls = {"count": 0}

    def op():
        calls["count"] += 1
        return {"ok": True}

    assert run_idempotent(ledger, "k1", op) == {"ok": True}
    assert run_idempotent(ledger, "k1", op) == {"ok": True}
    assert calls["count"] == 1


def test_degradation_transitions():
    assert (
        update_state_for_error(
            ModeState.NORMAL,
            TransientError("tmp"),
            transient_failures=2,
            retry_exhausted=False,
        )
        == ModeState.RETRYING
    )
    assert (
        update_state_for_error(
            ModeState.NORMAL,
            TransientError("tmp"),
            transient_failures=1,
            retry_exhausted=True,
        )
        == ModeState.READ_ONLY
    )
    assert (
        update_state_for_error(
            ModeState.NORMAL,
            InternalError("boom"),
            transient_failures=0,
            retry_exhausted=False,
        )
        == ModeState.IDLE_SAFE
    )
    assert apply_recovery(ModeState.RETRYING) == ModeState.NORMAL


def test_engine_enforces_mutation_guard():
    metrics = _Metrics()
    mode = process_events(
        [{"idempotency_key": "m1", "type": "mutation"}],
        mode=ModeState.READ_ONLY,
        validate_input=lambda _: None,
        validate_external_response=lambda _: None,
        mutate_handler=lambda _: {"changed": True},
        external_call=lambda _: {"ok": True},
        retry_policy=lambda fn: fn(),
        ledger=OperationLedger(),
        logger=_Logger(),
        metrics=metrics,
        update_mode_for_error=update_state_for_error,
    )
    assert mode == ModeState.IDLE_SAFE
    assert metrics.counts["runtime.errors"] == 1


def test_engine_requires_idempotency_key():
    with pytest.raises(ValueError, match="idempotency_key is required"):
        process_events(
            [{"type": "mutation"}],
            mode=ModeState.NORMAL,
            validate_input=lambda _: None,
            validate_external_response=lambda _: None,
            mutate_handler=lambda _: {"changed": True},
            external_call=lambda _: {"ok": True},
            retry_policy=lambda fn: fn(),
            ledger=OperationLedger(),
            logger=_Logger(),
            metrics=_Metrics(),
            update_mode_for_error=update_state_for_error,
        )


def test_engine_honors_iteration_limit_and_wait_strategy():
    calls = {"mutations": 0, "sleeps": 0}

    def mutate_handler(_):
        calls["mutations"] += 1
        return {"ok": True}

    def sleeper(seconds):
        assert seconds == 0.01
        calls["sleeps"] += 1

    mode = process_events(
        [{"idempotency_key": f"k{i}", "type": "mutation"} for i in range(5)],
        mode=ModeState.NORMAL,
        validate_input=lambda _: None,
        validate_external_response=lambda _: None,
        mutate_handler=mutate_handler,
        external_call=lambda _: {"ok": True},
        retry_policy=lambda fn: fn(),
        ledger=OperationLedger(),
        logger=_Logger(),
        metrics=_Metrics(),
        update_mode_for_error=update_state_for_error,
        max_iterations=2,
        wait_seconds=0.01,
        sleeper=sleeper,
    )

    assert mode == ModeState.NORMAL
    assert calls["mutations"] == 2
    assert calls["sleeps"] == 2
