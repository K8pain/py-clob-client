# Functional How-To Proceed (`real_helpers`)

## 1) Define what we are building
- **Feature**: A safety-first helper toolkit for trading systems.
- **Audience**: Developers integrating strategy, execution, and risk controls.
- **Problem solved**: Prevents unsafe trading behavior (oversizing, invalid PnL assumptions, unbounded retries/timeouts, trading in bad regimes).
- **How it works**: Small functions are composed in a strict pre-trade and post-trade pipeline.
- **Core concepts**:
  - `pnl_engine`: net PnL and equity safety validation.
  - `risk_controls`: position cap, drawdown control, circuit breaker.
  - `market_regime`: regime classification + allow/block decision.
  - `execution_guard`: final allow/reject and explainability logs.
  - `resilience`: timeout, retry, heartbeat, restart.
  - `strategy_validation`: quality gates before live deployment.

## 2) User experience design (developer UX)
### Happy flow
1. Compute market regime.
2. Run risk caps and breaker checks.
3. Validate trade request.
4. Place order with timeout/retry protection.
5. Compute net PnL with fees/slippage.
6. Record structured decision logs.

### Alternative flow
- If any pre-trade check fails, return **skip** reason and do not place order.
- If timeout/retry exhausted, fail cleanly and log operation failure.
- If circuit breaker triggers, disable new entries and keep monitoring.

## 3) Technical needs
- No DB migrations are required for this helper-only implementation.
- Recommended runtime dependencies: standard library only.
- Architecture favors functions over classes for clarity and testability.
- Dependency injection pattern used for retry sleeper and restart/alert callbacks.
- Edge cases covered:
  - invalid/zero equity for jump validation,
  - timeout expiration,
  - bounded retry exhaustion,
  - stale heartbeat detection.

## 4) Testing + security checks
- Unit tests: `tests/real_helpers/test_real_helpers.py`.
- Deterministic checks include critical protections:
  - fees/slippage in PnL,
  - position cap,
  - regime block in chop,
  - circuit breaker trigger,
  - retry bounded failure,
  - timeout trigger,
  - watchdog stale detection,
  - strategy gate pass criteria.
- Security posture before ship:
  - no order without pre-trade validation,
  - no unbounded API wait,
  - no bypass of position/risk controls.

## 5) Work plan
- **Milestone A (done)**: Build core helper modules.
- **Milestone B (done)**: Add deterministic tests.
- **Milestone C (done)**: Add runnable operational script with logs.
- **Milestone D (next)**: Integrate with order placement path in application service layer.
- **Risks**:
  - External API behavior variability.
  - Strategy model assumptions diverging from live fills.

## 6) Ripple effects
- Update developer docs to require using `execution_guard.validate_trade_request` before order placement.
- Communicate new pre-trade contract to strategy developers.
- Ensure observability stack indexes structured decision logs.

## 7) Broader context
- Current helpers are intentionally simple and composable.
- Future extensions:
  - real ADX/ATR/Bollinger implementations from OHLC windows,
  - persistent circuit breaker state,
  - production supervisor integration (`systemd`/Docker healthcheck),
  - richer Monte Carlo and walk-forward analytics.

---

## Operational execution
Run:

```bash
python "ToTheMoon/real_helpers/run_operational_checks.py"
```

This executes all 14 safety principles in sequence and emits structured logs for each step.
