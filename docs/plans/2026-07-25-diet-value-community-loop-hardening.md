# Diet Value Community Loop Hardening Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the shipped diet value and peer-support loop resistant to duplicate publishing, recoverable across page re-entry, and immediately responsive on Mobile.

**Architecture:** Keep the backend as the source of truth. Enforce one non-deleted community post per owned diet record in PostgreSQL and the ORM, expose an owner-scoped source lookup, and let Mobile restore that state before showing the composer. Reaction taps update local state immediately and reconcile with the server response or roll back on failure.

**Tech Stack:** FastAPI, SQLAlchemy/PostgreSQL, Pydantic, React Native/Expo, Jest, pytest.

---

### Task 1: Source-level publish idempotency

**Files:**
- Modify: `backend/app/models/community.py`
- Modify: `backend/app/api/community.py`
- Modify: `backend/app/schemas/community.py`
- Create: `backend/migrations/managed/20260725_180000_community_source_idempotency.postgresql.sql`
- Create: `backend/migrations/managed/20260725_180000_community_source_idempotency.sqlite.sql`
- Test: `backend/tests/test_community_api.py`

1. Add a failing test that publishes one owned diet record with two different request idempotency keys and expects the same active post.
2. Add a failing test that owner-scoped source lookup returns the existing post and rejects another user's record.
3. Add a failing test proving a deleted share can be published again.
4. Add a partial unique index for one non-deleted `(user_id, source_type, source_id)` post.
5. Make create return the existing active post, return conflict for an under-review post, and recover from database races.
6. Run focused API and managed-migration tests.

### Task 2: Mobile state recovery and immediate reactions

**Files:**
- Modify: `mobile/services/community.ts`
- Modify: `mobile/app/community.tsx`
- Test: `mobile/services/__tests__/community.test.ts`
- Test: `mobile/app/__tests__/community.test.tsx`

1. Add a failing service test for owner-scoped source lookup.
2. Add a failing screen test proving an already-published record hides the composer.
3. Add a failing screen test proving a reaction count changes before the request resolves.
4. Implement existing-post lookup during initial load.
5. Apply an optimistic reaction update and roll back to the previous post when the request fails.
6. Keep all error copy explicit that the private diet record is unaffected.

### Task 3: Actionable stale weight feedback

**Files:**
- Modify: `backend/app/services/post_record_quality.py`
- Test: `backend/tests/test_post_record_quality.py`

1. Add a failing test that stale weight goal data adds an `更新体重` route action.
2. Route to `/body-measurements`, the existing owned weight and waist capture surface.
3. Verify fresh and unsafe goal states do not receive the stale-data action.

### Task 4: Gates and release

1. Run focused backend and Mobile tests.
2. Run Mobile TypeScript and target lint.
3. Regenerate API types and system maps if contract checks require it.
4. Run doc drift, dossier consistency, migration checks and `git diff --check`.
5. Commit only the exact feature files to `main`, push, deploy backend, then publish production OTA.
6. Record G5 evidence; keep G6 pending until true-device validation.
