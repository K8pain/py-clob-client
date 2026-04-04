"""Motor de paper trading para simular órdenes y cierres de posición."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .models import (
    FillReport,
    Ledger,
    OrderBookSnapshot,
    OrderStatus,
    PaperOrder,
    PaperPosition,
    PositionStatus,
    SettlementReport,
    SignalCandidate,
)


@dataclass
class PaperExecutionEngine:
    ledger: Ledger
    allow_negative_cash: bool = True
    open_orders: dict[str, PaperOrder] = field(default_factory=dict)
    positions: dict[str, PaperPosition] = field(default_factory=dict)
    last_fill_report: FillReport | None = None
    last_settlement_report: SettlementReport | None = None

    def create_order(self, signal: SignalCandidate) -> PaperOrder | None:
        reserved = signal.price * signal.size
        # Reserva caja antes de crear orden para mantener consistencia del ledger.
        if not self.ledger.reserve(reserved, allow_negative=self.allow_negative_cash):
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
            self.last_fill_report = None
            return 0.0

        # Simulación de fill por profundidad visible al precio límite o mejor.
        fillable = min(order.remaining, book.depth_at_or_better(order.limit_price))
        if fillable <= 0:
            self.last_fill_report = None
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
            # Orden completamente ejecutada: cierra y libera reserva no usada.
            order.status = OrderStatus.FILLED
            order.closed_at_utc = datetime.now(timezone.utc).isoformat()
            order.close_reason = "filled"
            unused = max(0.0, order.reserved_cash - (order.filled_size * order.limit_price))
            if unused > 0:
                self.ledger.release(unused)
            state = "PSEUDO_ORDER_FILLED"
        else:
            # Fill parcial: la orden permanece abierta para próximos ciclos.
            state = "PSEUDO_ORDER_PARTIAL_FILL"
        self.last_fill_report = FillReport(
            fill_size=fillable,
            average_fill_price=order.limit_price,
            remaining_size=order.remaining,
            remaining_reserved_cash=max(0.0, order.reserved_cash - (order.filled_size * order.limit_price)),
            state=state,
        )
        return fillable

    def expire_order(self, paper_order_id: str, cancelled: bool = False) -> None:
        order = self.open_orders[paper_order_id]
        if order.status != OrderStatus.OPEN:
            return
        order.status = OrderStatus.CANCELLED_LOCAL if cancelled else OrderStatus.EXPIRED
        order.closed_at_utc = datetime.now(timezone.utc).isoformat()
        order.close_reason = "local_cancel_rule" if cancelled else "expired"
        unused = max(0.0, order.reserved_cash - (order.filled_size * order.limit_price))
        if unused > 0:
            self.ledger.release(unused)

    def settle_market(self, market_id: str, winner_token_id: str | None) -> PaperPosition | None:
        pos = self.positions.get(market_id)
        if pos is None:
            self.last_settlement_report = None
            return None

        if winner_token_id is None:
            pos.status = PositionStatus.PENDING_RESOLUTION
            self.last_settlement_report = None
            return pos

        payout = pos.size if pos.token_id == winner_token_id else 0.0
        # Mercado binario: payoff final por share es 1.0 si acierta, 0.0 si falla.
        gross = payout - (pos.avg_price * pos.size)
        pos.pnl_gross = gross
        pos.pnl_net = gross
        basis = pos.avg_price * pos.size
        pos.return_pct = (gross / basis) if basis else 0.0
        pos.status = PositionStatus.WON if payout > 0 else PositionStatus.LOST
        pos.settled_at_utc = datetime.now(timezone.utc).isoformat()
        self.ledger.cash_available += payout
        opened = datetime.fromisoformat(pos.opened_at_utc)
        settled = datetime.fromisoformat(pos.settled_at_utc)
        self.last_settlement_report = SettlementReport(
            market_id=pos.market_id,
            token_id=pos.token_id,
            outcome="WIN" if pos.status == PositionStatus.WON else "LOSS",
            gross_stake=basis,
            gross_payoff=payout,
            net_pnl=gross,
            roi_percent=(pos.return_pct or 0.0) * 100.0,
            holding_duration_seconds=max(0, int((settled - opened).total_seconds())),
            result_class="WIN" if pos.status == PositionStatus.WON else "LOSS",
            filled_size=pos.size,
            average_fill_price=pos.avg_price,
            partial_fill=False,
        )
        return pos
