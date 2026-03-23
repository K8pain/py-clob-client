from __future__ import annotations

from .config import RiskConfig
from .models import OrderRequest, Position, RiskDecision


def evaluate_risk(order: OrderRequest, positions: list[Position], config: RiskConfig) -> RiskDecision:
    current_market_exposure = sum(position.net_qty * position.avg_cost for position in positions if position.market_id == order.market_id)
    global_exposure = sum(position.net_qty * position.avg_cost for position in positions)
    if current_market_exposure + (order.size * order.price) > config.max_position_per_market:
        return RiskDecision(False, "market_limit_exceeded")
    if global_exposure + (order.size * order.price) > config.max_global_exposure:
        return RiskDecision(False, "global_limit_exceeded")
    open_markets = {position.market_id for position in positions if position.net_qty > 0}
    if order.market_id not in open_markets and len(open_markets) >= config.max_open_positions:
        return RiskDecision(False, "max_open_positions_exceeded")
    return RiskDecision(True, "approved")
