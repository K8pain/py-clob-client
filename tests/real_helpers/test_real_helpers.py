import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HELPERS_DIR = ROOT / "ToTheMoon" / "real_helpers"


def load_module(name: str):
    spec = importlib.util.spec_from_file_location(name, HELPERS_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


pnl_engine = load_module("pnl_engine")
risk_controls = load_module("risk_controls")
market_regime = load_module("market_regime")
execution_guard = load_module("execution_guard")
resilience = load_module("resilience")
strategy_validation = load_module("strategy_validation")


class TestPnlEngine(unittest.TestCase):
    def test_net_pnl_includes_fees_and_slippage(self):
        pnl = pnl_engine.calculate_net_pnl(100, 110, 2, fee_rate=0.001, slippage_rate=0.01)
        self.assertEqual(pnl.gross_pnl, 20)
        self.assertAlmostEqual(pnl.fees, 0.42)
        self.assertAlmostEqual(pnl.slippage_cost, 0.2)
        self.assertAlmostEqual(pnl.net_pnl, 19.38)

    def test_impossible_equity_jump_flagged(self):
        self.assertFalse(pnl_engine.validate_equity_jump(1000, 2000, max_jump_pct=0.5))


class TestRiskControls(unittest.TestCase):
    def test_position_cap_blocks_oversizing(self):
        self.assertEqual(risk_controls.enforce_position_cap(15, 10), 10)

    def test_circuit_breaker_halts_after_threshold(self):
        state = risk_controls.check_circuit_breaker(
            consecutive_losses=3,
            max_consecutive_losses=3,
            rolling_drawdown_pct=0.05,
            max_drawdown_pct=0.1,
            last_n_trade_results=[-1, -2, 1],
            max_losses_in_window=5,
        )
        self.assertTrue(state.triggered)
        self.assertEqual(state.reason, "max_consecutive_losses")


class TestMarketRegime(unittest.TestCase):
    def test_regime_filter_blocks_chop(self):
        regime = market_regime.classify_market_regime(adx=10, band_width_pct=0.05)
        self.assertEqual(regime, market_regime.MarketRegime.CHOPPY)
        self.assertFalse(market_regime.is_trade_allowed_for_regime(regime))


class TestExecutionGuard(unittest.TestCase):
    def test_should_open_trade_requires_all_checks(self):
        allowed = execution_guard.should_open_trade(
            regime_allowed=True,
            pretrade_checks={"risk_ok": True, "api_ok": False},
        )
        self.assertFalse(allowed)


class TestResilience(unittest.TestCase):
    def test_retry_logic_retries_and_then_fails_cleanly(self):
        attempts = {"count": 0}

        def flaky():
            attempts["count"] += 1
            raise TimeoutError("temporary")

        with self.assertRaises(TimeoutError):
            resilience.retry_with_backoff(flaky, max_attempts=3, base_delay_seconds=0, sleeper=lambda _: None)
        self.assertEqual(attempts["count"], 3)

    def test_timeout_logic_triggers_correctly(self):
        import time
        with self.assertRaises(TimeoutError):
            resilience.api_timeout_guard(lambda: time.sleep(0.05), timeout_seconds=0.001)

    def test_watchdog_detects_stale_process(self):
        self.assertTrue(resilience.heartbeat_monitor(last_heartbeat_ts=0, threshold_seconds=10, now=20))


class TestStrategyValidation(unittest.TestCase):
    def test_paper_live_approval_gate_shape(self):
        result = strategy_validation.validate_backtest_results(
            sample_size=200,
            sharpe=1.5,
            max_drawdown_pct=0.1,
        )
        self.assertTrue(result.passed)


if __name__ == "__main__":
    unittest.main()
