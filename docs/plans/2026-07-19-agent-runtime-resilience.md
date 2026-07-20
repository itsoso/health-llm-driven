# Agent Runtime Resilience P2 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add durable Run control, safe stale-attempt settlement and bounded reconnect observability without persisting health content in the Runtime Ledger.

**Architecture:** `AgentRuntimeCoordinator` owns leases and control transitions; the Agent API owns worker task registration and bounded transport; `AgentRunEvent.sequence_no` is the durable content-free cursor. Existing messages and tool receipts remain authoritative for health content and side effects.

**Tech Stack:** Python, FastAPI, SQLAlchemy, PostgreSQL, SQLite test compatibility, asyncio, pytest.

---

### Task 1: Durable Lease And Control State

**Files:**
- Modify: `backend/app/models/agent_runtime.py`
- Modify: `backend/app/services/agent_runtime.py`
- Modify: `backend/migrations/managed/*agent_runtime*.sql`
- Test: `backend/tests/test_agent_runtime_service.py`
- Test: `backend/tests/test_agent_runtime_migrations.py`

1. Write failing tests for worker lease initialization, renewal, stale Attempt fencing, cancellation request and deadline evaluation.
2. Run the focused tests and confirm failures are caused by missing Runtime control behavior.
3. Add additive control fields and Coordinator methods with content-free validation.
4. Run the focused tests and migration suite to green.

### Task 2: Safe Expired-Run Settlement

**Files:**
- Modify: `backend/app/services/agent_runtime.py`
- Test: `backend/tests/test_agent_runtime_recovery.py`
- Test: `backend/tests/test_agent_runtime_concurrency.py`

1. Write failing tests for expired read-only Runs, unresolved write Runs, cancel/deadline settlement and concurrent scanner ownership.
2. Verify the tests fail before production changes.
3. Implement bounded recovery scanning with row/advisory locking and current-Attempt fencing.
4. Verify SQLite and real PostgreSQL behavior.

### Task 3: API Cancellation And Worker Cooperation

**Files:**
- Modify: `backend/app/api/agent.py`
- Modify: `backend/app/config.py`
- Test: `backend/tests/test_agent_runtime_api.py`

1. Write failing owner-scope and cancellation API tests.
2. Add an in-process Run task registry and an owner-scoped cancel endpoint.
3. Renew/check Runtime control at stream yield boundaries and before completion.
4. Ensure cancellation after a verified write never emits a false failure.
5. Run `/agent/send` and `/agent/stream` regressions.

### Task 4: Event Cursor And Bounded SSE Buffer

**Files:**
- Modify: `backend/app/services/agent_runtime.py`
- Modify: `backend/app/api/agent.py`
- Modify: `backend/app/config.py`
- Test: `backend/tests/test_agent_runtime_api.py`
- Test: `backend/tests/test_agent_runtime_service.py`

1. Write failing tests for owner-scoped cursor pagination, payload privacy and bounded disconnected transport.
2. Implement `list_events_after()` with strict limit/cursor validation.
3. Add an owner-scoped Run status/events endpoint.
4. Replace the unbounded SSE queue with a bounded, disconnect-aware bridge.
5. Verify final-message replay remains authoritative after dropped live chunks.

### Task 5: Gates, Review And Delivery

1. Run focused Runtime tests under SQLite.
2. Run real PostgreSQL state, migration and concurrency tests.
3. Run Agent API/Executor, write receipt, image-diet and strict-local regressions.
4. Run Ruff, `py_compile`, document drift, Dossier consistency and `git diff --check`.
5. Request independent code review and fix every Critical/Important finding.
6. Update the Dossier, commit only P2 files and push the feature branch.

## Explicit Non-goals

- No framework migration, service split, Kafka or event sourcing.
- No automatic retry of uncertain writes.
- No health text or token delta in Runtime events.
- No strict-local iPhone protocol change.
- No deployment or Runtime enablement.
