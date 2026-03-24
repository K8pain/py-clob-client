from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from py_clob_client.client import ClobClient


class PositionSide(str, Enum):
    YES = "YES"


@dataclass(frozen=True)
class StrategyConfig:
    host: str = "https://clob.polymarket.com"
    gamma_api_url: str = "https://gamma-api.polymarket.com"
    market_keywords: tuple[str, ...] = ("bitcoin", "ethereum", "solana")
    buy_below: float = 0.40
    sell_above: float = 0.60
    stake_usd: float = 10.0
    max_consecutive_losses: int = 3
    state_file: str = "ToTheMoon/state.json"
    trades_file: str = "ToTheMoon/paper_trades.json"


@dataclass
class Position:
    market_slug: str
    token_id: str
    side: PositionSide
    entry_price: float
    size: float
    opened_at: str


@dataclass
class TradeRecord:
    market_slug: str
    token_id: str
    side: str
    action: str
    timestamp: str
    price: float
    size: float
    pnl: float


class MeanReversionPaperStrategy:
    """Paper-trading strategy: buy YES under 0.40, sell above 0.60.

    This strategy starts with market discovery and returns active *UP or DOWN*
    crypto markets (BTC/ETH/SOL). It only tracks simulated positions in JSON.
    """

    def __init__(self, config: StrategyConfig):
        self.config = config
        self.client = ClobClient(config.host)
        self.state_path = Path(config.state_file)
        self.trades_path = Path(config.trades_file)
        self.state = self._load_state()

    def discover_active_up_down_markets(self, page_limit: int = 3) -> List[Dict[str, Any]]:
        """Discover active markets and keep only crypto UP/DOWN markets with YES token ids."""
        markets: List[Dict[str, Any]] = []
        cursor = "MA=="

        for _ in range(page_limit):
            response = self.client.get_simplified_markets(next_cursor=cursor)
            data = response.get("data", [])
            if not data:
                break

            for market in data:
                if self._is_candidate_market(market):
                    normalized = self._normalize_market(market)
                    if normalized is not None:
                        markets.append(normalized)

            cursor = response.get("next_cursor")
            if not cursor or cursor == "LTE=":
                break

        return markets

    def evaluate_market(self, market: Dict[str, Any]) -> Optional[TradeRecord]:
        """Check a market and generate a paper trade if thresholds are triggered."""
        if self.state.get("circuit_breaker_active"):
            return None

        token_id = market["yes_token_id"]
        price = float(self.client.get_midpoint(token_id))
        now = self._utc_now()

        open_positions = self.state.setdefault("open_positions", {})
        existing = open_positions.get(token_id)

        if existing is None and price < self.config.buy_below:
            size = round(self.config.stake_usd / price, 6)
            position = Position(
                market_slug=market["market_slug"],
                token_id=token_id,
                side=PositionSide.YES,
                entry_price=price,
                size=size,
                opened_at=now,
            )
            open_positions[token_id] = asdict(position)
            trade = TradeRecord(
                market_slug=position.market_slug,
                token_id=position.token_id,
                side=position.side.value,
                action="BUY",
                timestamp=now,
                price=price,
                size=size,
                pnl=0.0,
            )
            self._record_trade(trade)
            self._save_state()
            return trade

        if existing is not None and price > self.config.sell_above:
            entry_price = float(existing["entry_price"])
            size = float(existing["size"])
            pnl = round((price - entry_price) * size, 6)

            trade = TradeRecord(
                market_slug=existing["market_slug"],
                token_id=token_id,
                side=existing["side"],
                action="SELL",
                timestamp=now,
                price=price,
                size=size,
                pnl=pnl,
            )

            self._apply_pnl(pnl)
            open_positions.pop(token_id, None)
            self._record_trade(trade)
            self._save_state()
            return trade

        return None

    def run_once(self, page_limit: int = 3) -> List[TradeRecord]:
        """Single execution cycle suitable for cron every 15 minutes."""
        trades: List[TradeRecord] = []
        markets = self.discover_active_up_down_markets(page_limit=page_limit)
        for market in markets:
            trade = self.evaluate_market(market)
            if trade is not None:
                trades.append(trade)
        return trades

    def _is_candidate_market(self, market: Dict[str, Any]) -> bool:
        if market.get("active") is False or market.get("closed") is True:
            return False

        title = " ".join(
            [
                str(market.get("question", "")),
                str(market.get("market_slug", "")),
                str(market.get("description", "")),
            ]
        ).lower()

        has_keyword = any(keyword in title for keyword in self.config.market_keywords)
        is_up_down = "up" in title and "down" in title
        return has_keyword and is_up_down

    def _normalize_market(self, market: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        yes_token_id = self._extract_yes_token_id(market.get("tokens", []))
        if yes_token_id is None:
            return None

        return {
            "market_slug": str(market.get("market_slug", "unknown")),
            "question": str(market.get("question", "")),
            "yes_token_id": yes_token_id,
            "raw": market,
        }

    @staticmethod
    def _extract_yes_token_id(tokens: Iterable[Dict[str, Any]]) -> Optional[str]:
        for token in tokens:
            outcome = str(token.get("outcome", "")).upper()
            token_id = token.get("token_id") or token.get("id")
            if outcome == "YES" and token_id:
                return str(token_id)
        return None

    def _load_state(self) -> Dict[str, Any]:
        if not self.state_path.exists():
            return {
                "open_positions": {},
                "consecutive_losses": 0,
                "circuit_breaker_active": False,
            }

        with self.state_path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def _save_state(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        with self.state_path.open("w", encoding="utf-8") as f:
            json.dump(self.state, f, indent=2)

    def _record_trade(self, trade: TradeRecord) -> None:
        self.trades_path.parent.mkdir(parents=True, exist_ok=True)
        history: List[Dict[str, Any]] = []
        if self.trades_path.exists():
            with self.trades_path.open("r", encoding="utf-8") as f:
                history = json.load(f)

        history.append(asdict(trade))
        with self.trades_path.open("w", encoding="utf-8") as f:
            json.dump(history, f, indent=2)

    def _apply_pnl(self, pnl: float) -> None:
        if pnl < 0:
            self.state["consecutive_losses"] = int(self.state.get("consecutive_losses", 0)) + 1
        else:
            self.state["consecutive_losses"] = 0

        if self.state["consecutive_losses"] >= self.config.max_consecutive_losses:
            self.state["circuit_breaker_active"] = True

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).isoformat()
