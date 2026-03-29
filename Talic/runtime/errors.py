class TransientError(Exception):
    """An operation failed and may succeed if retried."""


class PermanentError(Exception):
    """An operation failed and should not be retried."""


class InternalError(Exception):
    """An unexpected runtime invariant failure."""
