from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from ..contracts import MarketResult, MarketStateSnapshot, PaperOrder, PaperOrderStatus, PaperPosition


@dataclass(frozen=True)
class PaperFillEvent:
    order_id: str
    market_id: str
    side: str
    fill_price: float
    fill_ts: str


class PaperExecutionEngine:
    """Conservative paper execution:

    - Resting order fills only if last trade touches/crosses quote OR
      if top of book moves through quote level.
    """

    def place_order(self, market_id: str, side: str, price: float, size: float) -> PaperOrder:
        return PaperOrder(
            order_id=f"ord_{uuid4().hex[:12]}",
            market_id=market_id,
            side=side,
            price=price,
            size=size,
            status=PaperOrderStatus.RESTING,
            created_ts=_utc_now(),
        )

    @staticmethod
    def should_fill(order: PaperOrder, snapshot: MarketStateSnapshot) -> bool:
        if order.status != PaperOrderStatus.RESTING:
            return False

        if snapshot.last_trade_price is not None:
            if order.side == "YES" and snapshot.last_trade_price <= order.price:
                return True
            if order.side == "NO" and snapshot.last_trade_price <= order.price:
                return True

        if order.side == "YES" and snapshot.best_ask is not None and snapshot.best_ask <= order.price:
            return True
        if order.side == "NO" and snapshot.best_bid is not None and snapshot.best_bid <= order.price:
            return True

        return False

    def fill_order(self, order: PaperOrder, fill_price: Optional[float] = None) -> PaperFillEvent:
        order.status = PaperOrderStatus.FILLED
        order.filled_ts = _utc_now()
        return PaperFillEvent(
            order_id=order.order_id,
            market_id=order.market_id,
            side=order.side,
            fill_price=fill_price if fill_price is not None else order.price,
            fill_ts=order.filled_ts,
        )

    @staticmethod
    def cancel_order(order: PaperOrder, reason: str) -> None:
        order.status = PaperOrderStatus.CANCELLED
        order.cancelled_ts = _utc_now()
        order.cancel_reason = reason

    @staticmethod
    def apply_fill(position: PaperPosition, fill: PaperFillEvent, size: float) -> None:
        if fill.side == "YES":
            total_cost = position.avg_yes_price * position.yes_size + fill.fill_price * size
            position.yes_size += size
            position.avg_yes_price = total_cost / max(position.yes_size, 1e-9)
            position.fill_count_yes += 1
        else:
            total_cost = position.avg_no_price * position.no_size + fill.fill_price * size
            position.no_size += size
            position.avg_no_price = total_cost / max(position.no_size, 1e-9)
            position.fill_count_no += 1
        position.net_exposure = position.yes_size + position.no_size

    @staticmethod
    def resolve_market(position: PaperPosition, outcome: str, market_id: str) -> MarketResult:
        yes_settlement = 1.0 if outcome.upper() == "YES" else 0.0
        no_settlement = 1.0 - yes_settlement

        yes_pnl = (yes_settlement - position.avg_yes_price) * position.yes_size
        no_pnl = (no_settlement - position.avg_no_price) * position.no_size
        gross = yes_pnl + no_pnl
        position.resolved_pnl = round(gross, 6)

        return MarketResult(
            market_id=market_id,
            resolved_outcome=outcome.upper(),
            resolution_ts=_utc_now(),
            gross_pnl=round(gross, 6),
            fees=0.0,
            rebates=0.0,
            net_pnl=round(gross, 6),
        )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
