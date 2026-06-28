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

This implementation executes P0, the P1 dedao-kbase draft observability and reviewer workflow API slices, plus the P2 source freshness and pgvector fallback-safe semantic backend slices. It avoids new medical content and does not relax reviewed-only serving.

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

## Task 5: dedao-kbase Reviewer Workflow API

**Files:**
- Modify: `backend/app/api/system_knowledge.py`
- Modify: `backend/app/services/system_knowledge_service.py`
- Test: `backend/tests/test_system_knowledge_phase0.py`

**Step 1: Write the failing tests**

Add admin API tests for:
- `GET /api/v1/admin/knowledge/dedao_kbase/draft_review`
- `POST /api/v1/admin/knowledge/dedao_kbase/draft_review/approve`

The review bundle test should read the configured artifact directory, return draft gate status and compact previews, and avoid returning raw `body` content from paid knowledge artifacts. The approve test should call the artifact review promotion path, mark draft claim and relation metadata as reviewed, return a serving-allowed gate, and record an audit row.

**Step 2: Implement review bundle and approve endpoints**

Add service helpers that:
- resolve `settings.system_kb_artifact_dir`
- call `validate_artifact_review_gate` for current draft gate status
- return manifest and preview data for pages, entities, claims, protocols, contraindications, eval cases, and relations
- call `review_draft_artifacts` for reviewer approval

Add admin routes that record:
- `KBAudit(op="dedao_kbase_draft_review_bundle")`
- `KBAudit(op="dedao_kbase_draft_review_approved")`

**Step 3: Verification**

Run:

```bash
DATABASE_URL=sqlite:///./backend/test_kb_review_workflow.db PYTHONPATH=backend backend/venv/bin/python -m pytest backend/tests/test_system_knowledge_phase0.py::test_admin_operations_dashboard_surfaces_dedao_kbase_draft_sync backend/tests/test_system_knowledge_phase0.py::test_admin_dedao_kbase_draft_review_bundle_reads_configured_artifacts backend/tests/test_system_knowledge_phase0.py::test_admin_dedao_kbase_draft_review_approve_promotes_configured_artifacts -q
PYTHONPATH=backend backend/venv/bin/python -m compileall -q backend/app/api/system_knowledge.py backend/app/services/system_knowledge_service.py backend/tests/test_system_knowledge_phase0.py
PYTHONPATH=backend backend/venv/bin/python backend/scripts/run_external_health_knowledge_release_gate.py --artifact-dir backend/data/system_kb_v2_seed
```

Expected: pytest pass, compileall exit 0, release gate pass.

## Task 6: P2 Source Freshness Policy

**Files:**
- Modify: `backend/app/services/system_knowledge_service.py`
- Test: `backend/tests/test_system_knowledge_phase0.py`

**Implemented behavior:**
- Domain coverage now includes `source_freshness` for external reviewed sources.
- Sources are de-duplicated by `(kind, source)`.
- Staleness windows are explicit by source kind:
  - guideline/article/other: 365 days
  - database: 180 days
  - course: 730 days
  - research/book: 1095 days
- Missing `last_reviewed_at` and stale sources are surfaced as `kb_stale_sources_present` in the operations dashboard action items.

**Verification:**

```bash
DATABASE_URL=sqlite:///./backend/test_kb_p2.db PYTHONPATH=backend backend/venv/bin/python -m pytest backend/tests/test_system_knowledge_phase0.py::test_admin_operations_dashboard_flags_stale_source_freshness -q
```

Expected: pass.

## Task 7: P2 pgvector Semantic Backend

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/app/services/system_knowledge_service.py`
- Modify: `backend/.env.example`
- Test: `backend/tests/test_system_knowledge_vector_backend.py`

**Implemented behavior:**
- Search retrieval still returns the same response shape and channel names.
- When PostgreSQL, `SYSTEM_KB_PGVECTOR_ENABLED=true`, an embedding provider is configured, and `kb_document_embeddings` exists, vector search prefers `pgvector:<SYSTEM_KB_EMBEDDING_MODEL>`.
- If pgvector, the embedding provider, or dense rows are unavailable, retrieval falls back to the existing `sparse_term_cosine_v1` vector backend.
- Reindex now attempts to create and populate `kb_document_embeddings`, but dense indexing failures do not break reviewed KB serving.

**Production note:**
- The current production PostgreSQL host did not report the `vector` extension as available during implementation verification. Until pgvector is installed and `reindex_knowledge_documents` has populated dense embeddings, production will keep serving via sparse fallback.

**Verification:**

```bash
DATABASE_URL=sqlite:///./backend/test_kb_p2.db PYTHONPATH=backend backend/venv/bin/python -m pytest backend/tests/test_system_knowledge_vector_backend.py::test_search_vector_channel_prefers_pgvector_backend_when_available -q
PYTHONPATH=backend backend/venv/bin/python -m compileall -q backend/app/config.py backend/app/services/system_knowledge_service.py backend/tests/test_system_knowledge_vector_backend.py
PYTHONPATH=backend backend/venv/bin/python backend/scripts/run_external_health_knowledge_release_gate.py --artifact-dir backend/data/system_kb_v2_seed
```

Expected: pytest pass, compileall exit 0, release gate pass.
