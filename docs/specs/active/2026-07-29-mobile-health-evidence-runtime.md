# Feature Spec: Mobile Health Evidence Runtime

> Status: local G3/G4 passed; integrated-main CI and production deployment pending
>
> **Current release override (2026-08-12):** production deployment/activation and all OTA channels
> are frozen. Historical rollout steps below are future invariants only; do not execute them. Manual
> Gate is BLOCK, G5/G6 are BLOCK, and local/CI evidence does not make this shipped.
> Owner: Codex + product owner
> Updated: 2026-07-29
> Related PRD/PDD: `docs/prd/2026-07-29-mobile-health-evidence-runtime.md`
> Related code: `backend/app/services/agent_executor.py`, `backend/app/services/system_knowledge_service.py`, `mobile/components/chat/cards/`

## 1. Decision

Build one backend-owned health evidence runtime for every chat surface. It compiles
query-specific personal context from `HealthTwin`, routes medical claims only to
reviewed authoritative knowledge, verifies the final answer, and gives Mobile a
structured symptom-intake and evidence UI. No medical fine-tuning is required for
this slice.

## 2. Problem

The same health question can currently feel materially weaker on Mobile even though
Mobile and Mac call the same agent endpoint:

- client-specific prompt/model affordances can change the surrounding execution;
- the agent receives large, generic personal-context blobs rather than the smallest
  decision-relevant evidence packet;
- `knowledge_search` can fall back from reviewed System KB results to raw
  Dedao-derived Chroma snippets;
- `sources_used` reports available tables and prompt labels rather than the evidence
  actually selected and cited in the answer;
- free-form health answers do not pass through one final deterministic medical
  verification choke point;
- Mobile lacks a low-friction way to answer the highest-value red-flag questions.

If unchanged, a strong model can still synthesize from incomplete, irrelevant, or
insufficiently authoritative context. Improving only the Mobile prompt would create
another divergent clinical path.

## 3. Requirement Admission

```yaml
RequirementAdmission:
  request: "让 Mobile 健康问答赶上乃至超越 Mac；强模型结合个人上下文与权威知识库，不先做医疗微调。"
  classification: cross_surface_health_advice_runtime
  first_user_fit: "需要把基因、可穿戴、检查/体检、饮食、用药和症状用于个性化健康决策的用户"
  core_loop_step: "Data/Twin -> Safety Gate -> Action"
  first_class_objects:
    - HealthProblem
    - HealthTwin
    - SafetyGuardian
    - LeverageAction
  target_surface:
    - Backend
    - Mobile
    - Mac
  source_of_truth: Backend
  safety_level: medical_boundary_and_privacy_sensitive
  prescription_or_causal_verdict: no
  autonomy_tier: suggest
  evidence_provenance: required_for_medical_claims
  claim_hedging: required
  verification_window: "same turn plus golden evaluation before release"
  success_metric: "same query and same user snapshot produce the same clinical evidence manifest on Mobile and Mac"
  added_user_burden: "only high-information symptom follow-up chips when a mandatory discriminator is missing"
  burden_justification: "prevents unsafe generic advice and avoids long questionnaires"
  non_goals:
    - medical model fine-tuning
    - autonomous diagnosis or prescribing
    - exposing paid Dedao text at runtime
    - migrating every health domain in the first slice
  smallest_end_to_end_slice: "low-back-pain triage + personal-context compilation + reviewed-source bundle + answer verification + Mobile follow-up card"
  stale_surface_to_remove_or_archive: "raw Dedao fallback inside the common knowledge_search runtime path"
  spec_required: yes
```

## 4. Non-Goals

- No diagnosis, treatment plan, medication start/stop/change, or causal claim.
- No full replacement of all legacy context renderers outside health-advice turns.
- No direct runtime retrieval from paid Dedao PDFs, Markdown, or Chroma.
- No training or fine-tuning on user health data.
- No database migration in the first vertical slice.
- No new Watch or Web interaction surface.
- No attempt to make every medical topic production-complete in this change; the
  low-back-pain bundle establishes the reusable contract and gates.

## 5. Product Object Mapping

| Object | Change |
|---|---|
| `HealthProblem` | Symptom questions become an explicit intent/risk envelope. |
| `HealthTwin` | Becomes the single personal-state snapshot used by the compiler. |
| `SafetyGuardian` | Gains pre-synthesis sufficiency and post-synthesis claim gates. |
| `LeverageAction` | Advice is emitted only with provenance, boundary, and next-step semantics. |

## 6. User Flow

```text
user asks "我腰疼怎么办"
  -> backend freezes one TurnSnapshot and HealthTwin
  -> intent envelope identifies symptom/low-back domain and mandatory discriminators
  -> personal context compiler selects safety core + relevant evidence and explicit gaps
  -> authority router retrieves only reviewed, licensed, fresh, applicable System KB claims
  -> sufficiency gate chooses answer / clarify / urgent-safe fallback
  -> sufficient only: selected strong model proposes approved claim IDs
  -> clarify/safe_fallback: bypass model and render deterministic safety text
  -> deterministic verifier publishes only approved claim summaries or safety text
  -> Mobile/Mac receive the same evidence manifest
  -> Mobile renders high-value follow-up chips and evidence trace
```

## 7. Surface Contract

| Surface | Responsibility | Contract |
|---|---|---|
| Mobile | Primary capture and execution surface | Render evidence/limitations and symptom follow-up affordances; never invent clinical routing locally. |
| Mac | Analysis/workbench renderer | Consume the same backend evidence manifest; desktop formatting may differ, clinical evidence may not. |
| Backend | Clinical source of truth | Compile personal evidence, route authority, enforce sufficiency, verify answer, emit trace. |
| External agents | Optional future consumers | Receive de-identified authority queries only; never receive a raw personal packet. |

## 8. Data Contract

```yaml
apis:
  - "POST /agent/stream: backward-compatible SSE fields plus health_evidence_manifest"
  - "POST /shared/create: optional server-owned durable message selection for agent shares"
events:
  - "done.health_evidence_manifest"
models:
  - HealthIntentEnvelope
  - PersonalEvidenceItem
  - PersonalEvidencePacket
  - AuthorityEvidenceItem
  - HealthEvidenceManifest
  - HealthAnswerVerification
fields:
  - intent
  - risk_level
  - context_categories_used
  - evidence_refs
  - authority_sources
  - missing_discriminators
  - sufficiency
  - verifier_verdict
enums:
  - "risk_level: low | medium | high | emergency"
  - "sufficiency: sufficient | clarify | safe_fallback"
  - "verifier_verdict: pass | repair | block"
backward_compatibility: "new SSE/meta/card fields are optional; older clients ignore them"
migration: none
```

The public manifest contains categories, stable evidence references, source metadata,
and gaps. It must not contain raw genetic values, record IDs, medication details, or
the full personal packet.

## 9. Safety, Privacy, And Medical Boundary

- This feature touches symptoms, medications, allergies, chronic conditions, labs,
  genetics, wearable data, and red-flag paths; all are L3 health data.
- Every lookup and Twin build remains scoped by the authenticated `user_id`.
- The private personal evidence packet exists only for the current backend turn and
  is not logged, persisted into SSE, or sent to external retrieval.
- Mandatory context is represented as either evidence or an explicit gap; failed
  Twin partitions must never be treated as proof that no condition exists.
- Emergency/red-flag evidence always wins over self-care guidance.
- The system must not diagnose, claim certainty, or recommend changing prescription
  medication. Medication suggestions require user-specific contraindication context
  and clinician/pharmacist boundaries.
- Medical claims may use only reviewed System KB material that passes authority,
  freshness, license, and applicability gates.
- The complete low-back pack remains excluded from generic search, claim detail,
  and the legacy knowledge tool. Exactly five reviewed claims may be retrieved by
  the controlled health-evidence runtime after the runtime allowlist, authority
  artifact, applicability, verifier, and delivery checks all pass.
- The release record truthfully names `product_owner` approval based on T1
  official-source and boundary review. It records `clinical_signoff=not_claimed`;
  no independent clinical credential or sign-off is implied.
- The feature flag gates both the AgentExecutor health path and the new low-back
  Guardian rule, so disabled means the candidate behavior is inert on every
  existing SafetyGuardian consumer.
- Persisted answers are revalidated independently of the synthesis flag. Removing
  a claim from the runtime allowlist or changing its immutable artifact digest
  sanitizes history, replay, Desktop trace, model context, and public shares.
- Read-time query classification is a minimum risk floor. A sealed answer may
  retain a higher risk promoted from its frozen Twin/SafetyGuardian context, but
  it may never replay below a risk explicitly present in the paired query.
- Mobile/Web selected assistant sharing submits only authenticated conversation
  and durable message IDs. The server resolves the paired user query and private
  verification proof; `/shared/create-text` is reserved for genuinely
  user-authored arbitrary text.
- Dedao material may support offline topic discovery and explanation drafting only.
  Paid text is never returned, quoted, embedded as runtime authority, or used as the
  sole support for a claim.

## 10. AI Behavior

In this golden slice, the model runs only when sufficiency is `sufficient`. Its
output is untrusted selection/scratch text: referenced approved claim IDs select
which claim summaries are deterministically rendered; if it references none, the
accepted claim set is rendered. Arbitrary model-authored medical or personalized
prose is never released.

`clarify`, `high`, `emergency`, authority-miss, and other `safe_fallback` turns
bypass the model and use deterministic text. The model may therefore help select
approved evidence, but it cannot:

- retrieve or cite raw Dedao content;
- infer missing medical facts from silence;
- expose private source references;
- override deterministic red flags or evidence sufficiency;
- present a differential diagnosis as a diagnosis;
- fabricate citations or say personal data was used when it was merely available.

Before synthesis, a deterministic sufficiency gate decides whether the runtime can
answer or must clarify/fallback. After sufficient-only model selection, the answer
verifier checks red-flag downgrade, diagnostic overclaim, medication self-change,
unsupported references, and evidence consistency, then releases deterministic
grounded summaries. Failure degrades to a deterministic safe response.

Personal context currently changes risk, sufficiency, evidence applicability,
detected red flags, and the questions asked. It does not yet produce free-form
personalized causal explanation. Sentence-level attribution from a personal fact to
an authority claim is future work and requires its own domain pack and evaluation.

## 11. Acceptance Criteria

```gherkin
Given the same user snapshot and "我腰疼怎么办"
When the request declares client=mobile or client=mac
Then the intent, risk, personal evidence refs, authority evidence refs, gaps, and verifier policy are identical

Given reviewed System KB has no acceptable hit
When knowledge_search runs
Then it returns an honest reviewed-KB miss and never returns a raw Dedao snippet

Given a relevant Twin partition failed to build
When personal context is compiled
Then the packet reports a failed partition and does not claim that the data is absent

Given mandatory red-flag discriminators are unknown
When the first low-back-pain response is built
Then it prominently screens urgent red flags and emits a small set of follow-up choices

Given an answer downgrades a detected red flag or recommends self-changing medication
When final verification runs
Then the answer is blocked or replaced with a deterministic safe response

Given sufficiency is clarify or safe_fallback
When the turn is released
Then no model call is required and deterministic policy text is persisted

Given sufficiency is sufficient
When model output contains arbitrary prose
Then only summaries from accepted claim IDs are released

Given a medical claim is shown
When the public manifest is inspected
Then it lists only the authoritative evidence actually selected for this turn

Given Mobile receives the structured card
When it renders the response
Then the user can see evidence/limitations and answer follow-up questions without retyping
```

## 12. Verification Plan

```bash
# Backend focused TDD
cd backend
DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai PYTHONPATH=. \
  /Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin/python \
  -m pytest tests/test_knowledge_search_merge.py \
  tests/test_health_evidence_runtime.py \
  tests/test_personal_context_compiler.py \
  tests/test_health_answer_verifier.py -q

# System KB seed and low-back golden cases
DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai PYTHONPATH=. \
  /Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin/python \
  -m pytest tests/test_system_knowledge_service.py \
  tests/test_kbase_claim_verification.py \
  tests/test_health_evidence_low_back_eval.py -q

# Mobile focused
cd mobile
npm test -- --runInBand \
  components/chat/cards/__tests__/HealthEvidenceCard.test.tsx \
  services/__tests__/chatHealthEvidence.test.ts

# Contract and repository hygiene
python3 scripts/dump_system_map.py
python3 scripts/check_doc_drift.py
python3 backend/scripts/check_dossier_consistency.py
git diff --check
```

Full integration, safety, CI-state, deployment, and production smoke commands are
recorded in the Dossier as their Gates are reached.

## 13. Rollout And Rollback

- `HEALTH_EVIDENCE_RUNTIME_ENABLED` remains false. Backend deploy, environment mutation and
  `--activate-health-evidence` are frozen; their historical proof protocol is test/design input only.
- The low-back entity, claims, relations, and eval candidates are listed in
  `CLINICAL_RELEASE_HOLD_DOCUMENT_IDS`; generic System KB search always excludes
  them. A separate exact allowlist releases only five claims to the controlled
  health-evidence runtime.
- Raw Dedao fallback removal is a safety correction and is not re-enabled by the
  feature flag.
- Do not deploy Backend/Web or call Mobile OTA/rollback. Old-client compatibility and rollback
  sequencing remain future invariants; current production state is unchanged.

## 14. Implemented Slice Boundary

- This is a low-back-pain golden safety slice and reusable cross-client runtime,
  not completion of all medical domains.
- The query-specific low-back compiler always includes symptoms, active problems,
  medicines, allergies, and chronic conditions. It can select relevant wearable
  context, and correctly excludes unrelated genetics, labs, and diet for this
  question. Those categories remain available to future domain-specific compilers.
- Structured Mobile continuation binds the follow-up to the parent assistant
  message and optional turn ID. Malformed or stale continuation metadata preserves
  the current user text and fails safely instead of silently substituting history.
- The low-back pack is not represented as clinician-approved. Five claims have
  product-owner approval for runtime-only use on the stated T1 source and boundary
  review basis; the feature is not described as shipped until production G6 passes.

## 15. Open Questions

Non-blocking after the first slice:

- Which next high-frequency symptom pack follows low-back pain?
- Should evidence details open in a dedicated provenance sheet or an inline card?
- Which metrics are sufficient to graduate from shadow comparison to default-on for
  additional domains?

There are no unresolved questions that change the safety boundary of this slice.

## 16. Changelog

| Date | Change | Reason |
|---|---|---|
| 2026-07-29 | Initial accepted spec | User approved the first-principles architecture and requested implementation. |
| 2026-07-29 | Recorded implemented golden-slice boundary and clinical hold | Keep model, personalization, and release claims aligned with the actual code and G4 status. |
