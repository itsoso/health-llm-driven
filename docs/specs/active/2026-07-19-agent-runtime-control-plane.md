# Feature Spec: Agent Runtime Control Plane P0

> Status: approved
> Updated: 2026-07-19
> PRD: `docs/prd/2026-07-19-agent-runtime-control-plane.md`
> Design: `docs/plans/2026-07-19-agent-runtime-control-plane-design.md`

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

- Terminal states: `succeeded`, `failed`, `cancelled`.
- `waiting_for_user` and `reconciliation_required` are durable non-running states and hold no worker lease.
- Invalid transitions fail loudly and leave an audit event without health content.

## 3. Persistence Contract

### agent_runs

Stores identity, ownership, conversation/input linkage, status, origin, timestamps, deadline, error code and version hashes. It must not store prompt or answer content.

### agent_run_attempts

Stores attempt number, worker identity, lease timestamps, status and coarse failure code.

### agent_tool_operations

Stores opaque `operation_id`, tool name, read/write classification, argument fingerprint, status and receipt resource reference. It must not store raw arguments or raw results.

### agent_run_events

Append-only milestone events with per-run sequence. Allowed payload values are bounded identifiers, counters, durations, status codes and policy decisions; health content is forbidden.

## 4. Admission Contract

- Unique `(user_id, client_turn_id)` when `client_turn_id` is present.
- Unique `(conversation_id, input_seq)`.
- PostgreSQL permits at most one Run in `queued` or `running` per conversation.
- Duplicate request returns the existing Run; a different request against a busy conversation receives a retryable busy result in P0, not a second executor.
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
- Runtime failures in shadow mode cannot suppress an otherwise valid Agent answer; failures are observable and block enforcement rollout.

## 7. P0 Acceptance Tests

1. Canonical run identity propagates through API, Executor, Kernel and LLM Usage.
2. Same client turn concurrently submitted twice creates one Run and one user message.
3. Two distinct turns against one conversation cannot execute concurrently.
4. Successful, failed, interrupted and waiting turns produce valid state transitions.
5. Write checkpoint and uncertain recovery tests retain their current behavior.
6. Event payload validation rejects health text and unbounded objects.
7. Existing clients pass without origin fields.
