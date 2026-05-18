# Health Operating Loop Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 把健康 Agent 从“能回答问题”推进到“每天带用户安全执行、验证、复盘”的个人健康操作系统。

**Architecture:** 以 `HealthTwin` 作为状态源, `DailyOperatingPlan` 作为当天操作协议, `ActionCard/InterventionEvent` 作为执行和验证事实流。短期先用 deterministic safety + existing specialists, 后续再让 LLM planner 在同一结构化合同下生成更细计划。

**Tech Stack:** FastAPI + SQLAlchemy + PostgreSQL, Expo React Native, Jest, pytest, existing KB V2 evidence refs.

## Progress

- [x] Task 1: Recovery Mode Visibility
- [x] Task 2: Plan Action Feedback Protocol
- [ ] Task 3: Arbiter For Cross-Domain Conflicts
- [ ] Task 4: 7/30/90 Day Review
- [ ] Task 5: Device-First Measurement Automation

---

## Task 1: Recovery Mode Visibility

**Files:**
- Modify: `mobile/components/dashboard/TodayPlanPanel.tsx`
- Test: `mobile/components/dashboard/__tests__/TodayPlanPanel.test.tsx`

**Steps:**
1. Write a failing React Native test: when `plan.state_summary.acute.should_rest_from_training=true`, the panel renders “恢复模式”, illness names, and the guardrail text.
2. Implement the minimal UI block above the action list.
3. Run `cd mobile && npm test -- components/dashboard/__tests__/TodayPlanPanel.test.tsx --runInBand`.
4. Verify existing backend acute-mode tests still pass.

**Acceptance:**
- User can immediately see “today is not a training day” without opening chat.
- Movement goals are visually overridden by recovery guidance.

## Task 2: Plan Action Feedback Protocol

**Files:**
- Create: `backend/app/models/intervention_event.py`
- Create migration: `backend/migrations/*_create_intervention_events.sql`
- Modify: `backend/app/api/daily_plan.py`
- Modify: `mobile/components/dashboard/TodayPlanPanel.tsx`
- Test: backend API + mobile action feedback tests.

**Steps:**
1. Add `POST /daily-plan/me/actions/{action_key}/feedback`.
2. Accept `accepted | adjusted | done | skipped | failed` plus optional reason.
3. Persist as append-only `intervention_events`; do not mutate source advice history.
4. Show mobile quick actions: 做到了 / 跳过 / 调整.

**Acceptance:**
- Every Daily Plan action can become a learning event.
- Future WSCLA can count only safe completed learning actions.

## Task 3: Arbiter For Cross-Domain Conflicts

**Files:**
- Modify: `backend/app/services/daily_operating_plan.py`
- Modify: `backend/app/orchestrator/cross_review.py`
- Test: diet vs movement vs sleep conflict cases.

**Steps:**
1. Add deterministic priority order: safety > acute illness > doctor directive > sleep debt/recovery > metabolic goal.
2. Suppress or rewrite conflicting actions before returning Daily Plan.
3. Emit `state_summary.arbitration_notes`.

**Acceptance:**
- No more “一边休跑、一边提醒运动不足”的 conflict.

## Task 4: 7/30/90 Day Review

**Files:**
- Create service: `backend/app/services/health_operating_review.py`
- Add API: `GET /daily-plan/review?window_days=7|30|90`
- Add mobile card in `mobile/app/my-progress.tsx` or dashboard.

**Acceptance:**
- User sees which actions changed weight, waist, BP, sleep, HRV, or labs.

## Task 5: Device-First Measurement Automation

**Files:**
- Extend body measurement service and docs.
- Add provider capability map for weight, waist, BP, CGM, HealthKit/Health Connect.

**Acceptance:**
- Manual input remains fallback; every measurement task has an automation path.
