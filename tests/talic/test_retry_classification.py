import pytest

from Talic.runtime.degradation import update_state_for_error
from Talic.runtime.errors import PermanentError, TransientError
from Talic.runtime.mode import ModeState
from Talic.runtime.retry_policy import run_with_retry


class _Logger:
    def warning(self, *args, **kwargs):
        return None


def test_only_transient_error_is_retried():
    logger = _Logger()

    transient_attempts = {"count": 0}

    def transient_operation():
        transient_attempts["count"] += 1
        if transient_attempts["count"] < 3:
            raise TransientError("temporary network error")
        return "ok"

    assert run_with_retry(transient_operation, logger, max_attempts=3, min_wait=0, max_wait=0) == "ok"
    assert transient_attempts["count"] == 3

    permanent_attempts = {"count": 0}

    def permanent_operation():
        permanent_attempts["count"] += 1
        raise PermanentError("schema contract violation")

    with pytest.raises(PermanentError):
        run_with_retry(permanent_operation, logger, max_attempts=5, min_wait=0, max_wait=0)

    assert permanent_attempts["count"] == 1


def test_bounded_attempts_and_transition_to_read_only_on_exhaustion():
    logger = _Logger()
    attempts = {"count": 0}

    def always_fails():
        attempts["count"] += 1
        raise TransientError("timeout")

    with pytest.raises(TransientError):
        run_with_retry(always_fails, logger, max_attempts=2, min_wait=0, max_wait=0)

    assert attempts["count"] == 2

    next_mode = update_state_for_error(
        ModeState.RETRYING,
        TransientError("timeout"),
        transient_failures=attempts["count"],
        retry_exhausted=True,
    )
    assert next_mode == ModeState.READ_ONLY
