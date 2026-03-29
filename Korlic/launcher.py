from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import logging
import sqlite3
import sys
import time
from pathlib import Path
from typing import Callable

from .bot import KorlicBot
from .storage import KorlicStorage


DEFAULT_DB_PATH = Path("var/korlic/korlic.sqlite")
DEFAULT_LOG_PATH = Path("var/korlic/korlic-launcher.log")
DEFAULT_TRADES_LOG_PATH = Path("var/korlic/korlic-trades.log")
DEFAULT_REPORTS_PATH = Path("var/korlic/reports")


def _setup_logger(log_file: Path) -> logging.Logger:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("korlic-launcher")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    handler = logging.FileHandler(log_file, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    logger.addHandler(handler)
    bot_logger = logging.getLogger("korlic-bot")
    bot_logger.setLevel(logging.DEBUG)
    bot_logger.handlers.clear()
    bot_logger.addHandler(handler)
    return logger


def _load_bot(factory_ref: str, db_path: Path) -> KorlicBot:
    module_name, sep, attr_name = factory_ref.partition(":")
    if not sep:
        raise ValueError("factory debe tener formato 'paquete.modulo:funcion'")

    module = importlib.import_module(module_name)
    factory = getattr(module, attr_name)
    if not callable(factory):
        raise TypeError("factory no es callable")

    try:
        bot = factory(db_path=str(db_path))
    except TypeError:
        bot = factory()

    if not isinstance(bot, KorlicBot):
        raise TypeError("factory debe retornar KorlicBot")

    if str(bot.storage.db_path) != str(db_path):
        bot.storage = KorlicStorage(str(db_path))
    return bot


async def _run_once(bot: KorlicBot, logger: logging.Logger) -> None:
    started = time.perf_counter()
    await bot.run_cycle()
    elapsed = int((time.perf_counter() - started) * 1000)
    logger.info("run_cycle completed latency_ms=%s", elapsed)


def _append_trade_log(db_path: Path, trade_log_file: Path, since_id: int = 0) -> int:
    query = (
        "SELECT id, ts_utc, event_type, decision, reason_code, market_id, token_id "
        "FROM events WHERE id > ? AND event_type IN ("
        "'SIGNAL_DETECTED', 'NO_TRADE', "
        "'PSEUDO_ORDER_OPENED', 'PSEUDO_ORDER_PARTIAL_FILL', 'PSEUDO_ORDER_FILLED', 'PSEUDO_ORDER_EXPIRED', "
        "'PAPER_POSITION_OPENED', 'PAPER_POSITION_UPDATED', 'PAPER_POSITION_SETTLED_WIN', 'PAPER_POSITION_SETTLED_LOSS'"
        ") ORDER BY id ASC"
    )
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(query, (since_id,)).fetchall()
    if not rows:
        return since_id
    trade_log_file.parent.mkdir(parents=True, exist_ok=True)
    with trade_log_file.open("a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(
                f"{row[1]} | {row[2]} | decision={row[3]} | reason={row[4]} | "
                f"market_id={row[5]} | token_id={row[6]}\n"
            )
    return int(rows[-1][0])


async def _run_loop(bot: KorlicBot, logger: logging.Logger, interval_seconds: float) -> None:
    logger.info("loop started interval_seconds=%s", interval_seconds)
    while True:
        await _run_once(bot, logger)
        await asyncio.sleep(interval_seconds)


async def _run_loop_with_trade_log(
    bot: KorlicBot,
    logger: logging.Logger,
    db_path: Path,
    trade_log_file: Path,
    interval_seconds: float,
) -> None:
    logger.info("loop started interval_seconds=%s trade_log_file=%s", interval_seconds, trade_log_file)
    last_id = 0
    while True:
        await _run_once(bot, logger)
        last_id = _append_trade_log(db_path, trade_log_file, since_id=last_id)
        await asyncio.sleep(interval_seconds)


def _tail_file(path: Path, lines: int, follow: bool) -> int:
    if not path.exists():
        print(f"log file no existe: {path}", file=sys.stderr)
        return 1

    with path.open("r", encoding="utf-8") as fh:
        chunk = fh.readlines()[-lines:]
        for line in chunk:
            print(line, end="")

        if not follow:
            return 0

        while True:
            line = fh.readline()
            if line:
                print(line, end="")
                continue
            time.sleep(0.5)


def _query_events(db_path: Path, limit: int, event_type: str | None) -> list[dict[str, object]]:
    query = (
        "SELECT id, ts_utc, event_type, decision, reason_code, latency_ms, payload "
        "FROM events "
    )
    params: list[object] = []
    if event_type:
        query += "WHERE event_type = ? "
        params.append(event_type)
    query += "ORDER BY id DESC LIMIT ?"
    params.append(limit)

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(query, params).fetchall()

    result: list[dict[str, object]] = []
    for row in rows:
        payload = json.loads(row[6])
        result.append(
            {
                "id": row[0],
                "ts_utc": row[1],
                "event_type": row[2],
                "decision": row[3],
                "reason_code": row[4],
                "latency_ms": row[5],
                "payload": payload,
            }
        )
    return result


def _query_trade_counters(db_path: Path) -> dict[str, object]:
    with sqlite3.connect(db_path) as conn:
        total, net_pnl = conn.execute("SELECT COUNT(*), COALESCE(SUM(net_pnl), 0) FROM pseudo_trades").fetchone()
        wins = conn.execute("SELECT COUNT(*) FROM pseudo_trades WHERE result_class='WON'").fetchone()[0]
        losses = conn.execute("SELECT COUNT(*) FROM pseudo_trades WHERE result_class='LOST'").fetchone()[0]
        pushes = conn.execute("SELECT COUNT(*) FROM pseudo_trades WHERE result_class='PUSH'").fetchone()[0]
    return {
        "total_trades": total,
        "won_trades": wins,
        "lost_trades": losses,
        "push_trades": pushes,
        "net_pnl": float(net_pnl),
    }


def _query_event_diagnostics(db_path: Path) -> dict[str, object]:
    with sqlite3.connect(db_path) as conn:
        evaluations = conn.execute(
            "SELECT COUNT(*) FROM events WHERE event_type IN ('SIGNAL_DETECTED', 'NO_TRADE')"
        ).fetchone()[0]
        signals = conn.execute("SELECT COUNT(*) FROM events WHERE event_type='SIGNAL_DETECTED'").fetchone()[0]
        opened_orders = conn.execute("SELECT COUNT(*) FROM events WHERE event_type='PSEUDO_ORDER_OPENED'").fetchone()[0]
        fills = conn.execute(
            "SELECT COUNT(*) FROM events WHERE event_type IN ('PSEUDO_ORDER_PARTIAL_FILL', 'PSEUDO_ORDER_FILLED')"
        ).fetchone()[0]
        top_no_trade = conn.execute(
            """
            SELECT reason_code, COUNT(*) as cnt
            FROM events
            WHERE event_type='NO_TRADE'
            GROUP BY reason_code
            ORDER BY cnt DESC, reason_code ASC
            LIMIT 5
            """
        ).fetchall()

    return {
        "evaluations": evaluations,
        "signals": signals,
        "opened_orders": opened_orders,
        "fills": fills,
        "top_no_trade_reasons": [{"reason_code": row[0], "count": row[1]} for row in top_no_trade],
    }


def _print_tail(path: Path, lines: int, title: str) -> None:
    if not path.exists():
        print(f"[{title}] no existe: {path}")
        return
    print(f"[{title}] {path}")
    with path.open("r", encoding="utf-8") as fh:
        for line in fh.readlines()[-lines:]:
            print(line, end="")


def _run_all(args: argparse.Namespace) -> int:
    db_path = Path(args.db_path)
    log_file = Path(args.log_file)
    logger = _setup_logger(log_file)

    if args.factory:
        bot = _load_bot(args.factory, db_path)
        asyncio.run(_run_once(bot, logger))

    storage = KorlicStorage(args.db_path)
    files = storage.export_csv_reports(args.output_dir)
    print(
        json.dumps(
            {
                "reports": files,
                "trades": _query_trade_counters(db_path),
                "diagnostics": _query_event_diagnostics(db_path),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    _print_tail(log_file, lines=args.lines, title="launcher-log tail")
    _print_tail(Path(files["pseudo_trades"]), lines=args.lines, title="pseudo_trades.csv tail")
    if args.keep_running and args.factory:
        asyncio.run(
            _run_loop_with_trade_log(
                bot=bot,
                logger=logger,
                db_path=db_path,
                trade_log_file=Path(args.trades_log_file),
                interval_seconds=args.interval_seconds,
            )
        )
    return 0


def _print_specs() -> None:
    lines = [
        "",
        "=== Korlic launcher | comandos ===",
        "1) Run una vez:",
        "   python -m Korlic.launcher run-once --factory Korlic.factory:build_bot",
        "2) Run continuo:",
        "   python -m Korlic.launcher run-loop --factory Korlic.factory:build_bot --interval-seconds 5",
        "3) Ver log (tail -f):",
        "   python -m Korlic.launcher tail-log --follow",
        "4) Ver señales/órdenes/trades (tail -f):",
        "   python -m Korlic.launcher tail-trades --follow",
        "5) Ver eventos persistidos (SQLite):",
        "   python -m Korlic.launcher events --limit 30",
        "6) Exportar reportes CSV:",
        "   python -m Korlic.launcher export-reports",
        "7) Pipeline MVP desatendido:",
        "   python -m Korlic.launcher --all --factory Korlic.factory:build_bot",
        "8) Pipeline continuo con --all:",
        "   python -m Korlic.launcher --all --factory Korlic.factory:build_bot --keep-running",
        "",
    ]
    print("\n".join(lines))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Orquestador CLI de Korlic para operación por SSH.")
    parser.add_argument("--all", action="store_true", help="Ejecuta pipeline MVP: run-once, reportes y tails.")
    parser.add_argument("--factory", help="Factory 'modulo:funcion' que retorna KorlicBot para --all.")
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--log-file", default=str(DEFAULT_LOG_PATH))
    parser.add_argument("--trades-log-file", default=str(DEFAULT_TRADES_LOG_PATH))
    parser.add_argument("--output-dir", default=str(DEFAULT_REPORTS_PATH))
    parser.add_argument("--interval-seconds", type=float, default=5.0, help="Intervalo para modo continuo.")
    parser.add_argument("--keep-running", action="store_true", help="Con --all, no termina y sigue en loop.")
    parser.add_argument("-n", "--lines", type=int, default=30, help="Líneas para tail en --all.")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("specs", help="Muestra comandos sugeridos.")

    run_once = sub.add_parser("run-once", help="Ejecuta un ciclo de Korlic.")
    run_once.add_argument("--factory", required=True, help="Factory 'modulo:funcion' que retorna KorlicBot.")
    run_once.add_argument("--db-path", default=str(DEFAULT_DB_PATH))
    run_once.add_argument("--log-file", default=str(DEFAULT_LOG_PATH))

    run_loop = sub.add_parser("run-loop", help="Ejecuta ciclos de Korlic en loop.")
    run_loop.add_argument("--factory", required=True, help="Factory 'modulo:funcion' que retorna KorlicBot.")
    run_loop.add_argument("--db-path", default=str(DEFAULT_DB_PATH))
    run_loop.add_argument("--log-file", default=str(DEFAULT_LOG_PATH))
    run_loop.add_argument("--trades-log-file", default=str(DEFAULT_TRADES_LOG_PATH))
    run_loop.add_argument("--interval-seconds", type=float, default=5.0)

    tail_log = sub.add_parser("tail-log", help="Muestra log del launcher.")
    tail_log.add_argument("--log-file", default=str(DEFAULT_LOG_PATH))
    tail_log.add_argument("-n", "--lines", type=int, default=100)
    tail_log.add_argument("--follow", action="store_true")

    tail_trades = sub.add_parser("tail-trades", help="Muestra log de señales/órdenes/trades.")
    tail_trades.add_argument("--trades-log-file", default=str(DEFAULT_TRADES_LOG_PATH))
    tail_trades.add_argument("-n", "--lines", type=int, default=100)
    tail_trades.add_argument("--follow", action="store_true")

    events = sub.add_parser("events", help="Consulta últimos eventos en SQLite.")
    events.add_argument("--db-path", default=str(DEFAULT_DB_PATH))
    events.add_argument("--limit", type=int, default=50)
    events.add_argument("--event-type")

    export = sub.add_parser("export-reports", help="Exporta reportes CSV desde SQLite.")
    export.add_argument("--db-path", default=str(DEFAULT_DB_PATH))
    export.add_argument("--output-dir", default=str(DEFAULT_REPORTS_PATH))

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.all:
        return _run_all(args)

    if not args.command:
        parser.error("debes indicar un comando o usar --all")

    if args.command == "specs":
        _print_specs()
        return 0

    if args.command == "tail-log":
        return _tail_file(Path(args.log_file), lines=args.lines, follow=args.follow)

    if args.command == "tail-trades":
        return _tail_file(Path(args.trades_log_file), lines=args.lines, follow=args.follow)

    if args.command == "events":
        rows = _query_events(Path(args.db_path), limit=args.limit, event_type=args.event_type)
        print(json.dumps(rows, indent=2, ensure_ascii=False))
        return 0

    if args.command == "export-reports":
        storage = KorlicStorage(args.db_path)
        files = storage.export_csv_reports(args.output_dir)
        print(json.dumps(files, indent=2, ensure_ascii=False))
        return 0

    db_path = Path(args.db_path)
    logger = _setup_logger(Path(args.log_file))
    bot = _load_bot(args.factory, db_path)

    if args.command == "run-once":
        asyncio.run(_run_once(bot, logger))
        _append_trade_log(db_path, Path(args.trades_log_file))
        return 0

    asyncio.run(
        _run_loop_with_trade_log(
            bot=bot,
            logger=logger,
            db_path=db_path,
            trade_log_file=Path(args.trades_log_file),
            interval_seconds=args.interval_seconds,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
