# Mobile Health Evidence Owner Release Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Release the source-verified low-back authority pack only through the controlled health-evidence runtime under an explicit product-owner approval contract, without claiming independent clinical review.

**Architecture:** Keep the low-back pack blocked from generic search, claim detail, and the legacy knowledge tool. Add an exact runtime-only claim allowlist and an internal retrieval path whose results must pass the existing authority artifact check, deterministic verifier, and delivery sanitizer; record the scoped owner approval in the seed review manifest, then re-run the full safety and cross-client gates before deployment.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy/PostgreSQL, pytest, JSONL System KB seeds, React Native/Expo, Jest, TypeScript.

**Execution status (2026-07-29):** Tasks 1–8 are complete with local G3 evidence
and exact-HEAD G4 GO. Task 9 is at clean-main integration; integrated CI, G5,
Mobile OTA, and G6 remain pending.

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
- `decision` is `approved_for_health_evidence_runtime_by_product_owner`.
- `reviewer_role` is `product_owner`.
- `clinical_signoff` is `not_claimed`.
- `serving_allowed` is `true`.
- `serving_scope` is `health_evidence_runtime_only`.
- every released claim is reviewed, T1, within its review window, and backed by
  an official NICE, NHS, ACR, or WHO URL.
- no claim contains a `dedao:` source or paid-course body.

**Step 2: Add scoped serving-path assertions**

Keep tests asserting that claim detail and generic search exclude the entire pack.
Add tests asserting that the internal health-evidence retrieval path returns only
the five owner-ratified reviewed claims. Add a legacy-path regression proving that
feature-flag OFF cannot pass a tampered low-back `summary/body` to the model.
Keep separate tests proving draft claims remain excluded.

**Step 3: Run tests and verify RED**

Run:

```bash
cd backend
../venv/bin/pytest tests/test_system_knowledge_phase0.py tests/test_health_evidence_low_back_eval.py -q
```

Expected: failures caused by the missing runtime-scoped retrieval/allowlist and
pending manifest decision.

### Task 2: Release the pack truthfully to the controlled runtime

**Files:**
- Modify: `backend/app/services/clinical_claim_release.py`
- Modify: `backend/app/services/system_knowledge_service.py`
- Modify: `backend/app/services/system_knowledge_eval.py`
- Modify: `backend/app/services/health_evidence/authority.py`
- Modify: `backend/app/services/health_evidence/runtime.py`
- Modify: `backend/app/services/health_evidence/delivery.py`
- Modify: `backend/data/system_kb_v2_seed/review_manifest.json`

**Step 1: Preserve generic hold and add a runtime allowlist**

Keep all low-back claim, entity, and eval IDs in
`CLINICAL_RELEASE_HOLD_DOCUMENT_IDS`. Add an exact
`HEALTH_EVIDENCE_RUNTIME_RELEASED_CLAIM_IDS` set containing only the five claim
IDs and a separate runtime-scope permission check.

Add an internal retrieval function that:

- is not reachable from public knowledge APIs or the legacy knowledge tool;
- queries only reviewed `claim` documents in the runtime allowlist;
- preserves the stored artifact fields required by the authority hash check;
- returns no entity, eval, draft, or arbitrary caller-selected IDs.

Route health-evidence runtime retrieval through this function and then through
the authority router. Do not add an `include_held=True` parameter to the generic
search API.

The internal low-back golden-eval runner may use the same runtime-scoped claim
retrieval so the four held eval artifacts can test the released claims. Other
evals continue using the normal public search behavior; the runtime exception
must not become a generic `include_held` switch.

Add a test binding the runtime allowlist exactly to the manifest claim list and
approval scope. The manifest is an audit record; application authorization must
remain explicit in code.

**Step 2: Record the actual approval basis**

Update the authority-pack record to:

```json
{
  "decision": "approved_for_health_evidence_runtime_by_product_owner",
  "reviewer": "product-owner-2026-07-29",
  "reviewer_role": "product_owner",
  "clinical_signoff": "not_claimed",
  "serving_allowed": true,
  "serving_scope": "health_evidence_runtime_only",
  "source_policy": "T1 official guidance only; no raw Dedao or paid-course text"
}
```

Do not rewrite claim, entity, or eval metadata. The existing authority artifact
hash binds claim metadata; owner approval belongs in the release manifest rather
than changing the reviewed clinical artifacts. Do not write `clinician`,
`clinical_review`, or an invented credential.

**Step 3: Run focused tests and verify GREEN**

Run:

```bash
cd backend
../venv/bin/pytest tests/test_system_knowledge_phase0.py tests/test_health_evidence_low_back_eval.py -q
```

Expected: all tests pass.

### Task 3: Remove obsolete runtime test bypasses

**Files:**
- Modify: `backend/tests/test_health_authority_router.py`
- Modify: `backend/tests/test_health_evidence_runtime.py`
- Modify: `backend/tests/test_agent_executor_health_evidence_runtime.py`
- Modify: `backend/tests/test_health_evidence_low_back_eval.py`

**Step 1: Exercise the real scoped release path**

The released low-back pack must exercise the real runtime-only serving path.
Remove fixtures that replace runtime permission checks or clear the static hold.
Generic-serving tests must continue to use the real hold and expect exclusion.

**Step 2: Preserve fail-closed tests**

Keep or add tests for draft evidence, wrong population/use case, stale review,
non-T1 sources, malformed metadata, artifact tampering, feature-flag OFF legacy
leakage, model bypass attempts, and replay sanitation.

Add history and durable-replay tests proving:

- removing/re-holding a previously used claim sanitizes the persisted answer;
- persisted health-evidence metadata is still checked when new synthesis is
  feature-flagged off;
- artifact/version mismatch sanitizes rather than replaying stale text.
- a held trusted doc ID containing a unique malicious sentinel cannot reach
  generic search or the legacy knowledge-tool prompt when the feature flag is
  off.

The feature flag controls creation of new health-evidence answers. It must not
disable revocation checks for answers that already carry health-evidence metadata.

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

### Task 4: Seal scope, eval, and delivery-envelope integrity

**Files:**
- Modify: `backend/app/services/clinical_claim_release.py`
- Modify: `backend/app/services/health_evidence/authority.py`
- Modify: `backend/app/services/health_evidence/delivery.py`
- Modify: `backend/app/services/health_evidence/runtime.py`
- Modify: `backend/app/services/system_knowledge_eval.py`
- Modify: `backend/tests/test_health_evidence_low_back_eval.py`
- Modify: `backend/tests/test_agent_health_delivery_gate.py`
- Modify: `backend/tests/test_system_knowledge_phase0.py`
- Modify: `backend/data/system_kb_v2_seed/review_manifest.json`

**Step 1: Write exploit regressions**

Add failing tests proving:

- runtime scope is an exact allowlist even when a claim is also removed from the
  generic hold;
- an empty runtime allowlist returns no candidate;
- a same-ID tampered claim cannot make a golden eval pass;
- an arbitrary eval cannot obtain privileged retrieval by spoofing
  `metadata.case_id`;
- sufficient pass/repair envelopes reject empty, duplicate, extra, or mismatched
  evidence references;
- a valid text SHA cannot preserve forged card, source, or risk metadata.

**Step 2: Implement strict contracts**

Branch permission checks by scope before generic hold logic. Select privileged
eval behavior by immutable eval document ID, require sealed eval identity
consistency, and count only claims matching current artifact policy. Bind the
canonical manifest digest into verification and reconstruct the single
health-evidence card and sources from verified manifest fields rather than
caller-supplied metadata.

**Step 3: Verify RED→GREEN**

Run focused PostgreSQL runtime/eval/delivery tests, Ruff, and seed integrity.

### Task 5: Apply revocation policy to every read surface

**Files:**
- Modify: `backend/app/services/starter_pregen_producer.py`
- Modify: `backend/app/services/starter_pregen.py`
- Modify: `backend/app/services/agent_conversation_service.py`
- Modify: `backend/app/services/history_compaction.py`
- Modify: `backend/app/api/desktop.py`
- Modify: `backend/app/api/shared_conversation.py`
- Modify: `mobile/hooks/useChatEngine.ts`
- Modify: `mobile/utils/share.ts`
- Modify: `mobile/app/(tabs)/chat.tsx`
- Modify: `frontend/src/services/api/ai.ts`
- Modify: `frontend/src/app/ai-assistant/page.tsx`
- Modify: relevant focused tests for each surface

**Step 1: Write cross-surface leak regressions**

Persist a previously valid health answer, revoke its claim, and prove that it
cannot emerge from:

- starter pre-generation cache or duplicate replay;
- model conversation history or compacted history;
- Desktop conversation trace;
- public conversation share creation or later share reads;
- Mobile/Web selected-message sharing, which previously flattened assistant
  answers into `/shared/create-text` and discarded their revocation proof.

Cover feature-flag OFF, tampered artifact, and revoke-after-share cases.

**Step 2: Centralize paired conversation projection**

Use one paired user→assistant projection that calls the health delivery sanitizer
for all read surfaces. Do not cache health-evidence pre-generation without the
full verification envelope; the preferred minimal behavior is to reject those
answers from pregen and bump its Redis namespace. Bind compaction caches to the
release-policy version or exclude health answers so revocation invalidates them.

Selected assistant sharing is server-owned. Clients submit only the authenticated
conversation ID and durable message IDs; the server resolves the paired user query,
reads the verification envelope from persisted messages, projects under the
current release policy, and stores only the minimum private proof needed for later
revalidation. Client-supplied answer text, manifest, verification, or evidence
metadata is never accepted. `/shared/create-text` remains available only for
genuinely user-authored arbitrary text.

**Step 3: Verify all clients**

Run focused API/service tests for Mobile history, Mac trace, Siri/WeChat/Telegram
facade replay, GenUI, share, pregen, and model-context construction. Also prove
that Mobile/Web selected assistant shares use durable IDs, reject ephemeral or
foreign IDs, preserve the selected excerpt, and sanitize after claim revocation.

### Task 6: Correct source-bound claim artifacts

**Files:**
- Modify: `backend/tests/test_health_evidence_low_back_eval.py`
- Modify: `backend/tests/test_health_authority_router.py`
- Modify: `backend/tests/test_symptoms_redlines.py`
- Modify: `backend/data/system_kb_v2_seed/claims.jsonl`
- Modify: `backend/data/system_kb_v2_seed/entities.jsonl`
- Modify: `backend/data/system_kb_v2_seed/eval_cases.jsonl`
- Modify: `backend/data/system_kb_v2_seed/manifest.json`
- Modify: `backend/app/services/health_evidence/authority.py`

**Step 1: Write failing provenance and boundary tests**

Add tests proving:

- the emergency claim says that any one listed neurologic warning triggers the
  escalation boundary;
- the serious-cause claim has exact official locators covering its examples;
- the ACR source uses `https://acsearch.acr.org/docs/69483/Narrative/`;
- the WHO source records the official publication/section locator;
- a serious-cause retrieval eval exists;
- unilateral uncomplicated sciatica, a historical stable urinary issue, and
  isolated severe pain do not trigger the cauda-equina emergency rule.

Run the focused tests and confirm they fail for the expected source/writing gaps.

**Step 2: Correct the artifacts atomically**

Make the minimum wording/source changes, add the missing eval, update seed counts,
and recompute the exact `LOW_BACK_CLAIM_POLICY` artifact SHA-256 values. Do not
weaken population, use-case, or no-diagnosis boundaries.

**Step 3: Verify GREEN and seed integrity**

Run:

```bash
cd backend
../venv/bin/pytest \
  tests/test_health_evidence_low_back_eval.py \
  tests/test_health_authority_router.py \
  tests/test_symptoms_redlines.py -q
../venv/bin/python scripts/check_system_kb_seed_integrity.py
```

Expected: all tests and seed integrity pass.

### Task 7: Update governance records

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

### Task 8: Full G3 and G4 verification

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

### Task 9: Commit, push, deploy, and verify

**Files:**
- Modify only the Dossier with release evidence after each gate.

**Step 1: Commit and push the feature branch**

Stage only files owned by this feature. Push with an explicit refspec because
the repository has a custom `remote.origin.push` mapping.

**Step 2: Integrate into a clean current `main`**

Do not use the existing dirty/stale main checkout. Update from remote in a clean
worktree, integrate the reviewed commit, regenerate Mobile and Web OpenAPI types
plus the system map from the merged source, and run integrated verification.
Push only that exact clean result and require its main CI to be green before
deployment. Verify the exact deployed SHA.

**Step 3: Deploy Backend**

Run:

```bash
./deploy.sh -b -y
```

Require deploy health score at or above the project threshold and verify the
runtime flag/config.

**Step 4: Deploy Web**

The selected-message sharing contract changed on the Web client, so publish the
matching frontend:

```bash
./deploy.sh -f -y
```

Verify the public share page uses the server-projected selection title and
messages.

**Step 5: Publish Mobile OTA**

Because the Mobile diff is JS/TS only, run:

```bash
./scripts/mobile-ota.sh production "release source-verified health evidence runtime"
```

Do not create a TestFlight build unless runtime compatibility or a native diff is
discovered.

**Step 6: G6 production verification**

Verify backend health, a safe ordinary low-back path, emergency escalation,
history/replay, continuation, Mobile card rendering, and a Mac/Mobile output
comparison. Record rollback SHA and OTA update ID in the Dossier.
