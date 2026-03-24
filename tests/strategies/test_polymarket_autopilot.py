from datetime import date
from pathlib import Path

from ToTheMoon.strategies.strategies.polymarket_autopilot import (
    MarketSnapshot,
    PaperTradingStore,
    PolymarketAutopilot,
    SignalDirection,
    StrategyConfig,
    StrategyName,
    TradeSignal,
)


def test_execute_paper_trade_and_take_profit(tmp_path: Path) -> None:
    store = PaperTradingStore(tmp_path / "paper.db", starting_capital=10_000)
    signal = TradeSignal(
        strategy=StrategyName.TAIL,
        market_id="market-1",
        direction=SignalDirection.YES,
        confidence=0.1,
        rationale="Trend confirmation",
    )

    executed = store.execute_paper_trade(signal, execution_price=0.50)
    closed = store.rebalance_take_profit(
        {
            "market-1": MarketSnapshot(
                market_id="market-1",
                question="Will this resolve YES?",
                yes_price=0.60,
                no_price=0.40,
                volume_24h=1500,
                news_score=0.1,
            )
        },
        profit_target=0.07,
    )

    assert executed is True
    assert closed == 1
    assert store.available_cash() > 10_000
    assert store.list_open_positions() == []


def test_generate_tail_bonding_and_spread_signals(tmp_path: Path) -> None:
    store = PaperTradingStore(tmp_path / "paper.db")
    autopilot = PolymarketAutopilot(
        store=store,
        log_directory=tmp_path,
        config=StrategyConfig(),
    )

    store.record_market_snapshots(
        [
            MarketSnapshot(
                market_id="market-1",
                question="Q",
                yes_price=0.65,
                no_price=0.35,
                volume_24h=100.0,
                news_score=0.8,
            ),
            MarketSnapshot(
                market_id="market-2",
                question="Q2",
                yes_price=0.80,
                no_price=0.20,
                volume_24h=100.0,
                news_score=0.1,
            ),
        ]
    )

    snapshots = [
        MarketSnapshot(
            market_id="market-1",
            question="Q",
            yes_price=0.50,
            no_price=0.58,
            volume_24h=140.0,
            news_score=0.8,
        ),
        MarketSnapshot(
            market_id="market-2",
            question="Q2",
            yes_price=0.75,
            no_price=0.33,
            volume_24h=140.0,
            news_score=0.1,
        ),
    ]

    signals = autopilot.generate_signals(snapshots)
    strategy_names = {signal.strategy for signal in signals}

    assert StrategyName.BONDING in strategy_names
    assert StrategyName.SPREAD in strategy_names
    assert StrategyName.TAIL in strategy_names


def test_publish_daily_summary_writes_channel_report(tmp_path: Path) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> list[dict[str, object]]:
            return [
                {
                    "id": "market-1",
                    "question": "Will X happen?",
                    "outcomePrices": "[0.61, 0.43]",
                    "volume24hr": 5000,
                    "commentCount": 12,
                }
            ]

    class FakeClient:
        def get(self, *_args, **_kwargs) -> FakeResponse:
            return FakeResponse()

    store = PaperTradingStore(tmp_path / "paper.db")
    autopilot = PolymarketAutopilot(store=store, log_directory=tmp_path, client=FakeClient())
    summary_path = autopilot.publish_daily_summary(as_of=date(2026, 3, 22))

    content = summary_path.read_text(encoding="utf-8")
    assert "#polymarket-autopilot" in content
    assert "paper trading only" in content.lower()


def test_runner_run_once_prints_progress(tmp_path: Path, capsys) -> None:
    from ToTheMoon.strategies.strategies.polymarket_autopilot import runner

    class StubAutopilot:
        def run_cycle(self) -> dict[str, int]:
            return {"snapshots": 3, "executed_trades": 1, "closed_positions": 0}

        def publish_daily_summary(self) -> Path:
            return tmp_path / "polymarket-autopilot.log"

    summary_path = runner.run_once(StubAutopilot())
    captured = capsys.readouterr().out

    assert summary_path == tmp_path / "polymarket-autopilot.log"
    assert "ciclo completado" in captured
    assert "resumen guardado" in captured
