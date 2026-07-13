# KBase Persistent Review Workspace Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Preserve Dedao Knowledge Release drafts across deployments and safely rebuild them when the canonical System KB base changes.

**Architecture:** Separate the immutable repository seed from a configured persistent review workspace. Record a deterministic base fingerprint with the Release cursor, use incremental sync only for a valid matching workspace, and otherwise atomically rebuild by replaying all Releases.

**Tech Stack:** Python, SQLAlchemy, Pydantic settings, pytest, Celery, JSONL artifacts.

---

### Task 1: Bind the Persistent Review Path

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/app/tasks/system_knowledge_lifecycle.py`
- Modify: `backend/app/services/system_knowledge_service.py`
- Test: `backend/tests/test_dedao_kbase_release_consumer.py`

1. Add a failing test proving sync and review resolve the dedicated Dedao path.
2. Run the focused test and confirm it fails because the setting is absent.
3. Add `dedao_kbase_review_artifact_dir` and dedicated path helpers.
4. Run the focused test and confirm it passes.

### Task 2: Detect Lost or Stale Workspaces

**Files:**
- Modify: `backend/app/tasks/system_knowledge_lifecycle.py`
- Test: `backend/tests/test_dedao_kbase_release_consumer.py`

1. Add failing tests for a deleted workspace and a changed canonical seed.
2. Confirm both currently return `up_to_date` or reuse stale artifacts.
3. Add deterministic artifact fingerprinting and rebuild-mode selection.
4. Persist fingerprint, cursor, and replay mode only after success.
5. Confirm both tests pass.

### Task 3: Make Rebuild Atomic and Replayable

**Files:**
- Modify: `backend/app/tasks/system_knowledge_lifecycle.py`
- Test: `backend/tests/test_dedao_kbase_release_consumer.py`

1. Add a failing test that injects a rebuild failure and verifies the old
   workspace remains intact and the cursor does not advance.
2. Implement temporary sibling construction and atomic directory replacement.
3. Fetch Releases from the beginning in rebuild mode; retain cursor-based
   incremental fetch for a valid workspace.
4. Run focused Release consumer tests.

### Task 4: Configuration and Operations Contract

**Files:**
- Modify: `.env.example`
- Modify: `docs/dossiers/2026-07-13-kbase-persistent-review-workspace.md`
- Test: `backend/tests/test_dedao_kbase_release_consumer.py`

1. Document the persistent production path without credentials.
2. Run focused tests, System KB review tests, doc drift, and diff checks.
3. Commit the implementation and request review.

### Task 5: Deploy and Prove Persistence

1. Configure `DEDAO_KBASE_REVIEW_ARTIFACT_DIR` in production.
2. Deploy through the standard backend deployment gate.
3. Run the first sync and verify `draft_written`, the expected Release cursor,
   and `serving_allowed=false`.
4. Restart or redeploy and verify the workspace still exists.
5. Run the second sync and verify `up_to_date` without losing the review bundle.
6. Record G5/G6 evidence in the Dossier before any approval or serving publish.
