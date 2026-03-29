"""Minimal Talic runtime entrypoint with explicit dependency wiring."""

import argparse
import logging
from typing import Any, Iterable, Mapping

from Talic.runtime.degradation import update_state_for_error
from Talic.runtime.engine import process_events
from Talic.runtime.idempotency import OperationLedger
from Talic.runtime.mode import ModeState
from Talic.runtime.retry_policy import run_with_retry
from Talic.runtime.validators import validate_external_response, validate_handler_input


class Metrics:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    def increment(self, key: str) -> None:
        self.counts[key] = self.counts.get(key, 0) + 1


def _build_logger() -> logging.Logger:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    return logging.getLogger("talic")


def _build_dependencies() -> tuple[OperationLedger[Mapping[str, Any]], logging.Logger, Metrics]:
    ledger: OperationLedger[Mapping[str, Any]] = OperationLedger()
    logger = _build_logger()
    metrics = Metrics()
    return ledger, logger, metrics


def _mutate_handler(event: Mapping[str, Any]) -> Mapping[str, Any]:
    return {"status": "mutated", "event": event.get("idempotency_key")}


def _external_call(event: Mapping[str, Any]) -> Mapping[str, Any]:
    return {"status": "ok", "event": event.get("idempotency_key")}


def _demo_events() -> Iterable[Mapping[str, Any]]:
    return [
        {"idempotency_key": "m1", "type": "mutation"},
        {"idempotency_key": "e1", "type": "external_call"},
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Talic runtime loop")
    parser.add_argument("--mode", default=ModeState.NORMAL.value, choices=[m.value for m in ModeState])
    parser.add_argument("--demo", action="store_true", help="Run with built-in demo events")
    args = parser.parse_args()

    ledger, logger, metrics = _build_dependencies()
    mode = ModeState(args.mode)
    events = _demo_events() if args.demo else []

    final_mode = process_events(
        events,
        mode=mode,
        validate_input=validate_handler_input,
        validate_external_response=validate_external_response,
        mutate_handler=_mutate_handler,
        external_call=_external_call,
        retry_policy=lambda fn: run_with_retry(fn, logger),
        ledger=ledger,
        logger=logger,
        metrics=metrics,
        update_mode_for_error=update_state_for_error,
    )

    logger.info("Talic runtime finished", extra={"final_mode": final_mode.value, "metrics": metrics.counts})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
