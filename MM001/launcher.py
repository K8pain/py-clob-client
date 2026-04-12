from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path

from . import config
from .bot import MM001Bot


def _load_bot(factory_ref: str, db_path: Path) -> MM001Bot:
    module_name, sep, attr_name = factory_ref.partition(":")
    if not sep:
        raise ValueError("factory debe tener formato modulo:funcion")
    module = importlib.import_module(module_name)
    factory = getattr(module, attr_name)
    bot = factory(db_path=str(db_path))
    if not isinstance(bot, MM001Bot):
        raise TypeError("factory debe retornar MM001Bot")
    return bot


def main() -> None:
    parser = argparse.ArgumentParser(description="MM001 launcher")
    parser.add_argument("--all", action="store_true", help="run full MVP simulation flow")
    parser.add_argument("--factory", default="MM001.factory:build_bot")
    parser.add_argument("--db-path", default=str(config.DEFAULT_DB_PATH))
    parser.add_argument("--output-dir", default=str(config.DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()

    if not args.all:
        raise SystemExit("Usa --all para ejecutar el flujo completo del MVP.")

    db_path = Path(args.db_path)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    bot = _load_bot(args.factory, db_path)
    summary = bot.run_all(output_dir=output_dir)
    summary_path = output_dir / "simulation_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
