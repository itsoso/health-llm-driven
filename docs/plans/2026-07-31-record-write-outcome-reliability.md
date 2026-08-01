# Health Record Write Outcome Reliability Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Preserve user-owned record dates and make Backend, SSE, and Mobile agree on verified, rejected, uncertain, and safely retryable health writes.

**Architecture:** Backend remains the source of truth: deterministic goal parsing carries date/amount into the domain write, `classify_write_execution` produces additive SSE facts, and the durable `done` outcome exposes retry authority. Mobile treats tool results as intermediate evidence, reaches terminal state only from authoritative completion/recovery, and sends the existing retry-source confirmation instead of blindly resubmitting a possibly committed write.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy, pytest, TypeScript, React Native/Expo, Jest.

---

### Task 1: Reproduce and preserve the historical water target

**Files:**
- Modify: `backend/tests/test_agent_goal_spec.py`
- Modify: `backend/tests/test_health_record_amount_regression.py`
- Modify: `backend/tests/test_agent_stream_no_false_record_claim.py`
- Modify: `backend/app/services/agent_kernel/goal_spec.py`
- Modify: `backend/app/services/agent_executor.py`

**Step 1: Write the failing parser test**

Add a test compiling `昨天喝水很多 补充记录 1200 毫升` at a frozen clock and assert:

```python
assert goal.kind == "simple_health_record"
assert goal.target_record_type == "water"
assert goal.target_date == "2026-07-16"
assert dict(goal.target_values) == {"amount_ml": "1200"}
```

**Step 2: Run the parser test and verify RED**

Run:

```bash
cd backend
PYTHONDONTWRITEBYTECODE=1 venv/bin/python -m pytest -q --no-cov -p no:cacheprovider tests/test_agent_goal_spec.py -k historical_water
```

Expected: FAIL because the current amount regex requires the quantity immediately after “喝水”, so the goal falls back to generic `write`.

**Step 3: Write the failing persistence test**

Call `_execute_tool(health_record)` with `record_date=2026-07-16`, freeze the executor reference clock at 2026-07-17, and assert both the `WaterIntake.record_date` and receipt payload date are 2026-07-16. Also assert `_write_receipt_from_tool_result(...)` returns a verified receipt for the same arguments.

**Step 4: Run the persistence test and verify RED**

Run:

```bash
cd backend
PYTHONDONTWRITEBYTECODE=1 venv/bin/python -m pytest -q --no-cov -p no:cacheprovider tests/test_health_record_amount_regression.py -k historical_date
```

Expected: FAIL because `_exec_health_record` currently uses the reference clock and ignores `data.record_date`.

**Step 5: Implement the minimum date-preserving behavior**

- Allow one bounded phrase between the water signal and the sole ml/l quantity.
- Resolve explicit dates for simple water goals as already done for diet.
- Include canonical `record_date` in `_simple_record_goal_arguments`.
- Build water `recorded_at` from the canonical date and reference time before calling `create_water_intake`.
- Keep response `record_date` sourced from the persisted row.

**Step 6: Run targeted tests and verify GREEN**

Run the two commands above plus the exact full-stream regression in `test_agent_stream_no_false_record_claim.py`.

**Step 7: Commit**

```bash
git add backend/app/services/agent_kernel/goal_spec.py backend/app/services/agent_executor.py backend/tests/test_agent_goal_spec.py backend/tests/test_health_record_amount_regression.py backend/tests/test_agent_stream_no_false_record_claim.py
git commit -m "fix(agent): preserve historical water record date"
```

### Task 2: Emit one typed backend write-outcome contract

**Files:**
- Modify: `backend/tests/test_agent_executor_completion_status.py`
- Modify: `backend/tests/test_agent_turn_outcome.py`
- Modify: `backend/app/services/agent_executor.py`
- Modify: `backend/app/services/agent_turn_outcome.py`

**Step 1: Write failing SSE contract tests**

For verified, pre-dispatch rejected, and missing-receipt results, assert `tool_result.data` contains:

```python
{
    "write_outcome": "verified|rejected|uncertain|failed",
    "dispatch_started": True | False | None,
    "resubmit_safe": True | False,
    "error_code": None | "...",
}
```

Keep the legacy `success`, `write_attempted`, `write_completed`, and `receipt` assertions.

**Step 2: Run tests and verify RED**

```bash
cd backend
PYTHONDONTWRITEBYTECODE=1 venv/bin/python -m pytest -q --no-cov -p no:cacheprovider tests/test_agent_executor_completion_status.py -k 'write_outcome or missing_receipt'
```

Expected: FAIL because the additive fields are absent.

**Step 3: Implement the additive event envelope**

After extracting the receipt, classify the result once with `classify_write_execution(result, receipt=receipt)` and append the content-free fields to the write `tool_result` event. `resubmit_safe` is true only when dispatch is proven false and the outcome is rejected/failed.

**Step 4: Write and run failing terminal-outcome test**

Extend `classify_agent_turn_outcome` with an explicit `write_reconciliation_required` fact. Assert it returns category `write_reconciliation_required`, reason `missing_receipt`, and `retryable=False` before generic tool/completion error branches.

**Step 5: Implement and verify GREEN**

Pass `bool(unverified_write_operations)` from the main Agent run into the classifier. Re-run both backend test files.

**Step 6: Commit**

```bash
git add backend/app/services/agent_executor.py backend/app/services/agent_turn_outcome.py backend/tests/test_agent_executor_completion_status.py backend/tests/test_agent_turn_outcome.py
git commit -m "fix(agent): expose authoritative write outcomes"
```

### Task 3: Parse write facts without generic Mobile failure inference

**Files:**
- Modify: `mobile/services/__tests__/chatStream.test.ts`
- Modify: `mobile/services/chat.ts`

**Step 1: Write failing parser tests**

Assert a rejected write tool result maps to `writeOutcome='rejected'`, `dispatchStarted=false`, `resubmitSafe=true`, a specific thought such as `记录信息需要补充`, and preserves legacy fields. Assert uncertain maps to `记录状态需要核对` and `resubmitSafe=false`.

**Step 2: Run and verify RED**

```bash
cd mobile
npm test -- --runInBand services/__tests__/chatStream.test.ts
```

Expected: FAIL because `StreamEvent` does not parse the new fields and uses the generic `暂时不可用` thought.

**Step 3: Implement minimal parsing and labels**

Add the write outcome fields to `StreamEvent`, parse them only for write tool results, and derive specific safe progress labels while retaining old-server fallback behavior.

**Step 4: Run and verify GREEN**

Re-run the command above.

**Step 5: Commit**

```bash
git add mobile/services/chat.ts mobile/services/__tests__/chatStream.test.ts
git commit -m "fix(mobile): parse typed health write outcomes"
```

### Task 4: Make Mobile terminal and retry behavior authoritative

**Files:**
- Modify: `mobile/utils/__tests__/agentTurnState.test.ts`
- Modify: `mobile/hooks/__tests__/useChatEngine.test.ts`
- Modify: `mobile/app/(tabs)/__tests__/chat.test.tsx`
- Modify: `mobile/utils/agentTurnState.ts`
- Modify: `mobile/hooks/useChatEngine.ts`
- Modify: `mobile/app/(tabs)/chat.tsx`

**Step 1: Write failing reducer tests**

Assert:

- a failed/uncertain write tool result moves to `verifying`, not terminal `failed`;
- a following `done(error, retryable=false)` becomes failed and non-recoverable;
- a missing receipt can never become recoverable;
- a `done(error)` with an active backend retry-source action becomes recoverable with `retryMode='retry_source'`;
- late progress still cannot overwrite a true terminal state.

**Step 2: Run and verify RED**

```bash
cd mobile
npm test -- --runInBand utils/__tests__/agentTurnState.test.ts
```

Expected: FAIL because the reducer terminalizes intermediate write failures and defaults failures to recoverable.

**Step 3: Implement the state contract**

- Extend `done` with retryability/error/retry mode from `turn_outcome` and `recovery_action`.
- Keep write tool failures in verifying state until `done` or runtime recovery.
- Default unverified writes to non-recoverable.
- Preserve transport-before-accept retry behavior.

**Step 4: Write failing hook/screen tests**

Assert uncertain writes never render `重试上一轮`. Assert an active retry-source action does render Retry and tapping it sends `重试`, while pre-accept transport failures still resend the original text.

**Step 5: Run and verify RED**

```bash
cd mobile
npm test -- --runInBand hooks/__tests__/useChatEngine.test.ts app/'(tabs)'/__tests__/chat.test.tsx
```

**Step 6: Implement minimal hook/screen behavior and verify GREEN**

Parse terminal metadata from `done`, dispatch it into the reducer, and branch the Retry handler by `retryMode`.

**Step 7: Commit**

```bash
git add mobile/services/chat.ts mobile/utils/agentTurnState.ts mobile/hooks/useChatEngine.ts mobile/app/'(tabs)'/chat.tsx mobile/utils/__tests__/agentTurnState.test.ts mobile/hooks/__tests__/useChatEngine.test.ts mobile/app/'(tabs)'/__tests__/chat.test.tsx
git commit -m "fix(mobile): prevent unsafe health write retries"
```

### Task 5: Integrated verification, review, and delivery

**Files:**
- Modify: `docs/dossiers/2026-07-31-record-write-outcome-reliability.md`
- Modify: release/system-map documentation only if structural drift checks require it

**Step 1: Run backend integration tests**

```bash
cd backend
DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai PYTHONDONTWRITEBYTECODE=1 venv/bin/python -m pytest -q --no-cov -p no:cacheprovider tests/test_agent_goal_spec.py tests/test_health_record_amount_regression.py tests/test_agent_stream_no_false_record_claim.py tests/test_agent_executor_completion_status.py tests/test_agent_turn_outcome.py tests/test_agent_write_retry_recovery.py tests/test_agent_runtime_tool_operations.py
```

Expected: all pass with a real zero exit code.

**Step 2: Run Mobile integration tests and typecheck**

```bash
cd mobile
npm test -- --runInBand services/__tests__/chatStream.test.ts utils/__tests__/agentTurnState.test.ts hooks/__tests__/useChatEngine.test.ts app/'(tabs)'/__tests__/chat.test.tsx
npx tsc --noEmit
```

Expected: all pass, no TypeScript errors.

**Step 3: Run repository checks**

```bash
git diff --check
python3 scripts/check_doc_drift.py
```

Expected: zero exit code; regenerate code-derived system map only if required.

**Step 4: Independent review and safety gate**

Review the committed diff specifically for:

- duplicate-write paths after accepted/uncertain outcomes;
- incorrect date/timezone persistence;
- old-client compatibility;
- owner isolation and health-data leakage;
- tests that bypass the real stream path.

Any BLOCK returns to the failing task and repeats tests/review.

**Step 5: Deploy backend and verify health**

Use the repository backend deploy protocol from a clean integration point. Record the deployed SHA, rollback SHA, service state, health endpoint, runtime ledger outcome, and startup error scan in the dossier.

**Step 6: Publish Mobile OTA and verify the real path**

Publish the JS/TS change only after backend health passes. Verify on a real device that a local rejection is specific and a simulated/controlled uncertain write has no Retry button.

**Step 7: Handle production row `#705` separately**

Do not mutate it as part of deployment. After explicit approval, update only user 52's row `#705` from 2026-08-01 to 2026-07-31 with before/after evidence and an audit note.

**Step 8: Finalize dossier and commit delivery metadata**

Update G3–G6 with actual evidence and set the dossier to shipped only after production and device validation pass.
