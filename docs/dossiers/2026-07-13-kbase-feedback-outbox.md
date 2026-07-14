# Dossier: KBase Consumer Feedback Outbox

| Field | Value |
|---|---|
| slug | `kbase-feedback-outbox` |
| stage | S4 review |
| status | in_progress |
| owner | Codex |

## Intake

Continue the source-to-knowledge closed loop by automatically returning real
Health consumption signals to Dedao KBase.

## G1 Admission

**PASS.** Producer-side assessment is online and requires real consumer
outcomes to become useful.

## G2 Feasibility and Risk

**PASS.** Existing release provenance, `KBAudit`, Celery, and idempotent
producer feedback are sufficient. Model-only conflict signals remain excluded.

## Safety Boundary

The user-facing answer and review paths never call KBase synchronously. The
outbox contains no user query, answer, note, reviewer identity, health record,
or other personal data. No feedback can directly approve, mutate, or publish a
Knowledge Release.

## Delivery Gates

- G3 tests: **PASS (changed scope).** The 85 release consumer, lifecycle, and
  System KB API tests pass. Pre-commit, doc drift, dossier consistency, seed
  integrity, dependency pinning, diff check, and generated system-map checks
  pass. The full local backend run reported 6510 passed, 44 failed, and 2
  skipped; the same failed-file set on clean `origin/main` reproduced 40
  baseline failures, primarily because the shared test database lacks current
  columns. CI remains the authoritative clean-environment gate.
- G4 review: **PENDING.**
- G5 deployment health: **PENDING.**
- G6 production verification: **PENDING.**

## Artifacts

- Design: `docs/plans/2026-07-13-kbase-feedback-outbox-design.md`
- Plan: `docs/plans/2026-07-13-kbase-feedback-outbox.md`
