from pathlib import Path

from polymarket_engine.backtester import run_backtest
from polymarket_engine.config import EngineConfig, RiskConfig, StorageConfig, StrategyConfig
from polymarket_engine.discovery import discover_catalog
from polymarket_engine.execution import PaperExecutionAdapter, RealExecutionAdapter
from polymarket_engine.features import build_incoherence_features, build_tail_features
from polymarket_engine.historical import HistoricalDownloader
from polymarket_engine.models import MarketSnapshot, OrderRequest, OrderSide, PositionSide
from polymarket_engine.normalization import normalize_market_snapshot, validate_catalog
from polymarket_engine.portfolio import Portfolio
from polymarket_engine.reporting import summarize_trades
from polymarket_engine.risk import evaluate_risk
from polymarket_engine.signal_engine import build_signal
from polymarket_engine.storage import CsvStore


def test_end_to_end_engine_flow(tmp_path: Path):
    raw_markets = [
        {
            "id": "m1",
            "event_id": "e1",
            "market_slug": "btc-40k-before-friday",
            "end_date_iso": "2026-12-31T00:00:00Z",
            "active": True,
            "closed": False,
            "tags": ["crypto"],
            "tokens": [
                {"token_id": "t_yes_1", "outcome": "YES"},
                {"token_id": "t_no_1", "outcome": "NO"},
            ],
        },
        {
            "id": "m2",
            "event_id": "e1",
            "market_slug": "btc-45k-before-friday",
            "end_date_iso": "2026-12-31T00:00:00Z",
            "active": True,
            "closed": False,
            "tags": ["crypto"],
            "tokens": [
                {"token_id": "t_yes_2", "outcome": "YES"},
                {"token_id": "t_no_2", "outcome": "NO"},
            ],
        },
    ]

    discovery = discover_catalog(raw_markets)
    validate_catalog(discovery.markets, discovery.tokens)

    store = CsvStore(tmp_path)
    store.write_rows("catalog/market_catalog.csv", [row.to_row() for row in discovery.markets])
    store.write_rows("catalog/token_catalog.csv", [row.to_row() for row in discovery.tokens])

    history_payloads = {
        "t_yes_1": [{"t": 1000, "p": 0.35}, {"t": 2000, "p": 0.95}],
        "t_no_1": [{"t": 1000, "p": 0.65}, {"t": 2000, "p": 0.05}],
        "t_yes_2": [{"t": 1000, "p": 0.30}, {"t": 2000, "p": 0.70}],
        "t_no_2": [{"t": 1000, "p": 0.70}, {"t": 2000, "p": 0.30}],
    }

    downloader = HistoricalDownloader(
        base_url="https://clob.polymarket.com",
        history_path="/prices-history",
        store=store,
        fetch_json=lambda _url, params: {"history": history_payloads[params["market"]]},
    )
    prices = downloader.download_for_tokens(discovery.tokens, interval="1h")

    incoherence = build_incoherence_features([t for t in discovery.tokens if t.outcome == "YES"], prices, threshold=0.08)
    tails = build_tail_features(discovery.tokens, prices, threshold=0.92)
    assert len(incoherence) == 1
    assert len(tails) >= 1

    signal = build_signal(tails[0], StrategyConfig(tail_threshold=0.92))
    assert signal is not None
    assert signal.side == PositionSide.NO

    snapshot = normalize_market_snapshot(
        MarketSnapshot(
            token_id=signal.token_id,
            best_bid=0.94,
            best_ask=0.96,
            midpoint=0.95,
            spread=0.02,
            last_trade=0.95,
            ts=10**10,
        ),
        stale_after_seconds=30,
    )
    order = OrderRequest(
        token_id=signal.token_id,
        side=OrderSide.BUY,
        price=snapshot.best_ask,
        size=2.0,
        market_id=signal.market_id,
        strategy_name=signal.kind.value,
        signal_reason=signal.reason,
    )
    decision = evaluate_risk(order, [], RiskConfig(max_position_per_market=100.0, max_global_exposure=1000.0, max_open_positions=5))
    assert decision.approved is True

    paper = PaperExecutionAdapter(store=store, fee_bps=10)
    event, fill = paper.execute(order, best_bid=snapshot.best_bid, best_ask=snapshot.best_ask)
    assert event.status == "filled"
    assert fill.fee > 0

    portfolio = Portfolio()
    position = portfolio.apply_fill(fill, signal.market_id, order.side, signal.side)
    assert position.net_qty == 2.0

    summary = summarize_trades([fill])
    assert summary["trade_count"] == 1.0

    backtest_summary = run_backtest(
        tails,
        {signal.token_id: snapshot},
        EngineConfig(strategy=StrategyConfig(tail_threshold=0.92, max_spread=0.05), storage=StorageConfig(base_dir=tmp_path)),
        store,
    )
    assert backtest_summary["trade_count"] >= 1.0

    assert (tmp_path / "execution" / "order_events.csv").exists()
    assert (tmp_path / "execution" / "fills.csv").exists()
    assert (tmp_path / "reports" / "strategy_summary.csv").exists()


def test_real_adapter_returns_homogeneous_payload():
    adapter = RealExecutionAdapter(client=None)
    order = OrderRequest(
        token_id="token-1",
        side=OrderSide.BUY,
        price=0.44,
        size=3.0,
        market_id="market-1",
        strategy_name="tail",
        signal_reason="extremeness_score=0.95",
    )
    payload = adapter.execute(order)
    assert payload["status"] == "ready_to_submit"
    assert payload["token_id"] == "token-1"
