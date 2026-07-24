# Agent Runtime Hardening Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make every newly managed cloud Agent Run traceable to a content-free execution contract, expose integrity gaps operationally, and then bring remaining cloud entrypoints behind the same durable lifecycle.

**Architecture:** Extend the existing PostgreSQL Run Ledger with nullable contract snapshot fields and derive deterministic digests from static Runtime metadata. Add aggregate administrator monitoring without storing user content. Introduce a facade around the existing Runtime Coordinator and AgentExecutor before migrating entrypoints one by one.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy, PostgreSQL, SQLite contract tests, pytest.

---

### Task 1: Runtime contract fingerprint helpers

**Files:**
- Modify: `backend/app/services/agent_kernel/tool_registry.py`
- Modify: `backend/app/services/agent_kernel/capability_policy.py`
- Test: `backend/tests/test_agent_kernel_tool_registry.py`
- Test: `backend/tests/test_agent_kernel_capability_policy.py`

1. Write failing tests proving fingerprints are 64-character lowercase SHA-256,
   deterministic, and change when operational metadata changes.
2. Run the two focused test files and verify RED.
3. Serialize only static ToolSpec/policy metadata with sorted keys and compact JSON.
4. Run the focused tests and verify GREEN.

### Task 2: Persist snapshots on new Runs

**Files:**
- Modify: `backend/app/models/agent_runtime.py`
- Modify: `backend/app/services/agent_runtime.py`
- Modify: `backend/app/api/agent.py`
- Create: `backend/migrations/managed/20260723_120000_agent_runtime_contract_snapshot.postgresql.sql`
- Create: `backend/migrations/managed/20260723_120000_agent_runtime_contract_snapshot.sqlite.sql`
- Modify: `backend/tests/test_agent_runtime_models.py`
- Modify: `backend/tests/test_agent_runtime_service.py`
- Modify: `backend/tests/test_agent_runtime_api.py`

1. Write failing model/service/API tests for snapshot persistence and replay stability.
2. Verify RED.
3. Add nullable columns and the paired managed migration.
4. Add `RuntimeContractSnapshot.current()` and pass it only at new managed admission.
5. Preserve the first snapshot on retry/replay.
6. Verify GREEN.

### Task 3: Add administrator integrity projection

**Files:**
- Modify: `backend/app/services/agent_runtime_rollout.py`
- Modify: `backend/app/api/monitoring.py`
- Modify: `backend/tests/test_agent_runtime_rollout.py`
- Modify: `backend/tests/test_agent_runtime_rollout_api.py`

1. Write failing tests for recent contract coverage, version distribution, message
   linkage gaps, current-attempt gaps and bounded age buckets.
2. Verify RED.
3. Implement aggregate, content-free queries with a bounded window.
4. Keep the projection observation-only.
5. Verify GREEN and verify monitoring responses contain no user ID, Run ID or
   health text.

### Task 4: Runtime Facade for internal cloud producers

**Files:**
- Create: `backend/app/services/agent_runtime_facade.py`
- Create: `backend/app/services/agent_runtime_lease.py`
- Test: `backend/tests/test_agent_runtime_facade.py`

1. Write failing tests for admission, lease, canonical identity, replay, cancellation,
   failure and message binding.
2. Verify RED.
3. Implement the facade by composing the existing Coordinator and Executor.
4. Extract lease heartbeat from the HTTP API and reuse it from the facade.
5. Verify GREEN without duplicating API-specific code.

### Task 5: Migrate Siri and WeChat

**Files:**
- Modify: `backend/app/api/siri.py`
- Modify: `backend/app/services/wechat_bot.py`
- Modify: relevant Siri and WeChat tests

1. Add failing tests that duplicate upstream messages create one Run and one write,
   and that each user/channel reuses one first-party Agent conversation.
2. Verify RED.
3. Route each entrypoint through the facade with a stable content-free turn identity.
4. Verify GREEN and preserve existing response wording/timeouts.

### Task 6: Evaluate and migrate remaining cloud paths

**Files:**
- Modify as justified: `backend/app/services/telegram_inbound.py`
- Modify as justified: `backend/app/services/voice_command_service.py`
- Modify as justified: `backend/app/services/starter_pregen_producer.py`
- Test: matching existing test files

For each path, first prove that Runtime ownership preserves its confirmation,
read-only or scratch-conversation semantics. Voice shortcut and Telegram writes
use direct-tool Runtime settlement. Telegram query/chat uses the full Agent
stream. Starter pregen remains explicitly outside managed Runtime because it is
read-only, disposable and has no user turn identity.

### Task 7: Gates and rollout

1. Run all Runtime, Kernel, entrypoint and monitoring focused tests.
2. Run Ruff, compile checks, schema compatibility, doc drift and `git diff --check`.
3. Run the LLM change classifier; run live Harness only if the classifier requires it
   and the user has explicitly authorized model spend.
4. Complete an independent privacy/safety review.
5. Commit only files from this plan, push, verify main CI, deploy from a clean main
   worktree, verify migration, health score and production Runtime aggregates.
6. Update the Dossier with exact evidence and only then advance to the App Store
   reliability phase.
