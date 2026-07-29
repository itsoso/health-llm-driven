# Mobile Health Evidence Owner Release Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Release the source-verified low-back authority pack under an explicit product-owner approval contract without claiming independent clinical review.

**Architecture:** Keep the existing reviewed-only authority, deterministic verifier, delivery sanitizer, and global kill-switch. Change the low-back pack from a hardcoded serving hold to an owner-ratified release recorded in the seed review manifest, then re-run the full safety and cross-client gates before deployment.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy/PostgreSQL, pytest, JSONL System KB seeds, React Native/Expo, Jest, TypeScript.

---

### Task 1: Define the release contract with failing tests

**Files:**
- Modify: `backend/tests/test_system_knowledge_phase0.py`
- Modify: `backend/tests/test_health_evidence_low_back_eval.py`
- Test: `backend/tests/test_system_knowledge_phase0.py`
- Test: `backend/tests/test_health_evidence_low_back_eval.py`

**Step 1: Replace the unsigned-pack assertions**

Add tests asserting that:

- `review_manifest.json` names the five low-back claim IDs.
- `decision` is `approved_for_serving_by_product_owner`.
- `reviewer_role` is `product_owner`.
- `clinical_signoff` is `not_claimed`.
- `serving_allowed` is `true`.
- every released claim is reviewed, T1, within its review window, and backed by
  an official NICE, NHS, ACR, or WHO URL.
- no claim contains a `dedao:` source or paid-course body.

**Step 2: Add serving-path assertions**

Replace the tests that expect 404/exclusion with tests asserting that an
owner-ratified reviewed claim is returned by claim detail and generic search.
Keep separate tests proving draft claims remain excluded.

**Step 3: Run tests and verify RED**

Run:

```bash
cd backend
../venv/bin/pytest tests/test_system_knowledge_phase0.py tests/test_health_evidence_low_back_eval.py -q
```

Expected: failures caused by the existing static hold and pending manifest
decision.

### Task 2: Release the pack truthfully

**Files:**
- Modify: `backend/app/services/clinical_claim_release.py`
- Modify: `backend/data/system_kb_v2_seed/review_manifest.json`
- Modify: `backend/data/system_kb_v2_seed/claims.jsonl`
- Modify: `backend/data/system_kb_v2_seed/entities.jsonl`
- Modify: `backend/data/system_kb_v2_seed/eval_cases.jsonl`

**Step 1: Remove only the low-back IDs from the emergency hold**

Keep `CLINICAL_RELEASE_HOLD_DOCUMENT_IDS` and
`is_clinical_claim_serving_allowed()` as the global kill-switch, but leave the
low-back pack out of the hold set.

**Step 2: Record the actual approval basis**

Update the authority-pack record to:

```json
{
  "decision": "approved_for_serving_by_product_owner",
  "reviewer": "product-owner-2026-07-29",
  "reviewer_role": "product_owner",
  "clinical_signoff": "not_claimed",
  "serving_allowed": true,
  "source_policy": "T1 official guidance only; no raw Dedao or paid-course text"
}
```

Update pack document metadata so `reviewed_by` reflects source/boundary review
and `owner_ratification` reflects the separate product release decision. Do not
write `clinician`, `clinical_review`, or an invented credential.

**Step 3: Run focused tests and verify GREEN**

Run:

```bash
cd backend
../venv/bin/pytest tests/test_system_knowledge_phase0.py tests/test_health_evidence_low_back_eval.py -q
```

Expected: all tests pass.

### Task 3: Remove obsolete hold-specific test bypasses

**Files:**
- Modify: `backend/tests/test_health_authority_router.py`
- Modify: `backend/tests/test_health_evidence_runtime.py`
- Modify: `backend/tests/test_agent_executor_health_evidence_runtime.py`
- Modify: `backend/tests/test_health_evidence_low_back_eval.py`

**Step 1: Delete release-hold monkeypatches**

The released low-back pack must exercise the real serving path. Remove fixtures
that replace `is_clinical_claim_serving_allowed` or clear the static hold.

**Step 2: Preserve fail-closed tests**

Keep or add tests for draft evidence, wrong population/use case, stale review,
non-T1 sources, malformed metadata, model bypass attempts, and replay sanitation.

**Step 3: Run the health-evidence suite**

Run:

```bash
cd backend
../venv/bin/pytest \
  tests/test_health_authority_router.py \
  tests/test_health_evidence_runtime.py \
  tests/test_agent_executor_health_evidence_runtime.py \
  tests/test_health_evidence_low_back_eval.py -q
```

Expected: all tests pass without release-gate monkeypatches.

### Task 4: Update governance records

**Files:**
- Modify: `docs/prd/2026-07-29-mobile-health-evidence-runtime.md`
- Modify: `docs/specs/active/2026-07-29-mobile-health-evidence-runtime.md`
- Modify: `docs/plans/2026-07-29-mobile-health-evidence-runtime.md`
- Modify: `docs/dossiers/2026-07-29-mobile-health-evidence-runtime.md`
- Modify: `docs/ARCHITECTURE.md`
- Regenerate: `docs/_generated/system-map.json`

**Step 1: Record the changed product decision**

State that owner ratification plus T1 source verification is the selected release
basis. Explicitly state that no independent clinical signoff is claimed.

**Step 2: Re-run the system-map generator**

Use the repository generator documented by `docs/system-map/INDEX.md`; never
hand-edit architecture counts.

**Step 3: Run documentation gates**

Run:

```bash
cd backend
../venv/bin/python ../scripts/check_doc_drift.py
../venv/bin/python ../scripts/check_dossier_consistency.py
```

Expected: both commands exit 0.

### Task 5: Full G3 and G4 verification

**Files:**
- Verify only.

**Step 1: Run the exact backend suite**

Run the Dossier-listed CI-mode suite without piping to `tail`.

**Step 2: Run PostgreSQL integration tests**

Run the related broad suite against PostgreSQL and confirm no SQLite fallback.

**Step 3: Run Mobile verification**

Run the exact Jest suites, `npx tsc --noEmit`, and targeted ESLint.

**Step 4: Run static/integrity gates**

Run Ruff, seed integrity, Dossier consistency, doc drift, and
`git diff --check`.

**Step 5: Independent review**

Obtain a fresh spec review and code/safety review. Record the exact evidence and
G4 decision in the Dossier. Any test or safety BLOCK returns to implementation.

### Task 6: Commit, push, deploy, and verify

**Files:**
- Modify only the Dossier with release evidence after each gate.

**Step 1: Commit and push the feature branch**

Stage only files owned by this feature. Push with an explicit refspec because
the repository has a custom `remote.origin.push` mapping.

**Step 2: Integrate into a clean current `main`**

Do not use the existing dirty/stale main checkout. Update from remote in a clean
worktree, integrate the reviewed commit, and verify the exact deployed SHA.

**Step 3: Deploy Backend**

Run:

```bash
./deploy.sh -b
```

Require deploy health score at or above the project threshold and verify the
runtime flag/config.

**Step 4: Publish Mobile OTA**

Because the Mobile diff is JS/TS only, run:

```bash
./scripts/mobile-ota.sh production "release source-verified health evidence runtime"
```

Do not create a TestFlight build unless runtime compatibility or a native diff is
discovered.

**Step 5: G6 production verification**

Verify backend health, a safe ordinary low-back path, emergency escalation,
history/replay, continuation, Mobile card rendering, and a Mac/Mobile output
comparison. Record rollback SHA and OTA update ID in the Dossier.
