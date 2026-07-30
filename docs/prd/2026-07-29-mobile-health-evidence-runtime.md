# PRD: Mobile Health Evidence Runtime

> Status: local G3/G4 passed; integrated-main CI and production deployment pending
> Date: 2026-07-29
> Feature Spec: `docs/specs/active/2026-07-29-mobile-health-evidence-runtime.md`
> Dossier: `docs/dossiers/2026-07-29-mobile-health-evidence-runtime.md`

## 1. Outcome

Mobile health advice must be at least clinically equivalent to Mac for the same
question and user state, then exceed Mac where a phone is naturally better: symptom
capture, quick clarification, wearable continuity, report/camera ingestion, and
immediate execution.

Clinical equivalence is defined by a server-owned contract, not by similar wording:
the same intent, risk classification, personal evidence selection, authoritative
evidence selection, missing discriminators, and deterministic verification policy.

## 2. First-Principles Thesis

Answer quality is bounded by:

```text
decision quality
  = model reasoning
  × relevant personal context
  × authoritative evidence
  × safety/sufficiency gates
  × capture-and-feedback quality
```

A stronger model cannot compensate for absent red-flag facts, irrelevant context,
unreviewed evidence, or a client-divergent execution path. Medical fine-tuning is
therefore not the first bottleneck. The first release invests in context selection,
retrieval authority, verification, and feedback.

## 3. User Jobs

1. “Tell me what I should do now without pretending to diagnose me.”
2. “Use the health data that actually matters to this question.”
3. “Show me why the recommendation is trustworthy and what is still unknown.”
4. “Let me answer the critical follow-up questions with minimal friction.”
5. “Give me the same clinical quality whether I start on Mobile or Mac.”

## 4. Requirements

### R1 — One Clinical Runtime

All clients call the same health evidence runtime before final synthesis. Client name,
layout capabilities, and desktop formatting cannot change the clinical evidence
packet.

### R2 — Query-Specific Personal Context

The runtime freezes one `HealthTwin` per turn and compiles:

- safety core: recent symptoms, active problems, current medicines, allergies,
  chronic conditions, and personalized red lines;
- domain evidence: only facts relevant to the current question;
- explicit gaps, conflicts, freshness, reliability, and failed partitions;
- just-in-time read requests where the canonical Twin lacks needed detail.

Full personal data must not be copied into the prompt by default.

For the low-back slice, the mandatory safety core is symptoms, active problems,
medicines, allergies, and chronic conditions. Relevant wearable signals may be
selected, while unrelated genetics, labs, and diet are intentionally excluded.
Broader use of those categories belongs in future query-specific domain packs, not
in a generic always-on prompt.

### R3 — Reviewed Authority Only

Runtime medical evidence comes only from reviewed System KB documents that pass:

- authority tier;
- freshness/review validity;
- license scope;
- question/domain applicability;
- source presence and traceability.

No raw Dedao snippet may appear as runtime evidence or fallback. Dedao integration is
an offline authoring boundary: topic coverage, explanation structure, and transformed
claim drafts must be re-grounded in official evidence and reviewed before publishing.

### R4 — Evidence Sufficiency

The runtime returns one of:

- `sufficient`: answer within the evidence envelope;
- `clarify`: ask only the highest-information missing questions;
- `safe_fallback`: show urgent boundaries and conservative next steps without an
  unsupported personalized claim.

Silence is never interpreted as a negative red flag.

### R5 — Final Verification

Only a `sufficient` turn invokes the configured strong model. The model output is
not publishable prose; it may identify accepted claim IDs, after which the
deterministic verifier renders the corresponding approved summaries. If no IDs are
identified, the accepted set is rendered. `clarify` and `safe_fallback` bypass the
model.

The verifier checks at minimum:

- red-flag downgrade;
- diagnostic/certainty overclaim;
- medication start/stop/change;
- unsupported medical recommendations;
- claim-to-source consistency;
- claimed personal-data use versus selected evidence;
- leakage of paid source content.

Blocked answers are replaced with a deterministic safe response; verification
failure is visible in server trace but does not expose private details. The first
slice intentionally does not release free-form personalized causal explanation.

### R6 — Truthful Trace

The response trace records evidence actually selected and passed into synthesis. It
does not label every populated table as “used”. Public fields expose categories and
safe source metadata, not raw personal values or database IDs.

### R7 — Mobile Advantage

For symptom advice, Mobile renders:

- urgent red flags first;
- a compact evidence/limitations card;
- the smallest set of follow-up chips for missing discriminators;
- a clear next action.

Mobile must not implement separate medical logic.

### R8 — Low-Back-Pain Golden Slice

The first domain pack covers:

- alternative serious causes and urgent neurological red flags;
- conservative activity/self-care boundaries;
- when routine or urgent evaluation is appropriate;
- medication caveats without individualized prescribing;
- imaging boundary;
- acute versus chronic scope.

Official source baseline verified 2026-07-29:

- NICE NG59, published 2016, last updated 2020:
  `https://www.nice.org.uk/guidance/ng59`
- WHO guideline for chronic primary low back pain, 2023:
  `https://www.who.int/publications/i/item/9789240081789`
- NHS Back pain patient guidance, page reviewed 2026-03-05:
  `https://www.nhs.uk/conditions/back-pain/`
- ACR Appropriateness Criteria, Low Back Pain topic:
  `https://acsearch.acr.org/docs/69483/Narrative/`

NICE/WHO support professional management recommendations; NHS supplies plain-language
urgent symptom wording; ACR supports imaging applicability. Each imported claim must
retain exact source/version/applicability metadata.

The documents added by this implementation are not represented as
clinician-approved content. The product owner accepted T1 official-source and
boundary review as the release basis and explicitly confirmed that no independent
clinical sign-off is claimed. The entire pack remains excluded from generic
serving; exactly five claims are eligible only inside the controlled
health-evidence runtime after artifact, applicability, verifier, and delivery
checks pass.

## 5. Success Metrics

Release gates:

- 100% Mobile/Mac semantic parity across the low-back golden corpus.
- 0 raw Dedao runtime results in tests and production trace.
- 100% red-flag golden cases escalate correctly.
- 100% missing mandatory discriminators appear as explicit gaps or questions.
- 0 public manifests contain raw personal health values, user IDs, or record IDs.
- 100% medical claims in golden responses map to an accepted authority source.

Post-release product metrics:

- symptom clarification completion rate;
- evidence-card expansion rate;
- unsafe/unsupported verifier block rate;
- answer repair rate;
- user “helpful and relevant” score by surface;
- time from first question to an actionable, safe next step.

## 6. Scope And Delivery

### P0 — Correctness Floor

- remove raw Dedao runtime fallback;
- add unified intent/evidence manifest contract;
- make source usage truthful;
- add cross-surface parity and low-back golden tests.

### P1 — Personal Context Compiler

- typed evidence/gap/conflict contracts;
- mandatory-context matrix;
- query-specific selection from one `HealthTwin`;
- privacy-safe prompt and public manifest renderers.

### P2 — Authority Router And Domain Pack

- authority/freshness/license/applicability gates;
- official low-back claim/protocol/eval bundle;
- explicit offline-only Dedao policy and build provenance.

### P3 — Synthesis Choke Point

- pre-synthesis sufficiency decision;
- post-synthesis health answer verifier;
- trace and safe fallback.

### P4 — Mobile Experience

- evidence and limitations card;
- symptom follow-up chips;
- Mobile parsing/persistence;
- cross-surface semantic parity evaluation.

## 7. Non-Functional Requirements

- Existing non-health chat and record flows remain backward compatible.
- Context compilation is deterministic for a frozen snapshot and bounded by an
  explicit item/token budget.
- No raw personal packet is logged.
- Knowledge-route failure is observable and fail-honest.
- All new user-visible numbers use the shared display formatting rule.
- Server modules remain small and independently testable.

## 8. Risks And Mitigations

| Risk | Mitigation |
|---|---|
| Generic advice becomes falsely reassuring | Mandatory red-flag gaps + deterministic escalation. |
| Personalization leaks sensitive data | Server-only private packet + safe public projection + isolation tests. |
| Authority metadata is missing or stale | Fail-closed router and review-expiry tests. |
| Dedao copyrighted text leaks | Remove runtime route; transformed-claim-only offline policy and verifier scan. |
| New context duplicates legacy blobs | Feature-flagged single injection point and prompt duplication test. |
| Mobile UI ships before backend | Backend-first deploy; optional client fields; old-client graceful degradation. |
| Verifier blocks too much | Golden positive/negative corpus and observable verdicts. |

## 9. Release Boundary

The first releasable claim is narrow:

> For low-back-pain symptom questions, Mobile and Mac use the same server-generated
> clinical evidence packet; Mobile additionally offers structured clarification.

No broader medical-domain completion claim is allowed until its authority pack and
golden evaluations pass the same gates.

Current implementation truth:

- the backend clinical semantics are shared by Mobile and Mac;
- Mobile adds an evidence card and structured multi-question continuation bound to
  the parent assistant message;
- personal facts currently affect risk, sufficiency, applicability, detected
  signals, and clarification—not free-form personalized explanation;
- generic knowledge surfaces continue to hold the entire low-back pack, while an
  exact runtime-only allowlist contains the five owner-ratified claims;
- persisted answers and public agent shares are revalidated against the current
  allowlist and immutable artifact digests, even when new synthesis is disabled;
- Mobile/Web selected assistant shares send durable message IDs to the server
  instead of flattening health answers into unverified plain text; the server uses
  a neutral title so hidden support symptoms cannot leak through page metadata;
- local feature-candidate G3 and exact-HEAD G4 have passed; no production
  deployment or shipped-capability claim is permitted before integrated-main CI,
  deployment-health, and production-verification gates pass.
