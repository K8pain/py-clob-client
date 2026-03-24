from __future__ import annotations

import pytest

from conftest import load_helper_module

pnl = load_helper_module("pnl_engine")


def test_calculate_gross_and_net_pnl_include_fees_and_slippage():
    gross = pnl.calculate_gross_pnl(100, 105, 2, "long")
    net = pnl.calculate_net_pnl(100, 105, 2, "long", fee_rate=0.001, slippage_bps=10)
    assert gross == 10
    assert net < gross


def test_update_compounded_equity_rejects_impossible_jump():
    with pytest.raises(ValueError, match="unrealistic equity jump"):
        pnl.update_compounded_equity(1000, 900, max_single_trade_return=0.5)


def test_update_cumulative_pnl():
    assert pnl.update_cumulative_pnl(50, -10) == 40
