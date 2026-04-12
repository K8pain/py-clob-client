from __future__ import annotations

import csv
import random
from dataclasses import dataclass, field
from pathlib import Path

from . import config
from .models import BotMetrics, Fill, Inventory, MarketTick
from .strategy import build_quotes, fee_equivalent


@dataclass
class MadawcV3Bot:
    cycles: int = config.SIMULATION_CYCLES
    inventory: Inventory = field(default_factory=Inventory)
    metrics: BotMetrics = field(default_factory=BotMetrics)

    def run_all(self, output_dir: Path) -> dict[str, float]:
        rng = random.Random(config.SIMULATION_RANDOM_SEED)
        output_dir.mkdir(parents=True, exist_ok=True)
        ticks_file = output_dir / "ticks.csv"
        with ticks_file.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["cycle", "yes_mid", "no_mid", "yes_bid", "yes_ask", "no_bid", "no_ask", "net_yes"])
            mid = config.SIMULATION_BASE_PRICE
            for cycle in range(1, self.cycles + 1):
                shock = rng.uniform(-config.SIMULATION_VOLATILITY, config.SIMULATION_VOLATILITY)
                mid = max(0.05, min(0.95, mid + shock))
                tick = MarketTick(cycle=cycle, yes_mid=mid, no_mid=1.0 - mid, spread=0.01)
                quotes = build_quotes(tick, self.inventory)
                self._simulate_fill_and_pnl(tick, quotes, rng)
                writer.writerow([cycle, round(mid, 6), round(1.0 - mid, 6), round(quotes.yes_bid, 6), round(quotes.yes_ask, 6), round(quotes.no_bid, 6), round(quotes.no_ask, 6), round(self.inventory.net_yes, 6)])

        self.metrics.directional_mtm = self.inventory.net_yes * (mid - config.SIMULATION_BASE_PRICE)
        return {
            "spread_pnl": round(self.metrics.spread_pnl, 4),
            "merge_pnl": round(self.metrics.merge_pnl, 4),
            "split_sell_pnl": round(self.metrics.split_sell_pnl, 4),
            "taker_fees": round(self.metrics.taker_fees, 4),
            "rebate_income": round(self.metrics.rebate_income, 4),
            "reward_income": round(self.metrics.reward_income, 4),
            "directional_mtm": round(self.metrics.directional_mtm, 4),
            "total_realized": round(self.metrics.total_realized, 4),
            "net_yes_inventory": round(self.inventory.net_yes, 4),
        }

    def _simulate_fill_and_pnl(self, tick: MarketTick, quotes, rng: random.Random) -> None:
        qty = config.SIMULATION_SIZE
        maker_buy = Fill(side="YES", qty=qty, price=quotes.yes_bid, maker=True)
        maker_sell = Fill(side="YES", qty=qty, price=quotes.yes_ask, maker=True)

        self.metrics.spread_pnl += qty * (maker_sell.price - maker_buy.price)
        self.metrics.rebate_income += fee_equivalent(qty, tick.yes_mid, config.FEE_RATE_BPS) * 0.10
        self.metrics.reward_income += fee_equivalent(qty, tick.yes_mid, config.FEE_RATE_BPS) * 0.08

        if rng.random() < config.TAKER_FRACTION:
            self.metrics.taker_fees += fee_equivalent(qty, tick.yes_mid, config.FEE_RATE_BPS)

        if config.ENABLE_PAIR_MERGE:
            yes_buy = quotes.yes_bid
            no_buy = quotes.no_bid
            edge = 1.0 - yes_buy - no_buy
            if edge >= config.MERGE_EDGE_MIN:
                self.metrics.merge_pnl += qty * edge

        if config.ENABLE_SPLIT_SELL:
            yes_sell = quotes.yes_ask
            no_sell = quotes.no_ask
            edge = yes_sell + no_sell - 1.0
            if edge >= config.SPLIT_SELL_EDGE_MIN:
                self.metrics.split_sell_pnl += qty * edge
