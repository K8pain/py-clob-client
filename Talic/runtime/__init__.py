"""Runtime primitives for Talic handlers."""

from .degradation import apply_recovery, update_state_for_error
from .engine import process_events
from .errors import InternalError, PermanentError, TransientError
from .mode import ModeState, transition_to

__all__ = [
    "ModeState",
    "transition_to",
    "TransientError",
    "PermanentError",
    "InternalError",
    "update_state_for_error",
    "apply_recovery",
    "process_events",
]
