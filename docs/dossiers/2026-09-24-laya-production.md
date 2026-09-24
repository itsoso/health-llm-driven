# Laya production integration and administrator control

| 字段 | 值 |
| --- | --- |
| 状态 | building |
| 当前阶段 | S5 implementation and verification |
| Controller | Health Harness |

## G1 admission

裁决: PASS

The user explicitly requested deployment and an administrator switch for the
existing decision-routing infrastructure. The accepted feature specification is
`docs/specs/active/2026-09-24-decision-providers.md`. No new autonomous health
write is introduced; scope and acceptance follow that bounded specification.

## Execution evidence

Status: implementation. User authorization: deploy Laya online, integrate production,
and let administrator user_id=3 enable/disable it. Controller: Health Harness.

Source baseline: origin/main da95511d271a497ad7b1c018f4720274a4a53bfb.
Production read-only baseline: 05b6e4d396084103975c43e4a5fc4d044d8e66da,
backend active, zero restarts at inspection. Original dirty workspace preserved.

Admission: infrastructure for existing read-capability/model routing. Web owns
admin control; backend/PostgreSQL is authoritative. SafetyGuardian and WriteIntent
permissions remain independent. No new health-data write or medical claim.

Scope: default-disabled global switch, only active is_admin user_id=3 can access;
durable PostgreSQL state, optimistic concurrency and transactional audit; private
loopback Laya on the production host; existing Jev/SystemOne adapters retained.
No process-only switch, public inference endpoint or client-provided user identity.

Acceptance: admin/nonadmin/unauth access, strict requests, cross-session persistence,
stale writes, immediate off-before-send, provider failure handling, PostgreSQL
constraints/concurrency/migration, UI operation, CPU inference, exact CI, backup,
governed deployment, production authenticated toggle and synthetic routing evidence.

Known pre-existing release blocker: baseline CI 35938658617 has two App Store
release-pack tests failing because an Android-only map fallback contains a
platform-specific word. Investigate/reconcile before any external publication.

Rollback: disable control, then original route; retain additive control table/audit.
Full code rollback uses the governed release path. Deployment is not complete
until actual production control and routing have been verified.

G3 in progress. G4 pending fixed-commit review. G5 blocked by baseline main CI.
G6 not started; no production mutation has been performed.

Fresh evidence:
- PostgreSQL control/consent suite: 13 passed, including CAS concurrency and migration replay.
- API/UI initial focused tests: 49 passed and 6 passed respectively.
- Installer/config/control/deploy regression: 30 passed, one PostgreSQL-only skip on SQLite.
- Trusted publisher unit suite: 83 passed after first-use candidate generation.
- Both API clients regenerated successfully from the locked backend environment.
- Baseline CI repair prepared separately at 018cd3caa: one platform-neutral map
  fallback line; original two failing tests and pre-commit passed. Independent
  review GO. Awaiting explicit narrow publication exception under AGENTS §7.

Review fixes: reject future revision before CAS; allow disable during provider
misconfiguration; emergency off skips sidecar health/provisioning; reject existing
vendor/runtime systemd units; exclusive service account/group checked on reuse;
systemd validation, enabled status, venv existence and locked-version inventory.

Further fresh checks: PostgreSQL 15 passed; frontend full gate 411 tests plus
typecheck/lint passed; publisher/release suites 176 passed; LLM invariants 12/12,
health-agent core 50/50, live orchestrator 5/5, trajectory 12/12 and goldens 9/9.
Live synthetic evaluation has known non-production warnings for absent usage-log
tables in its disposable in-memory database; it does not prove Laya quality.
An initial Agent test run lacked Pi node_modules in the isolated worktree and
was interrupted after explicit failures. Linking the unchanged lock-matching
Pi installation fixed the targeted cases (10 passed); full relevant suite subsequently passed all 249 tests (one PostgreSQL-only skip).
Both generated-client types, System Map and source Ruff check passed.

Independent-service rollback contract: backend rollback retains the idle Laya
service and additive table. No existing service upgrade/overwrite is authorized
by this installer; incomplete or mismatched installations remain BLOCK.

Focused coverage measured from that run: 88.12% across decisions, admin API and
consent (423/480 statements). The initial coverage command inherited global
--cov=app and exited nonzero for unrelated unexercised application modules;
explicit focused coverage report passed the 80% threshold. A clean scoped
coverage command is being run to remove that invocation ambiguity.
Installer review regressions: 21 passed. Linux startup/auth/inference are verified
by the governed provision phase before stopping the old backend; they have not
been executed in production in this session.
