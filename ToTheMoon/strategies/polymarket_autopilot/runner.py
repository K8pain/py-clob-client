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


def run_once(autopilot: PolymarketAutopilot, simulation_days: int = 180) -> Path:
    result = autopilot.run_simulation(cycles=max(1, simulation_days))
    summary_path = autopilot.publish_window_summary(lookback_days=max(1, simulation_days))
    print(
        "[polymarket-autopilot] simulación completada | "
        f"days={result['cycles']} | snapshots={result['snapshots']} | "
        f"executed_trades={result['executed_trades']} | closed_positions={result['closed_positions']}"
    )
    print(f"[polymarket-autopilot] resumen guardado en: {summary_path}")
    return summary_path


def run_scheduler(autopilot: PolymarketAutopilot) -> None:
    print("[polymarket-autopilot] scheduler activo. Publicará resumen diario a las 08:00 (ventana 180 días).")
    autopilot.run_daily_scheduler()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Polymarket Autopilot runner (paper trading only)")
    parser.add_argument(
        "--base-path",
        type=Path,
        default=Path("ToTheMoon/strategies/polymarket_autopilot"),
        help="Directorio base para data/ y logs/.",
    )
    parser.add_argument(
        "--mode",
        choices=["once", "scheduler"],
        default="once",
        help="once: ejecuta simulación y genera resumen. scheduler: loop diario 08:00.",
    )
    parser.add_argument(
        "--simulation-days",
        type=int,
        default=180,
        help="Ventana de simulación/resumen para modo once (recomendado: 90 o 180).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    autopilot = build_autopilot(base_path=args.base_path)
    try:
        if args.mode == "scheduler":
            run_scheduler(autopilot)
            return 0

        run_once(autopilot, simulation_days=args.simulation_days)
        return 0
    except Exception as exc:
        print(f"[polymarket-autopilot] error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
