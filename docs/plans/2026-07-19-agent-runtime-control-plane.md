# Agent Runtime Control Plane P0 Implementation Plan

> **Goal:** Make each cloud Agent turn a durable, uniquely traceable Run while preserving the existing AgentExecutor, write checkpoints, receipts and client contracts.
>
> **Architecture:** Add a modular-monolith `AgentRuntimeCoordinator` around the current Executor. The API owns the canonical `RunContext`; Executor and Kernel consume it but never regenerate identity. A content-free Run Ledger records lifecycle state, while conversation admission prevents two distinct active turns from interleaving one conversation.
>
> **Scope:** P0-A canonical Run identity and P0-B durable Run Ledger plus per-conversation admission. Strict-local iPhone execution remains device-only and creates no server Run.

## Invariants

1. One `(user_id, client_turn_id)` maps to one logical `run_id`.
2. API usage capture, Executor completion, Kernel trace and Run Ledger use the same `run_id`.
3. At most one active Run (`queued` or `running`) exists per conversation.
4. Runtime tables never persist prompts, replies, health values, image URLs or raw tool arguments/results.
5. Existing client-turn replay and message checkpoint behavior stays authoritative and backward compatible.
6. Existing public API response fields are unchanged; `run_id` and `attempt_id` are additive.

## Task 1: Define Run Ledger Contract and Migrations

**Files:**
- Create: `backend/app/models/agent_runtime.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/migrations/managed/20260719_120000_create_agent_runtime.postgresql.sql`
- Create: `backend/migrations/managed/20260719_120000_create_agent_runtime.sqlite.sql`
- Modify: `backend/tests/test_managed_migrations.py`
- Create: `backend/tests/test_agent_runtime_models.py`

**Step 1: Write failing model and migration tests**

Cover:
- all four tables exist after ORM `create_all`;
- `(user_id, client_turn_id)` is unique when client turn is present;
- only one active Run per non-null conversation;
- PostgreSQL and SQLite managed migration files exist and contain equivalent tables/indexes;
- deleting a user cascades Run rows, while message references use `SET NULL`.

Run:

```bash
cd backend
DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai .venv/bin/python -m pytest \
  tests/test_agent_runtime_models.py tests/test_managed_migrations.py -q
```

Expected: new tests fail because models and migrations do not exist.

**Step 2: Implement the smallest schema**

Add:
- `AgentRun`: opaque identity, owner/conversation/message links, client identity, input sequence, state, origin, bounded local correlation IDs, deadline, coarse error code and timestamps.
- `AgentRunAttempt`: attempt identity/number, state, worker/lease metadata and timestamps.
- `AgentToolOperation`: opaque operation identity, tool name, effect class, fingerprint, state and verified resource reference; no raw arguments/results.
- `AgentRunEvent`: monotonic event sequence, allowlisted milestone name and bounded content-free payload.

Use `JSONColumn` for PostgreSQL JSONB / SQLite JSON compatibility. Add the PostgreSQL partial unique active-Run index and an equivalent SQLite partial index.

**Step 3: Run model and migration tests**

Expected: pass.

## Task 2: Implement Runtime State Machine and Privacy Boundary

**Files:**
- Create: `backend/app/services/agent_runtime.py`
- Create: `backend/tests/test_agent_runtime_service.py`

**Step 1: Write failing service tests**

Cover:
- `create_or_resume_run()` creates `queued` Run and first attempt;
- duplicate client turn returns the existing logical Run without another attempt unless explicitly resumed;
- valid transitions: `queued -> running -> succeeded|failed|waiting_for_user|reconciliation_required|cancelled`;
- invalid terminal-to-running transition raises a typed error;
- Run completion binds durable conversation/source/assistant message IDs;
- event payload accepts only bounded operational keys and rejects health/content-like keys;
- Runtime logs/rows contain no original user message.

Run:

```bash
cd backend
DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai .venv/bin/python -m pytest \
  tests/test_agent_runtime_service.py -q
```

Expected: fail because coordinator does not exist.

**Step 2: Implement coordinator and immutable context**

Add:
- `RunContext(run_id, attempt_id, user_id, conversation_id, client_turn_id, origin, origin_device_id, local_execution_id, privacy_mode)`;
- typed `RunBusyError`, `InvalidRunTransition`, `UnsafeRunEventPayload`;
- transition table and terminal/active state sets;
- `create_or_resume_run`, `mark_running`, `bind_messages`, `complete`, `fail`, and `record_event`;
- additive feature mode parsing (`off`, `enforce`) with default `off` for safe rollout.

In `off`, canonical identity still propagates but no new rows or admission behavior are enabled. In `enforce`, a busy different client turn produces `RunBusyError`, and database uniqueness is the final guard. A row-writing observe mode was intentionally removed because it cannot honestly coexist with the active-Run uniqueness invariant.

**Step 3: Run service tests**

Expected: pass.

## Task 3: Propagate Canonical Run Identity Through Executor and Kernel

**Files:**
- Modify: `backend/app/services/agent_executor.py`
- Modify: `backend/app/services/agent_kernel/context.py` only if type handling requires it
- Modify: `backend/tests/test_agent_event_stream.py`
- Modify: `backend/tests/test_agent_executor_status_events.py`

**Step 1: Write failing identity tests**

Cover:
- `AgentExecutor.run_stream(..., run_id="run-canonical", attempt_id="attempt-1")` produces Kernel trace with exactly `run-canonical`;
- final `done` contains additive `run_id` and `attempt_id`;
- deterministic GenUI and starter-pregen replies receive the same identity and terminal mapping;
- replayed client turns preserve caller-supplied canonical identity;
- omitting IDs keeps direct/internal callers backward compatible.

Run:

```bash
cd backend
DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai .venv/bin/python -m pytest \
  tests/test_agent_event_stream.py tests/test_agent_executor_status_events.py -q
```

Expected: fail because Executor does not accept canonical IDs.

**Step 2: Add optional identity parameters**

- Extend `run_stream` and `_start_agent_kernel_turn` with optional `run_id` / `attempt_id`.
- Pass `run_id` into `build_turn_snapshot`; keep Kernel fallback generation only for legacy direct callers.
- Add identities to every `done` path through one helper/choke point where possible.
- Do not change prompt construction, tool dispatch, message content or write checkpoint logic.

**Step 3: Run identity tests and focused Executor regression**

Expected: pass.

## Task 4: Integrate Runtime Into `/stream` and `/send`

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/app/api/agent.py`
- Create: `backend/tests/test_agent_runtime_api.py`
- Modify: `backend/tests/test_agent_conversations_api.py` only for additive assertions if needed

**Step 1: Write failing API tests**

Cover both endpoints:
- API-generated `run_id` is passed to Usage and Executor;
- successful `done` binds conversation/message IDs and terminal state;
- Executor error marks Run/Attempt failed with a coarse code;
- duplicate `(user_id, client_turn_id)` reuses the same Run;
- in `enforce`, a second distinct turn against an active conversation is retryable and never starts Executor;
- `off` mode leaves legacy behavior unchanged;
- strict-local requests are not routed to these cloud endpoints; explicit cloud origin fields are optional and content-free.

Run:

```bash
cd backend
DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai .venv/bin/python -m pytest \
  tests/test_agent_runtime_api.py tests/test_agent_conversations_api.py -q
```

Expected: fail before API integration.

**Step 2: Add runtime lifecycle wrapper**

- Add `agent_runtime_mode: str = "off"` to settings.
- Generate one API-owned `run_id` and `attempt_id` before Usage capture.
- Create/claim Runtime row using the background DB session for `/stream` and request DB session for `/send`.
- Pass the same context to Executor and Usage tracker.
- On `done`, bind durable IDs and map existing `completion_status`/`turn_outcome` to Runtime state.
- On exceptions/cancellation, mark coarse failed/cancelled state without storing user content.
- Emit additive `run_id` / `attempt_id` in final data and send `meta`.
- Preserve client disconnect behavior: background `/stream` keeps running and finalizes the Run.

**Step 3: Run API tests**

Expected: pass.

## Task 5: Verify Conversation Admission Under Concurrency

**Files:**
- Create: `backend/tests/test_agent_runtime_concurrency.py`
- Modify: `backend/app/services/agent_runtime.py`

**Step 1: Write failing concurrency tests**

Cover:
- two different turns for one conversation admit exactly one active Run in `enforce`;
- duplicate client turn resolves to one Run;
- two different conversations can proceed;
- terminal Run releases the conversation for the next input sequence;
- PostgreSQL test uses two independent sessions when `TEST_POSTGRES_DATABASE_URL` is available; SQLite covers deterministic service semantics in normal CI.

**Step 2: Implement short-lived admission lock**

- PostgreSQL: transaction advisory lock keyed by conversation ID during claim + input sequence allocation.
- SQLite/test: process-local keyed lock plus partial unique index.
- Never hold the admission lock across model/tool execution.
- Convert unique conflicts into typed duplicate/busy outcomes after re-querying.

**Step 3: Run concurrency tests**

Expected: pass.

## Task 6: Full Regression, Safety Gate and Documentation

**Files:**
- Modify: `docs/dossiers/2026-07-19-agent-runtime-control-plane.md`
- Modify generated system map only if the project drift checker requires it

**Step 1: Run focused Agent suite**

```bash
cd backend
DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai .venv/bin/python -m pytest \
  tests/test_agent_runtime_models.py \
  tests/test_agent_runtime_service.py \
  tests/test_agent_runtime_api.py \
  tests/test_agent_runtime_concurrency.py \
  tests/test_agent_event_stream.py \
  tests/test_agent_conversations_api.py \
  tests/test_agent_executor_status_events.py \
  tests/test_agent_executor_completion_status.py -q
```

**Step 2: Run migration and doc gates**

```bash
cd backend
DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai .venv/bin/python -m pytest tests/test_managed_migrations.py -q
cd ..
.venv/bin/python scripts/check_dossier_consistency.py
.venv/bin/python scripts/check_doc_drift.py
```

Use the repository's actual available virtualenv path if root `.venv` is absent.

**Step 3: Perform safety review**

Review all runtime persistence and logs for:
- owner scoping;
- no health content in Runtime rows/events;
- fail-loud state errors;
- no duplicate write path;
- no change to strict-local behavior;
- rollback/kill-switch behavior.

**Step 4: Update Dossier gates**

Record exact test evidence, safety findings, rollout mode and remaining deferred work. Deployment is a separate Gate after review; do not deploy P0 Runtime directly from an unmerged feature branch.

## Deferred Follow-up

- P1 ToolSpec Registry and `ToolGateway.execute()` as the only tool execution choke point.
- Business-layer operation idempotency and reconcile implementations.
- Process-death recovery scanner, lease renewal and durable event cursor.
- Cancellation/supersede, `waiting_for_user` resume and parent/child Runs.
- Bounded live event buffering and context/policy version snapshots.
