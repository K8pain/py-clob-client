# real_helpers

Safety-first helper modules for future trading code, implemented as small testable functions.

## Modules
- `pnl_engine.py`: fees/slippage-aware PnL and compounding checks.
- `risk_controls.py`: position cap, drawdown, and circuit breaker.
- `market_regime.py`: simple regime classification and trade permission.
- `execution_guard.py`: pre-trade validation and skip reason logging.
- `resilience.py`: timeout guard, exponential backoff retries, and watchdog hooks.
- `strategy_validation.py`: gates for sample size, sharpe, and drawdown.
