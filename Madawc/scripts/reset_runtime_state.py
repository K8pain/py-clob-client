"""Limpieza manual de estado runtime de MADAWC v2 antes de relanzar."""

from __future__ import annotations

import argparse
from pathlib import Path


DEFAULT_DB_PATH = Path("var/korlic/korlic.sqlite")
DEFAULT_LOG_PATH = Path("var/korlic/korlic-launcher.log")
DEFAULT_TRADES_LOG_PATH = Path("var/korlic/korlic-trades.log")
DEFAULT_REPORTS_PATH = Path("var/korlic/reports")


def _remove_file(path: Path) -> bool:
    if not path.exists():
        return False
    path.unlink()
    return True


def _remove_reports(path: Path) -> int:
    if not path.exists() or not path.is_dir():
        return 0
    removed = 0
    for child in path.iterdir():
        if child.is_file():
            child.unlink()
            removed += 1
    return removed


def main() -> int:
    parser = argparse.ArgumentParser(description="Limpia DB, logs y reportes runtime de MADAWC v2")
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--launcher-log", type=Path, default=DEFAULT_LOG_PATH)
    parser.add_argument("--trades-log", type=Path, default=DEFAULT_TRADES_LOG_PATH)
    parser.add_argument("--reports-dir", type=Path, default=DEFAULT_REPORTS_PATH)
    args = parser.parse_args()

    removed_db = _remove_file(args.db_path)
    removed_launcher_log = _remove_file(args.launcher_log)
    removed_trades_log = _remove_file(args.trades_log)
    removed_reports = _remove_reports(args.reports_dir)

    print(
        "reset_runtime_state "
        f"db_removed={removed_db} "
        f"launcher_log_removed={removed_launcher_log} "
        f"trades_log_removed={removed_trades_log} "
        f"report_files_removed={removed_reports}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
