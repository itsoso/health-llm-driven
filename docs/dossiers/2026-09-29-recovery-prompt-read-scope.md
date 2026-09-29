# Recovery starter advice blocked by optional personal reads

| Field | Value |
| --- | --- |
| status | shipping |
| current_stage | S6 release validation |
| Primary controller | health-harness-orchestrator (incident) |
| Overlay | safety-gate |
| Source baseline | 26917b8458ca5639b8b99b11755dd56714d1cd04 |
| Local run | docs/_generated/harness-runs/b3d938f9cd6c.jsonl |

## G1/G2 Scope and evidence

裁决: PASS

Repair the existing recovery starter and retain the personal-read boundary.

An owner-scoped production investigation confirmed a recovery-advice starter
was classified as advice/symptom/analyze. The model proposed an unrequested
personal read, the gateway blocked it, and the terminal permission notice
replaced the advice even though knowledge retrieval succeeded. The prior Web
draft/focus fix did not address this backend outcome. No raw user health text,
records, identifiers or credentials are retained here.

G1/G2: existing behavior repair, not new read authority. A closed whole-original-
request proof recognizes generated current-symptom recovery advice. Unknown
residue, quotes, third parties, arbitrary annotations and added operations do
not match. Restrict model tools to knowledge retrieval and independently reject
other tools at dispatch, including in shadow mode. Only a completed answer can
recover an optional read denial; required reads, writes, cancellation, medical
safety and incomplete generation retain their gates. Keep static medical rules,
avoid personal-profile preloading, and isolate the current self-contained turn
from old conversation messages. No schema, migration, dependency or API change.

## Verification

- Corrected RED with installed real Pi transport: 7 failed, 2 passed. Earlier
  missing-runtime errors were setup failures, not product evidence.
- Scope proof unit tests: 55 passed, including clinical stages, injected
  annotations, compound actions, clinical terminology and contract fingerprint.
- Broad CI-mode run: 5920 passed, 2 PostgreSQL-only skipped; two new synthetic
  test harness failures were corrected (hidden tool schema and invalid analysis
  argument). Existing capability/gateway tests passed. Final focused integration
  results are recorded in the release evidence below.
- Real-provider LLM gate: invariants 12/12, health-agent core 50/50,
  orchestrator 5/5 (mean 0.9), trajectory 12/12, goldens 9/9. Synthetic consent
  subject in an in-memory database, existing TokenPlan connection fields only.
- System Map regenerated; map, navigation and doc-drift checks passed.
- G4 independent fixed-commit review, exact-main CI, clean backend deployment
  and post-deployment user-flow validation remain required before completion.


## G4 correction

Independent review of d4b5c7729 returned NO-GO: actionable old meal cards and
Twin-based KB/citation fallbacks still loaded personal context. Two independent
synthetic reproductions failed. Both single and panel now suppress old card
projection and citation Twin reads; message-based KB remains available while
private Twin fallback is disabled for this proven scope. An additional client
verification-snapshot regression failed before its narrow guard was added.
No clinical safety admission or static safety rules were bypassed.

After first corrections, affected single/panel/actionable/citation tests:
89 passed. Original fixed-candidate focused CI-mode integration:181 passed,
2 PostgreSQL-only skipped. New final combined run and fixed-revision G4 review
must pass before external publication.

Second review additionally found opener metadata could supply a conflicting
quick reply and execute ActionCard side effects before the gateway. A new real
Pi test failed before remediation. This exact advice scope now skips opener
side effects and opaque entry-context injection, while normal opener replies,
model selection and display-format handling keep their existing paths.
Candidate 5a95263a8 passed 266 focused/neighbor CI-mode tests (2 PostgreSQL-only
skips), and its bound live LLM gate passed 5/5 (mean 0.94); the final narrow
correction requires a fresh fixed-commit review and live confirmation.


## G3 verification and G4 fixed-source review

裁决: GO

The final runtime candidate 94163333c passed independent G4 review after the
opener correction. Its final focused CI-mode integration run passed 107 tests
with 2 PostgreSQL-only skips; its live LLM gates passed invariants 12/12, core
50/50, orchestrator 5/5 (mean 0.92), trajectory 12/12 and goldens 9/9. There is
no schema or database-semantics change.

The first remote CI run 36565969363 found this dossier used an unsupported
capitalized Status key and lacked a machine-readable G1 verdict. This
document-only correction aligns the evidence with the existing dossier
contract; it changes no runtime code. Exact-revision remote CI and production
user-flow validation remain pending, and deployment has not started.

## Production acceptance follow-up

Candidate 1d7981692 passed exact CI 36566681131 and the normal backend
transaction, including health 60/60 and runtime KB contract. The deployed Web
accepted a starter click, focused its draft and permitted editing. The original
personal-read denial disappeared, but the live answer still failed acceptance:
complete generation with knowledge-only tools reached unverified_dose_action.
The existing incidental-medical rewrite excluded all medical-topic requests,
including the proven non-drug recovery starter. No production health payload
or raw generated draft is retained here.

Six real-Pi regression variants failed before the correction. The existing
single tool-free rewrite now also accepts the closed current-input recovery
scope, only for an otherwise complete draft whose sole violation is an
unverified regimen. The final medical guard remains authoritative; a second unsafe draft,
truncation or attempted tool remains blocked. Explicit medication requests,
compound reads and unproven input remain excluded. The recovery prompt now
expressly excludes drug/supplement instructions including continuing an existing
regimen. Fresh tests, fixed-candidate review, CI and production acceptance are
required before this follow-up can be considered delivered.

A repair-negative test also exposed explicit unnamed medication-duration advice
not recognized by the existing guard. Five focused RED cases reproduced this.
The course tripwire now also rejects an advisory verb followed by medicine
administration and a duration; historical facts, negation and non-drug rest
recommendations have paired regression coverage. This tightens the final guard.
