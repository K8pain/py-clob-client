from dataclasses import dataclass
from statistics import mean
from typing import Sequence


@dataclass(frozen=True)
class ValidationResult:
    passed: bool
    reason: str


def validate_backtest_results(sample_size: int, sharpe: float, max_drawdown_pct: float, min_sample_size: int = 100, min_sharpe: float = 1.0, max_allowed_drawdown_pct: float = 0.2) -> ValidationResult:
    if sample_size < min_sample_size:
        return ValidationResult(False, "insufficient_sample_size")
    if sharpe < min_sharpe:
        return ValidationResult(False, "sharpe_too_low")
    if max_drawdown_pct > max_allowed_drawdown_pct:
        return ValidationResult(False, "drawdown_too_high")
    return ValidationResult(True, "ok")


def run_monte_carlo_checks(simulated_returns: Sequence[float], min_win_rate: float = 0.45) -> ValidationResult:
    if not simulated_returns:
        return ValidationResult(False, "no_simulations")
    wins = sum(1 for r in simulated_returns if r > 0)
    win_rate = wins / len(simulated_returns)
    return ValidationResult(win_rate >= min_win_rate, "ok" if win_rate >= min_win_rate else "monte_carlo_unstable")


def run_walk_forward_validation(window_scores: Sequence[float], min_avg_score: float = 0.0) -> ValidationResult:
    if not window_scores:
        return ValidationResult(False, "no_windows")
    avg_score = mean(window_scores)
    return ValidationResult(avg_score >= min_avg_score, "ok" if avg_score >= min_avg_score else "walk_forward_unstable")
