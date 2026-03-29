from Talic.runtime.degradation import update_state_for_error
from Talic.runtime.engine import process_events
from Talic.runtime.idempotency import OperationLedger
from Talic.runtime.mode import ModeState, is_transition_allowed, transition_to


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


def test_mode_state_allowed_and_forbidden_transitions():
    all_states = list(ModeState)
    expected_allowed = {
        ModeState.NORMAL: {ModeState.NORMAL, ModeState.RETRYING, ModeState.READ_ONLY, ModeState.IDLE_SAFE},
        ModeState.RETRYING: {ModeState.RETRYING, ModeState.NORMAL, ModeState.READ_ONLY, ModeState.IDLE_SAFE},
        ModeState.READ_ONLY: {ModeState.READ_ONLY, ModeState.NORMAL, ModeState.IDLE_SAFE},
        ModeState.IDLE_SAFE: {ModeState.IDLE_SAFE, ModeState.NORMAL},
    }

    for current in all_states:
        for target in all_states:
            allowed = target in expected_allowed[current]
            assert is_transition_allowed(current, target) is allowed
            if allowed:
                assert transition_to(current, target) == target
            else:
                try:
                    transition_to(current, target)
                    assert False, f"expected invalid transition {current.value}->{target.value}"
                except ValueError:
                    assert True


def test_mutations_blocked_in_read_only_and_idle_safe():
    for initial_mode in (ModeState.READ_ONLY, ModeState.IDLE_SAFE):
        mutation_calls = {"count": 0}
        metrics = _Metrics()

        def mutate_handler(_):
            mutation_calls["count"] += 1
            return {"changed": True}

        resulting_mode = process_events(
            [{"idempotency_key": f"k-{initial_mode.value}", "type": "mutation"}],
            mode=initial_mode,
            validate_input=lambda _: None,
            validate_external_response=lambda _: None,
            mutate_handler=mutate_handler,
            external_call=lambda _: {"ok": True},
            retry_policy=lambda fn: fn(),
            ledger=OperationLedger(),
            logger=_Logger(),
            metrics=metrics,
            update_mode_for_error=update_state_for_error,
        )

        assert mutation_calls["count"] == 0
        assert resulting_mode == ModeState.IDLE_SAFE
        assert metrics.counts["runtime.errors"] == 1
