# Agent Runtime Canary Control Plane Design

## Context

Agent Runtime P0-P2 has established canonical Run identity, durable lifecycle state,
conversation admission, tool-operation receipts, cancellation, leases and recovery.
Those capabilities are deployed with `agent_runtime_mode=off`, so production traffic
still follows the legacy unmanaged path.

The next risk is rollout rather than execution semantics. Switching directly from
`off` to `enforce` would expose every cloud Agent turn to a new admission and recovery
path without a bounded blast radius or a database-backed emergency stop.

## Goals

1. Enable Runtime for a stable, deterministic subset of cloud Agent users.
2. Stop admitting new managed Runs automatically when aggregate safety signals regress.
3. Keep existing managed Runs observable, cancellable and recoverable after a pause.
4. Expose administrator-only aggregate metrics and explicit pause/resume controls.
5. Keep all rollout records free of prompts, answers, health text and tool payloads.
6. Preserve the existing `off` and `enforce` behavior and require no client release.

## Non-goals

- Do not enable production canary traffic in this change.
- Do not change the iPhone strict-local execution or sync protocol.
- Do not build durable token streaming, parent/child Runs or a separate Runtime service.
- Do not automatically resume after a circuit pause.
- Do not use mobile release-policy tables as a backend Runtime feature flag.

## Runtime Modes

| Mode | New Run admission | Existing managed Run API | Recovery scanner |
|---|---|---|---|
| `off` | unmanaged legacy path | hidden | disabled |
| `canary` | selected users only while circuit is active | available | enabled |
| `enforce` | all cloud users while circuit is active | available | enabled |

When the circuit is paused, new requests use the existing unmanaged path. This is an
intentional compatibility rollback, not a failed request. Existing managed Runs remain
in the ledger and continue to support status, cancellation and recovery.

Invalid modes and invalid rollout configuration fail during admission with an explicit
configuration error. A database error while reading the circuit is not silently treated
as active; the request falls back to the legacy path and emits a structured warning.

## Stable Canary Selection

Canary selection is evaluated only in `canary` mode:

1. An operator allowlist has precedence and is intended for internal verification.
2. Other users are assigned to one of 10,000 stable buckets using
   `sha256("agent-runtime-canary-v1:<user_id>")`.
3. `agent_runtime_canary_percent` is an integer from 0 through 100. A user is selected
   when the bucket is below `percent * 100`.

The algorithm is versioned and deterministic across processes. Raw user IDs and bucket
values are not written to logs or rollout audit rows.

## Persistent Rollout State

`agent_runtime_rollout_state` is a singleton control row:

- `status`: `active` or `paused`.
- `reason_code`: coarse operational reason, never free-form health text.
- `version`: optimistic control-plane revision.
- last evaluation window and aggregate counts.
- `updated_by_user_id`: administrator ID for manual changes; nullable for system changes.
- timestamps.

`agent_runtime_rollout_events` is an append-only control audit:

- action: `pause` or `resume`.
- actor: `system` or `admin`.
- reason code and aggregate counts that justified the action.
- optional administrator ID.
- timestamp.

Neither table stores Run IDs, end-user IDs, prompts, responses, health facts, tool
arguments or tool results.

## Aggregate Safety Snapshot

The rollout evaluator reads a configurable recent window and returns only counts and
rates:

- terminal Runs and status counts.
- system failures, excluding user cancellation and explicit deadline cancellation.
- Runs requiring reconciliation.
- active Runs with an expired lease after the recovery scanner had a chance to settle.
- tool operations by terminal status.
- duration p50/p95 where the database supports it; application-side bounded calculation
  is acceptable for the initial small canary.

Default controls are deliberately conservative:

- window: 15 minutes.
- minimum terminal sample: 20 Runs before rate-based decisions.
- system-failure pause threshold: 10%.
- reconciliation pause threshold: any new reconciliation Run.
- stale active lease pause threshold: any remaining stale Run after recovery.

Hard signals (reconciliation or stale active lease) do not require the minimum sample.
Rate-based failure decisions do. All thresholds are configuration values with strict
range validation.

## Circuit Behavior

The periodic task executes in this order:

1. Recover expired Runs and settle unsafe operations using the existing P2 scanner.
2. Compute the aggregate snapshot.
3. Persist the evaluation summary.
4. If a pause threshold is crossed, atomically transition `active -> paused` and append
   one audit event.
5. If already paused, do not create duplicate pause events.

The system never auto-resumes. An administrator must inspect metrics and invoke resume.
Resume changes only future admission; it does not replay any Run or tool operation.

## API

Administrator-only endpoints under `/monitoring/agent-runtime`:

- `GET /rollout`: mode, configured canary percentage, circuit status and aggregate
  snapshot. No user-level records.
- `POST /pause`: idempotently pause future managed admission using a finite reason code.
- `POST /resume`: idempotently resume future managed admission.

Owner-scoped `/agent/runs/{run_id}` and cancellation remain available in `canary` and
`enforce`, even while the circuit is paused.

## Failure Handling

- Missing singleton row is created transactionally with `active` status.
- Concurrent system/admin transitions use a row lock and idempotent status checks.
- Metrics/evaluator failure is logged and surfaced by task failure; it never resumes or
  mutates a paused circuit.
- Circuit read failure bypasses Runtime admission for that request and emits a warning.
- The recovery scanner remains active in `canary` and `enforce`, independent of circuit
  state, so pausing cannot strand already managed Runs.

## Privacy and Security

- Administrator authorization uses the existing authenticated `is_admin` contract.
- Manual control changes create an append-only audit row.
- API responses and logs contain aggregate counts and finite reason codes only.
- No OpenTelemetry or log field receives tool arguments/results, prompt text or answer
  text.
- Runtime and rollout tables remain cloud-only; strict-local iPhone flows do not call
  these endpoints.

## Rollout Sequence

1. Deploy code and migrations with `agent_runtime_mode=off`.
2. Verify state row, metrics endpoint, recovery task and manual pause/resume in
   production without admitting Runtime traffic.
3. Set `canary` with allowlisted internal users and 0% hash traffic.
4. Run read-only and write receipt drills, including interruption and cancellation.
5. Increase hash traffic through explicit deployment Gates: 1%, 5%, 20%, 50%, 100%.
6. Move to `enforce` only after each window meets the success thresholds and no
   reconciliation is unresolved.

Every percentage change is an operational rollout decision, not part of this code
deployment.

