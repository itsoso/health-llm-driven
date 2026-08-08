# Semantic Illness Query

| Field | Value |
|---|---|
| date | 2026-08-08 |
| status | in_progress |
| current_stage | G3 PASS; G4 fifth remediation complete, fresh final re-review pending |
| owner_surface | Backend Agent / Mobile, Mac and Web chat |

## Problem

The production query `我上一次口腔溃疡是什么时候 最近半年分别有哪些记录`
was treated as an incomplete record-creation command. A follow-up query then
attempted an unsupported symptom query and surfaced unrelated wearable/sleep
data.

## Evidence

- The user supplied screenshots of both failures and approved the hybrid
  semantic-query architecture on 2026-08-08.
- Local reproduction on `origin/main` classifies the full query as
  `primary=write, domain=unknown, operation=create`.
- The follow-up query is `read` but remains `domain=unknown`.
- `health_query` does not register illness or symptom dimensions.
- `tool_validator._validate_query` silently coerces an invalid dimension to
  `comprehensive`, which reads wearable data and explains the unrelated sleep
  result.
- The clean-worktree baseline passed 601 existing classifier and illness-manage
  tests before implementation.
- A live `qwen3.7-max` TokenPlan evaluation selected
  `health_query(dimension=illness, keyword=口腔溃疡, days=183)` for the exact
  query, its paraphrase and a negated-write query. The read capability gate
  exposed no `health_record` tool. The explicit-write contrast selected
  `health_record(record_type=illness)`.
- A separate no-window evaluation selected `health_query(dimension=illness,
  keyword=口腔溃疡)` without `days`; the deterministic reader now interprets
  that shape as full illness history rather than the generic seven-day default.

No production health record was read or copied during diagnosis. The only
health phrase retained is the user-provided reproduction required for tests.

## Decision

Implement the approved design in
`docs/plans/2026-08-08-semantic-illness-query-design.md` and product contract in
`docs/specs/active/2026-08-08-semantic-illness-query.md`:

- determine read/write authorization from the speech act, not the token
  `记录` alone;
- let the LLM express illness entity and time semantics through a registered,
  typed query plan;
- compile illness queries to a deterministic owner-scoped canonical reader;
- fail loudly on unknown semantic dimensions; and
- preserve all explicit health-record write contracts.

## Gates

### G1 Product Admission: PASS

This repairs the existing review/converse loop and maps persisted illness
episodes to read-only `ExecutionEvent` evidence. It creates no new medical
claim, autonomous action or user burden. Existing illness writes remain behind
their current confirmation boundary.

### G2 Feasibility And Risk: PASS

The classifier, schema, validator, executor and illness API/model paths were
inspected. The change needs no database or client migration. Main risks are
false suppression of legitimate writes, cross-user illness disclosure,
semantic fallback into the wrong data family, and a model omitting the illness
name. Failure-first contrast tests, explicit owner filters, fail-loud dimension
validation and no-match honesty address those risks.

### G3 Tests: PASS

- Failure-first tests reproduced the original write misclassification, invalid
  dimension fallback, full-history omission, server-date boundary error,
  plaintext exception leak, unsupported batch shape and polite-write regression.
- The first post-remediation compatibility group passed 1,132 tests, including the
  classifier, validator, canonical readers, batch planner, Agent executor,
  ToolGateway, health management, write-adapter rejection and behavior battery.
- The requested live `qwen3.7-max` evaluation passed the exact query, paraphrase,
  negated-write query, explicit-write contrast and no-window latest query.
- Targeted Ruff, Python compilation, `git diff --check`, doc drift and dossier
  consistency all passed.
- After functional re-review found additional polite request forms, the
  classifier/capability/ToolGateway regression group passed 1,243 tests with a
  request/capability/negation grammar matrix.
- After the next safety and code reviews found sentence-initial historical
  questions, future-dated episodes, compositional request prefixes and modified
  negations, failure-first tests reproduced all four boundaries. The expanded
  related regression group now passes 1,758 tests.
- A subsequent NO-GO exposed unpunctuated Mobile speech-history frames, a bare
  `has_write` fallback, negated write + advice compounds, product-capability
  questions with helpers, cross-clause question leakage, long illness windows
  silently becoming seven days, and undisclosed 100-row truncation. Failure-first
  tests cover each boundary; the final expanded compatibility group passes
  1,850 tests, including classifier, IntentFrame, CapabilityPolicy, ToolGateway,
  validator, canonical reader, goal spec and all prior behavior batteries.
- Two further independent reviews found that finite helper stripping still
  authorized negated bridge forms such as `不要让系统帮我记录`, capability
  questions with `请问/我想问` wrappers, historical/completed forms using write
  synonyms other than `记录`, and an undirected batch-query recovery message.
  Failure-first coverage reproduced the gaps. The replacement shared
  clause/scope parser now drives both the classifier and the kernel preflight,
  and the expanded related compatibility group passes 1,969 tests.
- The shared-parser contract also passes a generated matrix covering every
  registered write action across 350 negation/bridge combinations, plus
  positive modal, cross-clause, completed-history, capability-question and
  lexical-collision controls. The exact screenshot query is not mistaken for a
  cancellation merely because `分别` contains the character `别`.

### G4 Safety Review: PENDING

The first independent review returned NO-GO and deployment stopped. It found:

- SQLAlchemy exception text could expose an illness keyword in logs/output;
- illness windows used the service date instead of the frozen user date;
- `health_query_batch` inherited illness without keyword/full-history support;
  and
- polite explicit write questions could be classified as reads.

All findings now have failure-first regressions and code fixes. The exact
screenshot query also has a real ToolGateway test proving a model-requested
`health_record` is blocked before dispatch. Independent re-review is required
before G4 may pass.

The second safety re-review then returned NO-GO because sentence-initial
historical questions such as `记录过口腔溃疡吗` still authorized writes and
future-dated illness rows were not bounded above. A separate final code review
also found that compositional polite requests could lose write intent and that
negations containing `再` could gain it. These findings are now covered by a
bounded compositional request grammar, a negation × helper × modifier matrix,
ToolGateway preflight tests and a frozen-date inclusive upper bound. A fresh
independent review of the new commit remains mandatory.

The next independent safety review returned NO-GO because unpunctuated forms
such as `记录过口腔溃疡没有` and historical noun fragments could still pass the
bare `has_write` fallback. Its companion code review also found negated compound
turns (`勿/甭...记录，分析...`) could write, explicit writes could be cancelled by
a question in a later clause, helper-bearing capability questions could write,
and `days=730` silently became seven days. Deployment remained stopped.

The remediation removes bare-token write authorization, recognizes completed
and historical `记录` frames, parses bounded clauses and request prefixes,
shares structural negation terms with the kernel backstop, preserves a remaining
analysis goal after write cancellation, supports illness windows through 36,500
days with fail-loud bounds, and discloses 100-row truncation. Real ToolGateway
dispatch spies prove the new historical, negated and capability cases never
cross the adapter boundary. A new independent review is still required.

The following independent safety and code reviews again returned NO-GO before
deployment. They showed that finite helper lists did not compose with
`让小巴帮我/让系统帮我`, inquiry wrappers could hide product-capability
questions, completed forms such as `保存过/录入过/新增过` could still authorize
writes, and illness submitted to the batch tool lacked a directional recovery
contract. Deployment remained stopped.

The fifth remediation replaces the duplicated finite negation logic with one
shared clause/scope parser used by both intent classification and the final
ToolGateway write backstop. It separates clause-local negation, non-negating
modal questions, product-capability subjects, completed/history frames and
lexical containers; write actions come from one shared registry. The batch
validator now directs the model to a single
`health_query(dimension='illness', keyword=..., days=...)` and forbids switching
domains. Focused tests first failed, then the related suite passed 1,951 tests;
Ruff, compilation, generated system-map drift, dossier consistency and diff
checks also pass. Positive controls where `不` belongs to a symptom description
rather than the later write action pass separately at classifier and capability
layers. A brand-new independent review of this implementation remains
mandatory before G4 can pass.

### G5 Deployment Health: PENDING

Backend deploy and health checks have not started.

### G6 Production Verification: PENDING

Requires a read-only production query showing an illness tool call and no
write attempt. No health record may be created for the drill.

## Rollback

Rollback is the prior Backend release. There is no schema migration or data
backfill, so rollback requires no data repair.
