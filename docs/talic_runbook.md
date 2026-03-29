# Talic Runtime Runbook

This runbook defines operational semantics for Talic runtime modes, incident recovery conditions, and minimum observability requirements.

## 1) Mode semantics

### `NORMAL`
- Full runtime behavior.
- Mutating operations (`type=mutation`) are allowed.
- External calls are allowed.
- Expected steady state.

### `RETRYING`
- Runtime observed repeated transient failures.
- Mutations are blocked by runtime guard (only `NORMAL` can mutate).
- External calls may still run through bounded retry policy.
- Use this as a warning state indicating instability, not full outage.

### `READ_ONLY`
- Runtime reached retry exhaustion for transient failures.
- Mutations are blocked.
- Read/external non-mutating operations can continue when safe.
- Preserves availability while reducing side-effect risk.

### `IDLE_SAFE`
- Safe-degraded state after internal or permanent failures.
- Mutations are blocked.
- External calls are blocked by engine guard for `external_call` events.
- Runtime stays alive but effectively performs no risky work until operator recovery.

## 2) Recovery conditions and operator actions

### Transition triggers (runtime behavior)
- `NORMAL -> RETRYING`: transient failure count reaches threshold.
- `RETRYING/NORMAL -> READ_ONLY`: transient retry path exhausted.
- `* -> IDLE_SAFE`: permanent error or internal invariant error.
- `RETRYING|READ_ONLY|IDLE_SAFE -> NORMAL`: explicit recovery action after root cause mitigation.

### Recovery checklist

1. **Identify failing dependency**
   - Review last error logs (`event processing failed`, retry warnings, external error details).
2. **Classify issue**
   - Transient (timeouts, temporary 5xx) vs permanent/internal (schema mismatch, invariant break).
3. **Mitigate cause**
   - Rollback bad config, restore upstream connectivity, or patch contract mismatch.
4. **Validate health signals**
   - Error rate below threshold and retries stabilize (see alert section).
5. **Apply controlled recovery**
   - Trigger recovery (`apply_recovery`) to return to `NORMAL`.
6. **Watch post-recovery window**
   - Monitor for 10–15 minutes for repeated degradation loops.

### Operator actions by mode

- **If `RETRYING` persists > 5 minutes**:
  - investigate upstream latency/failure,
  - consider temporary rate reduction or dependency failover.

- **If `READ_ONLY` entered**:
  - treat as partial outage,
  - verify business impact from blocked mutations,
  - restore upstream service before recovering.

- **If `IDLE_SAFE` entered**:
  - treat as critical safety event,
  - freeze config changes,
  - perform root-cause analysis before recovery.

## 3) Required logs, metrics, and alert thresholds

## Required logs

Emit structured logs for:
- mode transitions (from/to mode + reason),
- retry attempts and exhaustion,
- idempotent replay skips,
- event processing failures with mode and error,
- recovery actions.

Minimum log fields:
- `timestamp`,
- `mode`,
- `event_type`,
- `idempotency_key` (if present),
- `error_class`,
- `error_message`,
- `attempt` (for retries).

## Required metrics

At minimum, track:
- `runtime.processed` (counter),
- `runtime.errors` (counter),
- `runtime.idempotent_replay` (counter),
- `runtime.mode` (gauge or state tag),
- `runtime.retry_attempts` (counter),
- `runtime.time_in_mode_seconds` (timer/histogram).

## Alert thresholds (initial MVP defaults)

- **High error rate**: `runtime.errors / (runtime.processed + runtime.errors) > 0.10` for 5 minutes.
- **Retry storm**: `runtime.retry_attempts >= 50` within 5 minutes.
- **Read-only stuck**: runtime in `READ_ONLY` for more than 10 minutes.
- **Idle-safe entered**: immediate page (critical).
- **Idempotent replay spike**: replay ratio > 20% for 10 minutes (possible duplicate event source).

Tune thresholds after observing production baseline.

## 4) Operational Definition of Done

Before production rollout:
- mode transitions are observable in logs,
- all required metrics exported,
- alerts configured for thresholds above,
- on-call knows recovery checklist,
- a dry-run incident is executed for `READ_ONLY` and `IDLE_SAFE`.
