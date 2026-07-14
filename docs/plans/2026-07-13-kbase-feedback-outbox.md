# KBase Consumer Feedback Outbox Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Reliably forward real Health citation and adjudication outcomes to Dedao KBase without blocking user-facing requests.

**Architecture:** Preserve producer claim provenance in imported artifacts, enrich existing review audits, and add a cursor-based Celery flusher over `KBAudit`. Reuse the authenticated release client and producer idempotency contract.

**Tech Stack:** Python, SQLAlchemy, Celery, FastAPI, pytest, Dedao Knowledge Release REST API.

---

### Task 1: Preserve producer claim identity

**Files:**
- Modify: `backend/app/integrations/dedao_kbase_release_consumer.py`
- Test: `backend/tests/test_dedao_kbase_release_consumer.py`

1. Write a failing test for `release_claim_id` metadata.
2. Run the focused test and confirm RED.
3. Preserve the original bounded claim ID in claim and relation metadata.
4. Re-run and confirm GREEN.

### Task 2: Preserve adjudication provenance

**Files:**
- Modify: `backend/app/services/kbase_review_workspace.py`
- Modify: `backend/app/api/system_knowledge.py`
- Test: `backend/tests/test_dedao_kbase_release_consumer.py`
- Test: `backend/tests/test_system_knowledge_phase0.py`

1. Write failing tests for release provenance in direct and packet-applied adjudication audits.
2. Confirm RED.
3. Return bounded provenance from the workspace service and persist it in the existing audit diff.
4. Confirm GREEN.

### Task 3: Add the feedback flusher

**Files:**
- Modify: `backend/app/tasks/system_knowledge_lifecycle.py`
- Test: `backend/tests/test_dedao_kbase_release_consumer.py`

1. Write failing tests for used/rejected grouping, no-signal cursor movement, retry idempotency, and failure cursor retention.
2. Confirm RED.
3. Implement the cursor-based flusher with bounded batches and deterministic event IDs.
4. Confirm GREEN.

### Task 4: Schedule and release

**Files:**
- Modify: `backend/app/celery_app.py`
- Modify: `docs/dossiers/2026-07-13-kbase-feedback-outbox.md`

1. Add a five-minute beat entry and structural test if required by existing conventions.
2. Run focused tests, backend tests, system-map drift checks, pre-commit, and diff checks.
3. Record review and deployment evidence. Do not deploy through a red Gate.
