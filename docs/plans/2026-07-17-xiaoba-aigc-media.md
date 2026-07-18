# XiaoBa AIGC Media Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add confirmed, private, asynchronous Model Studio Wan image and short-video generation to Xiaoba chat.

**Architecture:** An encrypted, owner-scoped confirmation ledger sits ahead of
the private media-job ledger. The Agent can only draft an external-media
request; a user card click atomically consumes a one-time confirmation and
starts the Wan call. Clients render confirmation then job cards from the same
backend source of truth.

**Tech Stack:** FastAPI, SQLAlchemy/PostgreSQL, paired managed migrations, httpx, DashScope Model Studio HTTP APIs, React Native/Expo, Jest, pytest.

---

### Task 1: Configuration And Provider Contract

**Files:**
- Modify: `backend/app/config.py`
- Create: `backend/app/services/aigc_media_service.py`
- Test: `backend/tests/test_aigc_media_service.py`

1. Write tests for missing credential, Token Plan endpoint rejection, regional
   endpoint normalization, image request construction, and video task creation.
2. Implement typed settings that require `DASHSCOPE_AIGC_API_KEY` and validate
   a Model Studio (not Token Plan) endpoint.
3. Implement an httpx adapter with bounded timeouts. Keep image calls sync and
   video calls async. Never log prompts, source bytes, or Authorization values.
4. Run `pytest backend/tests/test_aigc_media_service.py -q --no-cov`.

### Task 2: Private Media Job Ledger And API

**Files:**
- Create: `backend/app/models/aigc_media_job.py`
- Create: paired `backend/migrations/managed/*aigc_media_jobs.{postgresql,sqlite}.sql`
- Create: `backend/app/api/aigc_media.py`
- Modify: `backend/app/api/main.py`, `backend/app/models/__init__.py`
- Test: `backend/tests/test_aigc_media_api.py`, `backend/tests/test_managed_migrations.py`

1. Write owner-isolation, state-transition, cancellation, and unavailable
   provider tests.
2. Create durable confirmation and job tables and owner-scoped read/cancel API
   endpoints. Keep draft creation inside the Agent dispatcher; the only client
   write must consume a server-issued opaque confirmation ID.
3. Use compare-and-set terminal transitions; transient polling errors stay
   retryable, and result downloads stream with a bounded byte cap.
4. Run API and migration tests under `DATABASE_URL=sqlite:///:memory:`.

### Task 3: Agent Tool And Dynamic Card

**Files:**
- Modify: `backend/app/services/tool_schema_registry.py`
- Modify: `backend/app/services/llm/tool_validator.py`
- Modify: `backend/app/services/agent_kernel/capability_policy.py`
- Modify: `backend/app/services/agent_executor.py`
- Modify: `backend/app/services/atomic_capability_registry.py`
- Test: `backend/tests/test_aigc_media_agent.py`, `backend/tests/test_agent_kernel_capability_policy.py`

1. Write tests proving that read/ambiguous turns cannot create a draft, no
   provider call occurs before card confirmation, and a confirmation is single-use.
2. Register and validate `draft_aigc_media`; include it only for explicit
   media-create intent. Provider consent is exclusively the server-issued card
   confirmation path, never an LLM argument.
3. Emit `aigc_media_confirmation.v1` and `aigc_media_job.v1` descriptors with
   registered manual-confirm action policy metadata.
4. Run targeted Agent Kernel and card tests.

### Task 4: Mobile Dynamic Rendering

**Files:**
- Modify: `mobile/components/chat/cards/types.ts`
- Modify: `mobile/components/chat/cards/registry.tsx`
- Modify: `mobile/services/chatCardActions.ts`
- Create: `mobile/components/chat/cards/AigcMediaJobCard.tsx`
- Test: `mobile/components/chat/cards/__tests__/AigcMediaJobCard.test.tsx`

1. Write pending/success/failure/cancel ownership-safe rendering tests.
2. Render in the existing chat, reuse the existing attachment picker, and poll
   only while the card is visible and job is active.
3. Disable cancellation after a terminal status and never display provider
   internals or raw error text.
4. Run Jest and `npx tsc --noEmit`.

### Task 5: Contract, Security, And Release

**Files:**
- Modify: generated client types after backend schema changes
- Modify: `docs/dossiers/2026-07-17-xiaoba-aigc-media.md`

1. Run backend integration tests, managed migration test, `ruff`, mobile Jest,
   mobile TypeScript, and API type generation.
2. Review external-media disclosure, owner isolation, cancellation race, output
   privacy, and fail-loud behavior.
3. Commit only feature files; push `main`; deploy backend first, verify health
   and owner-scoped production endpoint behavior; then issue a mobile OTA if the
   card changes are JavaScript-only.
