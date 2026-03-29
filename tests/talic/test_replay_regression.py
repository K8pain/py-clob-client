from Talic.runtime.degradation import update_state_for_error
from Talic.runtime.engine import process_events
from Talic.runtime.idempotency import OperationLedger
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


def _seed_ledger_from(source: OperationLedger, target: OperationLedger) -> None:
    for key, entry in source._entries.items():  # noqa: SLF001 - controlled test setup
        target.record(key, entry.result)


def test_restart_and_ledger_replay_keeps_state_and_outputs_identical():
    events = [
        {"idempotency_key": "m-1", "type": "mutation", "value": 2},
        {"idempotency_key": "m-2", "type": "mutation", "value": 5},
    ]

    first_ledger = OperationLedger()
    first_state = {"sum": 0}
    first_outputs = []

    def first_mutate_handler(event):
        first_state["sum"] += event["value"]
        result = {"sum": first_state["sum"]}
        first_outputs.append(result)
        return result

    first_mode = process_events(
        events,
        mode=ModeState.NORMAL,
        validate_input=lambda _: None,
        validate_external_response=lambda _: None,
        mutate_handler=first_mutate_handler,
        external_call=lambda _: {"ok": True},
        retry_policy=lambda fn: fn(),
        ledger=first_ledger,
        logger=_Logger(),
        metrics=_Metrics(),
        update_mode_for_error=update_state_for_error,
    )

    replay_ledger = OperationLedger()
    _seed_ledger_from(first_ledger, replay_ledger)

    replay_state = {"sum": first_state["sum"]}
    replay_outputs = []

    def replay_mutate_handler(event):
        replay_state["sum"] += event["value"]
        result = {"sum": replay_state["sum"]}
        replay_outputs.append(result)
        return result

    replay_mode = process_events(
        events,
        mode=ModeState.NORMAL,
        validate_input=lambda _: None,
        validate_external_response=lambda _: None,
        mutate_handler=replay_mutate_handler,
        external_call=lambda _: {"ok": True},
        retry_policy=lambda fn: fn(),
        ledger=replay_ledger,
        logger=_Logger(),
        metrics=_Metrics(),
        update_mode_for_error=update_state_for_error,
    )

    assert first_mode == replay_mode == ModeState.NORMAL
    assert replay_outputs == []
    assert replay_state == first_state
    assert [entry.result for entry in replay_ledger._entries.values()] == [
        entry.result for entry in first_ledger._entries.values()
    ]
