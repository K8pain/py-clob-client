from __future__ import annotations

from conftest import load_helper_module

validation = load_helper_module("strategy_validation")


def test_validate_backtest_results_flags_failures():
    approved, failures = validation.validate_backtest_results(
        sample_size=50,
        min_sample_size=100,
        sharpe_ratio=0.8,
        min_sharpe_ratio=1.0,
        max_drawdown=0.25,
        max_allowed_drawdown=0.2,
        scenario_pass_rate=0.6,
        min_scenario_pass_rate=0.7,
    )
    assert not approved
    assert len(failures) == 4


def test_walk_forward_and_parameter_sensitivity():
    assert validation.run_walk_forward_validation([1.0, 0.9], [0.9, 0.8], stability_tolerance=0.3)
    assert validation.parameter_sensitivity_analysis([1.0, 1.1, 0.9], max_variation=0.2)


def test_monte_carlo_and_approval_gate():
    passes, percentile = validation.run_monte_carlo_checks([0.01, 0.02, -0.01, 0.005, 0.03], min_percentile_return=-0.02)
    assert passes
    assert percentile <= 0.01
    assert validation.approve_strategy([True, True, True])
