import pytest

from Talic.runtime.degradation import update_state_for_error
from Talic.runtime.errors import InternalError, PermanentError, TransientError
from Talic.runtime.mode import ModeState
from Talic.runtime.retry_policy import run_with_retry
from Talic.runtime.validators import validate_handler_input


class _Logger:
    def warning(self, *args, **kwargs):
        return None


def test_schema_drift_invalid_payload_is_rejected():
    with pytest.raises(TypeError):
        validate_handler_input(["not", "a", "mapping"])


def test_network_timeout_is_treated_as_transient_retryable_error():
    attempts = {"count": 0}

    def flaky_call():
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise TransientError("network timeout")
        return {"ok": True}

    assert run_with_retry(flaky_call, _Logger(), max_attempts=2, min_wait=0, max_wait=0) == {"ok": True}
    assert attempts["count"] == 2


def test_invariant_violations_map_to_safe_degradation():
    assert (
        update_state_for_error(
            ModeState.NORMAL,
            InternalError("state invariant violated"),
            transient_failures=0,
            retry_exhausted=False,
        )
        == ModeState.IDLE_SAFE
    )

    assert (
        update_state_for_error(
            ModeState.NORMAL,
            PermanentError("contract invariant violated"),
            transient_failures=0,
            retry_exhausted=False,
        )
        == ModeState.IDLE_SAFE
    )
