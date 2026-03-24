# Polymarket MVP Strategy Runbook

This runbook is for developers/operators running the `ToTheMoon.strategies.polymarket_mvp` primitives in paper-trading pipelines.

## 1) What we are building (MVP definition)
- **Feature**: low-dependency signal/scoring primitives for Polymarket paper trading.
- **Audience**: quant/dev users extending the ToTheMoon prototype.
- **Problem solved**: standardize market parsing, signal scoring, entry simulation, and settlement math for two alpha ideas.
- **How it works**:
  1. Normalize raw market data into `MarketDefinition`.
  2. Build comparable groups with `build_related_groups`.
  3. Compute reference probabilities from live book state.
  4. Score alpha candidates (`score_related_market_incoherence`, `score_tail_premium`).
  5. Simulate execution with `simulate_entry` and settle with `settle_trade`.
- **Core concepts**: `MarketDefinition` + `MarketState` + `UnderlyingState` -> `SignalCandidate` -> `PaperTrade` -> `ResolutionRecord`.

## 2) UX / usage flow
- **Happy path**:
  1. Build normalized market universe.
  2. Build groups and score signals.
  3. Simulate entries and persist outputs.
  4. Resolve trades when outcomes finalize.
- **Alternative path**: if data is stale, depth/spread thresholds fail, or sample size is insufficient, no signal/trade is emitted.
- No UI is included; workflow is code-first and file/DB-integrated by host runtime.

## 3) Technical needs
- Required Python types are in `core.py`; keep inputs pre-normalized.
- Keep signal modules independent of websocket/DB details (inject normalized state as arguments).
- No extra runtime dependency beyond standard library for this module.
- Edge cases to handle in callers:
  - stale timestamps,
  - missing YES/NO token IDs,
  - unparseable strikes,
  - low depth / wide spread,
  - poor tail bucket sample size.

## 4) Testing and security checks
- Minimum checks before shipping strategy changes:
  - run unit tests for polymarket MVP primitives,
  - run existing ToTheMoon strategy tests.
- Security posture for this package:
  - no order posting,
  - no private key handling,
  - paper-only calculations.

## 5) Work plan for changes
- **Required DoD**:
  - tests pass,
  - public API remains stable or is documented,
  - docs updated in this folder.
- **Optional**:
  - richer calibrations,
  - runtime orchestration examples.
- **Key risks**:
  - timestamp skew bugs,
  - incorrect operator parsing,
  - overfitting thresholds.

## 6) Ripple effects
When changing thresholds/types/functions:
- update tests under `tests/tothemoon/`,
- update this runbook/howto/ops docs,
- notify runtime integrators using these exports.

## 7) Broader context
- Current module is a primitive layer, not a full trading engine.
- Future extension ideas:
  - plug into SQLite persistence and replay,
  - add calibration/backfill helpers,
  - optional stricter enums/protocols for feed contracts.
