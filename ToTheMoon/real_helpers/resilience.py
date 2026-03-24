import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import TypeVar


T = TypeVar("T")
RETRIABLE_ERRORS = (TimeoutError, ConnectionError)


def api_timeout_guard(operation: Callable[[], T], timeout_seconds: float) -> T:
    """Run operation with a hard timeout and raise TimeoutError on expiration."""
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(operation)
        try:
            return future.result(timeout=timeout_seconds)
        except FutureTimeoutError as exc:
            future.cancel()
            raise TimeoutError("operation timed out") from exc


def retry_with_backoff(
    operation: Callable[[], T],
    max_attempts: int,
    base_delay_seconds: float = 0.1,
    sleeper: Callable[[float], None] | None = None,
) -> T:
    sleeper = sleeper or time.sleep
    for attempt in range(1, max_attempts + 1):
        try:
            return operation()
        except RETRIABLE_ERRORS:
            if attempt == max_attempts:
                raise
            sleeper(base_delay_seconds * (2 ** (attempt - 1)))



def heartbeat_monitor(last_heartbeat_ts: float, threshold_seconds: float, now: float | None = None) -> bool:
    now = now if now is not None else time.time()
    return (now - last_heartbeat_ts) > threshold_seconds


def restart_stalled_worker(is_stale: bool, restart_fn: Callable[[], None], alert_fn: Callable[[str], None]) -> bool:
    if not is_stale:
        return False
    restart_fn()
    alert_fn("worker_restarted_after_stall")
    return True
