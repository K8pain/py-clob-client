from __future__ import annotations

import argparse
import csv
import importlib
import json
import logging
import time
from pathlib import Path

from . import config
from .bot import MM001Bot


def _setup_logger(log_file: Path, log_level: str = "INFO") -> logging.Logger:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    level = getattr(logging, str(log_level).upper(), logging.INFO)
    logger = logging.getLogger("mm001-launcher")
    logger.setLevel(level)
    logger.handlers.clear()
    handler = logging.FileHandler(log_file, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    logger.addHandler(handler)
    return logger


def _append_cycle_aggregate_log(cycle_log_file: Path, loop_iteration: int, summary: dict[str, float]) -> None:
    cycle_log_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "loop_iteration": loop_iteration,
        "summary": summary,
    }
    with cycle_log_file.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _format_launcher_metrics_table(loop_iteration: int, summary: dict[str, float]) -> str:
    inventory_state = summary.get("current_inventory_state", {}) or {}
    stuck_market = summary.get("largest_inventory_stuck_market", {}) or {}
    rows = [
        ("loop_iteration", str(loop_iteration)),
        ("cumulative_realized_pnl_net", f"{float(summary.get('cumulative_realized_pnl_net', 0.0)):.4f}"),
        ("win_rate", f"{float(summary.get('win_rate', 0.0)):.4f}"),
        ("average_pnl_per_cycle", f"{float(summary.get('average_pnl_per_cycle', 0.0)):.4f}"),
        ("average_win_pnl", f"{float(summary.get('average_win_pnl', 0.0)):.4f}"),
        ("average_loss_pnl", f"{float(summary.get('average_loss_pnl', 0.0)):.4f}"),
        ("fill_count", str(int(summary.get("fill_count", 0)))),
        ("current_inventory_state", json.dumps(inventory_state, ensure_ascii=False, sort_keys=True)),
        (
            "largest_inventory_stuck_market",
            json.dumps(stuck_market, ensure_ascii=False, sort_keys=True),
        ),
    ]
    key_width = max(len(key) for key, _ in rows)
    val_width = max(len(value) for _, value in rows)
    border = f"+-{'-' * key_width}-+-{'-' * val_width}-+"
    body = "\n".join(f"| {key:<{key_width}} | {value:>{val_width}} |" for key, value in rows)
    return f"{border}\n{body}\n{border}"


def _append_trades_log(output_dir: Path, trades_log_file: Path, loop_iteration: int) -> None:
    ticks_file = output_dir / "ticks.csv"
    if not ticks_file.exists():
        return
    trades_log_file.parent.mkdir(parents=True, exist_ok=True)
    with ticks_file.open("r", encoding="utf-8", newline="") as src, trades_log_file.open("a", encoding="utf-8") as out:
        for row in csv.DictReader(src):
            out.write(
                f"loop={loop_iteration} cycle={row.get('cycle', '')} yes_mid={row.get('yes_mid', '')} "
                f"no_mid={row.get('no_mid', '')} net_yes={row.get('net_yes', '')} "
                f"taker_trade={row.get('taker_trade', '0')} total_realized_cum={row.get('total_realized_cum', '')}\n"
            )


def _load_bot(factory_ref: str, db_path: Path) -> MM001Bot:
    module_name, sep, attr_name = factory_ref.partition(":")
    if not sep:
        raise ValueError("factory debe tener formato modulo:funcion")
    module = importlib.import_module(module_name)
    factory = getattr(module, attr_name)
    if not callable(factory):
        raise TypeError("factory debe ser callable")
    bot = factory(db_path=str(db_path))
    if not isinstance(bot, MM001Bot):
        raise TypeError("factory debe retornar MM001Bot")
    return bot


def _run_iteration(
    factory_ref: str,
    db_path: Path,
    output_dir: Path,
    trades_log_file: Path,
    cycle_log_file: Path,
    loop_iteration: int,
    logger: logging.Logger,
) -> dict[str, float]:
    bot = _load_bot(factory_ref, db_path)
    summary = bot.run_all(output_dir=output_dir)
    summary_path = output_dir / "simulation_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    _append_trades_log(output_dir, trades_log_file, loop_iteration)
    _append_cycle_aggregate_log(cycle_log_file, loop_iteration, summary)
    logger.info("mm001.metrics.table\n%s", _format_launcher_metrics_table(loop_iteration, summary))
    logger.info(
        "iteration=%s spread_pnl=%s taker_trades=%s total_realized=%s net_yes_inventory=%s",
        loop_iteration,
        summary.get("spread_pnl"),
        summary.get("taker_trades"),
        summary.get("total_realized"),
        summary.get("net_yes_inventory"),
    )
    print(json.dumps(summary, indent=2), flush=True)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="MM001 launcher")
    parser.add_argument("--all", action="store_true", help="run full MVP simulation flow")
    parser.add_argument("--factory", default="mmaker001.MM001.factory:build_bot")
    parser.add_argument("--db-path", default=str(config.DEFAULT_DB_PATH))
    parser.add_argument("--output-dir", default=str(config.DEFAULT_OUTPUT_DIR))
    parser.add_argument("--log-file", default="var/mm001/mm001-launcher.log")
    parser.add_argument("--trades-log-file", default="var/mm001/mm001-trades.log")
    parser.add_argument("--aggregate-log-file", default="var/mm001/reports/cycle_aggregates.jsonl")
    parser.add_argument("--log-level", choices=("DEBUG", "INFO", "WARNING", "ERROR"), default="INFO")
    parser.add_argument("--interval-seconds", type=float, default=240.0)
    parser.add_argument("--max-runs", type=int, default=0, help="0=loop infinito, >0 límite de iteraciones")
    args = parser.parse_args()

    if not args.all:
        raise SystemExit("Usa --all para ejecutar el flujo completo del MVP.")

    db_path = Path(args.db_path)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    logger = _setup_logger(Path(args.log_file), log_level=args.log_level)
    logger.info("loop started interval_seconds=%s", args.interval_seconds)

    iteration = 0
    while True:
        iteration += 1
        _run_iteration(
            args.factory,
            db_path,
            output_dir,
            Path(args.trades_log_file),
            Path(args.aggregate_log_file),
            iteration,
            logger,
        )
        if args.max_runs > 0 and iteration >= args.max_runs:
            break
        time.sleep(max(0.0, args.interval_seconds))


if __name__ == "__main__":
    main()
