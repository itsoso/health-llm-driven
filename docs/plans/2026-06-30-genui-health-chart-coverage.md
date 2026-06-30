# GenUI Health Chart Coverage Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Expand Aheng chat GenUI charting from the current wearable/weight subset to common health-management metrics: blood pressure, waist, body fat, blood glucose, and SpO2, with a structured no-data fallback.

**Architecture:** Keep the deterministic backend builder as the single source of chart data. Extend `metric_line_chart` rather than introducing a new component; add one optional `metric_empty_state` block only for chart requests with insufficient data, so clients do not fall back to ASCII charts.

**Tech Stack:** FastAPI / SQLAlchemy / pytest for backend chart generation; React/Next MarkdownRenderer and React Native card registry for rendering; existing `reva-ui` fenced block contract.

**Status (2026-06-30):** implementation verified, pending commit/push/deploy. Backend GenUI now covers BP, waist, body fat, blood glucose, and SpO2; Web/Mobile render `metric_empty_state`.

---

### Task 1: Backend RED Tests

Status: Done.

**Files:**
- Modify: `backend/tests/test_genui_chart.py`

**Steps:**
1. Add tests that chart requests for blood pressure, waist, body fat, blood glucose, and SpO2 are detected and return `metric_line_chart`.
2. Add a test for chart intent with insufficient data that returns a `metric_empty_state` reva-ui block and does not call normal LLM.
3. Run: `DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai backend/venv/bin/pytest backend/tests/test_genui_chart.py -q`
4. Expected: new tests fail because metrics/fallback are not implemented.

### Task 2: Backend Implementation

Status: Done.

**Files:**
- Modify: `backend/app/services/genui/chart_builder.py`
- Modify: `backend/app/api/agent.py`

**Steps:**
1. Extend metric allowlist with table-backed specs:
   - `bp_systolic` / `bp_diastolic` from `blood_pressure_records`
   - `waist` from `waist_records`
   - `body_fat` from `weight_records`
   - `blood_glucose` from `basic_health`
   - `spo2` from `garmin_data.spo2_avg`
2. Add metric aliases for natural Chinese prompts.
3. Build an empty-state block for insufficient data; keep values deterministic and avoid LLM.
4. Re-run backend tests until green.

### Task 3: Client Renderer RED/GREEN

Status: Done.

**Files:**
- Modify: `frontend/src/components/assistant/MarkdownRenderer.tsx`
- Modify: `frontend/src/components/assistant/__tests__/MarkdownRenderer.test.tsx`
- Modify: `mobile/utils/revaUiBlocks.ts`
- Modify: `mobile/utils/__tests__/revaUiBlocks.test.ts`
- Modify: `mobile/components/chat/cards/registry.tsx`

**Steps:**
1. Add tests proving `metric_empty_state` is parsed/rendered without raw JSON leakage.
2. Implement a compact empty-state card in Web and Mobile.
3. Re-run focused frontend/mobile tests.

### Task 4: Verification And Release

Status: Verification done; release pending.

**Commands:**
- `DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai backend/venv/bin/pytest backend/tests/test_genui_chart.py -q`
- `npm --prefix frontend test -- --run src/components/assistant/__tests__/MarkdownRenderer.test.tsx`
- `npm --prefix frontend run build`
- `pnpm --dir mobile exec jest mobile/utils/__tests__/revaUiBlocks.test.ts mobile/components/chat/cards/__tests__/registry.test.tsx --runInBand`

**Release:**
- Commit and push to `main`.
- Deploy backend/web with `./deploy.sh --all -y` from a clean worktree if the main worktree has unrelated untracked files.
- For mobile JS changes, publish OTA with `scripts/mobile-ota.sh production`.
