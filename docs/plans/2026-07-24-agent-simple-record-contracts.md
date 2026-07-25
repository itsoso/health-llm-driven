# Agent Simple Record Contracts Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make explicit water and symptom record turns complete on the first attempt with a verified receipt even when the selected model emits prose instead of a tool call.

**Architecture:** Extend the existing typed Goal Contract Registry rather than adding another router. Compile high-confidence water and symptom creates into a simple-record goal, use server-owned extraction to build a deterministic `health_record` fallback, and accept completion only from the existing verified receipt path. Keep the durable Agent Runtime, ToolGateway, idempotency, capability policy, and client protocol unchanged.

**Tech Stack:** Python 3, FastAPI services, SQLAlchemy, pytest, existing Agent Kernel and Runtime ledgers.

---

### Task 1: Lock the failed trajectories

**Files:**
- Modify: `backend/eval/datasets/agent_trajectories.yaml`
- Modify: `backend/tests/test_agent_goal_spec.py`
- Modify: `backend/tests/test_agent_stream_no_false_record_claim.py`

1. Add explicit water and symptom create cases plus read-only and negated counterexamples.
2. Add a streaming regression where the model returns an unverified success sentence for `记录喝水500ml` with no tool call.
3. Assert that the server performs exactly one `health_record` call and emits success only when the result has a registered `water_record` receipt.
4. Run the focused tests and confirm the new water test fails because no deterministic water fallback exists.

### Task 2: Compile typed simple-record goals

**Files:**
- Modify: `backend/app/services/agent_kernel/types.py`
- Modify: `backend/app/services/agent_kernel/goal_spec.py`
- Modify: `backend/app/services/agent_kernel/postconditions.py`
- Modify: `backend/tests/test_agent_goal_registry.py`
- Modify: `backend/tests/test_agent_goal_postconditions.py`

1. Extend `GoalSpec` with a target record type and a small in-memory tuple of normalized target values.
2. Register a high-confidence simple-record compiler after specialized multi-record diet compilation.
3. Render an exact contract: one create, no substitute record type, verified receipt required, no oral success.
4. Register a simple-record postcondition verifier that accepts exactly one verified receipt of the expected registered resource type.
5. Run registry, compiler, and postcondition tests.

### Task 3: Add deterministic water execution

**Files:**
- Modify: `backend/app/services/agent_executor.py`
- Modify: `backend/tests/test_agent_stream_no_false_record_claim.py`
- Modify: `backend/tests/test_agent_executor_fast_routing.py`

1. Build a deterministic `health_record(water)` call from the server-compiled goal only when there is no receipt or attachment.
2. Invoke it in both normal streaming and multi-model paths before the existing record-intent fail-closed response.
3. Keep the current ToolGateway, confirmation policy, write checkpoint, runtime idempotency, and receipt extraction path unchanged.
4. Ensure an existing receipt prevents a second write.
5. Run the streaming and fast-routing tests.

### Task 4: Verify the affected Agent surface

**Files:**
- Modify: `docs/dossiers/2026-07-24-agent-trajectory-intelligence.md`
- Regenerate: `docs/_generated/system-map.json` only if the generator reports a structural change.

1. Run focused Kernel, receipt, fast-record, Runtime, and trajectory tests.
2. Run the offline Agent regression gate and stateful trajectory scorer.
3. Run Python compile and documentation drift checks.
4. Record exact evidence and residual risks in the dossier.
5. Commit only files from this slice and push the clean branch to `main`.
