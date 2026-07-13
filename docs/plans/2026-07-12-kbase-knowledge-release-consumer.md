# KBase Knowledge Release Consumer Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Consume immutable dedao-kbase Knowledge Releases incrementally while preserving Reva's draft review and serving safety gates.

**Architecture:** Add a small authenticated release client and compiler beside the legacy export importer. The scheduled lifecycle task reads releases after the last audited cursor, converts validated claims into System KB draft artifacts, records the cursor only after the draft write commits, and never publishes directly to serving. Consumer outcomes are posted back only after the local operation has a durable result.

**Tech Stack:** Python 3, urllib, SQLAlchemy/KBAudit, Celery, pytest, existing System KB artifact pipeline.

---

### Task 1: Release transport and validation

**Files:**
- Create: `backend/app/integrations/dedao_kbase_release_consumer.py`
- Test: `backend/tests/test_dedao_kbase_release_consumer.py`

1. Write failing tests for authenticated list/detail requests, bounded pagination, schema rejection, and feedback payloads.
2. Run the focused tests and confirm failure because the consumer does not exist.
3. Implement the minimal HTTP client with explicit timeouts and actionable HTTP errors.
4. Run the focused tests and confirm they pass.

### Task 2: Release-to-draft compilation

**Files:**
- Modify: `backend/app/integrations/dedao_kbase_release_consumer.py`
- Test: `backend/tests/test_dedao_kbase_release_consumer.py`

1. Write failing tests mapping release summary, claims, citations, content hash, release ID, and `usage_policy` into draft artifacts.
2. Verify high-risk/evidence-only metadata remains explicit and no release becomes reviewed automatically.
3. Implement compilation by producing the existing System KB export contract and reusing its reviewed-artifact compiler.
4. Run focused importer and consumer tests.

### Task 3: Incremental lifecycle task

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/app/tasks/system_knowledge_lifecycle.py`
- Modify: `backend/app/celery_app.py`
- Test: `backend/tests/test_dedao_kbase_release_consumer.py`

1. Write failing tests for cursor resume, empty batches, draft-only writes, audit persistence, and imported feedback.
2. Implement incremental sync using the latest successful `KBAudit` release cursor.
3. Reuse the existing scheduled sync entry: prefer releases when the base URL is configured and retain the legacy export path for rollback.
4. Run focused tests, System KB review-gate tests, privacy smoke, and `git diff --check`.

### Task 4: Documentation and release gate

**Files:**
- Modify: `docs/dossiers/2026-07-12-kbase-knowledge-release-consumer.md`
- Modify generated system-map artifacts only if the generator reports a structural change.

1. Record G1-G6 evidence and remaining operator configuration.
2. Run the system-map generator/check required by the repository.
3. Commit only files created or changed by this feature.
