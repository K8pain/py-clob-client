from dataclasses import dataclass
from typing import Any, Dict, Generic, Optional, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class LedgerEntry(Generic[T]):
    idempotency_key: str
    result: T


class OperationLedger(Generic[T]):
    def __init__(self) -> None:
        self._entries: Dict[str, LedgerEntry[T]] = {}

    def get(self, idempotency_key: str) -> Optional[LedgerEntry[T]]:
        return self._entries.get(idempotency_key)

    def has(self, idempotency_key: str) -> bool:
        return idempotency_key in self._entries

    def record(self, idempotency_key: str, result: T) -> LedgerEntry[T]:
        existing = self.get(idempotency_key)
        if existing is not None:
            return existing
        entry = LedgerEntry(idempotency_key=idempotency_key, result=result)
        self._entries[idempotency_key] = entry
        return entry


def run_idempotent(
    ledger: OperationLedger[T],
    idempotency_key: str,
    operation,
) -> T:
    existing = ledger.get(idempotency_key)
    if existing is not None:
        return existing.result

    result = operation()
    return ledger.record(idempotency_key, result).result
