from typing import Any, Callable, Iterable, Mapping

from .errors import InternalError, PermanentError, TransientError
from .mode import ModeState


def process_events(
    events: Iterable[Mapping[str, Any]],
    *,
    mode: ModeState,
    validate_input: Callable[[Mapping[str, Any]], None],
    validate_external_response: Callable[[Mapping[str, Any]], None],
    mutate_handler: Callable[[Mapping[str, Any]], Any],
    external_call: Callable[[Mapping[str, Any]], Mapping[str, Any]],
    retry_policy: Callable[[Callable[[], Any]], Any],
    ledger,
    logger,
    metrics,
    update_mode_for_error: Callable[..., ModeState],
    max_iterations: int = 100,
    wait_seconds: float = 0.0,
    sleeper: Callable[[float], None] = lambda _: None,
) -> ModeState:
    transient_failures = 0

    for iteration, event in enumerate(events):
        if iteration >= max_iterations:
            break

        validate_input(event)

        event_type = event.get("type")
        idempotency_key = event.get("idempotency_key")
        if not idempotency_key:
            raise ValueError("idempotency_key is required")

        existing = ledger.get(idempotency_key)
        if existing is not None:
            logger.info("replayed idempotency key", extra={"idempotency_key": idempotency_key})
            metrics.increment("runtime.idempotent_replay")
            continue

        try:
            if mode == ModeState.IDLE_SAFE and event_type == "external_call":
                raise InternalError("external calls are not allowed in IDLE_SAFE")

            if event_type == "mutation":
                if mode != ModeState.NORMAL:
                    raise PermanentError(f"mutating operations require NORMAL mode, got {mode.value}")
                result = mutate_handler(event)
            elif event_type == "external_call":
                result = retry_policy(lambda: external_call(event))
                validate_external_response(result)
            else:
                result = {"status": "ignored", "type": event_type}

            ledger.record(idempotency_key, result)
            transient_failures = 0
            metrics.increment("runtime.processed")

        except Exception as err:  # noqa: BLE001
            retry_exhausted = isinstance(err, TransientError)
            transient_failures += 1 if isinstance(err, TransientError) else 0
            mode = update_mode_for_error(
                mode,
                err,
                transient_failures=transient_failures,
                retry_exhausted=retry_exhausted,
            )
            metrics.increment("runtime.errors")
            logger.error("event processing failed", extra={"mode": mode.value, "error": str(err)})

        if wait_seconds > 0:
            sleeper(wait_seconds)

    return mode
