from __future__ import annotations

from dataclasses import dataclass

from . import config
from .models import Fill, Inventory, MarketTick


@dataclass
class QuotePlan:
    yes_bid: float
    yes_ask: float
    no_bid: float
    no_ask: float


def fee_equivalent(notional: float, price: float, fee_rate_bps: float) -> float:
    fee_rate = fee_rate_bps / 10_000.0
    return notional * fee_rate * price * (1.0 - price)


def minimum_net_spread(price: float) -> float:
    taker_exit = fee_equivalent(config.SIMULATION_SIZE, price, config.FEE_RATE_BPS) / max(config.SIMULATION_SIZE, 1.0)
    raw = taker_exit + config.ADVERSE_SELECTION_BUFFER + config.LATENCY_BUFFER - config.REBATE_EXPECTED - config.REWARD_EXPECTED
    return max(config.MIN_SPREAD_FLOOR, raw)


def reservation_price(mid_price: float, inventory: Inventory) -> float:
    skew = inventory.net_yes * config.INVENTORY_SKEW_FACTOR
    return max(0.01, min(0.99, mid_price - skew))


def build_quotes(tick: MarketTick, inventory: Inventory) -> QuotePlan:
    r_yes = reservation_price(tick.yes_mid, inventory)
    spread = minimum_net_spread(r_yes)
    half = spread / 2.0
    yes_bid = max(0.01, r_yes - half)
    yes_ask = min(0.99, r_yes + half)

    r_no = max(0.01, min(0.99, 1.0 - r_yes))
    no_bid = max(0.01, r_no - half)
    no_ask = min(0.99, r_no + half)
    return QuotePlan(yes_bid=yes_bid, yes_ask=yes_ask, no_bid=no_bid, no_ask=no_ask)


def apply_fill(inventory: Inventory, fill: Fill) -> None:
    signed_qty = fill.qty if fill.side == "YES" else -fill.qty
    inventory.cash -= fill.qty * fill.price
    inventory.yes += max(signed_qty, 0.0)
    inventory.no += max(-signed_qty, 0.0)
