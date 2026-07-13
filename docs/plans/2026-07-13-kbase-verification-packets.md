# KBase Verification Packets Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add fingerprint-bound machine verification packets that help reviewers adjudicate KBase claims without automatically changing or publishing medical knowledge.

**Architecture:** Extend the persistent review workspace with an append-only verification packet ledger. Deterministic checks run first; an injected model adapter may add a strict structured recommendation, but blockers always win. Packet application delegates to the existing atomic claim-adjudication service so all current review and serving gates remain authoritative.

**Tech Stack:** FastAPI, Pydantic, JSONL workspace artifacts, SQLAlchemy/KBAudit, pytest, Next.js 14, React Query, TypeScript, Vitest.

---

### Task 1: Verification packet domain service

**Files:**
- Create: `backend/app/services/kbase_claim_verification.py`
- Modify: `backend/app/services/kbase_review_workspace.py`
- Test: `backend/tests/test_kbase_claim_verification.py`

**Step 1:** Write failing tests for source completeness, missing external evidence, stale evidence, duplicate and contradiction blockers, and deterministic decision proposals.

**Step 2:** Run `DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai PYTHONPATH=backend backend/venv/bin/pytest backend/tests/test_kbase_claim_verification.py -v --no-cov` and confirm failures are caused by the missing service.

**Step 3:** Implement immutable packet models, claim-content hashing, deterministic checks, and fail-closed proposal precedence.

**Step 4:** Add failing workspace tests for exact fingerprint checks, atomic packet persistence, stale packet reads, and zero claim mutation.

**Step 5:** Implement `generate_review_verification_packet()` and bounded packet reads under `review_workspace_lock`, using sibling-candidate replacement and `verification_packets.jsonl`.

**Step 6:** Re-run the focused tests and commit `feat(kbase): add claim verification packets`.

### Task 2: Strict model recommendation adapter

**Files:**
- Modify: `backend/app/services/kbase_claim_verification.py`
- Test: `backend/tests/test_kbase_claim_verification.py`

**Step 1:** Write failing tests for valid strict JSON, invalid enum, missing citations, unsupported citations, low confidence, timeout/error fallback, and deterministic blocker override.

**Step 2:** Verify RED with the focused pytest command.

**Step 3:** Add an injected async/sync adapter boundary that receives bounded claim/source metadata and validates the returned contract. Do not call the production LLM factory from the domain service.

**Step 4:** Verify GREEN and commit `feat(kbase): validate model verification proposals`.

### Task 3: Admin API and audit

**Files:**
- Modify: `backend/app/api/system_knowledge.py`
- Modify: `backend/app/services/system_knowledge_service.py`
- Test: `backend/tests/test_system_knowledge_phase0.py`

**Step 1:** Write failing authenticated tests for packet generation, packet reads, stale 409 responses, redacted KBAudit rows, and applying an eligible packet through existing adjudication.

**Step 2:** Verify RED with `backend/venv/bin/pytest backend/tests/test_system_knowledge_phase0.py -k verification_packet -v --no-cov`.

**Step 3:** Add strict request/response models and endpoints under `/api/v1/admin/knowledge/dedao_kbase/draft_review/items/{doc_id}/verification`. Reject blocked or stale packet application and preserve the existing adjudication actor/fingerprint contract.

**Step 4:** Verify GREEN and commit `feat(kbase): expose verification packet review API`.

### Task 4: Generated API contracts

**Files:**
- Modify: `frontend/openapi.json`
- Modify: `frontend/src/types/api.generated.ts`
- Modify: `mobile/types/api.generated.ts`

**Step 1:** Run `cd frontend && npm run generate-types` and the repository Mobile type-generation command used by CI.

**Step 2:** Confirm all verification paths and schemas appear in both generated clients and `git diff --check` passes.

**Step 3:** Commit `chore(api): sync verification packet contracts`.

### Task 5: Admin verification UI

**Files:**
- Modify: `frontend/src/app/admin/knowledge/DedaoReleaseReviewPanel.tsx`
- Modify: `frontend/src/app/admin/knowledge/dedaoReleaseReview.ts`
- Modify: `frontend/src/app/admin/knowledge/__tests__/dedaoReleaseReview.test.ts`
- Modify: `frontend/src/app/admin/knowledge/__tests__/DedaoReleaseReviewPanel.test.tsx`

**Step 1:** Write failing helper and component tests for generation, checks, citations, blocked/stale presentation, eligible apply payloads, and no automatic approve/publish controls.

**Step 2:** Verify RED with the two focused Vitest files.

**Step 3:** Implement the compact verification section using existing console tokens and React Query invalidation. Keep stable dimensions and visible mutation errors.

**Step 4:** Run focused tests and `cd frontend && npm run build`; commit `feat(admin): add claim verification packets`.

### Task 6: Gates, review, release, and shadow verification

**Files:**
- Modify: `docs/dossiers/2026-07-13-kbase-verification-packets.md`
- Modify if required: `docs/_generated/system-map.json`

**Step 1:** Run focused backend and frontend suites, then the Next.js production build.

**Step 2:** Run `PATH="$PWD/backend/venv/bin:$PATH" pre-commit run --all-files` and `git diff --check`. Regenerate the system map only if drift checks require it.

**Step 3:** Request independent review and resolve every Critical, High, and Medium finding with regression tests.

**Step 4:** Update the Dossier, create a PR, wait for all CI gates, merge, and deploy through the standard full deployment path.

**Step 5:** In production, generate at most one non-applying shadow packet for an unresolved claim, verify audit redaction and `serving_allowed=false`, and do not adjudicate, finalize, or publish.
