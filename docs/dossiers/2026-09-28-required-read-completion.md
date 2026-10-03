# Required personal-read completion repair

> 历史本地审计补录（2026-10-03）：以下状态、测试数、发布 SHA 与回执来自原工作树既有记录，未在本次整合中重新验证；不是当前生产状态或本轮发布 Gate 的新鲜证据。本轮整合与验证见 docs/dossiers/2026-10-03-local-change-integration.md。

| 字段 | 值 |
| --- | --- |
| 状态 | shipped |
| 当前阶段 | G6 verified |
| Last reviewed | 2026-09-28 |

## G1 — Admission and scope

裁决: PASS

Bugfix to existing authenticated read and completion contracts.
Backend remains source of truth. No new write authority, schema, external
sharing or autonomous action. HealthTwin evidence and ExecutionEvent truth
must agree with the user's requested date and actual tool results.

Read-only owner-bound historical investigation found unresolved personal read
requests whose tools were all blocked, yet the final outcome was complete.
Ordinary advice's optional-read recovery was also reachable when scope parsing
failed. Recent-day summary variants were outside the daily grammar.

This slice restores exact-day retrospective summaries and requires positive
evidence that a rejected personal read was optional before discarding it.
The exact HTML presentation frame projects to the existing bounded reader;
no blanket removal of unknown owner/date/filter clauses is permitted. Existing isolation, quotes,
cancellation, writes and medical boundaries remain authoritative.

User authorized optimization and automatic publication/deployment after gates.
No raw conversations, health values, identities or credentials are retained here.

## Run

Local ledger: `docs/_generated/harness-runs/6838b5af04d4.jsonl`.
Independent read-only scope investigation runs alongside implementation.
Superpowers skills remain disabled; repository RED/GREEN and verification
requirements apply. Unrelated working-tree changes are preserved.

## Gates

- G2: PASS, bounded implementation and adversarial tests complete.
- G3: PASS, RED/GREEN, clean-source CI-mode and isolated PostgreSQL evidence below.
- G4: GO, independent review of fixed `d7c290ac4baaa320c440e2ddb9e6e0295a46c98d`.
- G5/G6: PASS, exact-main CI, clean-source deployment and production checks below.

## G3 — Incremental evidence

- Corrected RED: 10 failed, 8 passed. Initial run also contained four test-harness
  errors (missing executor identity and a stream-only helper on panel); these
  were corrected before implementation, not counted as product failures.
- A second RED proved false personal prose survived even after the outcome
  became blocked: 1 failed, 23 passed. The final public and persisted prose now
  explicitly discloses unresolved reads instead of substituting week averages.
- Completion/daily/plan regressions: 134 passed, 2 PostgreSQL-only skipped.
- HTML RED: 7 failed, 103 passed. Focused GREEN: 110 passed; neighboring
  longitudinal, scope, gateway and semantics regressions: 1,504 passed.
- Daily retrospective summary reuses diet/sleep exact-day binding; the shared
  ordinary/panel trajectory covers yesterday as well as today.
- Read recovery now needs a closed whole-request general-knowledge contract or
  the existing no-personal-evidence exercise draft contract. Failed parsing
  alone cannot establish that a personal read was optional.
- Clean fixed-revision CI-mode integration: 3,111 passed, 10 optional/PG-only
  skipped, exit 0. Independent temporary socket-only PostgreSQL: 112 passed,
  zero skipped, exit 0. Includes both exact-day diet/sleep isolation cases;
  source hashes were unchanged and the temporary cluster was stopped.
- Real-provider gate: PASS with baseline comparison, invariants 12/12,
  health-agent core 50/50, orchestrator 5/5 (average 0.92), trajectory contract
  12/12 and golden traces 9/9. Synthetic consent and an in-memory test database
  only; production credentials were restricted to provider configuration.
  The harness's absent usage-log table emitted warnings; this run does not
  claim quota or usage-persistence coverage.
- Tracked-secret scan, blocking Ruff, System Map and dossier checks passed.

## G4 / G5 — Review and publication

- Independent reviewer: GO on the fixed eight-file commit; no blocking safety
  finding. Positive-proof recovery, stream/panel prose, owner/date isolation,
  quotes, cancellation, hypothetical and mixed write boundaries reviewed.
- Live evidence bound to exact commit before push. SSH transport failed before
  push; authenticated HTTPS push succeeded. No force push or source changes.
- Exact GitHub CI: https://github.com/itsoso/health-llm-driven/actions/runs/36372144670
  completed successfully. Clean release checkout reused; no unrelated dirty
  work included. Production baseline `dcf56c3f9` was verified before deployment.

## G5 — Deployment

裁决: PASS

- `deploy.sh -b` exited 0 for exact reviewed/CI-green `d7c290ac4`.
- Production-equivalent private candidate config, rollback schema compatibility
  and locked dependencies passed. No managed migration was applied. Database
  backup/restore/offsite steps were default-off per the existing policy; this is
  not a claim of new backup coverage.
- Three health checks passed at 60/60, guard/staged KB contracts passed, Laya
  verified, runtime state finalized and the release lease released normally.
- Backend-only: no OTA or TestFlight needed. Temporary sensitive candidate
  configuration was deleted after successful deployment.

## G6 — Production verification

裁决: PASS

- Production SHA exactly matches the candidate. Backend, Celery worker and beat
  are active with zero restart counters; public health reports API, database,
  Redis and Celery healthy.
- Eleven read-only deployed-code synthetic scope checks passed: yesterday and
  day-before diet/sleep date binding, HTML week scope, foreign-owner/cancelled/
  mutation rejection, and required-read versus general-advice classification.
  These checks made no database or provider calls. End-to-end transport and
  database isolation evidence comes from the regression suites; no claim of
  replaying real historical conversations or manual mobile UI acceptance.
- Evidence: `/tmp/reva-required-read-ci.log`,
  `/tmp/reva-pg-required-read.tsPn8Q/tests.log`,
  `/tmp/reva-required-read-live.log`, `/tmp/reva-required-read-deploy.log`.
- This is the local post-release audit supplement to the deployed commit.
  Other historical issues, including contextual meal corrections and broader
  write-receipt consistency, remain outside this bounded release.
