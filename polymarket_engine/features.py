from __future__ import annotations

from collections import defaultdict

from .models import FeatureCandidate, PricePoint, TokenCatalogEntry


def build_incoherence_features(tokens: list[TokenCatalogEntry], prices: list[PricePoint], threshold: float) -> list[FeatureCandidate]:
    latest_price_by_token = _latest_price_by_token(prices)
    families: dict[tuple[str, str], list[TokenCatalogEntry]] = defaultdict(list)
    for token in tokens:
        families[(token.event_id, token.outcome.upper())].append(token)

    candidates: list[FeatureCandidate] = []
    for (_, _), family in families.items():
        observed = [latest_price_by_token[token.token_id] for token in family if token.token_id in latest_price_by_token]
        if len(observed) < 2:
            continue
        upper = max(observed)
        lower = min(observed)
        gap = round(upper - lower, 6)
        if gap < threshold:
            continue
        expensive_token = max(family, key=lambda item: latest_price_by_token.get(item.token_id, 0.0))
        candidates.append(
            FeatureCandidate(
                strategy_name="incoherence",
                token_id=expensive_token.token_id,
                market_id=expensive_token.market_id,
                side="NO",
                score=gap,
                gap=gap,
                reason=f"monotonicity_gap={gap}",
                time_to_resolution_seconds=7200,
            )
        )
    return candidates


def build_tail_features(tokens: list[TokenCatalogEntry], prices: list[PricePoint], threshold: float) -> list[FeatureCandidate]:
    latest_price_by_token = _latest_price_by_token(prices)
    candidates: list[FeatureCandidate] = []
    for token in tokens:
        price = latest_price_by_token.get(token.token_id)
        if price is None:
            continue
        extremeness = max(price, 1.0 - price)
        if extremeness < threshold:
            continue
        side = "NO" if price >= threshold else "YES"
        candidates.append(
            FeatureCandidate(
                strategy_name="tail",
                token_id=token.token_id,
                market_id=token.market_id,
                side=side,
                score=round(extremeness, 6),
                gap=round(abs(price - 0.5), 6),
                reason=f"extremeness_score={round(extremeness, 6)}",
                time_to_resolution_seconds=10800,
            )
        )
    return candidates


def _latest_price_by_token(prices: list[PricePoint]) -> dict[str, float]:
    latest: dict[str, PricePoint] = {}
    for point in prices:
        current = latest.get(point.token_id)
        if current is None or point.ts >= current.ts:
            latest[point.token_id] = point
    return {token_id: point.price for token_id, point in latest.items()}
