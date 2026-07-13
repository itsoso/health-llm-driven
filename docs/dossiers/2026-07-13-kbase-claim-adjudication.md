# Dossier: KBase Claim Adjudication

| Field | Value |
|---|---|
| slug | `kbase-claim-adjudication` |
| stage | S8 complete |
| status | complete |
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
- G5 deployment health: **PASS.** PR `#240` merged and final main commit
  `81903c48d` passed all `24` CI jobs, including client type drift, frontend,
  Mobile, Mac, backend quality, and every backend test shard. The standard full
  deploy backed up PostgreSQL, synchronized the guarded production environment,
  deployed that exact commit, rebuilt frontend and System KB indexes, and
  finished at health score `60/60`. Frontend, backend, Celery worker, and Celery
  beat are active; the public health and admin pages return HTTP 200; the skills
  manifest matches all `22` deployed skills.
- G6 production verification: **PASS.** A short-lived server-local admin token
  performed a read-only claim-list request after service restart and received
  HTTP 200. The persistent workspace reports `460` claims, `5` unresolved,
  a valid content fingerprint, and `serving_allowed=false`. A non-publishing
  impact-preview request returned HTTP 400 because the review gate remains
  closed. No production claim was adjudicated, no workspace was finalized, and
  no artifact was published during verification.

## Artifacts

- Design: `docs/plans/2026-07-13-kbase-claim-adjudication-design.md`
- Plan: `docs/plans/2026-07-13-kbase-claim-adjudication.md`
