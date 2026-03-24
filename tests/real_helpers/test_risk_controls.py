from __future__ import annotations

import pytest

from conftest import load_helper_module

risk = load_helper_module("risk_controls")


def test_enforce_position_cap_reduce_and_reject():
    assert risk.enforce_position_cap(15, 10, mode="reduce") == 10
    with pytest.raises(ValueError):
        risk.enforce_position_cap(15, 10, mode="reject")


def test_check_circuit_breaker_after_consecutive_losses():
    assert risk.check_circuit_breaker(
        consecutive_losses=3,
        max_consecutive_losses=3,
        rolling_drawdown=-1,
        max_drawdown=10,
        last_n_trade_results=[1, -1],
        max_losses_in_window=2,
        window_size=2,
    )


def test_enforce_capital_guards_blocks_oversizing():
    assert not risk.enforce_capital_guards(12, 10, 3, 1, 50, 100)
    assert risk.enforce_capital_guards(8, 10, 3, 1, 50, 100)
