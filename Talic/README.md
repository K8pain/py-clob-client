# Talic

Talic is a minimal resilient runtime for API bots that need deterministic behavior under retries, restarts, and partial failures.

## What Talic is

Talic is an operations-first runtime skeleton that enforces:
- bounded retries for transient failures,
- strict mode transitions,
- idempotent processing for mutating operations,
- safe degradation instead of hard crashes.

## Who it serves

Talic is for:
- developers implementing autonomous API workflows,
- operators/SREs responsible for bot uptime and incident recovery,
- teams that need explicit runtime guarantees before scaling strategy logic.

## Problem solved

Without a strict runtime contract, bots often fail in unsafe ways (duplicate side effects, infinite retries, hidden crash loops). Talic solves this by making runtime state explicit and by separating dependency construction from event processing.

## MVP scope and non-goals

### MVP scope
- single-process event loop with bounded iterations,
- strict mode enum (`NORMAL`, `RETRYING`, `READ_ONLY`, `IDLE_SAFE`),
- idempotency ledger to prevent duplicate mutations,
- retry policy integration for transient errors,
- structured logs and metrics hooks.

### Non-goals (MVP)
- multi-node orchestration,
- UI and human workflow tooling,
- secrets management and credential provisioning,
- domain-specific trading strategy logic.

## How Talic works

Talic processes a stream of events. For each event it validates input, checks idempotency, routes execution by event type, validates external responses, records outcomes, and updates mode based on error class.

Main concepts and relationships:
- **ModeState** controls what actions are allowed.
- **process_events** is the runtime orchestrator.
- **OperationLedger** enforces idempotency by key.
- **run_with_retry** handles transient external failures.
- **update_state_for_error** maps failures to degradation modes.

## User stories and flow behavior

### Happy flow
1. Runtime starts in `NORMAL`.
2. Event payload passes input validation.
3. Unseen `idempotency_key` is processed.
4. Mutation/external call succeeds.
5. Result is recorded in ledger; `runtime.processed` metric increments.
6. Mode remains `NORMAL`.

### Alternative flow
- **Duplicate event**: same `idempotency_key` is replayed, operation is skipped, replay metric increments.
- **Transient errors**: retries run with backoff; repeated failures may transition to `RETRYING`, then `READ_ONLY` if exhausted.
- **Permanent/internal errors**: runtime transitions to `IDLE_SAFE` and keeps loop alive for safe operator intervention.
- **Recovery**: operators can apply recovery to transition back to `NORMAL` once root cause is addressed.

## UX / UI impact

Talic MVP has no end-user UI. Operator experience is command-line and log/metric driven. Navigation impact is documentation-only:
- implementation guide in this file,
- operational runbook in `docs/talic_runbook.md`.

## Technical notes for implementers

- Keep runtime modules small and composable.
- Prefer function-level wiring and dependency injection (construct dependencies in one place, pass into `process_events`).
- Use typed mode enums to avoid invalid states.
- Document network and external API edge cases via mode semantics and runbook actions.

## Testing and security notes

- Prioritize unit tests for transition rules, idempotency, and degradation behavior.
- Add regression tests for restart + replay determinism.
- Keep runtime assertions active: validate all inputs and external responses.
- Avoid dynamic code execution and implicit retries.

## Planning, milestones, and risks (MVP)

- **M1**: Runtime contracts and mode invariants.
- **M2**: Retry/degradation integration and tests.
- **M3**: Operator runbook + observability thresholds.

Primary risk factors:
- external API schema drift,
- prolonged upstream outages causing retry storms.

Required for done:
- documented runtime semantics,
- executable entrypoint with explicit wiring,
- runbook with recovery actions.

Optional:
- deployment packaging/daemonization,
- dashboards and paging integration templates.

## Ripple effects and broader context

- Documentation updates are mandatory because operations depend on explicit mode semantics.
- Future extensions can add domain adapters and multi-bot supervisors while preserving single-runtime invariants.
- Current limitation is single-process scope; future moonshot is formal verification of transition safety.
