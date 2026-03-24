from __future__ import annotations

from .models import FillRecord


def summarize_trades(fills: list[FillRecord]) -> dict[str, float]:
    gross = sum(fill.price * fill.size for fill in fills)
    fees = sum(fill.fee for fill in fills)
    count = len(fills)
    avg_notional = gross / count if count else 0.0
    return {
        "trade_count": float(count),
        "gross_notional": round(gross, 6),
        "total_fees": round(fees, 6),
        "avg_notional_per_trade": round(avg_notional, 6),
    }
