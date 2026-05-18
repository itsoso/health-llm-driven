# Daily Plan Acute Arbiter (Suppress Training Conflicts) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 当 `HealthTwin.acute.should_rest_from_training=true` 时，Daily Operating Plan 不再展示任何“训练/跑步/力量”等运动类 intervention 行动，避免出现“暂停训练但仍提醒运动”的冲突。

**Architecture:** 在 `build_daily_operating_plan(...)` 生成 actions 后、进入 AdviceGuard 之前，加入一个 deterministic arbiter：当急性不适需要休息时，过滤掉运动类 intervention，并在 `state_summary.arbitration_notes` 记录压制原因与被压制 action_key。

**Tech Stack:** FastAPI + SQLAlchemy + SQLite tests, pytest.

---

## Task 1: Add failing test for acute arbiter

**Files:**
- Create: `backend/tests/test_daily_operating_plan_arbitration.py`

**Step 1: Write the failing test**

- Seed a user + active illness episode + recent respiratory symptom (so `should_rest_from_training=true`).
- Create one `ActionCard` that is active + accepted and clearly movement-related (title contains “跑步/训练”).
- Call `build_daily_operating_plan(db, user_id)`.
- Assert:
  - Plan contains `movement.pause_training_acute`.
  - Plan does **not** include `intervention.card.<id>`.
  - `state_summary.arbitration_notes` includes a suppression note.

**Step 2: Run test to verify it fails**

Run: `cd backend && PYTHONPATH=. python -m pytest tests/test_daily_operating_plan_arbitration.py -q`
Expected: FAIL because arbiter is not implemented and `arbitration_notes` does not exist.

---

## Task 2: Implement minimal arbiter

**Files:**
- Modify: `backend/app/services/daily_operating_plan.py`

**Step 1: Implement `_apply_arbiter(...)`**

- If `acute_rest` is true:
  - Keep the safety guardrail movement action.
  - Suppress movement-related intervention actions using conservative keyword checks.
  - Add `state_summary["arbitration_notes"]` list describing what was suppressed and why.

**Step 2: Run test to verify it passes**

Run the same pytest command. Expected: PASS.

**Step 3: Run nearby sanity tests**

Run: `cd backend && PYTHONPATH=. python -m pytest tests/test_twin_builder.py::TestBuilderWithPartialData::test_build_picks_up_active_cold_and_recent_respiratory_symptoms -q`
Expected: PASS.

---

## Task 3: Commit

```bash
git add backend/app/services/daily_operating_plan.py backend/tests/test_daily_operating_plan_arbitration.py docs/plans/2026-05-19-daily-plan-acute-arbiter.md
git commit -m "fix(daily-plan): suppress movement interventions in acute rest mode"
git push origin main
```

