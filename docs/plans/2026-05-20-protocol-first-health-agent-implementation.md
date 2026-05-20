# Protocol-first Health Agent Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a protocol-first health Agent that compiles professional knowledge into evidence-backed, safe, measurable daily actions.

**Architecture:** Extend the existing System KB V2 and Daily Operating Plan instead of creating a parallel stack. Add `ProtocolFragment`, `Contraindication`, `EvalCase`, and `InterventionEvent` contracts, route all user-visible health advice through an advice verifier, and use focused eval suites to prevent unsafe or unsupported recommendations.

**Tech Stack:** FastAPI, SQLAlchemy, PostgreSQL migrations, existing `backend/eval` harness, React Native/Expo mobile, existing System KB V2 JSONL artifacts and admin review flow.

---

## Scope

### In scope

- Structured protocol assets compiled from Dedao, books, papers, and guidelines.
- Deterministic verifier for evidence, contraindications, actionability, and verification metrics.
- Daily Plan action feedback and intervention event stream.
- Mobile evidence/action UX needed to close the loop.
- Health-specific eval suites for genetics, labs, wearables, supplements, sleep, movement, and paid-content compliance.

### Out of scope

- Medical diagnosis, prescription, or medication dose changes.
- Long-form paid content serving.
- Full clinician portal.
- Native app changes unless mobile API contracts require them.

---

## Implementation Principles

1. TDD first for each backend behavior.
2. Preserve user data isolation: every query must filter `user_id`.
3. Keep paid source content out of production serving text.
4. Prefer deterministic checks before LLM judge.
5. Low-risk lifestyle advice may be downgraded; high-risk unsupported advice must be blocked.
6. Commit after each coherent task group.

---

## Phase 1: Evidence Contract V2 and Protocol Schema

### Task 1: Add Protocol Schema Models

**Files:**
- Create: `backend/app/schemas/protocol.py`
- Test: `backend/tests/test_protocol_schema.py`

**Step 1: Write failing tests**

Cover:

- `ProtocolFragment` requires `protocol_id`, `domain`, `source_claims`, `risk_level`, `action_template`, `verification`, and `claim_boundary`.
- `Contraindication` requires `trigger`, `blocks`, `fallback`, and `severity`.
- `EvalCaseSpec` rejects cases without `must_not_include` for high-risk domains.

**Step 2: Run failing tests**

Run:

```bash
cd /Users/liqiuhua/work/personal/health-llm-driven
PYTHONPATH=backend backend/venv/bin/python -m pytest backend/tests/test_protocol_schema.py -q
```

Expected: fail because `backend/app/schemas/protocol.py` does not exist.

**Step 3: Implement schema**

Use Pydantic models with strict enums:

- `ProtocolDomain`: `metabolic`, `sleep`, `movement`, `recovery`, `supplement`, `emotion`, `measurement`, `doctor_handoff`.
- `RiskLevel`: `low`, `moderate`, `high`.
- `EvidenceSourceType`: `guideline`, `pubmed`, `dedao`, `book`, `course`, `personal_outcome`, `model_inference`.
- `VerificationSpec`: `metric`, `window_days`, `expected_direction`.

**Step 4: Run passing tests**

Run the same pytest command. Expected: pass.

**Step 5: Commit**

```bash
git add backend/app/schemas/protocol.py backend/tests/test_protocol_schema.py
git commit -m "feat(protocol): define health protocol evidence schema"
```

---

### Task 2: Extend System KB Artifact Contract

**Files:**
- Modify: `backend/app/services/system_knowledge_importer.py`
- Modify: `backend/app/services/system_knowledge_ingest.py`
- Modify: `backend/app/services/system_knowledge_service.py`
- Test: `backend/tests/test_system_knowledge_protocol_artifacts.py`

**Step 1: Write failing tests**

Create fixture JSONL rows for:

- `doc_type=protocol`.
- `doc_type=contraindication`.
- `doc_type=eval_case`.

Assert import preserves:

- `protocol_id`.
- `source_claims`.
- `applies_when`.
- `forbidden_when`.
- `verification`.
- `paid_source_policy`.

**Step 2: Run failing tests**

```bash
PYTHONPATH=backend backend/venv/bin/python -m pytest backend/tests/test_system_knowledge_protocol_artifacts.py -q
```

Expected: fail due to unknown doc types or dropped metadata.

**Step 3: Implement minimal import support**

Keep storage compatible with current `kb_documents` metadata. Do not add a migration unless current schema cannot hold metadata.

**Step 4: Run targeted tests**

```bash
PYTHONPATH=backend backend/venv/bin/python -m pytest backend/tests/test_system_knowledge_protocol_artifacts.py backend/tests/test_system_knowledge_phase0.py -q
```

Expected: pass.

**Step 5: Commit**

```bash
git add backend/app/services/system_knowledge_importer.py backend/app/services/system_knowledge_ingest.py backend/app/services/system_knowledge_service.py backend/tests/test_system_knowledge_protocol_artifacts.py
git commit -m "feat(kb): import protocol and contraindication artifacts"
```

---

## Phase 2: Advice Verifier

### Task 3: Add Health Advice Verifier

**Files:**
- Create: `backend/app/services/health_advice_verifier.py`
- Modify: `backend/app/services/advice_guard.py`
- Test: `backend/tests/test_health_advice_verifier.py`

**Step 1: Write failing tests**

Cases:

- Blocks supplement advice without evidence refs and verification metric.
- Blocks PGx/medication advice without guideline-grade source.
- Downgrades low-risk sleep advice with missing external evidence to `model_inference`.
- Blocks movement intensity increase when recovery contraindication is active.
- Blocks paid-source leakage when candidate body includes long source excerpt marker.

**Step 2: Run failing tests**

```bash
PYTHONPATH=backend backend/venv/bin/python -m pytest backend/tests/test_health_advice_verifier.py -q
```

Expected: fail because verifier does not exist.

**Step 3: Implement minimal verifier**

Implement deterministic function:

```python
verify_advice(candidate, evidence_resolution, personal_matrix, contraindications) -> AdviceVerification
```

Return:

- `allowed`.
- `decision`: `allowed`, `downgraded`, `blocked`.
- `reason`.
- `required_changes`.
- `audit_tags`.

**Step 4: Integrate with `AdviceGuard`**

Do not remove existing duplicate/conflict behavior. Call verifier after contract validation and before persistence for user-visible advice surfaces.

**Step 5: Run targeted tests**

```bash
PYTHONPATH=backend backend/venv/bin/python -m pytest backend/tests/test_health_advice_verifier.py backend/tests/test_advice_guard.py -q
```

Expected: pass.

**Step 6: Commit**

```bash
git add backend/app/services/health_advice_verifier.py backend/app/services/advice_guard.py backend/tests/test_health_advice_verifier.py
git commit -m "feat(advice): verify health recommendations before display"
```

---

### Task 4: Add Health Advice Eval Suite

**Files:**
- Create: `backend/eval/datasets/health_advice.yaml`
- Create: `backend/eval/baselines/health_advice_main.json`
- Modify: `backend/app/tasks/eval_runner.py`
- Test: `backend/tests/test_eval_health_advice_suite.py`

**Step 1: Write failing tests**

Assert:

- suite loads.
- contains at least 30 cases.
- includes categories: `genetics`, `supplement`, `sleep`, `movement`, `lab`, `paid_content`.
- each high-risk case has `must_not_include`.

**Step 2: Add initial dataset**

Seed cases:

- MTHFR TT and 5-MTHF dose overclaim.
- APOE ε4 and deterministic Alzheimer overclaim.
- Warfarin and vitamin K supplement boundary.
- Low HRV/sleep debt and HIIT conflict.
- OSA red flags and sleep hygiene-only failure.
- Paid course long-text leakage.

**Step 3: Register weekly suite**

Add `("health_advice", "main")` to `_SUITES` in `backend/app/tasks/eval_runner.py`.

**Step 4: Run targeted eval**

```bash
PYTHONPATH=backend backend/venv/bin/python -m eval run --suite health_advice --baseline main
```

Expected: report generated with no loader errors.

**Step 5: Commit**

```bash
git add backend/eval/datasets/health_advice.yaml backend/eval/baselines/health_advice_main.json backend/app/tasks/eval_runner.py backend/tests/test_eval_health_advice_suite.py
git commit -m "test(eval): add health advice verification suite"
```

---

## Phase 3: Intervention Event Loop

### Task 5: Add InterventionEvent Persistence

**Files:**
- Create: `backend/app/models/intervention_event.py`
- Create: `backend/migrations/20260520_create_intervention_events.sql`
- Modify: `backend/app/models/__init__.py`
- Test: `backend/tests/test_intervention_events.py`

**Step 1: Write failing tests**

Assert append-only events support:

- `suggested`.
- `accepted`.
- `adjusted`.
- `completed`.
- `skipped`.
- `verified`.

Assert all list queries filter by `user_id`.

**Step 2: Run failing tests**

```bash
PYTHONPATH=backend backend/venv/bin/python -m pytest backend/tests/test_intervention_events.py -q
```

Expected: fail because model/table does not exist.

**Step 3: Implement model and migration**

Use PostgreSQL-compatible types:

- `id SERIAL PRIMARY KEY`.
- `user_id INTEGER NOT NULL`.
- `program_id VARCHAR(120)`.
- `action_id VARCHAR(160)`.
- `event_type VARCHAR(32)`.
- `payload JSONB`.
- `created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()`.

Indexes:

- `(user_id, created_at)`.
- `(user_id, action_id)`.
- `(user_id, program_id)`.

**Step 4: Run tests**

```bash
PYTHONPATH=backend backend/venv/bin/python -m pytest backend/tests/test_intervention_events.py -q
```

Expected: pass.

**Step 5: Commit**

```bash
git add backend/app/models/intervention_event.py backend/app/models/__init__.py backend/migrations/20260520_create_intervention_events.sql backend/tests/test_intervention_events.py
git commit -m "feat(interventions): add append-only intervention events"
```

---

### Task 6: Add Daily Plan Feedback API

**Files:**
- Modify: `backend/app/api/daily_plan.py`
- Create: `backend/app/schemas/daily_plan_feedback.py`
- Test: `backend/tests/test_daily_plan_feedback.py`

**Step 1: Write failing tests**

Cover:

- `POST /api/v1/daily-plan/actions/{action_id}/events`.
- rejects unknown event types.
- writes `InterventionEvent`.
- prevents cross-user action event writes.
- returns updated action state.

**Step 2: Implement API**

Use `get_current_user_required`. Never trust `user_id` from request body.

**Step 3: Run targeted tests**

```bash
PYTHONPATH=backend backend/venv/bin/python -m pytest backend/tests/test_daily_plan_feedback.py backend/tests/test_waist_and_daily_plan.py -q
```

Expected: pass.

**Step 4: Commit**

```bash
git add backend/app/api/daily_plan.py backend/app/schemas/daily_plan_feedback.py backend/tests/test_daily_plan_feedback.py
git commit -m "feat(daily-plan): record action feedback events"
```

---

## Phase 4: Mobile Action Loop

### Task 7: Add Mobile Feedback Service

**Files:**
- Modify: `mobile/services/dailyPlan.ts`
- Test: `mobile/services/__tests__/dailyPlan.test.ts`

**Step 1: Write failing tests**

Assert service can call:

```ts
recordDailyPlanActionEvent(actionId, { event_type: 'completed', payload: {} })
```

and normalizes response state.

**Step 2: Implement service**

Keep existing API style and auth handling.

**Step 3: Run mobile service tests**

```bash
cd mobile
npm test -- --runInBand services/__tests__/dailyPlan.test.ts
```

Expected: pass.

**Step 4: Commit**

```bash
git add mobile/services/dailyPlan.ts mobile/services/__tests__/dailyPlan.test.ts
git commit -m "feat(mobile): add daily plan action feedback service"
```

---

### Task 8: Add Today Plan Action Controls

**Files:**
- Modify: `mobile/components/dashboard/TodayPlanPanel.tsx`
- Modify: `mobile/app/(tabs)/index.tsx`
- Test: `mobile/components/dashboard/__tests__/TodayPlanPanel.test.tsx`

**Step 1: Write failing tests**

Assert each action can render:

- Accept.
- Adjust.
- Complete.
- Skip.
- Evidence chip when `evidence_refs` exists.
- Verification metric text when present.

**Step 2: Implement UI**

Keep one-tap completion. Do not add a complex form in this phase.

**Step 3: Run targeted mobile tests**

```bash
cd mobile
npm test -- --runInBand components/dashboard/__tests__/TodayPlanPanel.test.tsx
```

Expected: pass.

**Step 4: Commit**

```bash
git add mobile/components/dashboard/TodayPlanPanel.tsx mobile/app/(tabs)/index.tsx mobile/components/dashboard/__tests__/TodayPlanPanel.test.tsx
git commit -m "feat(mobile): close daily plan action loop"
```

---

## Phase 5: Knowledge-to-Protocol Compiler

### Task 9: Extend Dedao Compiler Output

**Files:**
- Modify: `backend/scripts/ingest_course.py`
- Modify: `backend/app/services/system_knowledge_ingest.py`
- Modify: `backend/app/services/system_knowledge_pipeline.py`
- Test: `backend/tests/test_dedao_protocol_compiler.py`

**Step 1: Write failing tests**

Given a short source fixture, assert compiler emits:

- at least one claim.
- at least one protocol candidate when the source contains actionable advice.
- no long paid source excerpt.
- source metadata points to course/chapter.

**Step 2: Implement protocol candidate extraction**

Heuristics first:

- detect action verbs and measurable outcomes.
- require `verification.metric`.
- default `risk_level=low` unless supplement/medication/lab disease domain appears.

**Step 3: Run compiler tests**

```bash
PYTHONPATH=backend backend/venv/bin/python -m pytest backend/tests/test_dedao_protocol_compiler.py -q
```

Expected: pass.

**Step 4: Commit**

```bash
git add backend/scripts/ingest_course.py backend/app/services/system_knowledge_ingest.py backend/app/services/system_knowledge_pipeline.py backend/tests/test_dedao_protocol_compiler.py
git commit -m "feat(kb): compile course knowledge into protocol candidates"
```

---

### Task 10: Add Review Queue Counts

**Files:**
- Modify: `backend/app/api/system_knowledge.py`
- Modify: `backend/app/services/system_knowledge_service.py`
- Test: `backend/tests/test_admin_knowledge_protocol_review.py`

**Step 1: Write failing tests**

Assert operations dashboard reports:

- draft protocol count.
- contraindication count.
- eval case count.
- paid-content lint violations.
- high-risk protocols missing external evidence.

**Step 2: Implement counts**

Reuse existing coverage and operations dashboard patterns.

**Step 3: Run targeted tests**

```bash
PYTHONPATH=backend backend/venv/bin/python -m pytest backend/tests/test_admin_knowledge_protocol_review.py backend/tests/test_system_knowledge_phase0.py -q
```

Expected: pass.

**Step 4: Commit**

```bash
git add backend/app/api/system_knowledge.py backend/app/services/system_knowledge_service.py backend/tests/test_admin_knowledge_protocol_review.py
git commit -m "feat(admin): surface protocol knowledge review gaps"
```

---

## Phase 6: Personal Evidence Matrix

### Task 11: Add Personal Evidence Matrix Builder

**Files:**
- Create: `backend/app/services/personal_evidence_matrix.py`
- Test: `backend/tests/test_personal_evidence_matrix.py`

**Step 1: Write failing tests**

Assert builder normalizes:

- genetics.
- labs.
- body measurements.
- wearable sleep/recovery.
- daily behavior logs.
- missing data gaps.

Each signal must include:

- `signal_id`.
- `signal_type`.
- `freshness`.
- `reliability`.
- `domains`.
- `confidence_modifier`.

**Step 2: Implement minimal builder**

Consume existing Health Twin dict. Do not query new tables in this task.

**Step 3: Run tests**

```bash
PYTHONPATH=backend backend/venv/bin/python -m pytest backend/tests/test_personal_evidence_matrix.py -q
```

Expected: pass.

**Step 4: Commit**

```bash
git add backend/app/services/personal_evidence_matrix.py backend/tests/test_personal_evidence_matrix.py
git commit -m "feat(twin): build personal evidence matrix"
```

---

### Task 12: Use Matrix in Planner Evidence Policy

**Files:**
- Modify: `backend/app/orchestrator/orchestrator.py`
- Modify: `backend/app/services/daily_operating_plan.py`
- Test: `backend/tests/test_planner_personal_evidence_matrix.py`

**Step 1: Write failing tests**

Cases:

- if key lab is stale, planner emits data acquisition action instead of confident supplement advice.
- if recovery signals are poor, planner downgrades training intensity.
- if only genetic association exists, confidence remains low.

**Step 2: Implement integration**

Inject matrix summary into planner/verifier. Keep prompt concise and structured.

**Step 3: Run targeted tests**

```bash
PYTHONPATH=backend backend/venv/bin/python -m pytest backend/tests/test_planner_personal_evidence_matrix.py backend/tests/test_health_trajectory.py -q
```

Expected: pass.

**Step 4: Commit**

```bash
git add backend/app/orchestrator/orchestrator.py backend/app/services/daily_operating_plan.py backend/tests/test_planner_personal_evidence_matrix.py
git commit -m "feat(planner): use personal evidence matrix for advice confidence"
```

---

## Phase 7: Epigenetic Report Foundation

### Task 13: Add Epigenetic Report Model

**Files:**
- Create: `backend/app/models/epigenetic_report.py`
- Create: `backend/migrations/20260520_create_epigenetic_reports.sql`
- Modify: `backend/app/models/__init__.py`
- Test: `backend/tests/test_epigenetic_reports.py`

**Step 1: Write failing tests**

Assert:

- reports are scoped by `user_id`.
- report has `vendor`, `sample_date`, `clock_type`, `biological_age`, `pace_of_aging`, `confidence`, `raw_summary`.
- API/service returns `experimental/low` boundary by default.

**Step 2: Implement model**

Use JSONB for vendor-specific fields. Do not implement raw methylation file parsing yet.

**Step 3: Run tests**

```bash
PYTHONPATH=backend backend/venv/bin/python -m pytest backend/tests/test_epigenetic_reports.py -q
```

Expected: pass.

**Step 4: Commit**

```bash
git add backend/app/models/epigenetic_report.py backend/app/models/__init__.py backend/migrations/20260520_create_epigenetic_reports.sql backend/tests/test_epigenetic_reports.py
git commit -m "feat(epigenetics): add experimental report foundation"
```

---

## Phase 8: Verification and Release

### Task 14: Run Backend Verification

**Files:**
- No code changes expected.

**Step 1: Run targeted backend suites**

```bash
PYTHONPATH=backend backend/venv/bin/python -m pytest \
  backend/tests/test_protocol_schema.py \
  backend/tests/test_system_knowledge_protocol_artifacts.py \
  backend/tests/test_health_advice_verifier.py \
  backend/tests/test_intervention_events.py \
  backend/tests/test_daily_plan_feedback.py \
  backend/tests/test_personal_evidence_matrix.py \
  -q
```

Expected: pass.

**Step 2: Run eval suites**

```bash
PYTHONPATH=backend backend/venv/bin/python -m eval run --suite health_advice --baseline main
PYTHONPATH=backend backend/venv/bin/python -m eval run --suite safety --baseline main
```

Expected: no regressions.

---

### Task 15: Run Mobile Verification

**Files:**
- No code changes expected.

**Step 1: Run targeted mobile tests**

```bash
cd mobile
npm test -- --runInBand services/__tests__/dailyPlan.test.ts components/dashboard/__tests__/TodayPlanPanel.test.tsx
```

Expected: pass.

**Step 2: Manual smoke**

Open the app and verify:

- Today Plan renders actions.
- Evidence chip opens detail.
- Complete writes action event.
- Refresh preserves action state.

---

### Task 16: Deployment Decision

**Backend/API changes**

Use project deployment rule:

```bash
./deploy.sh -b
```

Then verify service health and relevant API endpoints.

**Pure mobile JS/TS/UI changes**

Use OTA:

```bash
scripts/mobile-ota.sh production "Protocol-first daily action loop"
```

**Native/TestFlight**

Use only if native config, Expo SDK, native dependency, entitlement, or TestFlight-only feature changes are introduced.

---

## Initial Milestone Recommendation

Do not implement every phase at once. The first production-grade milestone should be:

1. Task 1: Protocol schema.
2. Task 3: Advice verifier.
3. Task 4: Health advice eval suite.
4. Task 5: InterventionEvent.
5. Task 6: Daily Plan feedback API.
6. Task 7–8: Mobile action controls.

This delivers the minimum useful loop:

```text
evidence-backed advice → verified action → user completion → measurable outcome
```

After that, implement the compiler and evidence matrix with real production feedback instead of speculative schema expansion.
