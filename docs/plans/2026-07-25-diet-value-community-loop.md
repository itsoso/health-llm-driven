# Diet Value Receipt And Peer Support Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add trustworthy weight-goal feedback and an opt-in anonymous peer support loop to verified diet records.

**Architecture:** Extend the existing deterministic `post_record_quality` response rather than adding a second diet card. Add a minimal backend community projection whose source is an owned `DietRecord`; Mobile renders the goal block and a dedicated anonymous feed.

**Tech Stack:** FastAPI, SQLAlchemy/PostgreSQL, Pydantic, React Native/Expo, Jest, pytest.

---

### Task 1: Goal progress computation

**Files:**
- Modify: `backend/app/services/post_record_quality.py`
- Test: `backend/tests/test_post_record_quality.py`

1. Add failing tests for goal distance, seven-day change, stale data, missing data,
   achieved target, and unsafe low-BMI target.
2. Run the focused pytest and confirm RED.
3. Add deterministic owner-scoped weight/program/profile lookup.
4. Add `goal_progress` to the existing diet card payload.
5. Run focused tests and confirm GREEN.

### Task 2: Anonymous peer support backend

**Files:**
- Create: `backend/app/models/community.py`
- Create: `backend/app/schemas/community.py`
- Create: `backend/app/api/community.py`
- Create:
  - `backend/migrations/managed/20260725_120000_community_peer_support.postgresql.sql`
  - `backend/migrations/managed/20260725_120000_community_peer_support.sqlite.sql`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/api/main.py`
- Test: `backend/tests/test_community_api.py`

1. Write API tests for owner-only projection, idempotent post creation, privacy
   allowlist, one reaction per user, delete and report.
2. Run the tests and confirm RED.
3. Add models, migration, schemas and endpoints.
4. Run tests and confirm GREEN.
5. Regenerate API types after the contract is stable.

### Task 3: Mobile value receipt

**Files:**
- Modify: `mobile/components/chat/cards/RecordQualityCard.tsx`
- Test: `mobile/components/chat/cards/__tests__/RecordQualityCard.test.tsx`

1. Add failing tests for active, stale, achieved and hidden goal states.
2. Run Jest and confirm RED.
3. Add a compact goal progress block with accessible labels.
4. Run Jest and confirm GREEN.

### Task 4: Mobile peer feed

**Files:**
- Create: `mobile/services/community.ts`
- Create: `mobile/app/community.tsx`
- Modify: `mobile/components/chat/cards/RecordQualityCard.tsx`
- Test: `mobile/services/__tests__/community.test.ts`
- Test: `mobile/app/__tests__/community.test.tsx`

1. Add failing service and screen tests.
2. Implement typed API calls and anonymous feed.
3. Add explicit publish confirmation from a verified record.
4. Add support reactions, owner delete, report and failure retry.
5. Run focused tests and confirm GREEN.

### Task 5: Gates and release

1. Run backend focused tests plus migration checks.
2. Generate API types and run Mobile TypeScript/Jest.
3. Run privacy/safety review against the committed diff.
4. Run doc drift and dossier consistency checks.
5. Commit and push exact files to `main`.
6. Deploy backend first, then ship Mobile JS through production OTA.
7. Record production and true-device verification in the Dossier.
