# Dossier: KBase Claim Adjudication

| Field | Value |
|---|---|
| slug | `kbase-claim-adjudication` |
| stage | S5 implemented |
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

- G3 tests: **PASS.** `75` Release consumer and System KB API tests pass; `10`
  frontend helper and interaction tests pass. The Next.js production build,
  full pre-commit suite, and `git diff --check` pass. The build reports only
  pre-existing configuration, browser-data, lint, and image optimization
  warnings outside this feature. The repository has no
  `scripts/privacy-smoke.sh`, so changed files were manually scanned for
  credentials, machine paths, and copyrighted content.
- G4 review: **PASS.** Independent review first found stale claim-specific
  evidence fields when switching claims; the next pass found hidden legacy
  export claims and a prematurely enabled impact preview. Each finding received
  a regression test and fix. Final independent re-review reported no discrete
  correctness issue. Claim decisions remain fingerprint-bound and fail closed,
  legacy export drafts remain reviewable, preview requires a finalized gate,
  and the admin UI still exposes no serving publish action.
- G5 deployment health: **PENDING.** No deployment has occurred.
- G6 production verification: **PENDING.** Production verification must not
  adjudicate or publish the current medical claims.

## Artifacts

- Design: `docs/plans/2026-07-13-kbase-claim-adjudication-design.md`
- Plan: `docs/plans/2026-07-13-kbase-claim-adjudication.md`
