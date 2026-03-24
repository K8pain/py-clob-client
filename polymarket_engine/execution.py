from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from uuid import uuid4

from .models import FillRecord, OrderEvent, OrderRequest
from .storage import CsvStore


class PaperExecutionAdapter:
    def __init__(self, store: CsvStore, fee_bps: float = 0.0):
        self.store = store
        self.fee_bps = fee_bps

    def execute(self, order: OrderRequest, best_bid: float, best_ask: float) -> tuple[OrderEvent, FillRecord]:
        order_id = f"paper-{uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()
        price = best_ask if order.side.value == "BUY" else best_bid
        fee = round(price * order.size * self.fee_bps / 10000, 6)
        event = OrderEvent(
            order_id=order_id,
            token_id=order.token_id,
            market_id=order.market_id,
            status="filled",
            side=order.side.value,
            price=price,
            size=order.size,
            created_at=now,
            reason=order.signal_reason,
        )
        fill = FillRecord(
            fill_id=f"fill-{uuid4().hex[:12]}",
            order_id=order_id,
            token_id=order.token_id,
            price=price,
            size=order.size,
            fee=fee,
            ts=now,
        )
        self.store.append_rows("execution/order_events.csv", [event.to_row()], unique_by=("order_id",))
        self.store.append_rows("execution/fills.csv", [fill.to_row()], unique_by=("fill_id",))
        return event, fill


class RealExecutionAdapter:
    def __init__(self, client):
        self.client = client

    def execute(self, order: OrderRequest) -> dict:
        return {
            "token_id": order.token_id,
            "side": order.side.value,
            "price": order.price,
            "size": order.size,
            "market_id": order.market_id,
            "signal_reason": order.signal_reason,
            "status": "ready_to_submit",
        }
