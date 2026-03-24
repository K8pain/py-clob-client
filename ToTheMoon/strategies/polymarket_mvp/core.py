from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Optional


ASCENDING_OPERATORS = {"reach_up", "close_above"}
DESCENDING_OPERATORS = {"dip_down", "close_below"}
SUPPORTED_OPERATORS = ASCENDING_OPERATORS | DESCENDING_OPERATORS | {"range_between"}


@dataclass(frozen=True)
class MarketDefinition:
    market_slug: str
    market_id: str
    yes_token_id: str
    no_token_id: str
    question: str
    family: str
    operator_type: str
    strike: float
    expiry_ts: int
    status: str
    underlying: str
    temporal_bucket: str


@dataclass(frozen=True)
class MarketState:
    token_id: str
    best_bid: float
    best_ask: float
    midpoint: float | None
    last_trade: float | None
    spread: float
    tick_size: float
    visible_depth: float
    last_update_ts: int
    resolved_flag: bool = False


@dataclass(frozen=True)
class UnderlyingState:
    symbol: str
    spot: float
    source: str
    last_update_ts: int
    rolling_return_std: float
    rolling_range: float


@dataclass(frozen=True)
class StrategyThresholds:
    ttl_ms: int = 15_000
    max_spread_prob: float = 0.05
    min_depth_qty: float = 50.0
    min_edge_prob: float = 0.03
    min_liquidity_score: float = 0.25
    max_notional_per_trade: float = 25.0
    min_tail_z_score: float = 1.5
    min_bucket_obs: int = 30
    min_tail_premium: float = 0.04
    max_book_rtds_skew_ms: int = 5_000
    min_volatility: float = 1e-6


@dataclass(frozen=True)
class SignalCandidate:
    alpha_name: str
    market_id: str
    side: str
    reference_prob: float
    fair_prob: float
    edge_prob: float
    liquidity_score: float
    staleness_ms: int
    group_id: str
    rationale: dict[str, Any]


@dataclass(frozen=True)
class PaperTrade:
    trade_id: str
    market_id: str
    side: str
    qty: float
    entry_px: float
    fee_bps: float
    effective_cost: float
    opened_ts: int
    alpha_name: str
    rationale_json: dict[str, Any]


@dataclass(frozen=True)
class ResolutionRecord:
    trade_id: str
    resolved_ts: int
    payout: float
    pnl_abs: float
    pnl_pct: float
    outcome_label: str


def parse_market_definition(raw_market: dict[str, Any], now_ts: int | None = None) -> MarketDefinition | None:
    question = str(raw_market.get("question") or raw_market.get("market_slug") or "").strip()
    operator_type = _infer_operator_type(question)
    if operator_type is None:
        return None

    strike = _extract_strike(question)
    if strike is None and operator_type != "range_between":
        return None

    now_ts = now_ts or int(datetime.now(timezone.utc).timestamp())
    expiry_ts = int(raw_market.get("expiry_ts") or raw_market.get("end_date_iso_ts") or now_ts)
    yes_token_id, no_token_id = _extract_token_ids(raw_market.get("tokens", []))
    if yes_token_id is None or no_token_id is None:
        return None

    underlying = _infer_underlying(question)
    if underlying is None:
        return None

    status = str(raw_market.get("status") or ("active" if raw_market.get("active", True) else "inactive"))
    if status.lower() not in {"active", "open"}:
        return None

    family = operator_type
    temporal_bucket = _bucketize_expiry(expiry_ts - now_ts)

    return MarketDefinition(
        market_slug=str(raw_market.get("market_slug", raw_market.get("slug", "unknown"))),
        market_id=str(raw_market.get("market_id", raw_market.get("id", "unknown"))),
        yes_token_id=yes_token_id,
        no_token_id=no_token_id,
        question=question,
        family=family,
        operator_type=operator_type,
        strike=float(strike or 0.0),
        expiry_ts=expiry_ts,
        status=status.lower(),
        underlying=underlying,
        temporal_bucket=temporal_bucket,
    )


def build_related_groups(markets: Iterable[MarketDefinition], expiry_window_hours: int = 24) -> dict[str, list[MarketDefinition]]:
    grouped: dict[str, list[MarketDefinition]] = {}
    seconds = expiry_window_hours * 3600
    for market in markets:
        proximity = market.expiry_ts // max(seconds, 1)
        group_id = f"{market.underlying}:{market.operator_type}:{market.temporal_bucket}:{proximity}"
        grouped.setdefault(group_id, []).append(market)

    for key, items in grouped.items():
        grouped[key] = sorted(items, key=lambda item: (item.strike, item.expiry_ts, item.market_id))
    return grouped


def compute_reference_probability(state: MarketState, thresholds: StrategyThresholds, now_ms: int) -> float | None:
    staleness_ms = now_ms - state.last_update_ts
    if staleness_ms > thresholds.ttl_ms or state.visible_depth < thresholds.min_depth_qty:
        return None
    if state.spread <= thresholds.max_spread_prob and state.midpoint is not None:
        return _clamp01(state.midpoint)
    if state.last_trade is not None:
        return _clamp01(state.last_trade)
    return None


def score_related_market_incoherence(
    group: list[MarketDefinition],
    live_state: dict[str, MarketState],
    thresholds: StrategyThresholds,
    now_ms: int,
    fee_bps: float = 0.0,
) -> list[SignalCandidate]:
    if len(group) < 2:
        return []

    ordered = sorted(group, key=lambda item: item.strike)
    candidates: list[SignalCandidate] = []
    for lower, higher in zip(ordered, ordered[1:]):
        lower_state = live_state.get(lower.yes_token_id)
        higher_state = live_state.get(higher.yes_token_id)
        if lower_state is None or higher_state is None:
            continue

        lower_prob = compute_reference_probability(lower_state, thresholds, now_ms)
        higher_prob = compute_reference_probability(higher_state, thresholds, now_ms)
        if lower_prob is None or higher_prob is None:
            continue

        violation = _monotonic_violation(lower.operator_type, lower_prob, higher_prob)
        overpriced = higher if lower.operator_type in ASCENDING_OPERATORS else lower
        overpriced_state = higher_state if overpriced is higher else lower_state
        overpriced_prob = higher_prob if overpriced is higher else lower_prob
        fair_prob = lower_prob if overpriced is higher else higher_prob
        liquidity_score = _liquidity_score(overpriced_state, thresholds)
        fee_cost = (fee_bps / 10_000) * overpriced_state.best_ask
        edge_after_cost = violation - overpriced_state.spread - fee_cost
        if edge_after_cost < thresholds.min_edge_prob or liquidity_score < thresholds.min_liquidity_score:
            continue

        candidates.append(
            SignalCandidate(
                alpha_name="related_market_incoherence",
                market_id=overpriced.market_id,
                side="NO",
                reference_prob=overpriced_prob,
                fair_prob=fair_prob,
                edge_prob=edge_after_cost,
                liquidity_score=liquidity_score,
                staleness_ms=now_ms - overpriced_state.last_update_ts,
                group_id=f"{overpriced.underlying}:{overpriced.operator_type}:{overpriced.temporal_bucket}",
                rationale={
                    "violation_prob": round(violation, 6),
                    "overpriced_market_id": overpriced.market_id,
                    "lower_market_id": lower.market_id,
                    "higher_market_id": higher.market_id,
                    "spread_cost": overpriced_state.spread,
                    "fee_cost": round(fee_cost, 6),
                },
            )
        )
    return candidates


def score_tail_premium(
    candidate: MarketDefinition,
    market_state_obj: MarketState,
    underlying_obj: UnderlyingState,
    fair_prob_empirical: float,
    sample_size: int,
    thresholds: StrategyThresholds,
    now_ms: int,
) -> SignalCandidate | None:
    reference_prob = compute_reference_probability(market_state_obj, thresholds, now_ms)
    if reference_prob is None:
        return None
    if sample_size < thresholds.min_bucket_obs:
        return None
    if abs(market_state_obj.last_update_ts - underlying_obj.last_update_ts) > thresholds.max_book_rtds_skew_ms:
        return None
    if underlying_obj.rolling_return_std < thresholds.min_volatility:
        return None

    time_to_expiry_h = max((candidate.expiry_ts - now_ms // 1000) / 3600, 1 / 3600)
    sigma_term = underlying_obj.rolling_return_std * underlying_obj.spot * math.sqrt(time_to_expiry_h / 24)
    z_distance = abs(candidate.strike - underlying_obj.spot) / max(sigma_term, thresholds.min_volatility)
    if z_distance < thresholds.min_tail_z_score:
        return None

    tail_premium = reference_prob - fair_prob_empirical
    liquidity_score = _liquidity_score(market_state_obj, thresholds)
    if tail_premium < thresholds.min_tail_premium or liquidity_score < thresholds.min_liquidity_score:
        return None

    return SignalCandidate(
        alpha_name="tail_premium",
        market_id=candidate.market_id,
        side="NO",
        reference_prob=reference_prob,
        fair_prob=fair_prob_empirical,
        edge_prob=tail_premium,
        liquidity_score=liquidity_score,
        staleness_ms=now_ms - market_state_obj.last_update_ts,
        group_id=f"{candidate.underlying}:{candidate.operator_type}:{candidate.temporal_bucket}",
        rationale={
            "z_distance": round(z_distance, 6),
            "spot_rt": underlying_obj.spot,
            "rolling_sigma": underlying_obj.rolling_return_std,
            "sample_size": sample_size,
        },
    )


def simulate_entry(
    signal_obj: SignalCandidate,
    book_state: MarketState,
    max_notional: float,
    now_ms: int,
    fee_bps: float = 0.0,
) -> PaperTrade | None:
    entry_px = book_state.best_ask
    if entry_px <= 0 or book_state.visible_depth <= 0:
        return None

    qty = min(book_state.visible_depth, max_notional / entry_px)
    if qty <= 0:
        return None

    fee_cost = qty * entry_px * (fee_bps / 10_000)
    effective_cost = qty * entry_px + fee_cost
    return PaperTrade(
        trade_id=f"{signal_obj.alpha_name}:{signal_obj.market_id}:{now_ms}",
        market_id=signal_obj.market_id,
        side=signal_obj.side,
        qty=round(qty, 6),
        entry_px=entry_px,
        fee_bps=fee_bps,
        effective_cost=round(effective_cost, 6),
        opened_ts=now_ms,
        alpha_name=signal_obj.alpha_name,
        rationale_json=signal_obj.rationale,
    )


def settle_trade(trade: PaperTrade, resolved_label: str, now_ms: int | None = None) -> ResolutionRecord:
    now_ms = now_ms or int(datetime.now(timezone.utc).timestamp() * 1000)
    winning = resolved_label.strip().upper() == trade.side.upper()
    payout = trade.qty if winning else 0.0
    pnl_abs = round(payout - trade.effective_cost, 6)
    pnl_pct = round(pnl_abs / trade.effective_cost, 6) if trade.effective_cost else 0.0
    return ResolutionRecord(
        trade_id=trade.trade_id,
        resolved_ts=now_ms,
        payout=round(payout, 6),
        pnl_abs=pnl_abs,
        pnl_pct=pnl_pct,
        outcome_label=resolved_label,
    )


def _extract_token_ids(tokens: Iterable[dict[str, Any]]) -> tuple[Optional[str], Optional[str]]:
    yes_token_id: Optional[str] = None
    no_token_id: Optional[str] = None
    for token in tokens:
        outcome = str(token.get("outcome", "")).upper()
        token_id = token.get("token_id") or token.get("id")
        if not token_id:
            continue
        if outcome == "YES":
            yes_token_id = str(token_id)
        elif outcome == "NO":
            no_token_id = str(token_id)
    return yes_token_id, no_token_id


def _infer_operator_type(text: str) -> str | None:
    lowered = text.lower()
    if "between" in lowered and " and " in lowered:
        return "range_between"
    if "reach" in lowered or "hit" in lowered:
        return "reach_up"
    if "dip" in lowered or "drop to" in lowered or "fall to" in lowered:
        return "dip_down"
    if "close above" in lowered or "close over" in lowered:
        return "close_above"
    if "close below" in lowered or "close under" in lowered:
        return "close_below"
    return None


def _extract_strike(text: str) -> float | None:
    match = re.search(r"\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]+)?)", text)
    if not match:
        return None
    return float(match.group(1).replace(",", ""))


def _infer_underlying(text: str) -> str | None:
    lowered = text.lower()
    mappings = {
        "bitcoin": "BTC",
        "btc": "BTC",
        "ethereum": "ETH",
        "eth": "ETH",
        "solana": "SOL",
        "sol": "SOL",
    }
    for token, symbol in mappings.items():
        if token in lowered:
            return symbol
    return None


def _bucketize_expiry(tenor_seconds: int) -> str:
    if tenor_seconds <= 86_400:
        return "intraday"
    if tenor_seconds <= 3 * 86_400:
        return "1d-3d"
    if tenor_seconds <= 7 * 86_400:
        return "4d-7d"
    return ">7d"


def _monotonic_violation(operator_type: str, lower_prob: float, higher_prob: float) -> float:
    if operator_type in ASCENDING_OPERATORS:
        return max(0.0, higher_prob - lower_prob)
    if operator_type in DESCENDING_OPERATORS:
        return max(0.0, lower_prob - higher_prob)
    return 0.0


def _liquidity_score(state: MarketState, thresholds: StrategyThresholds) -> float:
    spread_score = max(0.0, 1.0 - (state.spread / max(thresholds.max_spread_prob, 1e-9)))
    depth_score = min(1.0, state.visible_depth / max(thresholds.min_depth_qty, 1e-9))
    return round((spread_score + depth_score) / 2, 6)


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))
