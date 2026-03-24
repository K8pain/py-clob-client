# HOWTO: Use `ToTheMoon.strategies.polymarket_mvp`

## Quick import
```python
from ToTheMoon.strategies.polymarket_mvp import (
    MarketDefinition,
    MarketState,
    UnderlyingState,
    StrategyThresholds,
    parse_market_definition,
    build_related_groups,
    score_related_market_incoherence,
    score_tail_premium,
    simulate_entry,
    settle_trade,
)
```

## Minimal workflow example
```python
thresholds = StrategyThresholds()
now_ms = 1_710_000_000_000

raw_market = {
    "id": "m1",
    "market_slug": "btc-reach-90k",
    "question": "Will Bitcoin reach $90,000 by Friday?",
    "tokens": [
        {"outcome": "YES", "token_id": "yes-1"},
        {"outcome": "NO", "token_id": "no-1"},
    ],
    "status": "active",
    "expiry_ts": 1_710_086_400,
}

market = parse_market_definition(raw_market)
if market is None:
    raise ValueError("Market not eligible")

book_state = MarketState(
    token_id=market.yes_token_id,
    best_bid=0.41,
    best_ask=0.43,
    midpoint=0.42,
    last_trade=0.42,
    spread=0.02,
    tick_size=0.01,
    visible_depth=100.0,
    last_update_ts=now_ms,
)

# Example: tail-premium scoring
underlying = UnderlyingState(
    symbol="BTC",
    spot=82_000,
    source="rtds",
    last_update_ts=now_ms,
    rolling_return_std=0.04,
    rolling_range=1_500,
)

signal = score_tail_premium(
    candidate=market,
    market_state_obj=book_state,
    underlying_obj=underlying,
    fair_prob_empirical=0.08,
    sample_size=80,
    thresholds=thresholds,
    now_ms=now_ms,
)

if signal:
    trade = simulate_entry(signal, book_state, max_notional=25.0, now_ms=now_ms)
    if trade:
        resolution = settle_trade(trade, resolved_label="NO")
        print(trade, resolution)
```

## Notes
- Use YES token `MarketState` as pricing reference for scoring.
- The strategy defaults to conservative gating (staleness/depth/spread/sample thresholds).
- For related-market alpha, pass grouped markets and a `token_id -> MarketState` map.
