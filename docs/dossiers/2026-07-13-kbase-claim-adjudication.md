# Dossier: KBase Claim Adjudication

| Field | Value |
|---|---|
| slug | `kbase-claim-adjudication` |
| stage | S3 planned |
| status | active |
| owner | Codex |

## Intake

Continue the production KBase-to-Health loop by replacing release-wide draft
approval with explicit, claim-level human decisions. Existing evidence-level C
medical claims must not become authoritative merely because their Release is
reviewed as a batch.

## G1 Admission

**PASS.** This closes a verified safety gap in an existing production workflow.
The first-class objects are the persistent review workspace, draft claim,
adjudication event, external evidence, workspace fingerprint, and KBAudit event.

## G2 Feasibility and Risk

**PASS.** The design reuses the existing persistent workspace lock, atomic
replacement, review gate, and separate publish endpoint. Decisions are bound to
an exact fingerprint. Rejected/background claims cannot enter Health serving;
`needs_evidence` claims remain blocking. The new UI has no publish action.

## Delivery Gates

- G3 tests: **PENDING.** Backend decision/finalization/API tests and frontend
  interaction/build checks have not run yet.
- G4 review: **PENDING.** Independent review is required after implementation.
- G5 deployment health: **PENDING.** No deployment has occurred.
- G6 production verification: **PENDING.** Production verification must not
  adjudicate or publish the current medical claims.

## Artifacts

- Design: `docs/plans/2026-07-13-kbase-claim-adjudication-design.md`
- Plan: `docs/plans/2026-07-13-kbase-claim-adjudication.md`
