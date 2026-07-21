# Agent Runtime Blocked Write Recovery Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Prevent policy-blocked model write calls from replacing advice with an uncertain-write error or duplicating a replayed turn.

**Architecture:** Make ToolGateway emit structured rejection facts, classify both structured and legacy rejections as pre-dispatch terminal outcomes, and force a no-tool synthesis round after a blocked write in a non-write turn. Keep replay idempotency in the mobile message merge layer.

**Tech Stack:** Python, FastAPI Agent Runtime, pytest, React Native TypeScript, Jest.

---

### Task 1: Freeze the write-outcome contract

**Files:**
- Modify: `backend/tests/test_agent_write_outcome.py`
- Modify: `backend/app/services/agent_write_outcome.py`
- Modify: `backend/app/services/agent_kernel/tool_gateway.py`

1. Add failing tests for structured policy rejection and legacy `[NEEDS_CLARIFICATION]`.
2. Run the focused tests and confirm the legacy marker is misclassified as uncertain.
3. Return a structured rejected payload from ToolGateway and add legacy compatibility.
4. Run the focused tests again.

### Task 2: Recover the original advice turn

**Files:**
- Create: `backend/tests/test_agent_blocked_write_recovery.py`
- Modify: `backend/app/services/agent_executor.py`

1. Add an integration test where an advice turn requests `health_record`.
2. Confirm the test currently returns the missing-receipt template.
3. Treat a policy rejection as a completed blocked attempt and force the next round to synthesize without tools.
4. Clarify the prompt contract so sleep advice is not an implicit event write.
5. Assert the adapter was not called, no uncertain write remains, and advice is returned.

### Task 3: Remove replay duplication on Mobile

**Files:**
- Modify: `mobile/hooks/__tests__/useChatEngine.test.ts`
- Modify: `mobile/hooks/useChatEngine.ts`

1. Add a failing test for a replay of an already persisted `client_turn_id`.
2. Merge replayed server history into the existing optimistic pair.
3. Verify terminal status replaces the progress banner and no duplicate bubble is appended.

### Task 4: Regression, review, and delivery

**Files:**
- Modify: `backend/app/services/voice_command_service.py`
- Modify: `backend/app/services/telegram_inbound.py`
- Modify: `backend/app/services/procedure_recipe_service.py`
- Modify: `backend/app/services/post_record_quality.py`
- Modify: their focused tests

1. Teach every direct execution surface to recognize structured rejections.
2. Run focused backend and mobile tests without output-truncating pipes.
3. Run the broader Agent Kernel/Runtime/write receipt regression suite.
4. Review the exact staged diff for health-write safety and unrelated WIP exclusion.
5. Commit only this fix, push `main`, deploy backend, and ship Mobile OTA only if Mobile code changed.
