from __future__ import annotations

from conftest import load_helper_module

regime = load_helper_module("market_regime")


def test_calculate_bollinger_bands():
    lower, middle, upper = regime.calculate_bollinger_bands([100 + i for i in range(20)])
    assert lower < middle < upper


def test_classify_market_regime_and_filter():
    detected = regime.classify_market_regime(adx=15, bollinger_width_pct=1.0, atr_pct=0.8)
    assert detected == "ranging"
    assert not regime.is_trade_allowed_for_regime("choppy", {"trending"})


def test_calculate_adx_returns_number():
    highs = [10 + i * 0.2 for i in range(30)]
    lows = [9 + i * 0.2 for i in range(30)]
    closes = [9.5 + i * 0.2 for i in range(30)]
    adx = regime.calculate_adx(highs, lows, closes)
    assert 0 <= adx <= 100
