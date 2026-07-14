# Dossier: KBase Consumer Feedback Outbox

| Field | Value |
|---|---|
| slug | `kbase-feedback-outbox` |
| stage | S8 complete |
| status | complete |
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
  columns. Main CI run `29299983644` is the authoritative clean-environment
  gate and passed all 24 jobs. A concurrent chat-image change initially put an
  image acknowledgement on the wrong execution path; a focused regression
  test, 39 related tests, blocking Ruff checks, and the required live-LLM gate
  all pass (`12/12` invariants, `50/50` health-agent cases, `5/5`
  orchestrator cases).
- G4 review: **PASS.** Reviewed the producer identity mapping, audit-to-event
  projection, privacy boundary, cursor semantics, deterministic idempotency,
  failure behavior, task registration, and generated architecture drift.
- G5 deployment health: **PASS.** Standard backend deploy published main
  commit `6d13dd62d`, created and integrity-checked a PostgreSQL backup,
  applied managed migrations, rebuilt the System KB index (`895` documents),
  restarted the backend plus Celery worker and beat, and finished at health
  score `60/60`. All three services are active and the deployed skills
  manifest matches all `22` local skills.
- G6 production verification: **PASS.** The production worker reports
  `flush_dedao_kbase_feedback` as registered and beat contains its schedule.
  A server-local run returned `up_to_date` at cursor `997` with no pending
  posts. The latest durable `dedao_kbase_feedback_flush` audit was written by
  `celery:dedao_kbase_feedback`; it scanned `46` source audits, advanced the
  cursor to `997`, and posted no event because none mapped to an eligible
  release outcome. No user content or health data was emitted during the
  verification.

## Artifacts

- Design: `docs/plans/2026-07-13-kbase-feedback-outbox-design.md`
- Plan: `docs/plans/2026-07-13-kbase-feedback-outbox.md`
