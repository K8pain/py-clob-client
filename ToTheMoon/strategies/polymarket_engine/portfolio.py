from __future__ import annotations

from .models import FillRecord, OrderSide, Position, PositionSide


class Portfolio:
    def __init__(self) -> None:
        self.positions: dict[str, Position] = {}

    def apply_fill(self, fill: FillRecord, market_id: str, side: OrderSide, position_side: PositionSide) -> Position:
        position = self.positions.get(fill.token_id)
        if position is None:
            position = Position(token_id=fill.token_id, market_id=market_id, side=position_side)
            self.positions[fill.token_id] = position
        signed_qty = fill.size if side == OrderSide.BUY else -fill.size
        new_qty = position.net_qty + signed_qty
        if signed_qty > 0:
            total_cost = (position.avg_cost * position.net_qty) + (fill.price * fill.size) + fill.fee
            position.avg_cost = 0.0 if new_qty == 0 else total_cost / max(new_qty, 1e-9)
        else:
            position.realized_pnl += ((fill.price - position.avg_cost) * fill.size) - fill.fee
        position.net_qty = round(new_qty, 6)
        return position

    def snapshot(self) -> list[Position]:
        return list(self.positions.values())
