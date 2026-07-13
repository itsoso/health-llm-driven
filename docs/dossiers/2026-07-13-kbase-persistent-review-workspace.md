# Dossier: KBase Persistent Review Workspace

| Field | Value |
|---|---|
| slug | `kbase-persistent-review-workspace` |
| stage | S6 verification |
| status | active |
| owner | Codex |

## Intake

Continue the KBase-to-Health closed loop after production verification exposed
that a later deployment removed the pending Release draft while retaining its
database cursor.

## G1 Admission

**PASS.** This repairs an existing safety workflow. The first-class objects are
the canonical seed, persistent review workspace, Release cursor, and base
fingerprint.

## G2 Feasibility and Risk

**PASS.** The design preserves fail-closed review and serving gates. Rebuilds
replay immutable Releases and update the cursor only after an atomic workspace
replacement.

## Delivery Gates

- G3 tests: **PASS.** `24` Release consumer/legacy importer tests and `5`
  admin review/approve/publish tests pass. Full pre-commit passes Ruff, doc
  drift, dossier consistency, System KB seed integrity, and exact dependency
  checks. `git diff --check` passes. The repository has no
  `scripts/privacy-smoke.sh`, so that named project check could not be run.
- G4 review: **PASS.** Initial independent review blocked on two High and two
  Medium findings; a second pass found two High and one Medium, then one High
  and one Medium as the boundary tightened. After remediation, final
  independent re-review reported no Critical, High, or Medium findings. The
  implementation shares one lock across sync/review/publish, cross-checks
  workspace and KBAudit cursors, recovers interrupted replacement, validates
  artifact counts at every review surface, binds approval to the previewed
  content fingerprint, and rejects overlapping canonical/review path trees.
- G5 deployment health: PENDING
- G6 production persistence verification: PENDING

## Artifacts

- Design: `docs/plans/2026-07-13-kbase-persistent-review-workspace-design.md`
- Plan: `docs/plans/2026-07-13-kbase-persistent-review-workspace.md`
