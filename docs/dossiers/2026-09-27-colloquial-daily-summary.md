# Colloquial daily summary execution repair

| 字段 | 值 |
| --- | --- |
| 状态 | shipping |
| 当前阶段 | G5 release preparation |
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

## Remaining gates

- Release continuation is authorized. Bind the independent safety review and
  actual main CI to the exact candidate, deploy from a clean source directory,
  and verify production revision, services, health and the repaired read scope.
- Backend-only change; no mobile runtime diff requires OTA or TestFlight.
