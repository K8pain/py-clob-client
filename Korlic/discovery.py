from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone

from .models import ClassificationStatus, ClassifiedMarket, MarketRecord

FIVE_MINUTE_REGEX = re.compile(r"\b(5\s*m(in(ute)?s?)?|300\s*s(ec)?)\b", re.IGNORECASE)
CRYPTO_TERMS = {"crypto", "bitcoin", "btc", "ethereum", "eth", "sol", "xrp", "doge"}


@dataclass(frozen=True)
class DiscoveryState:
    markets: dict[str, ClassifiedMarket]
    parser_version: str
    discovered_at: str


class MarketClassifier:
    def __init__(self, min_confidence: float = 0.8) -> None:
        self.min_confidence = min_confidence

    def is_crypto(self, market: MarketRecord) -> bool:
        haystack = " ".join([market.question, market.slug, market.category or "", *market.tags]).lower()
        return any(term in haystack for term in CRYPTO_TERMS)

    def classify(self, market: MarketRecord) -> ClassifiedMarket:
        if market.cadence_hint and market.cadence_hint.strip().lower() in {"5m", "5min", "300s"}:
            return ClassifiedMarket(market=market, status=ClassificationStatus.CANDIDATE_5M, confidence=1.0, method="metadata")

        haystack = " ".join([market.question, market.slug]).lower()
        if FIVE_MINUTE_REGEX.search(haystack):
            return ClassifiedMarket(market=market, status=ClassificationStatus.CANDIDATE_5M, confidence=0.85, method="regex")

        return ClassifiedMarket(
            market=market,
            status=ClassificationStatus.SKIPPED_AMBIGUOUS,
            confidence=0.0,
            method="ambiguous",
        )


class DiscoveryEngine:
    def __init__(self, classifier: MarketClassifier, parser_version: str = "v1") -> None:
        self.classifier = classifier
        self.parser_version = parser_version

    def build_universe(self, raw_markets: list[MarketRecord]) -> DiscoveryState:
        universe: dict[str, ClassifiedMarket] = {}
        for market in raw_markets:
            if not market.is_operable:
                continue
            if not self.classifier.is_crypto(market):
                continue
            classified = self.classifier.classify(market)
            if classified.status == ClassificationStatus.CANDIDATE_5M and classified.confidence >= self.classifier.min_confidence:
                universe[market.market_id] = classified
        return DiscoveryState(
            markets=universe,
            parser_version=self.parser_version,
            discovered_at=datetime.now(timezone.utc).isoformat(),
        )

    def refresh_universe(self, previous: DiscoveryState, fresh: DiscoveryState) -> DiscoveryState:
        merged = dict(previous.markets)
        for market_id, record in fresh.markets.items():
            merged[market_id] = record

        active_ids = set(fresh.markets)
        for market_id in list(merged):
            if market_id not in active_ids:
                del merged[market_id]

        return DiscoveryState(
            markets=merged,
            parser_version=fresh.parser_version,
            discovered_at=fresh.discovered_at,
        )
