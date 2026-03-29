from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from .models import Ledger, OrderBookSnapshot, OrderStatus, PaperOrder, PaperPosition, PositionStatus, SignalCandidate


@dataclass
class PaperExecutionEngine:
    ledger: Ledger
    open_orders: dict[str, PaperOrder] = field(default_factory=dict)
    positions: dict[str, PaperPosition] = field(default_factory=dict)

    def create_order(self, signal: SignalCandidate) -> PaperOrder | None:
        reserved = signal.price * signal.size
        if not self.ledger.reserve(reserved):
            return None

        order = PaperOrder(
            paper_order_id=f"paper-{uuid.uuid4().hex[:12]}",
            market_id=signal.market_id,
            token_id=signal.token_id,
            limit_price=signal.price,
            requested_size=signal.size,
            reserved_cash=reserved,
        )
        self.open_orders[order.paper_order_id] = order
        return order

    def try_fill(self, order: PaperOrder, book: OrderBookSnapshot) -> float:
        if order.status != OrderStatus.OPEN:
            return 0.0

        fillable = min(order.remaining, book.depth_at_or_better(order.limit_price))
        if fillable <= 0:
            return 0.0

        order.filled_size += fillable
        used_cash = fillable * order.limit_price
        self.ledger.cash_reserved -= used_cash
        self.ledger.add_holding(order.token_id, fillable)

        pos = self.positions.get(order.market_id)
        if pos is None:
            pos = PaperPosition(market_id=order.market_id, token_id=order.token_id, size=fillable, avg_price=order.limit_price)
            self.positions[order.market_id] = pos
        else:
            total = pos.size + fillable
            pos.avg_price = ((pos.avg_price * pos.size) + used_cash) / max(total, 1e-9)
            pos.size = total

        if order.remaining <= 1e-9:
            order.status = OrderStatus.FILLED
            unused = max(0.0, order.reserved_cash - (order.filled_size * order.limit_price))
            if unused > 0:
                self.ledger.release(unused)
        return fillable

    def expire_order(self, paper_order_id: str, cancelled: bool = False) -> None:
        order = self.open_orders[paper_order_id]
        if order.status != OrderStatus.OPEN:
            return
        order.status = OrderStatus.CANCELLED_LOCAL if cancelled else OrderStatus.EXPIRED
        unused = max(0.0, order.reserved_cash - (order.filled_size * order.limit_price))
        if unused > 0:
            self.ledger.release(unused)

    def settle_market(self, market_id: str, winner_token_id: str | None) -> PaperPosition | None:
        pos = self.positions.get(market_id)
        if pos is None:
            return None

        if winner_token_id is None:
            pos.status = PositionStatus.PENDING_RESOLUTION
            return pos

        payout = pos.size if pos.token_id == winner_token_id else 0.0
        gross = payout - (pos.avg_price * pos.size)
        pos.pnl_gross = gross
        pos.pnl_net = gross
        basis = pos.avg_price * pos.size
        pos.return_pct = (gross / basis) if basis else 0.0
        pos.status = PositionStatus.WON if payout > 0 else PositionStatus.LOST
        self.ledger.cash_available += payout
        return pos
