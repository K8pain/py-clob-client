"""Pruebas de evidencia para la lógica de limit orders en MADAWC."""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from Madawc_v2.bot import MadawcBot, MadawcConfig
from Madawc_v2.models import BookLevel, Ledger, MarketRecord, OrderBookSnapshot, SignalCandidate, StructuredEvent
from Madawc_v2.paper import PaperExecutionEngine


class InMemoryStorage:
    def __init__(self) -> None:
        self.events: list[StructuredEvent] = []

    def save_event(self, event: StructuredEvent) -> None:
        self.events.append(event)

    def save_runtime_state(self, ledger, orders, positions, dedupe) -> None:  # noqa: ANN001
        return None

    def load_runtime_state(self):
        return None

    def save_pseudo_trade(self, row):  # noqa: ANN001
        return None

    def export_csv_reports(self, output_dir: str):  # noqa: ARG002
        return {}

    def trade_counters(self) -> dict[str, float | int]:
        return {
            "total_trades": 0,
            "won_trades": 0,
            "lost_trades": 0,
            "open_trades": 0,
            "net_pnl": 0.0,
        }


class StubGamma:
    def __init__(self, markets: list[MarketRecord]) -> None:
        self._markets = markets

    async def get_active_markets(self) -> list[MarketRecord]:
        return self._markets


class StubClobByToken:
    def __init__(self, now_ms: int, books: dict[str, OrderBookSnapshot]) -> None:
        self._now_ms = now_ms
        self._books = books

    async def get_server_time_ms(self) -> int:
        return self._now_ms

    async def get_orderbook(self, token_id: str) -> OrderBookSnapshot:
        return self._books[token_id]

    async def get_market_resolution(self, market_id: str) -> tuple[bool, str | None]:  # noqa: ARG002
        return False, None


class StubWs:
    async def subscribe(self, asset_ids: list[str]) -> None:  # noqa: ARG002
        return None

    async def is_healthy(self) -> bool:
        return True


def test_two_sides_publish_same_limit_order_with_one_dollar_stake() -> None:
    now = datetime.now(timezone.utc)
    market = MarketRecord(
        market_id="m-two-sides",
        event_id="e-two-sides",
        question="BTC Up or Down 5m",
        slug="btc-updown-5m-test",
        token_ids=("tok-up", "tok-down"),
        end_time=now + timedelta(minutes=2),
        active=True,
        closed=False,
        accepting_orders=True,
        enable_order_book=True,
    )
    books = {
        "tok-up": OrderBookSnapshot(
            token_id="tok-up",
            bids=(BookLevel(price=0.04, size=100.0),),
            asks=(BookLevel(price=0.06, size=100.0),),
            ts_ms=0,
        ),
        "tok-down": OrderBookSnapshot(
            token_id="tok-down",
            bids=(BookLevel(price=0.04, size=100.0),),
            asks=(BookLevel(price=0.06, size=100.0),),
            ts_ms=0,
        ),
    }
    storage = InMemoryStorage()
    bot = MadawcBot(
        gamma=StubGamma([market]),
        clob=StubClobByToken(now_ms=int(now.timestamp() * 1000), books=books),
        ws=StubWs(),
        storage=storage,  # type: ignore[arg-type]
        config=MadawcConfig(max_trades_per_market=2, only_trade_this_markets=("Up or Down",)),
    )

    asyncio.run(bot.run_cycle())

    opened = [event for event in storage.events if event.event_type == "PSEUDO_ORDER_OPENED"]
    assert len(opened) == 2
    for event in opened:
        assert event.payload["limit_price"] == 0.05
        assert event.payload["requested_size"] == 20.0
        assert event.payload["reserved_cash"] == 1.0


def test_limit_order_fills_when_price_touches_limit_and_not_before() -> None:
    engine = PaperExecutionEngine(ledger=Ledger(cash_available=1000.0))
    order = engine.create_order(
        SignalCandidate(
            market_id="m-limit-touch",
            token_id="tok-limit-touch",
            price=0.05,
            size=20.0,
            seconds_to_end=120,
        )
    )
    assert order is not None

    no_fill = OrderBookSnapshot(
        token_id="tok-limit-touch",
        bids=(BookLevel(price=0.04, size=30.0),),
        asks=(BookLevel(price=0.06, size=30.0),),
        ts_ms=0,
    )
    filled_later = OrderBookSnapshot(
        token_id="tok-limit-touch",
        bids=(BookLevel(price=0.04, size=30.0),),
        asks=(BookLevel(price=0.05, size=30.0),),
        ts_ms=1,
    )

    assert engine.try_fill(order, no_fill) == 0.0
    assert order.status.value == "OPEN"

    assert engine.try_fill(order, filled_later) == 20.0
    assert order.status.value == "FILLED"


def test_when_one_side_fills_the_other_can_expire() -> None:
    now = datetime.now(timezone.utc)
    market = MarketRecord(
        market_id="m-fill-expire",
        event_id="e-fill-expire",
        question="BTC Up or Down in 1m",
        slug="btc-updown-1m-test",
        token_ids=("tok-fill", "tok-expire"),
        end_time=now + timedelta(seconds=4),
        active=True,
        closed=False,
        accepting_orders=True,
        enable_order_book=True,
    )
    books = {
        "tok-fill": OrderBookSnapshot(
            token_id="tok-fill",
            bids=(BookLevel(price=0.04, size=100.0),),
            asks=(BookLevel(price=0.05, size=100.0),),
            ts_ms=0,
        ),
        "tok-expire": OrderBookSnapshot(
            token_id="tok-expire",
            bids=(BookLevel(price=0.04, size=100.0),),
            asks=(BookLevel(price=0.06, size=100.0),),
            ts_ms=0,
        ),
    }
    storage = InMemoryStorage()
    bot = MadawcBot(
        gamma=StubGamma([market]),
        clob=StubClobByToken(now_ms=int(now.timestamp() * 1000), books=books),
        ws=StubWs(),
        storage=storage,  # type: ignore[arg-type]
        config=MadawcConfig(
            max_trades_per_market=2,
            order_expiry_seconds=5,
            only_trade_this_markets=("Up or Down",),
        ),
    )

    asyncio.run(bot.run_cycle())

    fills = [event for event in storage.events if event.event_type == "PSEUDO_ORDER_FILLED"]
    expirations = [event for event in storage.events if event.event_type == "PSEUDO_ORDER_EXPIRED"]
    assert len(fills) == 1
    assert len(expirations) == 1


def test_settlement_returns_plus_19_on_win_and_minus_1_on_loss() -> None:
    engine = PaperExecutionEngine(ledger=Ledger(cash_available=1000.0))

    winning_order = engine.create_order(
        SignalCandidate(
            market_id="m-win",
            token_id="tok-win",
            price=0.05,
            size=20.0,
            seconds_to_end=120,
        )
    )
    assert winning_order is not None
    assert (
        engine.try_fill(
            winning_order,
            OrderBookSnapshot(
                token_id="tok-win",
                bids=(BookLevel(price=0.04, size=30.0),),
                asks=(BookLevel(price=0.05, size=30.0),),
                ts_ms=0,
            ),
        )
        == 20.0
    )

    losing_order = engine.create_order(
        SignalCandidate(
            market_id="m-loss",
            token_id="tok-loss",
            price=0.05,
            size=20.0,
            seconds_to_end=120,
        )
    )
    assert losing_order is not None
    assert (
        engine.try_fill(
            losing_order,
            OrderBookSnapshot(
                token_id="tok-loss",
                bids=(BookLevel(price=0.04, size=30.0),),
                asks=(BookLevel(price=0.05, size=30.0),),
                ts_ms=0,
            ),
        )
        == 20.0
    )

    win_position = engine.settle_market("m-win", winner_token_id="tok-win")
    assert win_position is not None
    assert win_position.pnl_net == 19.0

    loss_position = engine.settle_market("m-loss", winner_token_id="tok-other")
    assert loss_position is not None
    assert loss_position.pnl_net == -1.0
