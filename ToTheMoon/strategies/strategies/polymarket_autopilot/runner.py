from __future__ import annotations

import argparse
from pathlib import Path

from .service import PolymarketAutopilot, StrategyConfig
from .storage import PaperTradingStore


def build_autopilot(base_path: Path, config: StrategyConfig | None = None) -> PolymarketAutopilot:
    strategy_config = config or StrategyConfig()
    store = PaperTradingStore(
        db_path=base_path / "data" / "paper_trading.db",
        starting_capital=strategy_config.starting_capital,
    )
    return PolymarketAutopilot(
        store=store,
        log_directory=base_path / "logs",
        config=strategy_config,
    )


def run_once(autopilot: PolymarketAutopilot) -> Path:
    result = autopilot.run_cycle()
    summary_path = autopilot.publish_daily_summary()
    print(
        "[polymarket-autopilot] ciclo completado | "
        f"snapshots={result['snapshots']} | executed_trades={result['executed_trades']} | "
        f"closed_positions={result['closed_positions']}"
    )
    print(f"[polymarket-autopilot] resumen guardado en: {summary_path}")
    return summary_path


def run_scheduler(autopilot: PolymarketAutopilot) -> None:
    print("[polymarket-autopilot] scheduler activo. Publicará resumen diario a las 08:00.")
    autopilot.run_daily_scheduler()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Polymarket Autopilot runner (paper trading only)")
    parser.add_argument(
        "--base-path",
        type=Path,
        default=Path("strategies/polymarket_autopilot"),
        help="Directorio base para data/ y logs/.",
    )
    parser.add_argument(
        "--mode",
        choices=["once", "scheduler"],
        default="once",
        help="once: ejecuta un ciclo y genera resumen. scheduler: loop diario 08:00.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    autopilot = build_autopilot(base_path=args.base_path)
    try:
        if args.mode == "scheduler":
            run_scheduler(autopilot)
            return 0

        run_once(autopilot)
        return 0
    except Exception as exc:
        print(f"[polymarket-autopilot] error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
