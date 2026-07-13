# KBase Claim Adjudication Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add fail-closed, claim-level adjudication for the persistent Dedao KBase review workspace without allowing the new admin surface to publish into Health serving.

**Architecture:** Keep workspace mutation in `kbase_review_workspace.py` and the existing System KB service boundary. Every decision copies the locked workspace into a sibling candidate, validates the expected fingerprint, updates artifacts plus an append-only adjudication ledger, validates counts/gates, and atomically replaces the workspace. The admin API exposes bounded item reads, one-claim decisions, finalization, and publish preview; the Next.js console renders those operations in a dense two-pane panel.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy/KBAudit, JSONL artifacts, pytest, Next.js 14, React Query, TypeScript, Vitest, Testing Library.

---

### Task 1: Claim adjudication workspace primitives

**Files:**
- Modify: `backend/app/services/kbase_review_workspace.py`
- Modify: `backend/tests/test_dedao_kbase_release_consumer.py`

**Step 1: Write the failing list test**

Add a fixture with draft claims and assert `list_review_claims()` returns bounded claim summaries, provenance, source count, current decision, and the workspace fingerprint without article-body duplication.

**Step 2: Run the test to verify it fails**

Run: `backend/venv/bin/pytest backend/tests/test_dedao_kbase_release_consumer.py -k list_review_claims -v`

Expected: FAIL because `list_review_claims` does not exist.

**Step 3: Implement the minimum read model**

Add JSON/JSONL helpers and `list_review_claims(artifact_dir, offset, limit, decision)` that reads claims and `adjudications.jsonl` under the existing lock. Include `doc_id`, title/claim text needed for review, evidence level, confidence, provenance, sources, review status, and latest decision. Cap pagination and never return unrelated article bodies.

**Step 4: Write and verify failing mutation tests**

Cover `approve`, `needs_evidence`, `reject`, and `background_only`; exact fingerprint enforcement; structured evidence validation; ledger content; and preservation of the original workspace when candidate validation fails.

Run: `backend/venv/bin/pytest backend/tests/test_dedao_kbase_release_consumer.py -k adjudicat -v`

Expected: FAIL because mutation is not implemented.

**Step 5: Implement atomic one-claim adjudication**

Add a decision enum/validation helper and `adjudicate_review_claim(...)`. Under `review_workspace_lock`, compare the exact fingerprint, copy to a sibling candidate, update the selected claim and connected relations, append one JSONL ledger event, refresh manifest counts/gate metadata, validate the candidate, then replace via the existing backup/recovery protocol. `approve` may append validated external evidence; `needs_evidence` remains draft; `reject` and `background_only` remove the claim and its relations.

**Step 6: Verify green and commit**

Run: `backend/venv/bin/pytest backend/tests/test_dedao_kbase_release_consumer.py -k "list_review_claims or adjudicat" -v`

Expected: PASS.

Commit: `feat(kbase): add atomic claim adjudication`

### Task 2: Fail-closed finalization

**Files:**
- Modify: `backend/app/services/kbase_review_workspace.py`
- Modify: `backend/app/services/system_knowledge_service.py`
- Modify: `backend/tests/test_dedao_kbase_release_consumer.py`

**Step 1: Write failing finalization tests**

Assert that finalization rejects unresolved draft and `needs_evidence` claims without mutation; after all claims are decided, it reviews retained generated entity/page containers, reviews valid relations, removes dangling relations, marks the manifest reviewed, and returns `serving_allowed=true`. Also assert a stale fingerprint fails.

**Step 2: Verify red**

Run: `backend/venv/bin/pytest backend/tests/test_dedao_kbase_release_consumer.py -k finaliz -v`

Expected: FAIL because claim-aware finalization is absent.

**Step 3: Implement minimum finalization**

Add `finalize_review_workspace(...)` with the same lock/candidate/replace transaction. Make `approve_dedao_kbase_draft_review()` delegate to this finalizer instead of `review_draft_artifacts()`, so legacy approval cannot bulk-promote unresolved claims.

**Step 4: Verify green and regressions**

Run: `backend/venv/bin/pytest backend/tests/test_dedao_kbase_release_consumer.py -v`

Expected: PASS.

Commit: `feat(kbase): gate review finalization on claim decisions`

### Task 3: Admin API and audit contract

**Files:**
- Modify: `backend/app/api/system_knowledge.py`
- Modify: `backend/app/services/system_knowledge_service.py`
- Modify: `backend/tests/test_system_knowledge_phase0.py`

**Step 1: Write failing endpoint tests**

Add authenticated tests for:

- `GET /api/v1/admin/knowledge/dedao_kbase/draft_review/items`
- `PATCH /api/v1/admin/knowledge/dedao_kbase/draft_review/items/{doc_id}`
- `POST /api/v1/admin/knowledge/dedao_kbase/draft_review/finalize`
- `POST /api/v1/admin/knowledge/dedao_kbase/reviewed_artifacts/publish/preview`

Assert decision payload validation, stale fingerprint status, no body in audit data, one `dedao_kbase_claim_adjudicated` audit per decision, unresolved finalization failure, and dry-run-only preview. Change the legacy approve test so `publish=true` is rejected and no serving mutation occurs.

**Step 2: Verify red**

Run: `backend/venv/bin/pytest backend/tests/test_system_knowledge_phase0.py -k "dedao_kbase and (items or adjudicat or finalize or publish)" -v`

Expected: FAIL with missing routes/new contract.

**Step 3: Implement request models and endpoints**

Add strict Pydantic models for decision, note, optional evidence, evidence level, confidence, and exact fingerprint. Map stale fingerprints to HTTP 409 and validation/workspace errors to HTTP 400. Record only identifiers, decision metadata, note, and evidence metadata in KBAudit. Remove publish execution from legacy approval; keep the existing separate publish endpoint unchanged but unreferenced by the new UI.

**Step 4: Verify green and commit**

Run: `backend/venv/bin/pytest backend/tests/test_system_knowledge_phase0.py -k dedao_kbase -v`

Expected: PASS.

Commit: `feat(kbase): expose claim review admin API`

### Task 4: Generated API contract

**Files:**
- Modify: `frontend/openapi.json`
- Modify: `frontend/src/types/api.generated.ts`

**Step 1: Generate from the live FastAPI application**

Run: `cd frontend && npm run generate-types`

Expected: OpenAPI and TypeScript types include the four new routes and their request schemas.

**Step 2: Verify deterministic diff and commit**

Run: `git diff --check && rg -n "draft_review/items|draft_review/finalize|publish/preview" frontend/openapi.json frontend/src/types/api.generated.ts`

Expected: all new paths appear and the diff is clean.

Commit: `chore(api): regenerate KBase review contracts`

### Task 5: Release Review admin panel

**Files:**
- Create: `frontend/src/app/admin/knowledge/DedaoReleaseReviewPanel.tsx`
- Create: `frontend/src/app/admin/knowledge/dedaoReleaseReview.ts`
- Create: `frontend/src/app/admin/knowledge/__tests__/dedaoReleaseReview.test.ts`
- Create: `frontend/src/app/admin/knowledge/__tests__/DedaoReleaseReviewPanel.test.tsx`
- Modify: `frontend/src/app/admin/knowledge/page.tsx`

**Step 1: Write failing helper tests**

Test decision labels, safe request payload construction, unresolved/finalizable state, and stale-fingerprint error recognition.

Run: `cd frontend && npm test -- src/app/admin/knowledge/__tests__/dedaoReleaseReview.test.ts`

Expected: FAIL because helpers are absent.

**Step 2: Implement and verify helper logic**

Implement small typed pure functions only. Re-run the focused test and expect PASS.

**Step 3: Write failing component tests**

Render the panel with mocked API/React Query. Assert claim selection, four explicit decision actions, detail/provenance visibility, finalization disabled while unresolved, reload prompt on HTTP 409, publish preview availability after finalization, and no `发布` command.

Run: `cd frontend && npm test -- src/app/admin/knowledge/__tests__/DedaoReleaseReviewPanel.test.tsx`

Expected: FAIL because the panel is absent.

**Step 4: Implement the dense two-pane panel**

Use existing dark console tokens, Lucide icons, stable pane dimensions, keyboard-accessible buttons, visible mutation errors, and React Query invalidation. Integrate near the top of `/admin/knowledge`. Expose finalization and dry-run preview only; do not import or call the production publish endpoint.

**Step 5: Verify frontend and commit**

Run: `cd frontend && npm test -- src/app/admin/knowledge/__tests__/dedaoReleaseReview.test.ts src/app/admin/knowledge/__tests__/DedaoReleaseReviewPanel.test.tsx`

Run: `cd frontend && npm run build`

Expected: focused tests and Next.js build PASS.

Commit: `feat(admin): add KBase claim review workspace`

### Task 6: Full gates, docs, and release evidence

**Files:**
- Modify: `docs/dossiers/2026-07-13-kbase-claim-adjudication.md`
- Modify if generated drift requires it: `docs/_generated/system-map.json`

**Step 1: Run backend regression tests**

Run: `backend/venv/bin/pytest backend/tests/test_dedao_kbase_release_consumer.py backend/tests/test_system_knowledge_phase0.py -v`

Expected: PASS.

**Step 2: Run frontend verification**

Run: `cd frontend && npm test -- src/app/admin/knowledge/__tests__/dedaoReleaseReview.test.ts src/app/admin/knowledge/__tests__/DedaoReleaseReviewPanel.test.tsx`

Run: `cd frontend && npm run build`

Expected: PASS.

**Step 3: Run repository gates**

Run: `PATH=/Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin:$PATH pre-commit run --all-files`

Run: `git diff --check`

If architecture drift is reported, run the project system-map generator and commit only generated output caused by this change. The repository has no privacy script; manually scan changed files for credentials, machine paths, and copyrighted content.

**Step 4: Review and release**

Request independent code review. Resolve every Critical/High/Medium finding, rerun all gates, update the Dossier with exact evidence, then create a PR. After CI and merge, deploy through the standard backend/frontend path and verify authenticated production reads, one non-publishing dry-run path, service health, and workspace persistence. Do not adjudicate current medical claims or publish them as part of deployment verification.
