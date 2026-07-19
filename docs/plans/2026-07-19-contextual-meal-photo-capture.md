# Contextual Meal Photo Capture Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Turn qualified Xiaoba chat food photos into owner-scoped, image-backed DietRecords with contextual automatic saving and an in-place confirmation fallback.

**Architecture:** A backend meal-photo policy combines structured vision evidence, semantic visual intent, and resolved user-local time. It writes only through one idempotent diet-record service. `DietPhotoAsset` stores canonical private media and provenance; API readers issue signed URLs for all clients.

**Tech Stack:** FastAPI, SQLAlchemy/PostgreSQL + SQLite managed migrations, Pydantic, existing private upload storage, React Native/Expo, Next.js, SwiftUI.

---

### Task 1: Lock the data and policy contracts with failing tests

**Files:**
- Create: `backend/tests/test_contextual_meal_photo_policy.py`
- Modify: `backend/tests/test_diet.py`
- Modify: `backend/tests/test_agent_executor*.py`

**Step 1:** Add failing tests for local breakfast/lunch/dinner eligibility, out-of-window confirmation, explicit semantic analysis-only, non-food rejection, and timezone resolution.

**Step 2:** Add failing persistence tests that assert a chat-origin asset attaches to a record, exactly one receipt is returned on retry, signed URLs never enter DB state, and a failed write never produces a recorded response.

**Step 3:** Run the focused tests and verify they fail because policy and asset model do not exist.

### Task 2: Add durable multi-photo ownership schema

**Files:**
- Modify: `backend/app/models/daily_health.py`
- Create: `backend/migrations/managed/20260719_*.postgresql.sql`
- Create: `backend/migrations/managed/20260719_*.sqlite.sql`
- Modify: `backend/app/schemas/diet.py`
- Test: `backend/tests/test_diet.py`

**Step 1:** Implement `DietPhotoAsset` using canonical `storage_key`, provenance, sanitized recognition snapshot, lifecycle and stable ordering.

**Step 2:** Implement paired PostgreSQL/SQLite migration. Keep all new references nullable for existing records and retain legacy `DietRecord.image_url` as cover compatibility.

**Step 3:** Implement ordered `photo_assets`/`image_urls` response fields that create signed URLs only when reading.

**Step 4:** Run model/API tests; then generate Web and Mobile OpenAPI types.

### Task 3: Extract a single write-and-receipt service

**Files:**
- Create: `backend/app/services/contextual_meal_photo_service.py`
- Modify: `backend/app/api/diet.py`
- Modify: `backend/app/services/agent_executor.py`
- Test: `backend/tests/test_diet.py`, `backend/tests/test_agent_executor*.py`

**Step 1:** Write failing tests for API, direct photo draft, and Agent chat paths sharing the same owner lock, idempotency key and receipt behavior.

**Step 2:** Add a dedicated contextual chat-photo persistence service for media copying, record/draft creation and source-message idempotency; retain the existing `POST /diet/records` path as the only consumer of a manual draft token, preserving cleanup, rollback and legacy endpoint behavior.

**Step 3:** Add chat-image-to-diet-asset copying from the current raw upload, never by accepting arbitrary URLs.

**Step 4:** Run focused tests until green.

### Task 4: Add semantic visual intent and local meal policy

**Files:**
- Create: `backend/app/services/contextual_meal_photo_policy.py`
- Modify: `backend/app/services/agent_executor.py`
- Modify: `backend/app/services/llm/tool_validator.py` or existing semantic intent boundary as discovery proves appropriate
- Test: `backend/tests/test_contextual_meal_photo_policy.py`

**Step 1:** Write failing tests that call the policy with structured vision candidates and explicit semantic intents. Do not encode decision logic as text regex.

**Step 2:** Resolve IANA timezone through the existing profile utility and derive a local meal context from constants.

**Step 3:** Require all auto conditions: chat-origin user upload, recognized food, high confidence, matching meal window, semantic capture/implicit-empty-image intent, and idempotency/dedup clearance.

**Step 4:** For all other food candidates, create `DietPhotoDraft` and return data for the current chat card. For analyze-only/non-food, do not create a diet draft.

**Step 5:** Run focused tests and prove each boundary path.

### Task 5: Render receipts and images on client surfaces

**Files:**
- Modify: `mobile/services/diet.ts`
- Modify: `mobile/components/chat/cards/DietDraftCard.tsx`
- Modify: `mobile/app/diet.tsx`
- Modify: `frontend/src/types/api.generated.ts` and existing diet list component
- Modify: `apps/mac/...` diet record client/view after locating its endpoint consumer
- Test: focused Mobile Jest, Web test, Mac test

**Step 1:** Write failing client tests for auto receipt with record id, confirmation card with a photo preview, and ordered photo thumbnails in history.

**Step 2:** Render cover thumbnail plus accessible gallery trigger; preserve no-image fallback.

**Step 3:** Use the existing verified write-receipt surface for automatic saves and retain the existing owner-scoped record deletion flow in diet history; do not add a second optimistic undo path before a dedicated restore policy is specified.

**Step 4:** Regenerate types and run TypeScript/Web/Mac checks.

### Task 6: Verification, review and release

**Files:**
- Modify: `docs/dossiers/2026-07-19-contextual-meal-photo-capture.md`
- Modify: `docs/specs/active/2026-07-11-diet-capture-excellence.md`

**Step 1:** Run focused backend, Mobile, Web and Mac tests, then CI-mode backend shards, type drift and doc drift without piping results.

**Step 2:** Request an independent privacy/write-path review of the final commit. Fix any BLOCK findings and rerun tests.

**Step 3:** Deploy backend from clean main, verify migrations and private-media owner isolation, regenerate types, then publish Mobile OTA.

**Step 4:** Verify on a real device with four cases: local lunch auto receipt, low-confidence lunch confirmation, non-food rejection, and history photo rendering/deletion.
