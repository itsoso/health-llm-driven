# Dossier: KBase Persistent Review Workspace

| Field | Value |
|---|---|
| slug | `kbase-persistent-review-workspace` |
| stage | S3 planning |
| status | approved |
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

- G3 tests: PENDING
- G4 review: PENDING
- G5 deployment health: PENDING
- G6 production persistence verification: PENDING

## Artifacts

- Design: `docs/plans/2026-07-13-kbase-persistent-review-workspace-design.md`
- Plan: `docs/plans/2026-07-13-kbase-persistent-review-workspace.md`
