from pathlib import Path

from .service import PolymarketAutopilot, StrategyConfig
from .storage import PaperTradingStore


if __name__ == "__main__":
    base_path = Path("ToTheMoon/strategies/polymarket_autopilot")
    store = PaperTradingStore(
        db_path=base_path / "data" / "paper_trading.db",
        starting_capital=StrategyConfig().starting_capital,
    )
    autopilot = PolymarketAutopilot(
        store=store,
        log_directory=base_path / "logs",
        config=StrategyConfig(),
    )
    autopilot.run_cycle()
    autopilot.publish_daily_summary()
