# Runtime Write Circuit Recovery Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Restore the two failed diet-record phrases, stop Runtime write blocks after one truthful tool outcome, and prevent one unresolved user write from disabling unrelated users.

**Architecture:** Keep the durable Runtime and verified-receipt boundary authoritative. Reuse local-time meal inference in the deterministic goal compiler; scope `reconciliation_detected` admission by unresolved owner until a bounded systemic threshold is reached; turn a proven pre-dispatch `runtime_control_unavailable` result into a deterministic terminal outcome; derive cards and client wording from receipt/terminal facts rather than attempted tool names.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy, pytest, TypeScript, React Native/Expo, Next.js/Vitest, Swift 6/Swift Package Manager.

---

### Task 1: Compile the anchor diet phrase deterministically

**Files:**
- Modify: `backend/tests/test_agent_goal_spec.py`
- Modify: `backend/app/services/agent_kernel/goal_spec.py`

**Step 1: Write the failing tests**

Freeze `ExecutionContext.current_time` at 21:05 local time and assert both phrases compile to one `simple_health_record`:

```python
assert goal.domain == "diet"
assert goal.operation == "create"
assert goal.target_record_type == "diet"
assert dict(goal.target_values) == {
    "meal_type": "snack",
    "food_items": "一个桃子",
}
```

Also keep an explicit-meal test proving the keyword beats the clock, and negative/question tests proving advice or ambiguous turns do not become writes.

**Step 2: Run the focused test and verify RED**

```bash
cd backend
PYTHONDONTWRITEBYTECODE=1 /Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin/python -m pytest -q --no-cov -p no:cacheprovider tests/test_agent_goal_spec.py -k 'peach or simple_diet'
```

Expected: the phrase without `加餐` falls back to generic `write`.

**Step 3: Implement the minimum compiler change**

- Pass the current local hour into `_simple_diet_target`.
- Preserve the current explicit-meal extraction path.
- For an unambiguous diet create without a meal label, extract only the current-turn food phrase after the write/eating verb.
- Reuse `diet_voice_parser.infer_meal_type`; do not create a second hour table.
- Keep the existing question, negation, compound, verification, and receipt gates.

**Step 4: Re-run the focused test and verify GREEN**

Run the Step 2 command, then the full `test_agent_goal_spec.py` file.

### Task 2: Make a Runtime write block a one-attempt terminal truth

**Files:**
- Modify: `backend/tests/test_agent_turn_outcome.py`
- Modify: `backend/tests/test_agent_executor_completion_status.py`
- Modify: `backend/tests/test_agent_runtime_service.py`
- Modify: `backend/app/services/agent_turn_outcome.py`
- Modify: `backend/app/services/agent_runtime.py`
- Modify: `backend/app/services/agent_executor.py`

**Step 1: Write the failing pure outcome test**

Add a `runtime_control_unavailable=True` fact to `classify_agent_turn_outcome` and assert:

```python
assert outcome["category"] == "service_unavailable"
assert outcome["reason_code"] == "runtime_control_unavailable"
assert outcome["retryable"] is False
```

Assert `runtime_outcome_from_done` persists it as a non-retryable failed Runtime run with the same error code.

**Step 2: Run the pure tests and verify RED**

```bash
cd backend
PYTHONDONTWRITEBYTECODE=1 /Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin/python -m pytest -q --no-cov -p no:cacheprovider tests/test_agent_turn_outcome.py tests/test_agent_runtime_service.py -k 'runtime_control or service_unavailable'
```

**Step 3: Write the failing full-stream test**

Use the real fast-record stream with a model response containing one valid `health_record`
call and `runtime_write_block_reason="circuit_paused"`. Assert:

- one tool attempt and zero adapter dispatches;
- one `tool_result` with `failed`, `dispatch_started=false`, and `runtime_control_unavailable`;
- no subsequent LLM synthesis call;
- deterministic text says the record was not written because protection is paused;
- `completion_status == "error"`;
- `record_intent_no_tool is False`;
- terminal category is `service_unavailable` and no `recovery_action` exists.

**Step 4: Run the stream test and verify RED**

```bash
cd backend
PYTHONDONTWRITEBYTECODE=1 /Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin/python -m pytest -q --no-cov -p no:cacheprovider tests/test_agent_executor_completion_status.py -k 'runtime_control_block'
```

Expected: current code continues into another model round and/or emits the generic detail prompt.

**Step 5: Implement the minimum terminal path**

- Add a helper that recognizes only `runtime_control_unavailable` with `dispatch_started is False`.
- Capture the terminal fact after the `tool_result` event, stop remaining tool calls, and break the model loop.
- Construct deterministic copy, including verified receipt context if an earlier independent write succeeded.
- Set `final_finish_reason="error"` and prevent `record_intent_no_tool` from overwriting the response.
- Thread the fact into the terminal outcome classifier and add the error code to the Runtime allowlist.

**Step 6: Re-run focused and adjacent tests**

Run Steps 2 and 4 plus existing missing-receipt and retry-source tests.

### Task 3: Scope one reconciliation without bypassing managed Runtime

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/app/services/agent_runtime_rollout.py`
- Modify: `backend/tests/test_agent_runtime_rollout.py`
- Modify: `backend/tests/test_agent_runtime_concurrency.py`

**Step 1: Write the failing admission tests**

Create a paused `reconciliation_detected` state and one content-free
`AgentRun(status="reconciliation_required")` for user A. With threshold `2`, assert:

- A receives no new run and reason `circuit_paused`;
- unrelated user B receives a managed run and reason `scoped_reconciliation_admission`;
- no prompt, response, tool args, or health values are read or serialized.

Add threshold `1`/two-unresolved tests proving all users remain globally blocked. Add manual
pause and stale/failure pause regressions proving their behavior is unchanged.

**Step 2: Run the rollout tests and verify RED**

```bash
cd backend
PYTHONDONTWRITEBYTECODE=1 /Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin/python -m pytest -q --no-cov -p no:cacheprovider tests/test_agent_runtime_rollout.py -k 'scoped_reconciliation or systemic_reconciliation'
```

**Step 3: Implement admission-time scoping**

- Add `agent_runtime_reconciliation_global_pause_threshold` with default `2` and bounds.
- While holding the rollout-state lock, derive the unacknowledged count from
  `reconciliation_generation - reconciliation_acknowledged_generation`, then select that
  many newest content-free `run.reconciliation_required` events whose Runs still have
  `status=reconciliation_required`, and select their owners.
- Exclude acknowledged historical and already resolved owners; if total event count and
  durable generation do not agree, keep the circuit globally fail-closed.
- Only apply this exception when `state.reason_code == "reconciliation_detected"`.
- Below threshold, create the unrelated user's run through the normal coordinator in the
  same locked admission transaction.
- Never return an unmanaged write-capable path.

**Step 4: Verify GREEN and concurrency semantics**

Run the full rollout test file and the relevant PostgreSQL concurrency tests. SQLite may
skip PostgreSQL-only row-lock tests; record the skip honestly.

### Task 4: Base draft suppression on verified state

**Files:**
- Modify: `backend/app/api/agent.py`
- Modify: `backend/tests/test_agent_conversations_api.py`

**Step 1: Write failing API-wrapper tests**

Assert a completed response with `tools_used=["health_record"]` but no receipt/pending
confirmation does not suppress a valid diet draft. Assert a verified `diet_record` receipt
does suppress it, and the existing medication pending-confirmation path remains suppressed.

**Step 2: Run and verify RED**

```bash
cd backend
PYTHONDONTWRITEBYTECODE=1 /Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin/python -m pytest -q --no-cov -p no:cacheprovider tests/test_agent_conversations_api.py -k 'draft_suppression or tools_used'
```

**Step 3: Implement and verify GREEN**

Map only verified receipt resource types and server-owned pending kinds to intake families.
Remove the broad `health_record in tools_used` suppression. Re-run the focused test and
`tests/test_inline_cards_intake_dedup.py`.

### Task 5: Tell users whether a Skill was attempted or completed

**Files:**
- Modify: `mobile/utils/chatTransparency.ts`
- Modify: `mobile/components/chat/ChatBubble.tsx`
- Modify: `mobile/utils/__tests__/chatTransparency.test.ts`
- Modify: `mobile/components/chat/__tests__/ChatBubbleToolsUsed.test.tsx`
- Modify: `frontend/src/components/assistant/chatTransparency.ts`
- Modify: `frontend/src/components/assistant/ChatView.tsx`
- Modify: `frontend/src/components/assistant/chatTransparency.test.ts`
- Modify: `apps/mac/Sources/HealthAgentMacCore/ChatTranscriptHTML.swift`
- Modify: `apps/mac/Sources/HealthAgentMacCore/AgentChatViewModel.swift`
- Modify: `apps/mac/Tests/HealthAgentMacCoreTests/ChatTranscriptHTMLTests.swift`

**Step 1: Write failing presentation tests**

For each client, pass `toolsUsed=["health_record"]` with `completionStatus="error"` and
assert the visible label is `尝试调用 Skill`. Assert `completionStatus="complete"` keeps
`调用 Skill`, and absent legacy completion status keeps the old label for compatibility.

**Step 2: Run client tests and verify RED**

```bash
cd mobile && npm test -- --runInBand utils/__tests__/chatTransparency.test.ts components/chat/__tests__/ChatBubbleToolsUsed.test.tsx
cd ../frontend && npm test -- --run src/components/assistant/chatTransparency.test.ts
cd ../apps/mac && swift test --filter ChatTranscriptHTMLTests
```

**Step 3: Implement the presentation-only change**

Thread existing `completion_status`/`completionStatus` into each transparency builder or
footer. Do not add a backend schema field. Keep tool names content-free and escaped.

**Step 4: Re-run focused tests and typechecks**

Run Step 2 plus Mobile/Frontend TypeScript checks and the full Mac package test suite if
time permits.

### Task 6: Integrated gates, delivery, and production recovery

**Files:**
- Modify: `docs/dossiers/2026-08-01-runtime-write-circuit-recovery.md`
- Modify: system-map/design documentation only if drift checks require it

**Step 1: Run backend integration tests**

```bash
cd backend
DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai PYTHONDONTWRITEBYTECODE=1 /Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin/python -m pytest -q --no-cov -p no:cacheprovider \
  tests/test_agent_goal_spec.py \
  tests/test_agent_turn_outcome.py \
  tests/test_agent_runtime_service.py \
  tests/test_agent_runtime_rollout.py \
  tests/test_agent_runtime_concurrency.py \
  tests/test_agent_executor_completion_status.py \
  tests/test_agent_write_retry_recovery.py \
  tests/test_agent_conversations_api.py \
  tests/test_inline_cards_intake_dedup.py
```

**Step 2: Run client gates**

Run Task 5 tests, Mobile/Frontend typechecks, and Mac tests. Do not pipe any test through
`tail`.

**Step 3: Run repository and safety checks**

```bash
git diff --check
PYTHONDONTWRITEBYTECODE=1 /Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin/python scripts/check_doc_drift.py
PYTHONDONTWRITEBYTECODE=1 /Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin/python backend/scripts/check_dossier_consistency.py
```

Review the complete diff for owner isolation, pre/post-dispatch truth, duplicate-write paths,
threshold rollback, privacy-free telemetry, and legacy-client behavior. Any safety BLOCK
returns to the failing task.

**Step 4: Commit, sync latest main, and push**

Stage only files listed in this plan. Rebase onto the latest clean `origin/main`, re-run the
focused Gate after conflict resolution, commit with project format, and push the branch or
fast-forward main according to the repository's current integration state.

**Step 5: Reconcile and resume production safely**

- Re-read the current rollout state and unresolved content-free operation metadata.
- Use the prior dossier's verified evidence; do not replay or mutate the uncertain health
  record.
- Resume only with the exact current reconciliation generation and record the audit event.
- If generation changed, stop and re-audit before any resume.

**Step 6: Deploy and verify**

Deploy from a clean integration point using `deploy.sh`. Record deployed SHA and rollback
SHA. Require health score, service active state, routes, startup/error scan, Runtime circuit
state, and database migration state to pass before continuing.

**Step 7: Exercise the exact production path**

As the authorized anchor user, submit each original phrase once with a unique client turn.
Require exactly one verified `diet_record` receipt, one owner-scoped persisted record, no
duplicate, no generic disclaimer/detail prompt, and no new reconciliation generation.

**Step 8: Finalize the Dossier**

Record actual G3–G6 evidence and set `shipped` only after the production loop closes. Keep
any client packaging/OTA limitation explicit rather than claiming it shipped.
