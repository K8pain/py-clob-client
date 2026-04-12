from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from Madawc_v3 import config
from Madawc_v3.bot import MadawcV3Bot
from Madawc_v3.factory import build_bot
from Madawc_v3.launcher import _load_bot, main
from Madawc_v3.models import BotMetrics, Fill, Inventory, MarketTick
from Madawc_v3.strategy import apply_fill, build_quotes, fee_equivalent, minimum_net_spread, reservation_price


def test_factory_build_bot_returns_expected_type() -> None:
    bot = build_bot(db_path="ignored.sqlite")
    assert isinstance(bot, MadawcV3Bot)


def test_fee_equivalent_and_minimum_net_spread_floor_behavior() -> None:
    fee = fee_equivalent(notional=100.0, price=0.5, fee_rate_bps=35.0)
    assert fee == pytest.approx(0.0875)

    spread = minimum_net_spread(price=0.01)
    assert spread >= config.MIN_SPREAD_FLOOR


def test_reservation_price_skew_and_quote_bounds() -> None:
    inv = Inventory(yes=20, no=2)
    r_yes = reservation_price(mid_price=0.55, inventory=inv)
    assert 0.01 <= r_yes <= 0.99

    tick = MarketTick(cycle=1, yes_mid=0.55, no_mid=0.45, spread=0.01)
    quotes = build_quotes(tick=tick, inventory=inv)
    assert 0.01 <= quotes.yes_bid <= quotes.yes_ask <= 0.99
    assert 0.01 <= quotes.no_bid <= quotes.no_ask <= 0.99


def test_apply_fill_updates_inventory_for_yes_and_no() -> None:
    inv = Inventory(yes=0.0, no=0.0, cash=1000.0)
    apply_fill(inv, Fill(side="YES", qty=10.0, price=0.5, maker=True))
    assert inv.yes == pytest.approx(10.0)
    assert inv.no == pytest.approx(0.0)
    assert inv.cash == pytest.approx(995.0)

    apply_fill(inv, Fill(side="NO", qty=4.0, price=0.4, maker=True))
    assert inv.yes == pytest.approx(10.0)
    assert inv.no == pytest.approx(4.0)
    assert inv.cash == pytest.approx(993.4)


def test_bot_metrics_total_realized_property() -> None:
    metrics = BotMetrics(spread_pnl=5, merge_pnl=3, split_sell_pnl=2, taker_fees=1, rebate_income=0.5, reward_income=0.25)
    assert metrics.total_realized == pytest.approx(9.75)


def test_bot_run_all_generates_outputs_and_summary_shape(tmp_path: Path) -> None:
    bot = MadawcV3Bot(cycles=5)
    summary = bot.run_all(output_dir=tmp_path)

    assert (tmp_path / "ticks.csv").exists()
    expected_keys = {
        "spread_pnl",
        "merge_pnl",
        "split_sell_pnl",
        "taker_fees",
        "rebate_income",
        "reward_income",
        "directional_mtm",
        "total_realized",
        "net_yes_inventory",
    }
    assert set(summary.keys()) == expected_keys


def test_load_bot_validation_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValueError):
        _load_bot("badformat", tmp_path / "db.sqlite")

    # module exists but attribute is not callable
    monkeypatch.setattr("Madawc_v3.factory.not_callable", 1, raising=False)
    with pytest.raises(TypeError):
        _load_bot("Madawc_v3.factory:not_callable", tmp_path / "db.sqlite")


def test_launcher_main_requires_all_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["launcher"])
    with pytest.raises(SystemExit):
        main()


def test_launcher_main_writes_simulation_summary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    out_dir = tmp_path / "reports"
    db_path = tmp_path / "bot.sqlite"
    monkeypatch.setattr(
        "sys.argv",
        [
            "launcher",
            "--all",
            "--factory",
            "Madawc_v3.factory:build_bot",
            "--db-path",
            str(db_path),
            "--output-dir",
            str(out_dir),
        ],
    )
    main()

    summary_path = out_dir / "simulation_summary.json"
    assert summary_path.exists()
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert "total_realized" in payload


def test_madawc_v3_statement_coverage_threshold(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Local coverage guard without external plugins (target >=85% statement lines)."""
    import trace

    import Madawc_v3.bot as bot_module
    import Madawc_v3.factory as factory_module
    import Madawc_v3.launcher as launcher_module
    import Madawc_v3.strategy as strategy_module

    modules = [bot_module, factory_module, launcher_module, strategy_module]

    tracer = trace.Trace(count=True, trace=False)

    def exercise() -> None:
        inv = Inventory(yes=5.0, no=2.0)
        tick = MarketTick(cycle=1, yes_mid=0.52, no_mid=0.48, spread=0.01)
        q = build_quotes(tick, inv)
        apply_fill(inv, Fill(side="YES", qty=2.0, price=q.yes_bid, maker=True))
        apply_fill(inv, Fill(side="NO", qty=1.0, price=q.no_bid, maker=True))
        _ = fee_equivalent(100, 0.5, 35)
        _ = minimum_net_spread(0.5)
        _ = reservation_price(0.4, inv)
        _ = build_bot("db.sqlite")
        bot = MadawcV3Bot(cycles=3)
        bot.run_all(output_dir=tmp_path / "cov_reports")
        bot._simulate_fill_and_pnl(tick, q, __import__("random").Random(1))

        # trigger alternative branches
        monkeypatch.setattr(config, "ENABLE_PAIR_MERGE", False)
        monkeypatch.setattr(config, "ENABLE_SPLIT_SELL", False)
        monkeypatch.setattr(config, "TAKER_FRACTION", 1.0)
        bot._simulate_fill_and_pnl(tick, q, __import__("random").Random(1))
        monkeypatch.setattr(config, "ENABLE_PAIR_MERGE", True)
        monkeypatch.setattr(config, "ENABLE_SPLIT_SELL", True)
        monkeypatch.setattr(config, "TAKER_FRACTION", 0.10)

        # exercise launcher paths (error + success)
        try:
            _load_bot("badformat", tmp_path / "invalid.sqlite")
        except ValueError:
            pass
        monkeypatch.setattr("Madawc_v3.factory.not_callable", 1, raising=False)
        try:
            _load_bot("Madawc_v3.factory:not_callable", tmp_path / "invalid.sqlite")
        except TypeError:
            pass
        monkeypatch.setattr("sys.argv", ["launcher"])  # missing --all
        try:
            main()
        except SystemExit:
            pass
        monkeypatch.setattr(
            "sys.argv",
            [
                "launcher",
                "--all",
                "--factory",
                "Madawc_v3.factory:build_bot",
                "--output-dir",
                str(tmp_path / "cov_launcher"),
            ],
        )
        main()

    tracer.runfunc(exercise)
    results = tracer.results()

    def relevant_lines(path: str) -> set[int]:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
        relevant: set[int] = set()
        for idx, raw in enumerate(lines, start=1):
            stripped = raw.strip()
            if not stripped:
                continue
            if stripped.startswith("#"):
                continue
            if stripped.startswith(("from ", "import ", "def ", "class ", "@")):
                continue
            if stripped.startswith(('"""', "'''", '"', "'")):
                continue
            relevant.add(idx)
        return relevant

    total_statements = 0
    executed_statements = 0
    for module in modules:
        path = str(Path(module.__file__).resolve())
        statements = relevant_lines(path)
        executed = {lineno for (filename, lineno), _ in results.counts.items() if str(Path(filename).resolve()) == path}
        total_statements += len(statements)
        executed_statements += len(statements & executed)

    ratio = (executed_statements / total_statements) * 100 if total_statements else 0.0
    assert ratio >= 85.0, f"coverage ratio too low: {ratio:.2f}%"
