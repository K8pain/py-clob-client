from __future__ import annotations

import argparse
import json
import logging
import textwrap
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from ToTheMoon.launcher import DEFAULT_CONFIG_PATH, _load_profile_config
from ToTheMoon.real_helpers.execution_guard import (
    should_close_trade,
    should_open_trade,
    track_skip_reason,
    validate_trade_request,
)
from ToTheMoon.real_helpers.market_regime import (
    calculate_adx,
    calculate_bollinger_bands,
    classify_market_regime,
    is_trade_allowed_for_regime,
)
from ToTheMoon.real_helpers.pnl_engine import (
    calculate_net_pnl,
    update_compounded_equity,
    update_cumulative_pnl,
)
from ToTheMoon.real_helpers.resilience import (
    api_timeout_guard,
    heartbeat_monitor,
    restart_stalled_worker,
    retry_with_backoff,
)
from ToTheMoon.real_helpers.risk_controls import (
    check_circuit_breaker,
    enforce_capital_guards,
    enforce_drawdown_limits,
    enforce_position_cap,
)
from ToTheMoon.real_helpers.strategy_validation import (
    approve_strategy,
    parameter_sensitivity_analysis,
    run_monte_carlo_checks,
    run_walk_forward_validation,
    validate_backtest_results,
)

BASE_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class HelperSpec:
    key: str
    title: str
    module_path: str
    purpose: str
    covered_functions: tuple[str, ...]


ALL_HELPERS: tuple[HelperSpec, ...] = (
    HelperSpec(
        key="execution-guard",
        title="Execution Guard",
        module_path="ToTheMoon/real_helpers/execution_guard.py",
        purpose="Validar si una operación se puede abrir/cerrar y registrar motivos de skip.",
        covered_functions=(
            "validate_trade_request",
            "should_open_trade",
            "should_close_trade",
            "track_skip_reason",
        ),
    ),
    HelperSpec(
        key="pnl-engine",
        title="PnL Engine",
        module_path="ToTheMoon/real_helpers/pnl_engine.py",
        purpose="Calcular PnL neto y evolución de equity/cumulativo.",
        covered_functions=("calculate_net_pnl", "update_cumulative_pnl", "update_compounded_equity"),
    ),
    HelperSpec(
        key="market-regime",
        title="Market Regime",
        module_path="ToTheMoon/real_helpers/market_regime.py",
        purpose="Detectar régimen de mercado con ADX, Bollinger y filtros de operación.",
        covered_functions=(
            "calculate_adx",
            "calculate_bollinger_bands",
            "classify_market_regime",
            "is_trade_allowed_for_regime",
        ),
    ),
    HelperSpec(
        key="risk-controls",
        title="Risk Controls",
        module_path="ToTheMoon/real_helpers/risk_controls.py",
        purpose="Aplicar límites de posición, drawdown, circuito y exposición.",
        covered_functions=(
            "enforce_position_cap",
            "enforce_drawdown_limits",
            "check_circuit_breaker",
            "enforce_capital_guards",
        ),
    ),
    HelperSpec(
        key="resilience",
        title="Resilience",
        module_path="ToTheMoon/real_helpers/resilience.py",
        purpose="Manejar timeout, retries/backoff y heartbeats de workers.",
        covered_functions=("api_timeout_guard", "retry_with_backoff", "heartbeat_monitor", "restart_stalled_worker"),
    ),
    HelperSpec(
        key="strategy-validation",
        title="Strategy Validation",
        module_path="ToTheMoon/real_helpers/strategy_validation.py",
        purpose="Validar robustez de resultados de estrategia antes de aprobar.",
        covered_functions=(
            "validate_backtest_results",
            "run_monte_carlo_checks",
            "run_walk_forward_validation",
            "parameter_sensitivity_analysis",
            "approve_strategy",
        ),
    ),
)


def _setup_logger(log_file: Path) -> logging.Logger:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("tothemoon-launcher-helpers")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    handler = logging.FileHandler(log_file, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    logger.addHandler(handler)
    return logger


def _enabled_helpers(cfg: dict[str, Any]) -> tuple[HelperSpec, ...]:
    enabled = set(cfg.get("enabled_helpers", []))
    return tuple(spec for spec in ALL_HELPERS if spec.key in enabled)


def _print_specs(specs: tuple[HelperSpec, ...]) -> None:
    print("\n=== Launcher Helpers | especificaciones ===")
    for idx, spec in enumerate(specs, start=1):
        print(f"\n[{idx}] {spec.title} ({spec.key})")
        print(f"  - Módulo: {spec.module_path}")
        print(f"  - Objetivo: {spec.purpose}")
        print(f"  - Funciones cubiertas: {', '.join(spec.covered_functions)}")


def _run_execution_guard() -> dict[str, Any]:
    allowed, reason = validate_trade_request(10.0, 15.0, 3, 1, False)
    return {
        "validate_trade_request": {"allowed": allowed, "reason": reason},
        "should_open_trade": should_open_trade(True, True, False),
        "should_close_trade": should_close_trade(False, True, False),
        "skip_counts": track_skip_reason({"risk_limit_hit": 1}, "risk_limit_hit"),
    }


def _run_pnl_engine() -> dict[str, Any]:
    net = calculate_net_pnl(0.45, 0.55, 100.0, "long", fee_rate=0.001, slippage_bps=5)
    return {
        "net_pnl": round(net, 6),
        "cumulative_pnl": round(update_cumulative_pnl(12.5, net), 6),
        "equity": round(update_compounded_equity(1_000.0, net), 6),
    }


def _run_market_regime() -> dict[str, Any]:
    highs = [100 + i * 0.4 for i in range(30)]
    lows = [99 + i * 0.35 for i in range(30)]
    closes = [99.5 + i * 0.37 for i in range(30)]
    prices = [100 + ((i % 5) - 2) * 0.2 for i in range(40)]
    adx = calculate_adx(highs, lows, closes, period=14)
    lower, middle, upper = calculate_bollinger_bands(prices, period=20)
    width_pct = ((upper - lower) / middle) * 100 if middle else 0
    regime = classify_market_regime(adx=adx, bollinger_width_pct=width_pct, atr_pct=1.7)
    return {
        "adx": round(adx, 4),
        "bollinger": {"lower": round(lower, 4), "middle": round(middle, 4), "upper": round(upper, 4)},
        "regime": regime,
        "trade_allowed": is_trade_allowed_for_regime(regime),
    }


def _run_risk_controls() -> dict[str, Any]:
    return {
        "position_cap_reduce": enforce_position_cap(25.0, 10.0, mode="reduce"),
        "drawdown_ok": enforce_drawdown_limits(-40.0, max_daily_loss=50.0),
        "circuit_breaker": check_circuit_breaker(
            consecutive_losses=2,
            max_consecutive_losses=3,
            rolling_drawdown=-8.0,
            max_drawdown=12.0,
            last_n_trade_results=[1.0, -2.0, -0.5, -1.5],
            max_losses_in_window=3,
            window_size=4,
        ),
        "capital_guards": enforce_capital_guards(5.0, 10.0, 3, 1, 30.0, 50.0),
    }


def _run_resilience(cfg: dict[str, Any]) -> dict[str, Any]:
    options = cfg.get("resilience", {})
    attempts = int(options.get("max_attempts", 3))
    base_delay = float(options.get("base_delay_seconds", 0.01))

    counter = {"n": 0}

    def flaky() -> str:
        counter["n"] += 1
        if counter["n"] < 2:
            raise RuntimeError("transient")
        return "ok"

    alerts: list[str] = []

    def restart() -> None:
        alerts.append("restart_called")

    result = retry_with_backoff(flaky, retriable_exceptions=(RuntimeError,), max_attempts=attempts, base_delay_seconds=base_delay)
    timeout_result = api_timeout_guard(lambda x: x + 1, 0.2, 1)
    stale = heartbeat_monitor(datetime.now(tz=timezone.utc) - timedelta(seconds=20), heartbeat_timeout_seconds=10)
    restarted = restart_stalled_worker(stale, restart, alerts.append)
    return {
        "retry_result": result,
        "retry_attempts": counter["n"],
        "api_timeout_guard": timeout_result,
        "stale_detected": stale,
        "restarted": restarted,
        "alerts": alerts,
    }


def _run_strategy_validation() -> dict[str, Any]:
    ok, failures = validate_backtest_results(150, 100, 1.4, 1.2, 0.12, 0.2, 0.78, 0.7)
    mc_ok, p5 = run_monte_carlo_checks([0.03, -0.01, 0.02, 0.015, -0.005, 0.04], min_percentile_return=-0.03)
    wf_ok = run_walk_forward_validation([1.1, 1.2, 1.0], [1.0, 1.05, 0.95], stability_tolerance=0.3)
    sens_ok = parameter_sensitivity_analysis([1.0, 0.95, 1.05, 1.02], max_variation=0.1)
    approved = approve_strategy([ok, mc_ok, wf_ok, sens_ok])
    return {
        "validate_backtest_results": {"ok": ok, "failures": failures},
        "monte_carlo": {"ok": mc_ok, "p5": p5},
        "walk_forward": wf_ok,
        "sensitivity": sens_ok,
        "approved": approved,
    }


def _run_helper(key: str, cfg: dict[str, Any], logger: logging.Logger) -> int:
    runners: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
        "execution-guard": lambda _: _run_execution_guard(),
        "pnl-engine": lambda _: _run_pnl_engine(),
        "market-regime": lambda _: _run_market_regime(),
        "risk-controls": lambda _: _run_risk_controls(),
        "resilience": _run_resilience,
        "strategy-validation": lambda _: _run_strategy_validation(),
    }
    try:
        payload = runners[key](cfg)
        logger.info("helper=%s payload=%s", key, payload)
        print(json.dumps({"helper": key, "result": payload}, indent=2, ensure_ascii=False))
        return 0
    except Exception as exc:
        logger.exception("Error ejecutando helper=%s", key)
        print(f"Error ejecutando helper '{key}': {exc}")
        return 1


def _run_all(specs: tuple[HelperSpec, ...], cfg: dict[str, Any], logger: logging.Logger) -> int:
    status = 0
    for spec in specs:
        print(f"\n>>> Ejecutando helper: {spec.title} ({spec.key})")
        rc = _run_helper(spec.key, cfg, logger)
        if rc != 0:
            status = rc
    return status


def _menu(specs: tuple[HelperSpec, ...], cfg: dict[str, Any], logger: logging.Logger) -> int:
    while True:
        print("\n=== Menú launcher_helpers ===")
        print("0) Salir")
        print("1) Ver especificaciones")
        print("2) Probar todos los helpers habilitados")
        for idx, spec in enumerate(specs, start=3):
            print(f"{idx}) Probar helper: {spec.title} [{spec.key}]")

        choice = input("Selecciona opción: ").strip()
        if choice == "0":
            return 0
        if choice == "1":
            _print_specs(specs)
            continue
        if choice == "2":
            _run_all(specs, cfg, logger)
            continue

        try:
            pos = int(choice) - 3
        except ValueError:
            print("Opción inválida.")
            continue

        if pos < 0 or pos >= len(specs):
            print("Opción fuera de rango.")
            continue

        _run_helper(specs[pos].key, cfg, logger)


def _build_parser(keys: list[str]) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Launcher para probar los helpers funcionales de ToTheMoon.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent(
            """
            Ejemplos:
              python -m ToTheMoon.launcher_helpers --action specs
              python -m ToTheMoon.launcher_helpers --action run --helper resilience
              python -m ToTheMoon.launcher_helpers --profile strict --action run-all
            """
        ),
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--profile", help="Perfil de configuración.")
    parser.add_argument("--action", choices=["menu", "specs", "run", "run-all"], default="menu")
    parser.add_argument("--helper", choices=keys)
    return parser


def main() -> int:
    parser = _build_parser([helper.key for helper in ALL_HELPERS])
    args = parser.parse_args()

    profile_cfg = _load_profile_config(config_path=args.config, profile=args.profile)
    cfg = profile_cfg.get("launcher_helpers", {})
    logger = _setup_logger(BASE_DIR / cfg.get("log_file", "logs/launcher_helpers.log"))
    specs = _enabled_helpers(cfg)

    if args.action == "specs":
        _print_specs(specs)
        return 0
    if args.action == "run":
        if not args.helper:
            parser.error("--helper es requerido cuando --action run")
        if args.helper not in {item.key for item in specs}:
            parser.error(f"El helper '{args.helper}' está deshabilitado por configuración")
        return _run_helper(args.helper, cfg, logger)
    if args.action == "run-all":
        return _run_all(specs, cfg, logger)
    return _menu(specs, cfg, logger)


if __name__ == "__main__":
    raise SystemExit(main())
