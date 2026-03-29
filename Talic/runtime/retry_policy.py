from tenacity import RetryCallState, Retrying, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

from .errors import TransientError


def _before_sleep_log(retry_state: RetryCallState, logger) -> None:
    err = retry_state.outcome.exception() if retry_state.outcome else None
    logger.warning(
        "retrying transient failure",
        extra={
            "attempt": retry_state.attempt_number,
            "error": str(err) if err else None,
        },
    )


def run_with_retry(operation, logger, *, max_attempts: int = 3, min_wait: float = 0.2, max_wait: float = 3.0):
    retryer = Retrying(
        stop=stop_after_attempt(max_attempts),
        retry=retry_if_exception_type(TransientError),
        wait=wait_exponential_jitter(initial=min_wait, max=max_wait),
        before_sleep=lambda s: _before_sleep_log(s, logger),
        reraise=True,
    )
    return retryer(operation)
