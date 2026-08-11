# Mobile Today Follow-up Card Repair Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 修复今日页复查卡“完成”按钮调用不受支持写路径的问题，消除内部英文指标，并让所有主动作都有明确即时反馈。

**Architecture:** 后端 `HealthAgendaItem` 投影继续作为写能力真源，只对存在真实完成端点的来源声明 `can_complete`。移动端 `DailyArtifactCard` 再按来源能力防御：医疗复查项显示“处理复查”并进入现有复查页面，不把 `HealthProblem` 误写成已完成；协议/用药/补剂走统一 Agenda 完成端点，Daily Plan 走其专用事件端点，并在成功后即时显示回执。指标中文名继续集中在 `trajectoryDisplay.ts`。

**Tech Stack:** FastAPI / SQLAlchemy、React Native / Expo Router、TanStack Query、Jest、Pytest

---

### Task 1: Lock the broken contracts with failing tests

**Files:**
- Modify: `backend/tests/test_agenda.py`
- Modify: `mobile/components/home/__tests__/DailyArtifactCard.test.tsx`
- Modify: `mobile/services/__tests__/trajectoryDisplay.test.ts`

**Step 1: Write the failing backend capability test**

Assert a due `health_problem` smart item reports `can_complete=False`, while a pending `health_protocol` remains completable.

**Step 2: Run the focused backend test and verify RED**

Run: `cd backend && pytest tests/test_agenda.py -q`

Expected: FAIL because `_to_smart_item` currently treats every due/overdue item as completable.

**Step 3: Write the failing mobile behavior tests**

Assert `follow_up_completed` renders as Chinese, a `health_problem` card renders “处理复查”, and pressing it invokes navigation rather than completion.

**Step 4: Run the focused mobile tests and verify RED**

Run: `cd mobile && npm test -- --runInBand --runTestsByPath services/__tests__/trajectoryDisplay.test.ts components/home/__tests__/DailyArtifactCard.test.tsx`

Expected: FAIL because the metric is unmapped and the card trusts the invalid completion flag.

### Task 2: Repair backend completion capability

**Files:**
- Modify: `backend/app/services/agenda_service.py`
- Test: `backend/tests/test_agenda.py`

**Step 1: Add a single supported-source capability predicate**

Restrict `can_complete` to actionable states with a real write path: `health_protocol`, `medication`, `supplement`, or `daily_plan_action`; keep `health_problem` and `review_schedule` read-only at this layer.

**Step 2: Run the backend test and verify GREEN**

Run: `cd backend && pytest tests/test_agenda.py tests/test_daily_artifact.py tests/test_agenda_range_complete.py -q`

Expected: PASS.

### Task 3: Repair mobile copy, routing, and feedback

**Files:**
- Modify: `mobile/services/trajectoryDisplay.ts`
- Modify: `mobile/components/home/DailyArtifactCard.tsx`
- Modify: `mobile/components/home/TodayContent.tsx`
- Test: `mobile/services/__tests__/trajectoryDisplay.test.ts`
- Test: `mobile/components/home/__tests__/DailyArtifactCard.test.tsx`

**Step 1: Localize the follow-up metric**

Map `follow_up_completed` to `复查完成情况`, and render its evidence as `后续确认复查是否完成。`.

**Step 2: Gate completion defensively on the client**

Only show “完成” for sources with a supported completion target. For `checkup` / `health_problem`, show “处理复查”; pressing it reuses `buildDailyArtifactExecuteRoute` and opens `/medical-exams`.

**Step 3: Add immediate successful completion receipt**

After a supported mutation succeeds, mark that action as completed locally while dependent Today queries refresh. Do not create a false receipt on error.

**Step 4: Run focused mobile tests and typecheck**

Run: `cd mobile && npm test -- --runInBand --runTestsByPath services/__tests__/trajectoryDisplay.test.ts components/home/__tests__/DailyArtifactCard.test.tsx components/home/__tests__/DynamicTodayRenderer.test.tsx utils/__tests__/dailyArtifactNavigation.test.ts`

Run: `cd mobile && npx tsc --noEmit --pretty false`

Expected: PASS.

### Task 4: Verify safety, drift, and release readiness

**Files:**
- Modify if required: `docs/dossiers/2026-08-11-mobile-today-followup-card-repair.md`

**Step 1: Run repository integrity checks**

Run: `python3 scripts/check_doc_drift.py`

Run: `git diff --check`

Expected: PASS.

**Step 2: Commit only task files**

Use a `fix(mobile)` Conventional Commit and explicitly stage the files listed above; do not stage unrelated workspace changes.

**Step 3: Run the safety review gate**

Review the committed diff for false medical completion, user isolation, error visibility, and accidental clinical-state mutation. A GO verdict is required before release.

**Step 4: Push and release**

Push `main`. If the backend contract changed, deploy backend first and verify health; then publish the Mobile production OTA and perform a production smoke check.
