# Agent Runtime Control Plane P0 Design

> Status: approved
> Updated: 2026-07-19
> PRD: `docs/prd/2026-07-19-agent-runtime-control-plane.md`
> Feature Spec: `docs/specs/active/2026-07-19-agent-runtime-control-plane.md`

## 1. Decision

Implement a modular-monolith Runtime Coordinator around the existing `AgentExecutor`. Do not replace the Agent Loop or introduce an external workflow framework. P0 makes Run identity, state and conversation admission durable; later phases move tool execution and process-death recovery behind the same control plane.

## 2. Why Incremental

The current Executor already contains valuable, tested semantics: durable user-message persistence, write-before-dispatch checkpoints, receipt verification, duplicate client-turn replay, fail-closed uncertain writes, model fallback and user-visible SSE events. Replacing it would increase the probability of duplicate health writes and regressions.

The Runtime therefore coordinates the Executor instead of reimplementing it.

## 3. Architecture

```text
Mobile / Web / Mac / Watch / Voice
                |
             Agent API
                |
        Runtime Coordinator
        |       |          |
   admission  Run Ledger  event sink
        |       |          |
        +--- RunContext ----+
                |
        existing AgentExecutor
        |       |          |
      Kernel   LLM       Tool dispatch
        |       |          |
        +-- canonical run_id+
```

### Runtime Coordinator responsibilities

- Create or resume one logical Run for a client turn.
- Allocate a conversation input sequence while holding a conversation-level database lock.
- Enforce one active Run per conversation.
- Create an Attempt and pass immutable `RunContext` to Executor.
- Translate Executor completion into a valid Run state transition.
- Emit content-free milestone events.

### Executor responsibilities

- Continue owning prompt construction, model rounds, tools, checkpoint recovery, message content and final answer assembly.
- Accept, but never regenerate, canonical `run_id` and `attempt_id`.
- Report structured outcomes to Runtime without writing Run lifecycle fields directly.

## 4. Data Model

### AgentRun

Required fields: `id`, `run_id`, `user_id`, `conversation_id`, `source_message_id`, `assistant_message_id`, `client_turn_id`, `input_seq`, `status`, `origin`, optional local correlation IDs, deadline, coarse error code, created/started/finished timestamps and metadata restricted to bounded non-content values.

### AgentRunAttempt

Required fields: `attempt_id`, `run_id`, `attempt_no`, `status`, worker ID, lease timestamps, start/end timestamps and coarse error code.

### AgentToolOperation

P0 creates the table and repository contract but does not migrate every dispatch. Existing write checkpoints remain authoritative until P1. Fields include opaque operation identity, tool name, effect class, fingerprint, status and verified resource reference.

### AgentRunEvent

Persist only milestones such as `run.created`, `run.started`, `run.waiting`, `run.succeeded`, `run.failed`, `run.cancelled`, `tool.requested`, `tool.receipt_verified`. Token deltas and health content remain transient.

## 5. Admission And Ordering

The coordinator acquires a PostgreSQL transaction advisory lock keyed by conversation ID, then checks active Runs and allocates `input_seq`. A partial unique index is the final database guard for active states. The lock is held only during admission, not for the LLM duration.

P0 behavior for a busy conversation:

- same `client_turn_id`: resume/replay the same Run;
- different turn: return a retryable busy outcome and let the client retry after the active turn completes;
- never start a second Executor that can interleave history.

This is intentionally simpler than queuing and superseding. Durable queued input and cancellation are P1/P2 work after Run semantics are proven.

## 6. State Mapping

| Executor outcome | Runtime state |
|---|---|
| finalized answer, no pending write ambiguity | `succeeded` |
| explicit confirmation required | `waiting_for_user` |
| uncertain external write | `reconciliation_required` |
| safe retryable or terminal error | `failed` with error code |
| explicit cancellation | `cancelled` |
| client disconnect while background continues | remains `running` |

`interrupted` is an Executor completion classification, not a durable terminal Run state by itself. The coordinator maps it to `failed`, `waiting_for_user` or `reconciliation_required` using existing checkpoint and turn-outcome evidence.

## 7. Privacy

- Runtime tables never contain prompts, responses, image URLs, health values, diagnoses, medication names or raw tool arguments/results.
- Events use allowlisted keys and bounded strings.
- Logs reference opaque Run/Attempt/Operation IDs and coarse status only.
- Existing conversation messages remain the health-content source of truth and retain user ownership filters.

## 8. Rollout And Rollback

1. `shadow`: create Ledger rows and compare outcomes without enforcing conversation admission.
2. `enforce_identity`: canonical IDs become authoritative.
3. `enforce_admission`: one active Run per conversation.

All migrations are additive. Kill switches disable new writes/admission while leaving existing rows readable. Rollback never deletes Run history or changes existing conversation messages.

## 9. Deferred Work

- Full ToolSpec Registry and `ToolGateway.execute()`.
- Downstream business `operation_id` and reconcile implementations.
- Database worker leases, recovery scanner and process-death auto-resume.
- Bounded streaming transport with durable event cursor.
- Cancellation, supersede, parent/child Runs and context compaction hashes.
