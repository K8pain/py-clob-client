from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from MM001 import config
from MM001.bot import ClobOrderBookSource, MM001Bot
from MM001.factory import build_bot
from MM001.launcher import (
    _append_cycle_aggregate_log,
    _append_trades_log,
    _format_launcher_metrics_table,
    _load_bot,
    _sleep_with_refresh,
    _setup_logger,
    main,
)
from MM001.models import BotMetrics, Fill, Inventory, MarketTick
from MM001.strategy import apply_fill, build_quotes, fee_equivalent, minimum_net_spread, reservation_price


def test_factory_build_bot_returns_expected_type(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "ORDERBOOK_SOURCE", "simulated")
    bot = build_bot(db_path="ignored.sqlite")
    assert isinstance(bot, MM001Bot)


def test_factory_raises_when_api_ids_are_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "ORDERBOOK_SOURCE", "api")
    monkeypatch.setattr(config, "YES_TOKEN_ID", "")
    monkeypatch.setattr(config, "NO_TOKEN_ID", "")
    with pytest.raises(ValueError, match="MM001_YES_TOKEN_ID and MM001_NO_TOKEN_ID"):
        build_bot()


def test_factory_raises_when_market_type_not_included(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "ORDERBOOK_SOURCE", "api")
    monkeypatch.setattr(config, "YES_TOKEN_ID", "yes")
    monkeypatch.setattr(config, "NO_TOKEN_ID", "no")
    monkeypatch.setattr(config, "MARKET_INCLUDE_ONLY", ("crypto",))
    monkeypatch.setattr(config, "CURRENT_MARKET_CATEGORY", "sports")
    with pytest.raises(ValueError, match="CURRENT_MARKET_CATEGORY/CURRENT_MARKET_SLUG enabled"):
        build_bot()


def test_factory_raises_when_market_slug_is_excluded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "ORDERBOOK_SOURCE", "api")
    monkeypatch.setattr(config, "YES_TOKEN_ID", "yes")
    monkeypatch.setattr(config, "NO_TOKEN_ID", "no")
    monkeypatch.setattr(config, "MARKET_INCLUDE_ONLY", ("crypto",))
    monkeypatch.setattr(config, "CURRENT_MARKET_CATEGORY", "crypto")
    monkeypatch.setattr(config, "MARKET_EXCLUDED_PREFIXES", ("Will Bitcoin reach",))
    monkeypatch.setattr(config, "CURRENT_MARKET_SLUG", "Will Bitcoin reach 120k before June?")
    with pytest.raises(ValueError, match="CURRENT_MARKET_CATEGORY/CURRENT_MARKET_SLUG enabled"):
        build_bot()


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


def test_clob_orderbook_source_retries_transient_errors() -> None:
    class DummyLevel:
        def __init__(self, price: float) -> None:
            self.price = str(price)

    class DummyBook:
        bids = [DummyLevel(0.49)]
        asks = [DummyLevel(0.51)]

    class FlakyClob:
        def __init__(self) -> None:
            self.calls = 0

        def get_order_book(self, token_id: str):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("temporary network issue")
            return DummyBook()

    source = ClobOrderBookSource(host="https://clob.polymarket.com", yes_token_id="yes", no_token_id="no")
    flaky = FlakyClob()
    source._client = flaky

    tick = source.next_tick(cycle=1, previous_mid=0.5, rng=__import__("random").Random(1))
    assert tick.yes_mid == pytest.approx(0.5)
    assert tick.no_mid == pytest.approx(0.5)
    assert flaky.calls >= 3


def test_bot_run_all_generates_outputs_and_summary_shape(tmp_path: Path) -> None:
    bot = MM001Bot(cycles=5)
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
        "taker_trades",
        "cumulative_realized_pnl_net",
        "win_rate",
        "average_pnl_per_cycle",
        "average_win_pnl",
        "average_loss_pnl",
        "fill_count",
        "maker_notional",
        "net_capture_per_unit_notional",
        "reward_to_fee_ratio",
        "adverse_taker_ratio",
        "inventory_utilization_ratio",
        "current_inventory_state",
        "largest_inventory_stuck_market",
    }
    assert set(summary.keys()) == expected_keys


def test_load_bot_validation_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValueError):
        _load_bot("badformat", tmp_path / "db.sqlite")

    # module exists but attribute is not callable
    monkeypatch.setattr("MM001.factory.not_callable", 1, raising=False)
    with pytest.raises(TypeError):
        _load_bot("MM001.factory:not_callable", tmp_path / "db.sqlite")


def test_launcher_main_requires_all_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["launcher"])
    with pytest.raises(SystemExit):
        main()


def test_sleep_with_refresh_calls_data_source_refresh(monkeypatch: pytest.MonkeyPatch) -> None:
    class DummySource:
        def __init__(self) -> None:
            self.calls = 0

        def refresh_cache(self) -> None:
            self.calls += 1

    bot = MM001Bot(data_source=DummySource())
    logger = _setup_logger(Path("var/mm001/test-refresh.log"))
    monkeypatch.setattr("time.sleep", lambda _: None)

    _sleep_with_refresh(bot, interval_seconds=2.2, logger=logger)
    assert bot.data_source.calls == 3


def test_launcher_main_writes_simulation_summary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "ORDERBOOK_SOURCE", "simulated")
    out_dir = tmp_path / "reports"
    db_path = tmp_path / "bot.sqlite"
    log_file = tmp_path / "mm001-launcher.log"
    trades_log = tmp_path / "mm001-trades.log"
    aggregate_log = tmp_path / "cycle_aggregates.jsonl"
    monkeypatch.setattr(
        "sys.argv",
        [
            "launcher",
            "--all",
            "--factory",
            "MM001.factory:build_bot",
            "--db-path",
            str(db_path),
            "--output-dir",
            str(out_dir),
            "--log-file",
            str(log_file),
            "--trades-log-file",
            str(trades_log),
            "--aggregate-log-file",
            str(aggregate_log),
            "--max-runs",
            "1",
        ],
    )
    main()

    summary_path = out_dir / "simulation_summary.json"
    assert summary_path.exists()
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert "total_realized" in payload
    assert log_file.exists()
    assert trades_log.exists()
    assert aggregate_log.exists()
    assert "mm001.metrics.table" in log_file.read_text(encoding="utf-8")


def test_launcher_main_accumulates_metrics_across_iterations(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "ORDERBOOK_SOURCE", "simulated")
    out_dir = tmp_path / "reports"
    db_path = tmp_path / "bot.sqlite"
    aggregate_log = tmp_path / "cycle_aggregates.jsonl"
    monkeypatch.setattr(
        "sys.argv",
        [
            "launcher",
            "--all",
            "--factory",
            "MM001.factory:build_bot",
            "--db-path",
            str(db_path),
            "--output-dir",
            str(out_dir),
            "--aggregate-log-file",
            str(aggregate_log),
            "--interval-seconds",
            "0",
            "--max-runs",
            "2",
        ],
    )
    main()

    payloads = [json.loads(line) for line in aggregate_log.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(payloads) == 2
    first = payloads[0]["summary"]["total_realized"]
    second = payloads[1]["summary"]["total_realized"]
    assert second > first


def test_format_launcher_metrics_table_includes_point9_metrics() -> None:
    table = _format_launcher_metrics_table(
        loop_iteration=3,
        summary={
            "cumulative_realized_pnl_net": 12.34,
            "win_rate": 0.75,
            "average_pnl_per_cycle": 1.23,
            "average_win_pnl": 2.34,
            "average_loss_pnl": -0.45,
            "fill_count": 9,
            "maker_notional": 500.0,
            "net_capture_per_unit_notional": 0.02,
            "reward_to_fee_ratio": 1.3,
            "adverse_taker_ratio": 0.1,
            "inventory_utilization_ratio": 0.03,
            "current_inventory_state": {"unpaired_yes_qty_total": 1.0},
            "largest_inventory_stuck_market": {"market_id": "SIMULATED_MM001", "unpaired_qty": 1.0},
        },
    )
    assert "cumulative_realized_pnl_net" in table
    assert "win_rate" in table
    assert "average_pnl_per_cycle" in table
    assert "fill_count" in table
    assert "maker_notional" in table
    assert "net_capture_per_unit_notional" in table
    assert "reward_to_fee_ratio" in table
    assert "adverse_taker_ratio" in table
    assert "inventory_utilization_ratio" in table
    assert "current_inventory_state" in table
    assert "largest_inventory_stuck_market" in table


def test_mm001_statement_coverage_threshold(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Local coverage guard without external plugins (target >=85% statement lines)."""
    import trace

    import MM001.bot as bot_module
    import MM001.factory as factory_module
    import MM001.launcher as launcher_module
    import MM001.strategy as strategy_module

    modules = [bot_module, factory_module, launcher_module, strategy_module]

    tracer = trace.Trace(count=True, trace=False)

    def exercise() -> None:
        monkeypatch.setattr(config, "ORDERBOOK_SOURCE", "simulated")
        inv = Inventory(yes=5.0, no=2.0)
        tick = MarketTick(cycle=1, yes_mid=0.52, no_mid=0.48, spread=0.01)
        q = build_quotes(tick, inv)
        apply_fill(inv, Fill(side="YES", qty=2.0, price=q.yes_bid, maker=True))
        apply_fill(inv, Fill(side="NO", qty=1.0, price=q.no_bid, maker=True))
        _ = fee_equivalent(100, 0.5, 35)
        _ = minimum_net_spread(0.5)
        _ = reservation_price(0.4, inv)
        _ = build_bot("db.sqlite")
        bot = MM001Bot(cycles=3)
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
        monkeypatch.setattr("MM001.factory.not_callable", 1, raising=False)
        try:
            _load_bot("MM001.factory:not_callable", tmp_path / "invalid.sqlite")
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
                "MM001.factory:build_bot",
                "--output-dir",
                str(tmp_path / "cov_launcher"),
                "--max-runs",
                "1",
            ],
        )
        main()
        monkeypatch.setattr(
            "sys.argv",
            [
                "launcher",
                "--all",
                "--factory",
                "MM001.factory:build_bot",
                "--output-dir",
                str(tmp_path / "cov_launcher_2"),
                "--interval-seconds",
                "0",
                "--max-runs",
                "2",
            ],
        )
        main()
        _setup_logger(tmp_path / "cov_launcher_extra.log", log_level="DEBUG")
        _append_cycle_aggregate_log(tmp_path / "cov_cycle_aggregates.jsonl", loop_iteration=1, summary={"total_realized": 1.0})
        _append_trades_log(tmp_path / "missing_output_dir", tmp_path / "cov_trades.log", loop_iteration=1)

        class DummyLevel:
            def __init__(self, price: float) -> None:
                self.price = str(price)

        class DummyBook:
            def __init__(self, bids: list[float], asks: list[float]) -> None:
                self.bids = [DummyLevel(p) for p in bids]
                self.asks = [DummyLevel(p) for p in asks]

        class DummyClob:
            def get_order_book(self, token_id: str):
                books = {
                    "yes": DummyBook([0.49], [0.51]),
                    "no": DummyBook([0.48], [0.52]),
                    "bid_only": DummyBook([0.5], []),
                    "ask_only": DummyBook([], [0.5]),
                    "empty": DummyBook([], []),
                }
                return books[token_id]

        source = ClobOrderBookSource(host="https://clob.polymarket.com", yes_token_id="yes", no_token_id="no")
        source._client = DummyClob()
        source.next_tick(cycle=1, previous_mid=0.5, rng=__import__("random").Random(1))
        source._book_mid("bid_only")
        source._book_mid("ask_only")
        try:
            source._book_mid("empty")
        except ValueError:
            pass

        monkeypatch.setattr(config, "ORDERBOOK_SOURCE", "api")
        monkeypatch.setattr(config, "YES_TOKEN_ID", "yes")
        monkeypatch.setattr(config, "NO_TOKEN_ID", "no")
        api_bot = build_bot("db.sqlite")
        api_bot.data_source._client = DummyClob()
        api_bot.cycles = 2
        api_bot.run_all(output_dir=tmp_path / "cov_api")

    tracer.runfunc(exercise)
    results = tracer.results()

    def relevant_lines(path: str) -> set[int]:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
        relevant: set[int] = set()
        for idx, raw in enumerate(lines, start=1):
            stripped = raw.strip()
            if not stripped:
                continue
            if stripped in {")", "]", "}", "),", "],", "},", "(", "[", "{"}:
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
