from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import datetime, timedelta, timezone
from typing import Any, Callable


def api_timeout_guard(operation: Callable[..., Any], timeout_seconds: float, *args: Any, **kwargs: Any) -> Any:
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(operation, *args, **kwargs)
        try:
            return future.result(timeout=timeout_seconds)
        except FuturesTimeoutError as exc:
            raise TimeoutError("operation timed out") from exc


def retry_with_backoff(
    operation: Callable[[], Any],
    retriable_exceptions: tuple[type[BaseException], ...],
    max_attempts: int = 3,
    base_delay_seconds: float = 0.1,
    sleeper: Callable[[float], None] = time.sleep,
) -> Any:
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")

    for attempt in range(1, max_attempts + 1):
        try:
            return operation()
        except retriable_exceptions:
            if attempt == max_attempts:
                raise
            sleeper(base_delay_seconds * (2 ** (attempt - 1)))


def heartbeat_monitor(
    last_heartbeat: datetime,
    heartbeat_timeout_seconds: float,
    now: datetime | None = None,
) -> bool:
    current_time = now or datetime.now(tz=timezone.utc)
    return current_time - last_heartbeat > timedelta(seconds=heartbeat_timeout_seconds)


def restart_stalled_worker(
    stale_detected: bool,
    restart_worker: Callable[[], None],
    alert_operator: Callable[[str], None],
) -> bool:
    if not stale_detected:
        return False
    restart_worker()
    alert_operator("worker restarted due to stale heartbeat")
    return True
