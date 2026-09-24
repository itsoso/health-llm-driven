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

G3 passed. G4 GO for code safety at 4df26708b1e599bc1809016f2bc241958a4a1e41.
The user explicitly authorized continuing publication on 2026-09-24; the narrow
baseline repair 018cd3caab9ad124c83bd5c5cf32adafd62cf357 was pushed to main.
G5 waits for that exact CI, then the combined candidate's exact CI and deployment.
G6 not started; no production mutation has been performed.

Fresh evidence:
- PostgreSQL control/consent suite: 13 passed, including CAS concurrency and migration replay.
- API/UI initial focused tests: 49 passed and 6 passed respectively.
- Installer/config/control/deploy regression: 30 passed, one PostgreSQL-only skip on SQLite.
- Trusted publisher unit suite: 83 passed after first-use candidate generation.
- Both API clients regenerated successfully from the locked backend environment.
- Baseline CI repair prepared separately at 018cd3caa: one platform-neutral map
  fallback line; original two failing tests and pre-commit passed. Independent
  review GO. The user subsequently authorized publication. CI run 35951912426
  found three mobile assertions still matching the old copy; the single test
  constant was aligned in 01d756b79c38a52775ccab45dd0a18213f3167b9, and all six
  workout-detail cases passed locally. Exact CI must pass before Laya is pushed.

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
coverage command then passed: 74 tests, three SQLite skips, 93.75% coverage.
Installer review regressions: 21 passed. Linux startup/auth/inference are verified
by the governed provision phase before stopping the old backend; they have not
been executed in production in this session.

Fixed-commit G4 review of c350c15e18e941d1bc571b839fc047b152c47342 found
one additional issue: deeply nested response JSON could raise RecursionError
instead of entering the explicit fallback. A real mock-transport reproduction
failed before the fix. The decoder now normalizes that specific failure to
invalid_response. Fresh scoped verification: 75 passed, three SQLite skips,
93.80% coverage. Independent focused re-review passed nine malformed-response
and timeout tests; final fixed-commit disposition was GO at 4df26708b.
No authorization, route floor or write authority is changed by the fix.

Release continuation: baseline repair CI 35952272265 passed. Combined candidate
d2af07fe75aad60cd8c0fed21e1ef0b6ab8ace71 had G4 GO and a fresh live LLM gate
(12/12 invariants, 50/50 core, 5/5 orchestrator, 12/12 trajectory, 9/9 goldens).
Its CI 35952595731 identified an existing lost-lease test harness that did not
isolate the newly added Laya preparation. The harness now stubs that unrelated
preparation while retaining its real pip/lease-loss/migration/restart assertions.

Read-only production preflight: user 3 is active and is_admin. Hugging Face
origin timed out, while PyPI/Torch CPU and the mirror's large artifacts were
reachable. The three unchanged upstream JSON files (2934 bytes total) are now
named canonical assets, with Apache 2.0 license and provenance. Large files use
the fixed mirror and verified HTTPS CDN, preserving original full hash/size
checks; arbitrary redirects, proxy environment and fallback are rejected.
New installer tests first failed, then all 31 passed after implementation.
Production-host full GET preflight matched both original hashes and sizes:
643835514-byte weights in 57.98 seconds, 34363188-byte tokenizer in 6.13 seconds.
Small configs use strictly decoded Base64 assets to preserve upstream missing
final newlines without exempting or disabling repository whitespace hooks.
Renewed fixed-commit review is pending.
Production application, model installation and authorization remain unchanged.

Exact candidate 3b0ec47d4bf12a80424a1fe655c7629f505b0d1b passed CI run
35955764718 and trusted validation run 35956929435. The governed backend run
35962192431 then failed before checkout, writer stop, live env mutation or Laya
installation: its canonical source was a depth-one clone, so the exported HEAD
bundle omitted parent ce8cd0d58 and could not prove the previous production
revision in the empty Laya proof repository. Production remained at 05b6e4d3;
backend/worker/beat retained their existing PIDs with zero restarts, live env
retained its original digest, and Laya retained only the exact empty candidate
source directory. The original NEEDS_OPERATOR evidence and release lease remain.

The repair removes only `--depth=1` from the fixed canonical clone and adds a
real two-commit bundle/import regression. Because existing recovery modes cannot
truthfully represent a running unchanged old release, a separate fail-closed
`--retire-unchanged` profile records CLOSED_UNCHANGED_RELEASE after proving the
old revision/env/runtime terminal, pre-lease zero-restart units and cgroup
processes, health/schema/KB, and strict Laya non-installation. It preserves the
failed workspace, log, stage and empty source while archiving the original lease
inode and revoking only the exact temporary identities. Focused release tests:
293 passed. Independent scope review: GO; final fixed-commit review and exact CI
are still required before this recovery profile or another deployment executes.

The unchanged-release inspection then reached the production virtualenv and
correctly stopped on two root-managed Node launcher links that predated this
release: `venv/bin/node` and `venv/bin/npm` point into the fixed
`/opt/node-toolchains/node-v22.19.0-linux-x64` installation. The verifier now
accepts only those two exact root-owned, single-link targets without executing
them; npm's second link must remain the exact relative `npm-cli.js` target and
its resolved file and parent must pass the existing secure-path checks. Every
other virtualenv link remains rejected. Fresh focused release verification:
361 passed and 84 subtests passed. Production is still unchanged while this
candidate awaits fixed-commit review and exact CI.
