# Evidence Boundaries Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add explicit evidence tier, confidence, and claim boundary fields to Personal Health Trajectory risks and Daily Operating Plan actions.

**Architecture:** Keep the contract response-only for this increment. The backend derives fields from existing Twin, genetic, wearable, and behavior signals; mobile services type the fields without changing UI layout. PostgreSQL remains the production target, and local SQLite is used only by existing tests.

**Tech Stack:** FastAPI, SQLAlchemy, PostgreSQL JSONB payloads, pytest, React Native/Expo, Jest, TypeScript.

---

### Task 1: Backend Contract Tests

**Files:**
- Modify: `backend/tests/test_health_trajectory.py`
- Modify: `backend/tests/test_waist_and_daily_plan.py`

**Steps:**
1. Add failing assertions that every `trajectory_risks[]` item contains `evidence_tier`, `confidence`, and `claim_boundary`.
2. Add failing assertions that every Daily Plan action contains the same fields.
3. Run `cd backend && source venv/bin/activate && python -m pytest tests/test_health_trajectory.py tests/test_waist_and_daily_plan.py -q --no-cov -x`.
4. Expected red state: missing `evidence_tier`.

### Task 2: Backend Implementation

**Files:**
- Modify: `backend/app/services/health_trajectory.py`
- Modify: `backend/app/services/daily_operating_plan.py`

**Steps:**
1. Add deterministic evidence mapping:
   - `clinical_guideline/high` for metabolic risks with clinical anchors.
   - `wearable_proxy/medium` for recovery risks using wearable data.
   - `genetic_association/low` for genetic-only risk signals.
   - `experimental/low` for methylation and aging pace.
2. Add default action boundaries that explicitly state the product does not replace diagnosis, prescriptions, or treatment.
3. Preserve existing `evidence_level` for backward compatibility.
4. Re-run the backend tests and keep them green.

### Task 3: Mobile Types And Tests

**Files:**
- Modify: `mobile/services/trajectory.ts`
- Modify: `mobile/services/dailyPlan.ts`
- Modify: `mobile/services/__tests__/trajectory.test.ts`
- Modify: `mobile/services/__tests__/dailyPlan.test.ts`

**Steps:**
1. Add TypeScript union types for evidence tier and confidence.
2. Extend `TrajectoryRisk` and `DailyPlanAction`.
3. Ensure service tests preserve the new fields.
4. Run `cd mobile && npm test -- --runTestsByPath services/__tests__/trajectory.test.ts services/__tests__/dailyPlan.test.ts --runInBand`.

### Task 4: Documentation And Verification

**Files:**
- Modify: `docs/AGENT_NATIVE_HEALTH_OS_ARCHITECTURE.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `mobile/PRODUCT_MAP.md`

**Steps:**
1. Document the evidence contract and scientific boundary.
2. Record that methylation remains a research-grade long-term proxy.
3. Run backend tests, mobile Jest, TypeScript, targeted ESLint, doc drift, and `git diff --check`.
4. Commit, push `main`, deploy via `./deploy.sh`, verify production health and OTA publish.
