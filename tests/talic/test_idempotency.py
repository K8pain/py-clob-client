from Talic.runtime.degradation import update_state_for_error
from Talic.runtime.engine import process_events
from Talic.runtime.idempotency import OperationLedger, run_idempotent
from Talic.runtime.mode import ModeState


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


def test_duplicate_idempotency_key_has_no_extra_side_effects():
    ledger = OperationLedger()
    side_effects = {"count": 0}

    def op():
        side_effects["count"] += 1
        return {"ok": True}

    assert run_idempotent(ledger, "dup-key", op) == {"ok": True}
    assert run_idempotent(ledger, "dup-key", op) == {"ok": True}
    assert side_effects["count"] == 1


def test_repeated_event_processing_produces_identical_final_state():
    events = [
        {"idempotency_key": "evt-1", "type": "mutation", "value": 3},
        {"idempotency_key": "evt-2", "type": "mutation", "value": 7},
    ]

    ledger = OperationLedger()
    state = {"sum": 0}

    def mutate_handler(event):
        state["sum"] += event["value"]
        return {"sum": state["sum"]}

    mode = ModeState.NORMAL
    mode = process_events(
        events,
        mode=mode,
        validate_input=lambda _: None,
        validate_external_response=lambda _: None,
        mutate_handler=mutate_handler,
        external_call=lambda _: {"ok": True},
        retry_policy=lambda fn: fn(),
        ledger=ledger,
        logger=_Logger(),
        metrics=_Metrics(),
        update_mode_for_error=update_state_for_error,
    )

    first_final_state = dict(state)
    assert mode == ModeState.NORMAL

    mode = process_events(
        events,
        mode=mode,
        validate_input=lambda _: None,
        validate_external_response=lambda _: None,
        mutate_handler=mutate_handler,
        external_call=lambda _: {"ok": True},
        retry_policy=lambda fn: fn(),
        ledger=ledger,
        logger=_Logger(),
        metrics=_Metrics(),
        update_mode_for_error=update_state_for_error,
    )

    assert mode == ModeState.NORMAL
    assert state == first_final_state
