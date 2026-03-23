from __future__ import annotations

from .config import EngineConfig
from .execution import PaperExecutionAdapter
from .models import OrderRequest, OrderSide
from .portfolio import Portfolio
from .reporting import summarize_trades
from .risk import evaluate_risk
from .signal_engine import build_signal
from .storage import CsvStore


def run_backtest(candidates, snapshots_by_token, config: EngineConfig, store: CsvStore) -> dict[str, float]:
    portfolio = Portfolio()
    paper = PaperExecutionAdapter(store)
    fills = []
    for candidate in candidates:
        signal = build_signal(candidate, config.strategy)
        if signal is None:
            continue
        snapshot = snapshots_by_token.get(signal.token_id)
        if snapshot is None or snapshot.stale or snapshot.spread > config.strategy.max_spread:
            continue
        order = OrderRequest(
            token_id=signal.token_id,
            side=OrderSide.BUY,
            price=snapshot.best_ask,
            size=1.0,
            market_id=signal.market_id,
            strategy_name=signal.kind.value,
            signal_reason=signal.reason,
        )
        decision = evaluate_risk(order, portfolio.snapshot(), config.risk)
        if not decision.approved:
            continue
        _, fill = paper.execute(order, snapshot.best_bid, snapshot.best_ask)
        portfolio.apply_fill(fill, signal.market_id, order.side, signal.side)
        fills.append(fill)
    summary = summarize_trades(fills)
    store.write_rows("reports/strategy_summary.csv", [summary])
    return summary
