# Mobile Health Evidence Runtime Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.
>
> Execution status (2026-07-29): Tasks 1–8 are implemented and locally verified
> for the product-owner-approved runtime-only release, cross-surface revocation,
> selected assistant sharing, and corrected source artifacts. Exact-HEAD G4 is GO;
> production deploy and Mobile OTA wait for clean-main integration and green CI.

**Goal:** Make Mobile and Mac consume one authoritative, personalized, verified health-advice runtime, then give Mobile a better low-back-pain clarification experience.

**Architecture:** A turn-scoped `HealthEvidenceRuntime` freezes intent and `HealthTwin`, compiles a private query-specific personal packet, retrieves a reviewed authority bundle, applies a sufficiency gate, and verifies the synthesized answer. The backend emits a privacy-safe manifest and optional card; clients render but never decide clinical policy.

**Tech Stack:** FastAPI, Python dataclasses/Pydantic, SQLAlchemy-backed `HealthTwin`, System KB JSONL/PostgreSQL search, pytest, React Native/Expo, TypeScript, Jest.

---

## Implemented boundary

- This delivery is the low-back golden safety slice plus reusable architecture,
  not all-domain personalization.
- The low-back compiler selects the safety core and query-relevant optional
  evidence; unrelated genetics, labs, and diet are deliberately omitted.
- A strong model runs only on `sufficient` turns. The deterministic verifier
  releases approved claim summaries; clarify/high/emergency/authority-miss paths
  bypass model synthesis.
- Structured continuation is bound to the parent assistant message and preserves
  the current user text on malformed/stale metadata.
- The complete low-back pack remains unavailable to generic knowledge surfaces.
  Exactly five product-owner-ratified claims may be used only by the controlled
  runtime after T1 source, applicability, immutable artifact, verifier, and
  delivery checks. No independent clinical sign-off is claimed.

## Task 1: Pin the reviewed-only knowledge boundary

**Status:** completed

**Files:**

- Modify: `backend/tests/test_knowledge_search_merge.py`
- Modify: `backend/app/services/agent_executor.py`

1. Rewrite the existing tests to require reviewed System KB results only.
2. Add failures proving System KB miss/error cannot fall back to raw Dedao Chroma.
3. Run the focused test and confirm RED against the current implementation.
4. Remove the raw Dedao branch from `_exec_knowledge_search`.
5. Return explicit reviewed-KB miss/error semantics with no silent fallback.
6. Re-run the focused test and confirm GREEN.

## Task 2: Add health evidence contracts and intent envelope

**Status:** completed

**Files:**

- Create: `backend/app/services/health_evidence/__init__.py`
- Create: `backend/app/services/health_evidence/contracts.py`
- Create: `backend/app/services/health_evidence/intent.py`
- Create: `backend/tests/test_health_evidence_runtime.py`

1. Write tests for low-back symptom intent, risk defaults, mandatory discriminator
   IDs, stable public projection, and Mobile/Mac semantic equality.
2. Confirm RED.
3. Implement immutable typed contracts with private and public projections.
4. Implement deterministic intent/domain classification for the first golden slice.
5. Confirm GREEN.

## Task 3: Build the query-specific Personal Context Compiler

**Status:** completed

**Files:**

- Create: `backend/app/services/health_evidence/personal_context.py`
- Create: `backend/tests/test_personal_context_compiler.py`
- Modify only if required: `backend/app/services/health_context_lite_service.py`

1. Write fixtures for symptoms, active problems, medicines, allergies, chronic
   conditions, labs, genetics, wearables, diet, and failed Twin partitions.
2. Test safety-core selection, domain relevance, evidence-or-gap invariant,
   deterministic budgeting, freshness, conflicts, and safe public projection.
3. Confirm RED.
4. Compile from a frozen `HealthTwin`; use existing matrix signals only as
   candidates and never query user tables independently.
5. Render a private prompt section and privacy-safe trace projection.
6. Confirm GREEN with existing Twin/matrix regression tests.

## Task 4: Add Authority Router and low-back official evidence pack

**Status:** five claims approved for runtime-only use; complete pack generically held

**Files:**

- Create: `backend/app/services/health_evidence/authority.py`
- Modify: `backend/data/system_kb_v2_seed/claims.jsonl`
- Modify: `backend/data/system_kb_v2_seed/entities.jsonl`
- Modify: `backend/data/system_kb_v2_seed/relations.jsonl`
- Modify: `backend/data/system_kb_v2_seed/eval_cases.jsonl`
- Modify: `backend/data/system_kb_v2_seed/review_manifest.json`
- Create: `backend/app/services/clinical_claim_release.py`
- Modify manifests using the repository importer/generator; do not hand-edit
  generated architecture counts.
- Create: `backend/tests/test_health_evidence_low_back_eval.py`

1. Add tests that reject missing source, unreviewed, stale, disallowed-license, or
   inapplicable claims.
2. Add low-back red-flag, self-care, medication-boundary, and imaging golden cases.
3. Confirm RED.
4. Implement authority-tier, freshness, license, and applicability gates around
   reviewed System KB results.
5. Add short transformed claims grounded in NICE, WHO, NHS, and ACR metadata;
   generic serving remains disabled, while runtime-only release requires the
   explicit product-owner manifest plus all deterministic gates.
6. Regenerate/import seed artifacts using repository tooling.
7. Confirm GREEN with System KB verification and golden tests.

## Task 5: Wire one turn-scoped evidence runtime into AgentExecutor

**Status:** completed behind `HEALTH_EVIDENCE_RUNTIME_ENABLED=false`

**Files:**

- Create: `backend/app/services/health_evidence/runtime.py`
- Modify: `backend/app/services/agent_executor.py`
- Modify: relevant settings file for `HEALTH_EVIDENCE_RUNTIME_ENABLED`
- Extend: `backend/tests/test_health_evidence_runtime.py`
- Extend: existing AgentExecutor stream/meta tests

1. Test that the same frozen user/query state yields the same clinical manifest for
   `client=mobile` and `client=mac`.
2. Test that enabled health advice receives one, and only one, personal evidence
   section; non-health turns remain unchanged.
3. Test that actual evidence refs replace table-presence source reporting for the
   health-evidence fields.
4. Confirm RED.
5. Build the runtime once per turn after `TurnSnapshot`, inject the private prompt
   envelope, and attach the safe manifest to done/meta.
6. Preserve client-specific presentation instructions after the clinical envelope.
7. Confirm GREEN.

## Task 6: Add evidence sufficiency and final answer verification

**Status:** completed

**Files:**

- Create: `backend/app/services/health_evidence/verifier.py`
- Create: `backend/tests/test_health_answer_verifier.py`
- Modify: `backend/app/services/agent_executor.py`

1. Write tests for red-flag downgrade, diagnostic overclaim, medication self-change,
   unsupported recommendation/citation, paid-text leakage, pass, repair, and block.
2. Confirm RED.
3. Reuse compatible rules from `health_advice_verifier.py`; do not duplicate medical
   policy in prompt prose.
4. Add pre-synthesis `sufficient | clarify | safe_fallback`.
5. Verify the final complete health answer at the single persistence/SSE choke point.
6. On block or verifier failure, emit a deterministic safe response and trace reason.
7. Confirm GREEN with health safety regressions.

## Task 7: Make Mobile visibly better

**Status:** completed in code; not OTA-published

**Files:**

- Create: `mobile/components/chat/cards/HealthEvidenceCard.tsx`
- Create: `mobile/components/chat/cards/__tests__/HealthEvidenceCard.test.tsx`
- Modify: `mobile/components/chat/cards/registry.tsx`
- Modify: `mobile/components/chat/cards/types.ts`
- Modify: `mobile/services/chat.ts`
- Modify: `mobile/hooks/useChatEngine.ts`
- Create or extend: Mobile chat parsing/persistence tests

1. Add tests for safe parsing, old-server compatibility, evidence/limitations
   rendering, red-flag prominence, and follow-up choice behavior.
2. Confirm RED.
3. Parse and persist the optional public manifest.
4. Render evidence used, known limitations, and 2–4 high-information follow-up
   choices without displaying raw private values.
5. Route a choice into the existing chat send/composer path with no client-side
   clinical inference.
6. Confirm GREEN and run the relevant chat regression suite.

## Task 8: Cross-surface golden evaluation and documentation

**Status:** completed; local G3 passed and exact-HEAD G4 is GO

**Files:**

- Extend: `backend/data/system_kb_v2_seed/eval_cases.jsonl`
- Create: a focused parity test under `backend/tests/`
- Modify: `docs/ARCHITECTURE.md` if structural contracts changed
- Regenerate: `docs/_generated/system-map.json`
- Update: `docs/dossiers/2026-07-29-mobile-health-evidence-runtime.md`

1. Cover no-red-flag acute pain, cauda-equina pattern, trauma/fever, chronic pain,
   medication contraindication gap, personal wearable irrelevance, and incomplete
   context.
2. Assert clinical manifest parity across Mobile/Mac and correct sufficiency state.
3. Run focused backend/Mobile tests, integration Gate, doc drift, and diff checks.
4. Obtain independent code and safety/privacy reviews; fix every blocker and rerun.
5. Record exact evidence in G3/G4.

## Task 9: Deploy, verify, and close the loop

**Status:** clean-main integration in progress. Local G3 and exact-HEAD G4 are
green; integrated-main CI, G5, and G6 remain pending. Generic serving hold stays
in place and is not a deployment blocker for the separate runtime-only allowlist.

**Files:**

- Update: `docs/dossiers/2026-07-29-mobile-health-evidence-runtime.md`

1. Read and follow `backend-deploy` and `mobile-ota` project skills.
2. Integrate into the latest clean `main`, regenerate Mobile/Web OpenAPI types and
   the system map from that merged source, then pass integrated tests and main CI.
3. Confirm the exact clean deploy source and rollback point.
4. Deploy backend first with the canonical base flag false; pass exact revision,
   generic-hold, staged runtime-only KB, service/route/log and health-score checks.
5. Deploy the matching Web client at the same SHA, then exercise the real Linux
   systemd/cgroup deadman, durable commit/revoke, crash-prefix and lost-SSH paths.
6. Use the dedicated health-evidence activation transaction and require
   health/auth/score/semantic contract plus every writer PID `flag=true`; publish
   Mobile OTA only after this backend/Web state is proven.
7. Validate a real authenticated Mobile and Mac low-back turn against the same user
   snapshot; compare public manifest semantics and verify Mobile follow-up behavior.
8. Record G5/G6 honestly; rollback on any failed Gate and require the rollback
   terminal proof to show every writer PID `flag=false`.
9. Commit and push only this feature’s files.
