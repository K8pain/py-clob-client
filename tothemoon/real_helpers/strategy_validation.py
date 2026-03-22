from __future__ import annotations

from statistics import mean, pstdev


def validate_backtest_results(
    sample_size: int,
    min_sample_size: int,
    sharpe_ratio: float,
    min_sharpe_ratio: float,
    max_drawdown: float,
    max_allowed_drawdown: float,
    scenario_pass_rate: float,
    min_scenario_pass_rate: float,
) -> tuple[bool, list[str]]:
    failures = []
    if sample_size < min_sample_size:
        failures.append("sample_size_too_small")
    if sharpe_ratio < min_sharpe_ratio:
        failures.append("sharpe_below_threshold")
    if max_drawdown > max_allowed_drawdown:
        failures.append("drawdown_too_high")
    if scenario_pass_rate < min_scenario_pass_rate:
        failures.append("scenario_stability_too_low")
    return len(failures) == 0, failures


def run_monte_carlo_checks(returns: list[float], min_percentile_return: float = -0.02) -> tuple[bool, float]:
    if not returns:
        raise ValueError("returns must not be empty")
    sorted_returns = sorted(returns)
    index = max(0, int(0.05 * len(sorted_returns)) - 1)
    fifth_percentile = sorted_returns[index]
    return fifth_percentile >= min_percentile_return, fifth_percentile


def run_walk_forward_validation(train_scores: list[float], test_scores: list[float], stability_tolerance: float = 0.25) -> bool:
    if len(train_scores) != len(test_scores) or not train_scores:
        raise ValueError("train_scores and test_scores must have same non-zero length")
    train_mean = mean(train_scores)
    test_mean = mean(test_scores)
    if train_mean == 0:
        return False
    return abs(train_mean - test_mean) / abs(train_mean) <= stability_tolerance


def parameter_sensitivity_analysis(metric_values: list[float], max_variation: float = 0.4) -> bool:
    if not metric_values:
        raise ValueError("metric_values must not be empty")
    avg = mean(metric_values)
    if avg == 0:
        return False
    variation = pstdev(metric_values) / abs(avg)
    return variation <= max_variation


def approve_strategy(all_checks: list[bool]) -> bool:
    return all(all_checks)
