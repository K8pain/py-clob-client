from .errors import InternalError, PermanentError, TransientError
from .mode import ModeState, transition_to


def update_state_for_error(
    current: ModeState,
    err: Exception,
    *,
    transient_failures: int,
    retry_exhausted: bool,
    retry_threshold: int = 2,
) -> ModeState:
    if isinstance(err, (InternalError, PermanentError)):
        return transition_to(current, ModeState.IDLE_SAFE)

    if isinstance(err, TransientError):
        if retry_exhausted:
            return transition_to(current, ModeState.READ_ONLY)
        if transient_failures >= retry_threshold:
            return transition_to(current, ModeState.RETRYING)

    return current


def apply_recovery(current: ModeState) -> ModeState:
    return transition_to(current, ModeState.NORMAL)
