# Operational Guide (Paper Trading)

## Runtime checklist
1. Feed freshness checks enabled.
2. Thresholds explicitly configured (do not rely on defaults in production runs).
3. Deterministic timestamps in replay/backtest mode.
4. Signal outputs persisted with rationale payload.

## Monitoring signals
Track at minimum:
- `signals_generated_total` by alpha.
- `signals_rejected_total` by rejection reason (stale, spread, depth, sample_size).
- `paper_trades_opened_total` and `paper_trades_settled_total`.
- PnL distribution by alpha and temporal bucket.

## Incident playbook
### No signals for long period
- Verify feed timestamps/skew.
- Check depth/spread thresholds are not too restrictive.
- Confirm parser still recognizes current market wording.

### Too many signals suddenly
- Inspect parsing drift (operator/strike extraction).
- Validate underlying volatility inputs for tail premium.
- Audit thresholds and sample-size minimums.

### Settlement mismatch
- Confirm `resolved_label` mapping to side (`YES`/`NO`).
- Recompute expected payout (`qty` if win, `0` if lose).

## Release checklist
- Run tests.
- Confirm exports are stable.
- Update this folder docs (`RUNBOOK.md`, `HOWTO.md`, `OPERATIONS.md`).
- Share changelog notes with runtime integrators.
