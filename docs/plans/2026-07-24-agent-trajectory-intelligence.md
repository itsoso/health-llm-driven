# Agent Trajectory Intelligence Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make XiaoBa reliably understand and complete stateful multi-turn health tasks, starting with recalculating and updating existing breakfast/lunch records from a visible diet card.

**Architecture:** Preserve the current Agent Runtime and add a typed task layer above it. Project only safe, actionable card objects into the immutable `TurnSnapshot`, compile the user request into a `GoalSpec`, then use deterministic kickoff and postcondition checks around the existing model/tool loop. Success is judged by tool trajectory, receipts, and database delta.

**Tech Stack:** Python, FastAPI, SQLAlchemy/PostgreSQL, pytest, existing Agent Kernel/Runtime, YAML/JSON eval datasets.

---

### Task 1: Stateful trajectory evaluation contract

**Files:**
- Create: `backend/eval/datasets/agent_trajectories.yaml`
- Create: `backend/tests/test_agent_trajectory_cases.py`
- Modify: `backend/tests/fixtures/agent_intent_corpus.json`

**Steps:**
1. Add the production incident as a Golden Case with prior card objects, expected goal, required tool sequence, expected DB delta, prohibited clarification, and receipt count.
2. Add adjacent cases: single-meal correction, multiple same-meal records, missing meal, negated update, and retry.
3. Run the new focused test and verify it fails because no `GoalSpec` or actionable context exists.
4. Keep the dataset deterministic; do not use an LLM judge for write correctness.

### Task 2: Safe actionable context projection

**Files:**
- Modify: `backend/app/services/agent_kernel/types.py`
- Modify: `backend/app/services/agent_kernel/context.py`
- Modify: `backend/app/services/agent_conversation_service.py`
- Modify: `backend/app/services/agent_executor.py`
- Test: `backend/tests/test_agent_kernel_turn_snapshot.py`
- Test: `backend/tests/test_agent_conversation_service.py`

**Steps:**
1. Add immutable `ActionableReference` data to `TurnSnapshot`.
2. Project recent `diet_daily_summary`, `diet`, `diet_draft`, and verified diet receipts into a minimal safe shape.
3. Exclude arbitrary assistant prose, image URLs, tokens, and unrelated health metadata.
4. Rebind the snapshot after conversation history is loaded and inject a short system-owned context block into the current user turn.
5. Verify the prior card survives history sanitation as typed context without exposing raw `reva-ui`.

### Task 3: GoalSpec compiler

**Files:**
- Create: `backend/app/services/agent_kernel/goal_spec.py`
- Modify: `backend/app/services/agent_kernel/types.py`
- Modify: `backend/app/services/agent_kernel/context.py`
- Modify: `backend/app/services/agent_executor.py`
- Test: `backend/tests/test_agent_goal_spec.py`

**Steps:**
1. Add a typed `GoalSpec` with `kind`, `domain`, `operation`, target date/meal types, required postconditions, and evidence.
2. Compile “重新估算和写入早午两餐” into `diet_recalculate_update` targeting breakfast and lunch.
3. Treat negation and questions as non-write.
4. Use actionable context only for referent resolution, never as write authorization.
5. Refine the kernel intent to `mutate/diet/update` while keeping ToolGateway enforcement.

### Task 4: Deterministic diet workflow kickoff

**Files:**
- Modify: `backend/app/services/agent_executor.py`
- Test: `backend/tests/test_health_manage_date_normalize.py`
- Test: `backend/tests/test_agent_executor_completion_status.py`

**Steps:**
1. When the model returns prose or asks for already-known fields, synthesize one read-only `health_manage(list)` call for the goal date.
2. Include target meal types in the tool-result instruction.
3. Reject model attempts to convert this goal into `health_record(create)`.
4. Resolve updates only to existing record IDs owned by the current user.
5. Verify the workflow never creates duplicate diet rows.

### Task 5: Postcondition verification

**Files:**
- Modify: `backend/app/services/agent_executor.py`
- Modify: `backend/app/services/agent_kernel/events.py`
- Test: `backend/tests/test_agent_write_outcome.py`
- Test: `backend/tests/test_agent_executor_completion_status.py`

**Steps:**
1. Track expected meal targets and verified update receipts.
2. Before accepting a final answer, require a read-back after the last write.
3. Compare read-back record IDs/meal types with the goal.
4. If a target is missing, return a precise partial result or minimal clarification; never claim full success.
5. Emit health-body-free trace counters for goal kind, target count, verified count, and clarification reason.

### Task 6: Regression gate and rollout

**Files:**
- Modify: `scripts/harness_llm_regression_gate.py`
- Modify: `docs/dossiers/2026-07-24-agent-trajectory-intelligence.md`
- Regenerate: `docs/_generated/system-map.json` only if architecture roster changes

**Steps:**
1. Add trajectory cases to the Agent regression gate.
2. Run focused unit tests, Agent Kernel tests, Runtime tests, and deterministic evals.
3. Run lint/type checks applicable to touched backend files.
4. Review privacy logs and tool idempotency.
5. Commit and push only the touched files.
6. Deploy backend, verify health, replay the exact user scenario, and compare database rows plus runtime receipts.
