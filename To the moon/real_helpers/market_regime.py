from __future__ import annotations

from statistics import mean, pstdev


def calculate_adx(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> float:
    if min(len(highs), len(lows), len(closes)) < period + 1:
        raise ValueError("not enough data to calculate ADX")

    true_ranges = []
    directional_plus = []
    directional_minus = []
    for i in range(1, period + 1):
        tr = max(
            highs[-i] - lows[-i],
            abs(highs[-i] - closes[-i - 1]),
            abs(lows[-i] - closes[-i - 1]),
        )
        true_ranges.append(tr)
        up_move = highs[-i] - highs[-i - 1]
        down_move = lows[-i - 1] - lows[-i]
        directional_plus.append(max(up_move, 0) if up_move > down_move else 0)
        directional_minus.append(max(down_move, 0) if down_move > up_move else 0)

    atr = mean(true_ranges)
    if atr == 0:
        return 0.0

    plus_di = 100 * (mean(directional_plus) / atr)
    minus_di = 100 * (mean(directional_minus) / atr)
    if plus_di + minus_di == 0:
        return 0.0
    return abs(plus_di - minus_di) / (plus_di + minus_di) * 100


def calculate_bollinger_bands(prices: list[float], period: int = 20, std_dev: float = 2.0) -> tuple[float, float, float]:
    if len(prices) < period:
        raise ValueError("not enough data for Bollinger Bands")

    window = prices[-period:]
    middle = mean(window)
    sigma = pstdev(window)
    upper = middle + std_dev * sigma
    lower = middle - std_dev * sigma
    return lower, middle, upper


def classify_market_regime(adx: float, bollinger_width_pct: float, atr_pct: float) -> str:
    if atr_pct >= 3.0:
        return "high_volatility"
    if adx >= 25 and bollinger_width_pct >= 4.0:
        return "trending"
    if adx < 20 and bollinger_width_pct < 2.0:
        return "ranging"
    if adx < 18 and atr_pct < 1.0:
        return "low_volatility"
    return "choppy"


def is_trade_allowed_for_regime(regime: str, allowed_regimes: set[str] | None = None) -> bool:
    if allowed_regimes is None:
        allowed_regimes = {"trending", "ranging"}
    return regime in allowed_regimes
