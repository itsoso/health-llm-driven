# Semantic Illness Query

| Field | Value |
|---|---|
| date | 2026-08-08 |
| status | in_progress |
| current_stage | G3 PASS; G4 ninth remediation complete, fresh exact-commit re-review pending |
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
- The next independent reviews supplied semantic classes not derived from the
  implementation vocabulary. Failure-first tests reproduced 110 failures across
  post-object completed questions, denial predicates, unpunctuated capability
  inquiries, colon-introduced prohibited actions, adversative clause boundaries
  and explicit historical backfill. After remediation, the expanded related
  suite passes 2,098 tests. A real ToolGateway adversarial matrix also proves 80
  denial/history/capability combinations across every registered write synonym
  return `dispatch_started=false`.
- Fresh reviews of commit `2430ba16a` then reproduced ordinary read verbs,
  result-state checks, reported/quoted speech, precondition and trailing
  revocations, capability complements, mixed-polarity clauses, vocative direct
  requests and punctuation-free backfills crossing or losing the write boundary.
  Failure-first coverage reproduced the defects before implementation.
- The seventh remediation makes authorization positive rather than veto-based.
  One shared speech-act parser now requires the governing action to be direct,
  affirmative and current; read, capability, result, history, report, quote,
  example and hypothetical frames are non-authorizing. It also preserves
  object-fronted commands, lexical `过` collisions, dated backfills and later
  positive contrast clauses. A compiled goal constrains mixed-polarity writes
  so the model cannot use the positive target to write the denied target.
- The expanded related regression suite passes 2,369 tests. Targeted Ruff,
  Python compilation and diff checks pass. Real ToolGateway spies prove all new
  non-authorizing examples return `dispatch_started=false`.
- A fresh live `qwen3.7-max` challenge deliberately exposed why the model is not
  the authority: its raw auto selection chose `health_record` for quoted
  document text. The deterministic classifier/gate converted that exact case
  to read/block before dispatch. For a fully specified direct meal request, the
  forced write-tool path returned `health_record(record_type=diet)` with data.
- Fresh reviews of the seventh remediation returned NO-GO before release. Real
  ToolGateway spies proved that arbitrary-source reported commands and health
  observations, ordinary read transformations over historical `记录` nouns,
  trailing pause/revocation language, and mixed-polarity target transfer could
  still cross dispatch. The same reviews also caught false rejection of polite
  conditional requests.
- The eighth remediation compiles one concrete governing authorization clause
  and binds it to `record_type`, meal target, named illness and deterministic
  numeric values before `health_record` can execute. Reported commands and
  observations share the same provenance gate; historical record nouns and
  trailing revocations cannot produce authority. The capability contract is
  versioned as `agent-capability-policy-v2` with `clause-target-v1` binding.
- Failure-first coverage now includes 120 command-speech combinations across
  every registered write synonym, 12 attributed/hypothetical observation
  combinations, real dispatch spies, mixed meal/type/value transfer and legal
  conditional/cross-clause controls. The complete related compatibility group
  passes 2,701 tests; targeted Ruff also passes.
- The requested live `qwen3.7-max` system challenge passed 9/9 synthetic cases:
  the exact query produced typed illness reads, history analysis stayed read
  only, reported and revoked frames made no write call, and direct/mixed writes
  selected only the authorized illness, weight or dinner target. No production
  account or database record was read or written.
- Fresh code and safety reviews of commit `9e4bcba9e` both returned NO-GO and
  deployment remained stopped. They found that one governing clause could not
  safely represent multiple writes, argument aliases and selectors were not
  uniformly bound, meal/food/date and medication dosage could drift, and some
  quoted, hypothetical, revoked or corrected forms could still resolve to the
  wrong target.
- The ninth remediation replaces single-clause binding with
  `authorized-target-set-v2`. Every direct positive clause contributes at most
  one exact target; reported, hypothetical, quoted, denied and revoked clauses
  contribute none. The gate checks top-level and nested aliases and binds the
  effective type/date plus deterministic selectors for diet, water, body
  metrics, illness, symptom, medication, supplement, exercise, mood,
  excretion, sleep, goal and reminder. Medication name and dosage are bound
  together. Natural `记录早餐，吃了……` detail remains supported, while drug
  entities cannot be absorbed as food.
- Mixed-polarity turns no longer compile into a whole-turn simple record goal.
  Retry recovery, structured food lists, attachment provenance and reminder
  enrichment now reach the capability gate with the same concrete semantics
  used by the downstream adapter.
- The post-remediation live `qwen3.7-max` system evaluation first scored 8/9.
  Its meal tool call dropped the explicit food quantities, and the deterministic
  gate correctly blocked it with zero dispatches. That red result is retained.
  Equivalent Chinese/Arabic quantity forms and the production `+` food
  separator were then normalized without relaxing quantity equality. With the
  real production tool schema and frozen current-date context, the complete
  challenge reran at 9/9: two illness reads, quoted/revoked blocks, exact
  illness/weight/mixed-meal writes, two separately bound medication drafts and
  the declarative breakfast write. No production account, database read or
  write adapter was used.
- The final related compatibility run passed 2,911/2,911 tests. It includes the
  shared speech-act grammar, target-set CapabilityPolicy, real ToolGateway,
  typed illness reads, validator/date boundaries, runtime write operations,
  retry recovery, write-outcome honesty and medication confirmation flows.
  Targeted Ruff, Python compilation, diff checks, generated system-map drift
  and Dossier consistency gates also pass.
- Fresh exact-commit reviews of `5491261b4` returned NO-GO before release.
  They reproduced composed revocations, deferred future conditions and
  third-party writes; conflicting medication aliases; dates recognized by the
  gate but ignored by adapters; model-invented illness fields; attachment meal
  drift; lost historical symptom dates; lexical `和牛` splitting; and reminder
  title/start-date drift. Deployment remained stopped.
- The tenth remediation versions the boundary as
  `agent-capability-policy-v4` / `authorized-target-set-v3`. One canonicalizer
  now runs before validator, policy and adapter dispatch. The exact normalized
  payload binds date aliases, medication dose aliases, illness status/notes,
  attachment meal slot, recurring reminder start and historical symptom date.
  Deferred/third-party/revoked clauses contribute no authority. An optional
  model-invented severity is projected out before dispatch, preserving the
  user's exact write without persisting a fabricated health fact.
- The current focused target-set suite passes 1,260 tests and the expanded
  classifier/query/validator/runtime compatibility suite passes 2,389 tests.
  The requested live `qwen3.7-max` evaluation first retained a red 9/12 run:
  two valid illness writes were rejected because the model invented severity,
  and one resolved-illness case actually required the manage/list workflow
  omitted from that create-only tool set. After field projection, the final 11
  valid query/write/revocation/deferred/third-party/date/reminder/multi-write
  cases pass 11/11 with zero database reads or writes.

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
domains. Focused tests first failed, then the related suite passed 1,969 tests;
Ruff, compilation, generated system-map drift, dossier consistency and diff
checks also pass. Positive controls where `不` belongs to a symptom description
rather than the later write action pass separately at classifier and capability
layers. A brand-new independent review of this implementation remains
mandatory before G4 can pass.

The two fresh reviews of commit `393f1ebfe` returned NO-GO and deployment again
stopped. They found that historical completion can appear after the object
(`保存口腔溃疡了吗`), product-capability questions use predicates such as
`会/支持/有没有…功能`, denial uses controls such as `禁止/拒绝/停止/未授权`,
and a colon can introduce the operation covered by a prohibition. They also
found the inverse risks: `但` must terminate an earlier symptom negation, and a
clear dated historical backfill must remain writable.

The sixth remediation extends the shared semantic frame rather than adding
surface-specific routing. It now models denial-control predicates, contextual
colon scope, adversative clause boundaries, capability subjects/predicates,
post-object completion and past-time position. Explicit dated backfill and
current-event commands such as `记录刚才打了一个喷嚏` are positive contrasts.
The final capability gate independently blocks capability/history frames even
if a future classifier regression labels them as writes. Failure-first cases,
the 2,098-test related suite, Ruff, compilation and repository structural gates
must all pass before another brand-new independent review may decide G4.

The two fresh reviews of commit `2430ba16a` returned NO-GO and deployment again
stopped. They demonstrated actual ToolGateway dispatch for basic read requests,
prior-result checks, reported speech, capability complements, independent
denial paraphrases and trailing revocations. They also found that one global
negation boolean blocked legitimate later writes, while vocative requests,
object-fronted commands, lexical `过*` words and punctuation-free backfills could
lose basic write behavior.

The seventh remediation replaces fail-open veto matching with positive,
action-scoped authorization shared by routing and the final tool gate. The last
write-bearing clause determines current polarity; quoted, attributed,
hypothetical, result, capability, history and read frames cannot authorize a
write. Mixed denied/positive turns additionally bind the requested record type
to the deterministic goal where available. Failure-first tests, a real gateway
dispatch matrix, 2,369 related regressions and the live qwen challenge all pass
at the system boundary. A brand-new independent safety and code review of the
new commit remains mandatory before G4 can pass.

Fresh independent safety and code reviews of commit `878e44c5e` both returned
NO-GO and deployment remained stopped. They reproduced actual dispatch for
arbitrary-source reports (`朋友说/同事转告`), attributed observation facts,
historical analysis/summarization whose object ended in `记录`, common trailing
pause/revocation language, and authorization transfer between denied and
permitted targets. A single full-turn domain could neither distinguish
breakfast from dinner nor bind `记录体重71kg` to weight 71. The reviews also found
that bare `如果/假如` metalinguistic matching rejected legitimate conditional
requests.

The eighth remediation changes the policy boundary from a whole-turn boolean
to a concrete governing clause. Provenance, polarity, historical/read role and
revocation are resolved before target compilation. The final ToolGateway then
reclassifies only that authorized clause and matches the requested record type,
meal selector, named illness and deterministic water/weight/blood-pressure/waist
values. Mixed polarity with no resolvable positive target fails closed to
clarification. Procedure recipes retain their separately prevalidated contract.
The classifier and final gate now share attributed-command and attributed-
observation handling, while polite conditional and read-then-write controls
remain writable. All local and live evidence is green, but a brand-new
independent safety and code review of the next exact commit remains mandatory
before G4 can pass.

Fresh independent reviews of commit `9e4bcba9e` again returned NO-GO. The
single governing target could not express two authorized writes, and the model
could vary selectors through aliases, omit or change meal/date/food values,
invent medication dosage, bind the wrong illness, or reuse an earlier corrected
value. Additional hypothetical, quotation and revocation forms also required
target-set-level provenance rather than a whole-turn goal. No deployment was
attempted.

The ninth remediation makes the authorized target set the only mutation
authority. It computes all direct positive clauses, compiles each target
independently, and compares the actual normalized request against type, entity,
value, date and family-specific selectors before dispatch. Missing or
unresolvable selectors fail closed. Multi-write turns retain separate targets;
mixed-polarity turns cannot be collapsed into one canonical write. The
capability contract is now `agent-capability-policy-v3` with
`authorized-target-set-v2`. Fresh exact-commit safety and code reviews remain
mandatory before G4 may pass.

Fresh independent safety and code reviews of exact commit `5491261b4` returned
NO-GO. In addition to authority leaks through combined revocation, deferred
conditions and third-party subjects, they found mismatches between fields the
gate inspected and fields the adapter consumed. Medication dose aliases,
illness optional fields, attachment meal slots, symptom dates, reminder
titles/start dates and lexical food splitting could therefore block legitimate
writes or dispatch different semantics. No deployment was attempted.

The tenth remediation makes the post-policy payload itself the authority:
aliases are canonicalized before validation, target comparison can remove only
safe unmentioned optional fields, and ToolGateway dispatches that same projected
payload. Historical symptom dates now survive through the real adapter;
recurring reminder dates, illness status/notes, attachment meal slots and
medication dosage conflicts are bound exactly. Combined revocations, future
conditions and third-party health subjects have no current-user write
authority. The capability contract is now `agent-capability-policy-v4` with
`authorized-target-set-v3`. Fresh exact-commit safety and code reviews remain
mandatory before G4 may pass.

### G5 Deployment Health: PENDING

Backend deploy and health checks have not started.

### G6 Production Verification: PENDING

Requires a read-only production query showing an illness tool call and no
write attempt. No health record may be created for the drill.

## Rollback

Rollback is the prior Backend release. There is no schema migration or data
backfill, so rollback requires no data repair.
