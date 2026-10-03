# Colloquial daily summary execution repair

> 历史本地审计补录（2026-10-03）：以下状态、测试数、发布 SHA 与回执来自原工作树既有记录，未在本次整合中重新验证；不是当前生产状态或本轮发布 Gate 的新鲜证据。本轮整合与验证见 docs/dossiers/2026-10-03-local-change-integration.md。

| 字段 | 值 |
| --- | --- |
| 状态 | shipped |
| 当前阶段 | G6 production verification passed |
| Last reviewed | 2026-09-28 |

## G1 — Request and admission

裁决: PASS

- Incident repair for the screenshot expression `今天我过得怎么样?`.
- Backend remains the source of truth. The repair restores the existing daily
  summary behavior; it adds no write, persistence, schema, notification, or
  autonomous execution authority.
- The accepted phrase is an explicit current-user, current-day retrospective
  request. Its server-owned read scope remains exactly `diet` and `sleep` for
  the current business day.
- Safety overlay selected because the result can contain user-facing health
  evaluation and advice. The user subsequently authorized automatic commit,
  publication and deployment after fixes pass their gates, and asked to continue.

## Cause and implementation boundary

- The daily summary grammar accepted formal phrases such as `给我今天总结`, but
  not the natural self-owned wording `今天我过得怎么样?`.
- Without a `DailyReadPlan`, the model-selected `health_analysis` call was
  rejected and no diet/sleep query ran, leaving only an evidence-free response.
- A closed colloquial grammar now accepts `我/今天/过得怎么样` order variants.
  It reuses the existing exact-day summary plan and advice goal.
- Foreign subjects, future dates, hypotheticals, cancellation, and compound
  deletion remain blocked. Model arguments still cannot choose owner or date.

## Verification evidence

- RED: 8 new failures. The Pi trajectory dispatched zero reads and the policy
  cases returned `health_query_dimension_conflict`.
- GREEN focused: 90 passed, 6 PostgreSQL-only skipped; target module coverage
  92.21% with an isolated coverage file and `--cov-reset`.
- Neighboring plan/summary regression: 177 passed, 6 skipped, including both
  screenshot exercise-plan phrasings.
- Capability-policy suite: all 2,266 assertions passed; its command exited 1
  only because the inherited full-app coverage target measured 28%, so target
  coverage was rerun correctly as noted above.
- Isolated temporary PostgreSQL: the two exact new diet/sleep trajectories
  passed and the instance was stopped. An initial six-case group also exposed
  one unrelated existing failure for a legacy `分析以下建议` case; it was not
  hidden or expanded into this repair.
- LLM change gate: PASS; changed paths do not require a live-provider run.

## G4 — Independent safety review

裁决: GO

- Independent read-only reviewer found no blocking safety issue in the bounded
  working diff. Adversarial checks covered foreign owners, future/other dates,
  hypotheticals, quotes/code/Markdown examples, cancellation, compound writes,
  extra dimensions, and unbounded analysis.
- Accepted phrases always bind to authenticated-current-user diet/sleep reads
  for one server-resolved business day. Model owner/date arguments cannot
  select a different principal or window.
- Reviewer suggested a non-blocking automated owner-key assertion; it was added
  without changing production behavior and included in the final focused rerun:
  91 passed, 8 PostgreSQL-only skipped.

## G5 — Release

裁决: PASS

- Candidate and deployed revision: `dcf56c3f9769411b1edbfb2a6e97b9d5d1618fe4`.
  Independent safety review reconfirmed GO for this immutable diff.
- Exact main CI [36360900468](https://github.com/itsoso/health-llm-driven/actions/runs/36360900468)
  completed successfully, including backend shards and PostgreSQL integration.
- Clean-source CI-mode integration: 2,357 passed, 8 PostgreSQL-only skipped.
  Offline LLM gate passed invariants, core, trajectories and goldens; the change
  gate did not require live-provider evaluation.
- Published from the clean existing release checkout with `./deploy.sh -b`.
  An initial pre-mutation bundle check exposed a stale local production ref;
  it was reconciled to the verified production revision. A subsequent Laya
  preparation timeout retained the original lease and immutable stage without
  changing backend writers or live configuration. Read-only checks and an
  independent reviewer approved the supported same-release adoption path.
- Same-release resume completed with exit 0. No gate was bypassed or lease
  deleted manually. Database backups/restores/offsite archive were skipped
  under the existing disabled policy; rollback-schema compatibility passed.
- Backend-only change; no mobile runtime diff requires OTA or TestFlight.

## G6 — Production verification

裁决: PASS

- Production HEAD matches the candidate, its tracked/untracked working tree is
  clean, and the release lease was released normally.
- Backend, socket, Celery worker and beat are active; service restart counters
  are zero. Public `/api/v1/health` reports API, database, Redis and Celery healthy.
- Deployment health checks passed three times at 60/60. Laya verification and
  guard/staged runtime-only KB contracts passed; runtime transaction finalized,
  with the health-evidence runtime feature flag remaining false.
- Read-only smoke checks against deployed code passed the exact screenshot
  daily-summary phrase, both exercise-plan phrasings, and foreign-owner,
  future, hypothetical and compound-delete rejection cases. Summary reads bind
  to diet/sleep on the current business day; exercise drafts do not acquire
  personal-history read authority.
- This production smoke did not access personal health records or perform a
  live-provider authenticated conversation. End-to-end orchestration evidence
  comes from the regression suite, not a claimed manual phone test.
- Local release logs: `/tmp/reva-summary-release-ci.log`,
  `/tmp/reva-summary-offline-gate.log`, `/tmp/reva-summary-deploy-resume.log`.
  This section is the local post-release audit supplement to the deployed commit.
