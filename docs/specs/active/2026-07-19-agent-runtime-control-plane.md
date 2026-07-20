# Feature Spec: Agent Runtime Control Plane P0-P3

> Status: approved
> Updated: 2026-07-20
> PRD: `docs/prd/2026-07-19-agent-runtime-control-plane.md`
> Design: `docs/plans/2026-07-19-agent-runtime-control-plane-design.md`
> Canary Design: `docs/plans/2026-07-20-agent-runtime-canary-design.md`

## 1. Identity Contract

```text
client_turn_id  client-generated retry/idempotency identity
run_id          server-generated logical Agent run identity
attempt_id      server-generated execution attempt identity
operation_id    server-generated or device-stable business side-effect identity
```

- `run_id` is generated once by Runtime Coordinator and passed into `AgentExecutor.run_stream()`.
- Kernel must never generate another ID when a Runtime `run_id` is present.
- LLM Usage capture, audit logs, messages and SSE `done` use the same ID.
- A replay of the same `client_turn_id` returns the existing Run and finalized message.

## 2. State Contract

```text
queued -> running -> waiting_for_user
                  -> succeeded
                  -> failed
                  -> cancelled
                  -> reconciliation_required
```

- Terminal states: `succeeded`, `failed`, `cancelled`, `reconciliation_required`.
- `waiting_for_user` is a durable non-running state; neither it nor terminal states hold a worker lease.
- Invalid transitions fail loudly and leave an audit event without health content.

## 3. Persistence Contract

### agent_runs

Stores identity, ownership, conversation/input linkage, current Attempt fencing, retryability, status, origin, timestamps, deadline and coarse error code. It must not store prompt or answer content.

### agent_run_attempts

Stores attempt number, worker identity, lease timestamps, status and coarse failure code.

### agent_tool_operations

Stores opaque `operation_id`, tool name, read/write classification, argument fingerprint, status and receipt resource reference. It must not store raw arguments or raw results.

### agent_run_events

Append-only milestone events with per-run sequence. P0 payload keys are restricted to allowlisted status/completion/error/tool/effect tokens, receipt/replay booleans and positive input sequence; health content is forbidden.

## 4. Admission Contract

- Unique `(user_id, client_turn_id)` when `client_turn_id` is present.
- Unique `(conversation_id, input_seq)`.
- PostgreSQL permits at most one Run in `queued` or `running` per conversation.
- Duplicate active request observes the existing Run without starting a second Executor. Only an explicitly retryable failed Run may create a new Attempt; completed/waiting/reconciliation/cancelled Runs replay their durable result.
- A new conversation is bound on `request_persisted`, before answer generation continues.
- SQLite tests enforce equivalent behavior in service code because partial concurrency semantics differ from PostgreSQL.

## 5. Local-First Contract

- `strict_local`: never calls this Runtime and never creates a server row.
- `local_first` explicit cloud enhancement may include `origin=local_bridge`, `origin_device_id`, `local_execution_id` and `privacy_mode`.
- Server always generates its own `run_id`; `local_execution_id` is a correlation value, not an authority to replay local health writes.
- Runtime telemetry never stores local health plaintext.

## 6. Compatibility Contract

- Existing `/agent/stream` and `/agent/send` request/response shapes remain valid.
- New SSE fields are additive.
- Existing message metadata, checkpoint recovery and write receipts remain available through the migration period.
- `off` mode cannot suppress an otherwise valid Agent answer because it performs no Ledger writes or admission.
- `enforce` mode fails closed on Runtime invariant violations; rollout requires migration and Runtime regression gates to be green first.

## 7. P0 Acceptance Tests

1. Canonical run identity propagates through API, Executor, Kernel and LLM Usage.
2. Same client turn concurrently submitted twice creates one Run and one user message.
3. Two distinct turns against one conversation cannot execute concurrently.
4. Successful, failed, interrupted and waiting turns produce valid state transitions.
5. Write checkpoint and uncertain recovery tests retain their current behavior.
6. Event payload validation rejects health text and unbounded objects.
7. Existing clients pass without origin fields.

## 8. Rollout Admission Contract

- Supported modes are exactly `off`, `canary` and `enforce`; any other value fails
  explicitly instead of guessing a mode.
- `off` preserves the unmanaged legacy path and performs no rollout-state write.
- `canary` selects an internal allowlist first, then a deterministic percentage bucket
  derived from the user ID. Selection does not depend on process memory or client build.
- `enforce` selects every cloud Agent request while the circuit is active.
- A paused or temporarily unreadable circuit routes new requests to the existing
  unmanaged path. It never treats an unknown circuit state as active.
- Once a `(user_id, client_turn_id)` is managed, its ownership is immutable. Retries
  resume that Run even after a pause or canary-percentage reduction, and write tools
  continue using the Runtime operation ledger for the life of that turn. Explicit
  `off` is the hard rollback exception and disables managed resume as well.
- New managed admission and circuit pause are linearized on the singleton circuit row;
  a pause cannot report success while an uncommitted selected Run slips through.
- Existing managed Runs remain owner-queryable, cancellable and recoverable in
  `canary` and `enforce`, including while new admission is paused.
- Strict-local iPhone execution never calls this admission path and remains unchanged.

## 9. Rollout State Contract

`agent_runtime_rollout_state` is a singleton operational row. It stores only:

- `active` or `paused` status;
- a finite pause reason code;
- a monotonic version;
- evaluation timestamps and aggregate counts;
- an optional administrator actor ID.

`agent_runtime_rollout_events` is append-only control audit for `pause` and `resume`.
Database checks and service validation both enforce valid actor/action/reason
combinations and non-negative counts. Neither table may store an end-user ID, Run ID,
prompt, answer, health text, tool arguments or tool results.

## 10. Automatic Pause Contract

The periodic maintenance task runs recovery before evaluation. It pauses future
managed admission when any of these conditions is true within the configured window:

1. at least one Run requires reconciliation;
2. at least one active Run still has an expired worker lease after recovery;
3. the system-failure rate reaches the configured threshold after the minimum terminal
   sample is reached.

Evaluation persists aggregate counters only. Repeated evaluations while paused do not
append duplicate pause events. The system never automatically resumes; an administrator
must inspect the aggregate snapshot and resume explicitly.
Manual resume acknowledges the current monotonic reconciliation generation. Run
settlement increments that generation while holding the same control-row lock;
automatic evaluation never acknowledges it. Commit ordering therefore prevents a late
transaction with an older `finished_at` from being hidden by resume or evaluation.

## 11. Administrator API Contract

- `GET /api/v1/monitoring/agent-runtime/rollout` returns typed mode, circuit,
  thresholds and aggregate snapshot fields only.
- `POST /api/v1/monitoring/agent-runtime/pause` is an idempotent manual pause.
- `POST /api/v1/monitoring/agent-runtime/resume` is an idempotent manual resume.
- All three endpoints require the existing administrator authorization contract.
- Manual transitions are audited without user-level health or conversation content.

## 12. P3 Acceptance Tests

1. Stable canary selection is deterministic, bounded and allowlist-first.
2. Invalid modes, percentages, allowlists, windows and thresholds fail explicitly.
3. Concurrent first pause creates one state transition and one audit event.
4. Recovery of an uncertain write produces reconciliation and automatically pauses.
5. A circuit read failure leaves the database session usable and bypasses managed
   admission for that request.
6. PostgreSQL and SQLite enforce finite control values and non-negative counts.
7. Monitoring responses are typed and contain no user-level IDs or health content.
8. Production deployment keeps `agent_runtime_mode=off`; enabling canary is a separate
   operational Gate.
9. A managed canary write records an operation receipt even though global mode is not
   `enforce`, and same-turn retries cannot escape to the unmanaged path after pause or
   percentage reduction.
10. Pause and selected Run admission are ordered under real PostgreSQL concurrency;
    rollout-window queries use their intended indexes.
11. An unresolved write operation overrides model completion: the Run cannot become
    succeeded or an ordinary failure and must advance the reconciliation generation.
