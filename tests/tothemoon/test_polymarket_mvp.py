from ToTheMoon.strategies.polymarket_mvp import (
    MarketDefinition,
    MarketState,
    PaperTrade,
    SignalCandidate,
    StrategyThresholds,
    UnderlyingState,
    build_related_groups,
    compute_reference_probability,
    parse_market_definition,
    score_related_market_incoherence,
    score_tail_premium,
    settle_trade,
    simulate_entry,
)


def test_parse_market_definition_extracts_operator_strike_and_bucket():
    market = parse_market_definition(
        {
            "id": "m1",
            "market_slug": "btc-80k",
            "question": "Will Bitcoin reach $80,000 by March 30?",
            "tokens": [
                {"outcome": "YES", "token_id": "yes-1"},
                {"outcome": "NO", "token_id": "no-1"},
            ],
            "active": True,
            "status": "active",
            "expiry_ts": 1_710_000_000,
        },
        now_ts=1_709_950_000,
    )

    assert market is not None
    assert market.operator_type == "reach_up"
    assert market.strike == 80000.0
    assert market.underlying == "BTC"
    assert market.temporal_bucket == "intraday"


def test_build_related_groups_clusters_by_underlying_operator_and_window():
    markets = [
        MarketDefinition("slug-1", "m1", "y1", "n1", "q1", "reach_up", "reach_up", 80000, 1_710_000_000, "active", "BTC", "1d-3d"),
        MarketDefinition("slug-2", "m2", "y2", "n2", "q2", "reach_up", "reach_up", 85000, 1_710_001_000, "active", "BTC", "1d-3d"),
        MarketDefinition("slug-3", "m3", "y3", "n3", "q3", "reach_up", "reach_up", 4500, 1_710_001_000, "active", "ETH", "1d-3d"),
    ]

    groups = build_related_groups(markets, expiry_window_hours=24)

    assert len(groups) == 2
    btc_group = next(group for key, group in groups.items() if key.startswith("BTC:"))
    assert [market.market_id for market in btc_group] == ["m1", "m2"]


def test_compute_reference_probability_prefers_midpoint_and_falls_back_to_last_trade():
    thresholds = StrategyThresholds(ttl_ms=20_000, max_spread_prob=0.03, min_depth_qty=10)
    midpoint_state = MarketState("t1", 0.39, 0.41, 0.4, 0.38, 0.02, 0.01, 25, 1000)
    stale_midpoint_state = MarketState("t2", 0.39, 0.45, None, 0.43, 0.06, 0.01, 25, 1000)

    assert compute_reference_probability(midpoint_state, thresholds, now_ms=15_000) == 0.4
    assert compute_reference_probability(stale_midpoint_state, thresholds, now_ms=15_000) == 0.43


def test_score_related_market_incoherence_returns_no_signal_for_overpriced_harder_strike():
    thresholds = StrategyThresholds(min_edge_prob=0.02, min_liquidity_score=0.2, min_depth_qty=10, max_spread_prob=0.05)
    markets = [
        MarketDefinition("btc-80k", "m1", "yes-1", "no-1", "Will BTC reach $80,000?", "reach_up", "reach_up", 80000, 1_710_000_000, "active", "BTC", "1d-3d"),
        MarketDefinition("btc-90k", "m2", "yes-2", "no-2", "Will BTC reach $90,000?", "reach_up", "reach_up", 90000, 1_710_000_000, "active", "BTC", "1d-3d"),
    ]
    live_state = {
        "yes-1": MarketState("yes-1", 0.48, 0.52, 0.5, 0.49, 0.02, 0.01, 100, 10_000),
        "yes-2": MarketState("yes-2", 0.58, 0.62, 0.6, 0.59, 0.02, 0.01, 100, 10_000),
    }

    signals = score_related_market_incoherence(markets, live_state, thresholds, now_ms=20_000, fee_bps=0)

    assert len(signals) == 1
    assert signals[0].market_id == "m2"
    assert signals[0].side == "NO"
    assert signals[0].rationale["violation_prob"] == 0.1


def test_score_tail_premium_uses_empirical_fair_value_and_requires_z_distance():
    thresholds = StrategyThresholds(
        min_tail_z_score=1.0,
        min_bucket_obs=20,
        min_tail_premium=0.05,
        min_depth_qty=10,
        min_liquidity_score=0.2,
    )
    market = MarketDefinition("btc-120k", "m3", "yes-3", "no-3", "Will BTC close above $120,000?", "close_above", "close_above", 120000, 1_710_172_800, "active", "BTC", "1d-3d")
    market_state = MarketState("yes-3", 0.18, 0.22, 0.2, 0.19, 0.02, 0.01, 100, 1_709_900_000_000)
    underlying = UnderlyingState("BTC", 100000, "rtds", 1_709_900_001_000, 0.05, 4000)

    signal = score_tail_premium(
        market,
        market_state,
        underlying,
        fair_prob_empirical=0.08,
        sample_size=40,
        thresholds=thresholds,
        now_ms=1_709_900_005_000,
    )

    assert signal is not None
    assert signal.side == "NO"
    assert round(signal.edge_prob, 6) == 0.12
    assert signal.rationale["sample_size"] == 40


def test_simulate_entry_and_settle_trade_compute_effective_cost_and_pnl():
    signal = SignalCandidate(
        alpha_name="related_market_incoherence",
        market_id="m2",
        side="NO",
        reference_prob=0.6,
        fair_prob=0.5,
        edge_prob=0.08,
        liquidity_score=0.8,
        staleness_ms=100,
        group_id="BTC:reach_up:1d-3d",
        rationale={"violation_prob": 0.1},
    )
    state = MarketState("no-2", 0.38, 0.4, 0.39, 0.4, 0.02, 0.01, 30, 20_000)

    trade = simulate_entry(signal, state, max_notional=10, now_ms=30_000, fee_bps=50)

    assert trade is not None
    assert trade.qty == 25.0
    assert trade.effective_cost == 10.05

    resolution = settle_trade(trade, resolved_label="NO", now_ms=40_000)

    assert resolution.payout == 25.0
    assert resolution.pnl_abs == 14.95
    assert resolution.outcome_label == "NO"
