# System KB Ops Eval Lifecycle Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Move System KB eval from test/release-only verification into the weekly governance lifecycle and admin operations dashboard.

**Architecture:** Reva keeps reviewed System KB as the serving authority. The lifecycle task should run lint, confidence decay, draft crystallization, and reviewed eval cases, then store one `KBAudit(op="lifecycle_report")` snapshot. The operations dashboard should surface eval failures or missing eval data as action items.

**Tech Stack:** FastAPI admin API, SQLAlchemy, Celery, `KBAudit`, `run_system_kb_eval_cases`, pytest with SQLite `DATABASE_URL`.

---

## Latest Knowledge Direction

1. **P0: Production eval signal.** Add reviewed eval execution to `run_system_kb_lifecycle_once` and surface failures/missing eval in `/admin/knowledge/operations_dashboard`.
2. **P1: dedao-kbase draft observability.** Show latest `dedao_kbase_export_sync_draft` audit and draft gate status in the operations dashboard.
3. **P1: reviewer workflow.** Add a compact admin review UI/API path for draft artifact diffs before promotion.
4. **P2: real semantic backend.** Replace deterministic semantic aliases with pgvector-backed embeddings while preserving the current search response shape.
5. **P2: source freshness policy.** Track guideline/source `last_reviewed_at` and stale source action items per domain.

This implementation executes P0 and the P1 dedao-kbase draft observability slice. It avoids new medical content and does not relax reviewed-only serving.

## Task 1: Lifecycle Eval Snapshot

**Files:**
- Modify: `backend/app/tasks/system_knowledge_lifecycle.py`
- Test: `backend/tests/test_system_knowledge_lifecycle.py`

**Step 1: Write the failing test**

Add a reviewed claim plus matching reviewed eval case, run `run_system_kb_lifecycle_once`, and assert:
- `result["eval"]["total"] == 1`
- `result["eval"]["passed"] == 1`
- `result["eval"]["failed"] == 0`
- the `lifecycle_report` audit stores the same `eval` summary.

**Step 2: Run test to verify it fails**

Run:

```bash
DATABASE_URL=sqlite:///./backend/test_kb_ops_eval.db PYTHONPATH=backend backend/venv/bin/python -m pytest backend/tests/test_system_knowledge_lifecycle.py -q
```

Expected: fail with missing `eval`.

**Step 3: Implement minimal lifecycle eval**

Import `run_system_kb_eval_cases` and call it from `run_system_kb_lifecycle_once`, with a high default limit and no case filter. Store a compact summary plus case details in the returned report.

**Step 4: Run test to verify it passes**

Run the same pytest command. Expected: pass.

## Task 2: Operations Dashboard Eval Action Items

**Files:**
- Modify: `backend/app/services/system_knowledge_service.py`
- Test: `backend/tests/test_system_knowledge_phase0.py`

**Step 1: Write the failing test**

Add a focused admin dashboard test with latest `lifecycle_report.diff.eval.failed == 1`, then assert `kb_eval_failures_present` is in `action_items`.

**Step 2: Run test to verify it fails**

Run:

```bash
DATABASE_URL=sqlite:///./backend/test_kb_ops_eval.db PYTHONPATH=backend backend/venv/bin/python -m pytest backend/tests/test_system_knowledge_phase0.py::test_admin_operations_dashboard_flags_eval_failures -q
```

Expected: fail because dashboard action items ignore eval.

**Step 3: Implement dashboard action items**

In `_knowledge_operations_action_items`, inspect `latest_lifecycle_report["diff"]["eval"]`:
- missing eval -> `kb_eval_report_missing`
- `failed > 0` -> `kb_eval_failures_present`
- `total == 0` -> `kb_eval_cases_missing`

**Step 4: Run test to verify it passes**

Run the focused dashboard test. Expected: pass.

## Task 3: Verification

Run:

```bash
DATABASE_URL=sqlite:///./backend/test_kb_ops_eval.db PYTHONPATH=backend backend/venv/bin/python -m pytest backend/tests/test_system_knowledge_lifecycle.py backend/tests/test_system_knowledge_phase0.py::test_admin_operations_dashboard_summarizes_kb_health backend/tests/test_system_knowledge_phase0.py::test_admin_operations_dashboard_flags_eval_failures -q
PYTHONPATH=backend backend/venv/bin/python -m compileall -q backend/app/tasks/system_knowledge_lifecycle.py backend/app/services/system_knowledge_service.py backend/tests/test_system_knowledge_lifecycle.py backend/tests/test_system_knowledge_phase0.py
PYTHONPATH=backend backend/venv/bin/python backend/scripts/run_external_health_knowledge_release_gate.py --artifact-dir backend/data/system_kb_v2_seed
```

Expected: pytest pass, compileall exit 0, release gate pass.

## Task 4: dedao-kbase Draft Observability

**Files:**
- Modify: `backend/app/services/system_knowledge_service.py`
- Test: `backend/tests/test_system_knowledge_phase0.py`

**Step 1: Write the failing test**

Seed a `KBAudit(op="dedao_kbase_export_sync_draft")` with a draft gate that is not serving-allowed, then assert:
- `/admin/knowledge/operations_dashboard` returns `latest_dedao_kbase_export_sync`
- the returned audit includes the source commit and gate payload
- `dedao_kbase_draft_review_needed` appears in `action_items`

**Step 2: Implement minimal dashboard observability**

Add a latest-audit helper for `dedao_kbase_export_sync_draft`, return it from the operations dashboard, and add the review-needed action item when the latest draft sync gate has blocking reasons. This is read-only observability; draft artifacts still require review plus the normal release gate before serving.
