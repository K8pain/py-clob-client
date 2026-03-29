from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from ToTheMoon.strategies.automated_paper_v1_web import MeanReversionPaperStrategy, StrategyConfig
from ToTheMoon.strategies.mvp1_market_maker.bin.runner import run_demo_cycle

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = BASE_DIR / "launcher_config.json"


@dataclass(frozen=True)
class ScriptSpec:
    key: str
    title: str
    script_path: str
    script_type: str
    purpose: str
    operation: str
    expected_output: str
    risks: str


DEFAULT_CONFIG: dict[str, Any] = {
    "active_profile": "baseline",
    "profiles": {
        "baseline": {
            "launcher": {
                "log_file": "logs/launcher.log",
                "enabled_scripts": ["mean-reversion", "autopilot-once", "autopilot-scheduler", "mvp1-demo"],
                "mean_reversion": {"page_limit": 3},
                "autopilot": {"simulation_days": 1},
            },
            "launcher_helpers": {
                "log_file": "logs/launcher_helpers.log",
                "enabled_helpers": [
                    "execution-guard",
                    "pnl-engine",
                    "market-regime",
                    "risk-controls",
                    "resilience",
                    "strategy-validation",
                ],
                "resilience": {"max_attempts": 3, "base_delay_seconds": 0.01},
            },
        },
        "strict": {
            "launcher": {
                "mean_reversion": {"page_limit": 1},
                "autopilot": {"simulation_days": 2},
            },
            "launcher_helpers": {
                "resilience": {"max_attempts": 2, "base_delay_seconds": 0.001},
            },
        },
    },
}

ALL_SPECS: tuple[ScriptSpec, ...] = (
    ScriptSpec(
        key="mean-reversion",
        title="Mean Reversion Paper Strategy",
        script_path="ToTheMoon/strategies/automated_paper_v1_web/mean_reversion.py",
        script_type="Funcional (paper trading)",
        purpose="Descubrir mercados UP/DOWN de crypto y simular compra/venta YES con umbrales de precio.",
        operation="Instancia MeanReversionPaperStrategy y ejecuta run_once(page_limit configurable).",
        expected_output="Lista de trades simulados + actualización de ToTheMoon/state.json y ToTheMoon/paper_trades.json.",
        risks="Dependencia de red contra CLOB/Gamma; puede no generar trades si no hay señales.",
    ),
    ScriptSpec(
        key="autopilot-once",
        title="Polymarket Autopilot (once)",
        script_path="ToTheMoon/strategies/polymarket_autopilot/runner.py",
        script_type="Script ejecutable",
        purpose="Ejecutar ciclos paper y publicar resumen diario.",
        operation="Corre el runner en modo once con --simulation-days configurable.",
        expected_output="Resumen en consola + archivos en data/ y logs/ dentro de strategies/polymarket_autopilot.",
        risks="Hace llamadas de red y puede tardar según disponibilidad de APIs.",
    ),
    ScriptSpec(
        key="autopilot-scheduler",
        title="Polymarket Autopilot (scheduler)",
        script_path="ToTheMoon/strategies/polymarket_autopilot/runner.py",
        script_type="Script ejecutable continuo",
        purpose="Mantener loop diario de publicación de resumen a las 08:00.",
        operation="Corre el runner con --mode scheduler.",
        expected_output="Proceso largo en ejecución continua + logs diarios.",
        risks="Bloquea la terminal (loop infinito) hasta interrupción manual.",
    ),
    ScriptSpec(
        key="mvp1-demo",
        title="MVP1 Market Maker Demo",
        script_path="ToTheMoon/strategies/mvp1_market_maker/bin/main.py",
        script_type="Script ejecutable",
        purpose="Ejecutar un ciclo de demostración del market maker paper con datos de ejemplo.",
        operation="Llama run_demo_cycle() y muestra un resumen JSON.",
        expected_output="Resumen de snapshots/órdenes/fills en JSON.",
        risks="No usa dinero real, pero escribe/actualiza base SQLite local del demo.",
    ),
)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _load_profile_config(config_path: Path, profile: str | None = None) -> dict[str, Any]:
    config = DEFAULT_CONFIG
    if config_path.exists():
        with config_path.open("r", encoding="utf-8") as handle:
            user_cfg = json.load(handle)
        config = _deep_merge(config, user_cfg)

    active = profile or config.get("active_profile", "baseline")
    profiles = config.get("profiles", {})
    baseline = profiles.get("baseline", {})
    selected = profiles.get(active, {})
    return _deep_merge(baseline, selected)


def _setup_logger(log_path: Path) -> logging.Logger:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("tothemoon-launcher")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    return logger


def _enabled_specs(cfg: dict[str, Any]) -> tuple[ScriptSpec, ...]:
    enabled = set(cfg.get("enabled_scripts", []))
    return tuple(spec for spec in ALL_SPECS if spec.key in enabled)


def _print_specs(specs: tuple[ScriptSpec, ...]) -> None:
    print("\n=== ToTheMoon launcher | especificaciones de scripts funcionales ===")
    for idx, spec in enumerate(specs, start=1):
        print(f"\n[{idx}] {spec.title} ({spec.key})")
        print(f"  - Ruta: {spec.script_path}")
        print(f"  - Tipo: {spec.script_type}")
        print(f"  - Objetivo: {spec.purpose}")
        print(f"  - Funcionamiento clave: {spec.operation}")
        print(f"  - Salida esperada: {spec.expected_output}")
        print(f"  - Riesgos/observaciones: {spec.risks}")


def _run_subprocess(command: list[str], logger: logging.Logger) -> int:
    logger.info("Ejecutando comando: %s", " ".join(command))
    process = subprocess.run(command, cwd=ROOT_DIR, text=True, capture_output=True)
    if process.stdout:
        print(process.stdout.rstrip())
        logger.info("STDOUT:\n%s", process.stdout.rstrip())
    if process.stderr:
        print(process.stderr.rstrip(), file=sys.stderr)
        logger.warning("STDERR:\n%s", process.stderr.rstrip())
    return process.returncode


def _run_mean_reversion(logger: logging.Logger, config: dict[str, Any]) -> int:
    page_limit = int(config.get("mean_reversion", {}).get("page_limit", 3))
    logger.info("Iniciando mean-reversion run_once(page_limit=%s)", page_limit)
    strategy = MeanReversionPaperStrategy(StrategyConfig())
    trades = strategy.run_once(page_limit=page_limit)
    print(json.dumps([trade.__dict__ for trade in trades], indent=2, ensure_ascii=False))
    logger.info("Mean reversion completado: trades=%s", len(trades))
    return 0


def _run_mvp1_demo(logger: logging.Logger, _: dict[str, Any]) -> int:
    logger.info("Iniciando run_demo_cycle de mvp1_market_maker")
    summary = run_demo_cycle()
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    logger.info("MVP1 demo completado")
    return 0


def _run_script(key: str, logger: logging.Logger, config: dict[str, Any]) -> int:
    try:
        runners: dict[str, Callable[[logging.Logger, dict[str, Any]], int]] = {
            "mean-reversion": _run_mean_reversion,
            "mvp1-demo": _run_mvp1_demo,
        }
        if key in runners:
            return runners[key](logger, config)

        if key == "autopilot-once":
            simulation_days = str(config.get("autopilot", {}).get("simulation_days", 1))
            return _run_subprocess(
                [
                    sys.executable,
                    "-m",
                    "ToTheMoon.strategies.polymarket_autopilot.runner",
                    "--mode",
                    "once",
                    "--simulation-days",
                    simulation_days,
                ],
                logger,
            )

        if key == "autopilot-scheduler":
            return _run_subprocess(
                [
                    sys.executable,
                    "-m",
                    "ToTheMoon.strategies.polymarket_autopilot.runner",
                    "--mode",
                    "scheduler",
                ],
                logger,
            )

        raise KeyError(f"Script no soportado: {key}")
    except Exception as exc:
        logger.exception("Fallo al ejecutar script '%s'", key)
        print(f"Error ejecutando '{key}': {exc}", file=sys.stderr)
        return 1


def _menu_text(specs: tuple[ScriptSpec, ...]) -> str:
    lines = ["\n=== Menú launcher ToTheMoon ===", "0) Salir", "1) Ver especificaciones"]
    for idx, spec in enumerate(specs, start=2):
        lines.append(f"{idx}) Ejecutar: {spec.title} [{spec.key}]")
    return "\n".join(lines)


def _run_interactive(specs: tuple[ScriptSpec, ...], logger: logging.Logger, config: dict[str, Any]) -> int:
    while True:
        print(_menu_text(specs))
        choice = input("Selecciona una opción: ").strip()
        if choice == "0":
            return 0
        if choice == "1":
            _print_specs(specs)
            continue

        try:
            idx = int(choice)
        except ValueError:
            print("Opción inválida. Usa un número del menú.")
            continue

        spec_index = idx - 2
        if spec_index < 0 or spec_index >= len(specs):
            print("Opción fuera de rango.")
            continue

        spec = specs[spec_index]
        if spec.key == "autopilot-scheduler":
            confirm = input("Este modo es continuo (loop). ¿Deseas continuar? [y/N]: ").strip().lower()
            if confirm not in {"y", "yes", "s", "si"}:
                print("Operación cancelada.")
                continue

        print(f"\n>>> Ejecutando {spec.title}...")
        rc = _run_script(spec.key, logger, config)
        print("✅ Ejecución completada." if rc == 0 else f"❌ Ejecución con error (rc={rc}).")


def _build_parser(all_keys: list[str]) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Launcher de ToTheMoon con menú, logs y configuración por perfiles.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent(
            """
            Ejemplos:
              python ToTheMoon/launcher.py --action specs
              python ToTheMoon/launcher.py --action run --script mean-reversion
              python ToTheMoon/launcher.py --profile strict --action run --script autopilot-once
            """
        ),
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--profile", help="Perfil de config a usar (baseline, strict, etc.).")
    parser.add_argument("--action", choices=["menu", "specs", "run"], default="menu")
    parser.add_argument("--script", choices=all_keys, help="Requerido cuando --action run")
    return parser


def main() -> int:
    parser = _build_parser([spec.key for spec in ALL_SPECS])
    args = parser.parse_args()

    profile_cfg = _load_profile_config(config_path=args.config, profile=args.profile)
    launcher_cfg = profile_cfg.get("launcher", {})
    log_file = BASE_DIR / launcher_cfg.get("log_file", "logs/launcher.log")
    logger = _setup_logger(log_file)
    specs = _enabled_specs(launcher_cfg)

    logger.info("Launcher iniciado action=%s script=%s profile=%s", args.action, args.script, args.profile)
    if args.action == "specs":
        _print_specs(specs)
        return 0

    if args.action == "run":
        if not args.script:
            parser.error("--script es requerido cuando --action run")
        if args.script not in {spec.key for spec in specs}:
            parser.error(f"El script '{args.script}' está deshabilitado por configuración.")
        return _run_script(args.script, logger, launcher_cfg)

    return _run_interactive(specs, logger, launcher_cfg)


if __name__ == "__main__":
    raise SystemExit(main())
