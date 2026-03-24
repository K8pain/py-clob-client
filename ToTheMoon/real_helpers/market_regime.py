from enum import Enum
from statistics import mean
from typing import Sequence


class MarketRegime(str, Enum):
    TRENDING = "trending"
    RANGING = "ranging"
    HIGH_VOLATILITY = "high_volatility"
    LOW_VOLATILITY = "low_volatility"
    CHOPPY = "choppy"


def calculate_adx(high: Sequence[float], low: Sequence[float], close: Sequence[float]) -> float:
    if not high or not low or not close:
        return 0.0
    ranges = [h - l for h, l in zip(high, low)]
    avg_range = mean(ranges) if ranges else 0.0
    avg_close = mean(close)
    return 0.0 if avg_close == 0 else min((avg_range / avg_close) * 500, 100)


def calculate_bollinger_bands(prices: Sequence[float], num_std: float = 2.0) -> tuple[float, float, float]:
    mid = mean(prices)
    variance = mean((p - mid) ** 2 for p in prices)
    std = variance ** 0.5
    return mid - num_std * std, mid, mid + num_std * std


def classify_market_regime(adx: float, band_width_pct: float) -> MarketRegime:
    if band_width_pct >= 0.08:
        return MarketRegime.HIGH_VOLATILITY
    if adx >= 25:
        return MarketRegime.TRENDING
    if band_width_pct <= 0.02:
        return MarketRegime.LOW_VOLATILITY
    if adx < 15 and band_width_pct > 0.04:
        return MarketRegime.CHOPPY
    return MarketRegime.RANGING


def is_trade_allowed_for_regime(regime: MarketRegime) -> bool:
    return regime in {MarketRegime.TRENDING, MarketRegime.RANGING}
