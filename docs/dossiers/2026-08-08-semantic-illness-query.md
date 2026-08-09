# Semantic Illness Query

| Field | Value |
|---|---|
| date | 2026-08-08 |
| status | in_progress |
| current_stage | G3 PASS after fourth dual NO-GO remediation; new exact-commit G4 pending |
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
inspected. Preserving an unknown illness severity requires one paired managed
PostgreSQL/SQLite migration plus the generated Web API contract update. Main risks are
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
- Fresh exact-commit safety and code reviews of `a7280179e` both returned
  NO-GO, so release again remained stopped. They reproduced revocation clauses
  separated from the write by conversational filler, implicit third-party
  subjects without `的`, policy/executor disagreement over legacy medication
  `dosage`, model-invented timestamps on date-only symptoms, unbound supplement
  fields, an API-level illness severity default, unstable aliases in the
  normalized payload and lexical `和牛` target collapse.
- The eleventh remediation treats the model output as a proposal and emits one
  server-owned canonical payload. Revocation walks back to the most recent real
  authority instead of treating filler as authority; subject ownership covers
  implicit friend/family forms; medication aliases share one parser in policy
  and executor; symptom timestamps are rebuilt from the frozen user timezone;
  supplement extras are projected out; canonical aliases are deleted after
  projection; and lexical `和牛` is protected before conjunction splitting.
- Unknown illness severity is now truly unknown end to end: schema and model
  use nullable severity, a managed PostgreSQL migration drops the old default
  and `NOT NULL`, generated Web types accept `null`, the illness page renders
  `未记录`, and Agent context never emits `None/10` or invents `5/10`.
  The capability boundary is versioned as `agent-capability-policy-v5` /
  `authorized-target-set-v4`.
- The final expanded classifier/query/policy/gateway/adapter/runtime/context
  suite passes 2,745 tests in three isolated groups (2,148 + 373 + 224), and
  Web TypeScript compilation plus page lint pass. A requested fresh
  `qwen3.7-max` 15-case
  run was attempted with synthetic text and zero database I/O, but the current
  TokenPlan credential returned `401 invalid_api_key` for every request before
  inference. This is recorded as an external evaluation blocker, not as a model
  pass or a product regression; the earlier valid 11/11 live run remains the
  latest completed model evidence.
- Fresh exact-commit safety and code reviews of `ed073c499` both returned
  NO-GO, and release remained stopped. They reproduced actual dispatch after
  conversational withdrawal, reported and hypothetical facts, third-party
  subjects, and follow-up corrections; incorrect medication count/strength and
  supplement-field semantics; food-conjunction ambiguity; non-canonical retry
  fingerprints; inability to clear illness severity; a missing SQLite
  migration pair; and unsafe rollback to an old non-null runtime after null
  rows exist.
- The twelfth remediation treats correction, ownership and provenance as
  relations in the authority set. A correction replaces the prior target and
  inherits only its write action/type context; report, hypothetical and
  third-party scope persist across adjacent clauses; explicit medication,
  severity and supplement facts are bound to the canonical dispatch payload.
  Food conjunctions preserve lexical compounds without protecting ordinary
  `米饭和牛肉`. Both turn-local and durable retry fingerprints now consume that
  same canonical payload.
- Nullable illness severity is now operationally complete: PATCH can
  explicitly clear it; PostgreSQL and SQLite have a paired managed migration;
  SQLite reconstruction preserves parent episodes, child progress rows,
  indexes and live foreign keys; historical score 5 rows remain unchanged
  because their provenance cannot be inferred; and the target-runtime rollback
  probe fails closed before starting an old writer if live rows violate its
  non-null contract. The capability
  boundary is versioned as `agent-capability-policy-v6` /
  `authorized-target-set-v5`.
- The final related semantic/classifier/policy/gateway/query/API/adapter/
  migration/rollback suite passes 2,757/2,757 tests in one process with
  coverage collection disabled. This clean run replaces the earlier parallel
  group evidence whose successful test processes contended only on the local
  coverage cache. Targeted Ruff, Python compilation, diff validation,
  generated system-map drift and Dossier consistency gates also pass. Fresh
  exact-commit reviews remain required.
- Fresh safety and code reviews of exact commit `bc4906d26` both returned
  NO-GO, so release again remained stopped. Real ToolGateway counterexamples
  showed that colonless and colon-introduced reported commands, deferred
  conditions, trailing withdrawal and arbitrary named third-party subjects
  could still dispatch. The reviewers also found unlisted correction forms,
  water aliases whose inspected and consumed payloads differed, invented
  adapter fields, lost compact supplement dosage/timing, and explicit null
  status reaching a non-null database column.
- The thirteenth remediation makes ownership a predicate relation rather than
  a list of people or kinship nouns. A health observation authorizes a trailing
  helper only when its governing subject reduces to the current user; an
  attributed colon is a provenance boundary; deferred, revoked and corrected
  frames are resolved before target compilation. Direct compound requests such
  as `计算热量和营养并记录饮食` remain writable without lending authority to
  reported commands.
- Numeric record aliases are now conflict-checked, collapsed and projected to
  the one field shape consumed by each adapter. Model-invented fields are
  discarded before dispatch and retry fingerprinting. Explicit and compact
  supplement phrases preserve canonical name, dosage and timing. The
  capability boundary is versioned as `agent-capability-policy-v7` /
  `authorized-target-set-v6`.
- Illness PATCH distinguishes omission from explicit null: omission leaves
  status untouched, while JSON null is rejected before it can reach the
  non-null column. Generated Web and Mobile contracts expose `status?: string`
  and retain nullable severity. The expanded semantic/policy/gateway group
  passes 2,040 tests; the first 2,824-test aggregate found one over-blocked
  positive compound diet request, which now has a focused regression and
  passes with the shared authority suite.
- The clean final single-process semantic/classifier/policy/gateway/query/API/
  adapter/migration/runtime aggregate passes 2,827/2,827 tests. Targeted Ruff,
  Python compilation, diff validation, generated system-map drift and Dossier
  consistency checks also pass. This is the G3 evidence for the next exact
  commit; two brand-new G4 reviewers remain mandatory.
- A brand-new code reviewer of exact commit `56e35be86` returned NO-GO and
  release remained stopped. The reviewer proved that a direct command could
  place an arbitrary subject between the write action and health predicate:
  `记录张三体重71kg`, `请记录小明体重71kg` and `记录邻居感冒` all reached the
  real Gateway and would write into the authenticated user's records. This was
  not a vocabulary miss; the owner parser incorrectly treated any predicate
  preceded by a write verb as current-user owned.
- The fourteenth remediation parses both sides of the relation. The initiator
  before a write action must reduce to a direct current-user request, and the
  subject between the action and each health predicate must reduce to the
  current user, time modifiers or structural labels. Every later predicate in
  the same clause is checked again, so a second arbitrary subject cannot borrow
  the first current-user fact. Denied observations and attribute continuations
  do not poison a later legitimate write. The boundary is versioned as
  `agent-capability-policy-v8` / `authorized-target-set-v7`; clean aggregate
  evidence and two new exact-commit reviews are pending.
- The fourteenth remediation's clean single-process semantic/classifier/policy/
  gateway/query/API/adapter/migration/runtime aggregate passes 2,850/2,850
  tests. This includes real Gateway non-dispatch for direct and colon-introduced
  arbitrary subjects (including compound surnames that begin with direction
  characters), legal current-user object and body-location requests,
  inline tool-call recovery, historical backfills and all previous alias/
  migration/rollback controls. Targeted static and structural gates must pass
  before the new exact commit is created.
- Before final review, latest `origin/main` commit `f65c4055d` was merged so the
  semantic boundary is reviewed together with the newly released atomic health
  correction, receipt-identity, non-finite numeric and whole-record deletion
  protections. The combined capability contract is now
  `agent-capability-policy-v9`: it retains `authorized-target-set-v7` and also
  exposes `record-delete-evidence-v2`.
- Merge-focused tests first found policy-reason precedence conflicts and stale
  adapter fixtures. The resolution keeps exact whole-record delete grammar
  authoritative only for true delete/cancellation frames, while update,
  clinician-provenance and recipe-replay denials keep their narrower reasons.
  It also treats current-user body locations, absolute dates and reminder
  schedule text as target context rather than third-party subjects; named
  third-party body observations still produce no authority.
- The final post-merge single-process compatibility run passes 3,482/3,482
  Backend tests. Mobile structured receipt/card regressions pass 111/111;
  Mobile and Web TypeScript compilation pass. Targeted Ruff, Python
  compilation, diff validation and structural document gates are run against
  this same merge result before the exact review commit is created.
- Independent safety and code reviews of exact merge commit `69f7d0301` both
  returned NO-GO, so push and deployment remained stopped. The safety review
  proved that update authority was not bound to the owner-scoped record and
  exact patch, and that a later third-party attribution could fail to revoke an
  earlier apparent current-user write. The code review proved that record
  families outside numeric and supplement writes could retain model-invented
  persisted fields.
- The remediation versions the capability boundary as
  `agent-capability-policy-v11` with `record-update-evidence-v2`. Water and
  illness corrections now require an owner-scoped candidate or explicit
  user-visible record identifier plus an exact user-stated patch; unsupported
  update families fail closed. Posterior ownership statements revoke earlier
  authority. Every supported record family is projected to user-evidenced
  fields, while nutrition estimates and other derived values require an opaque
  server authorization that model JSON cannot forge. Goal, sleep and reminder
  defaults are reconstructed deterministically instead of trusted from the
  proposed payload.
- The clean remediation aggregate passes 3,504/3,504 Backend tests, including
  real-Gateway non-dispatch for wrong-record corrections, posterior third-party
  ownership and model-invented exercise, symptom, excretion, sleep, mood, goal
  and reminder fields. Ruff, Python compilation, `git diff --check`, generated
  system-map drift and Dossier consistency checks pass against the same tree.
- A fresh requested `qwen3.7-max` six-case boundary evaluation attempted before
  inference with no production reads or writes, but the TokenPlan endpoint
  returned `401 invalid_api_key`. This run is recorded as externally blocked,
  not as a model pass or failure; the earlier valid live evidence remains
  historical evidence only.
- Fresh safety and code reviews of exact commit `b7f88e64e` both returned
  NO-GO, so push and deployment remained stopped. They proved that update
  speech acts still accepted quoted, hypothetical and posterior third-party
  ownership; arbitrary proposed IDs could bypass owner-scoped discovery;
  shadow mode could dispatch a blocked health write; reminder continuation
  could inherit stale assistant prose; illness updates used substring matching
  and overclaimed partial recovery; and several legitimate record families
  either failed closed or dropped explicit exercise values.
- The sixteenth remediation versions the boundary as
  `agent-capability-policy-v12` / `authorized-target-set-v8` /
  `record-update-evidence-v3`. Update authorization now requires a direct,
  affirmative, current-user speech act plus a same-turn owner-scoped list and
  an exact server-projected patch. Illness identity uses normalized equality;
  partial recovery maps to `improving`; all blocked health-record decisions are
  hard denials in both enforce and shadow modes. Reminder continuation is
  valid only for an adjacent user create request followed by the assistant's
  direct schedule question, and title/interval authority comes only from the
  user's text.
- Deterministic creation projection now covers `remember`, `event`,
  `supplement_group`, rhinitis check-ins and exercise distance/repetitions/sets
  without retaining model-invented fields. Real Gateway and full executor
  regressions prove owner-scoped illness list → exact update, stale reminder
  rejection, posterior ownership revocation and zero dispatch for semantic
  denials in both policy modes.
- The clean, single-process post-remediation aggregate passes 3,681/3,681
  Backend tests in 186.77 seconds. Targeted Ruff, Python compilation and
  `git diff --check` pass. Latest `origin/main` commit `140bd788a` was then
  merged; it changes only the iOS privacy-manifest release surface. Its Backend
  App Store preflight passes 4/4 and Mobile app-config suite passes 17/17.
  Structural document checks passed against the exact merge tree.
- Fresh code and safety reviews of exact commit `aa766b59c` both returned
  NO-GO, so push and deployment remained stopped. The code review found that
  colloquial partial recovery could be overclaimed as resolved, three public
  record contracts were incorrectly blocked, and the new contract tests did
  not reach the real executor adapters. The safety review reproduced real
  update dispatch for quoted, hypothetical, third-party, revoked, corrected
  and posterior-owner utterances in enforce and shadow modes.
- The seventeenth remediation versions the boundary as
  `agent-capability-policy-v13` / `authorized-target-set-v9` /
  `record-update-evidence-v4`. Update authority now rejects metalinguistic and
  quoted text, expanded hypothetical and third-party frames, posterior water
  ownership and trailing keep-original revocations. Self-correction authorizes
  only the final value. Colloquial `好了…` modifiers remain `improving`, while
  terminal or explicit complete recovery may resolve an episode.
- Deterministic current-user contracts now cover subjectless batch medicine
  intake, stable preference memory and lifecycle arrival events while matching
  named third-party subjects fails closed. Real executor tests prove these
  positive contracts reach their actual adapters, and quoted updates perform
  no PUT in either policy mode. The clean single-process compatibility run
  passes 3,707/3,707 Backend tests in 190.50 seconds. Targeted Ruff, Python
  compilation and `git diff --check` pass; repository structural gates and two
  brand-new exact-commit reviews remain required.
- Fresh code and safety reviews of exact commit `5e385effc` both returned
  NO-GO, so push and deployment remained stopped. The safety review reproduced
  real PUTs for additional metalinguistic, quotation, trailing-hypothetical,
  posterior-owner and revocation forms; an incomplete correction wrote the
  superseded value, and one health-manage block reason still dispatched in
  shadow mode. It also reproduced POSTs from quoted implicit events. The code
  review found uncertain recovery overclaimed as resolved, inverted third-party
  preference ownership, and overly narrow public-contract phrasing.
- The eighteenth remediation versions the boundary as
  `agent-capability-policy-v14` / `authorized-target-set-v10` /
  `record-update-evidence-v5`. It models quotation delimiters, metalinguistic
  provenance, update-result hypotheticals, posterior ownership and revocation
  as non-authorizing structures. A correction marker must compile a unique
  final value or the update fails closed. Every blocked `health_record` and
  `health_manage` decision is now a hard denial in both enforce and shadow.
- Real executor regressions prove all review examples perform no forbidden PUT
  or POST, while final-value corrections dispatch only the canonical final
  payload. Current-user public phrases and natural variants reach the real
  supplement-batch, memory and lifecycle-event adapters; named or inverted
  third-party variants never post. Uncertain recovery remains `improving`.
  The clean single-process compatibility run passes 3,771/3,771 Backend tests
  in 189.36 seconds. Targeted Ruff, Python compilation and `git diff --check`
  pass; repository structural gates and two brand-new exact-commit reviews
  remain required.
- Latest `origin/main` commit `fb05eca0d` was integrated after G3. It changes
  only the separate iOS build-245 verification Dossier; the Backend runtime and
  test tree are byte-identical to the 3,771-test run. System-map drift and all
  102 Dossier consistency checks pass on the merged tree.

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

Fresh safety and code reviews of exact commit `a7280179e` returned NO-GO and no
deployment was attempted. Their concrete counterexamples crossed both semantic
ownership and payload-identity boundaries: conversational filler hid a later
revocation, implicit friend/family subjects gained current-user authority,
medication `dosage` meant different things to policy and executor, a date-only
symptom retained a model-invented time zone, and nullable/user-omitted fields
were still defaulted or consumed downstream.

The eleventh remediation makes payload identity and claim ownership explicit.
The authorization set revokes the nearest actual authority through filler;
third-party fact ownership handles omitted possessive particles; every consumed
medication alias goes through one shared canonical parser; symptom dates and
times are reconstructed from the frozen turn context; unmentioned supplement
and illness fields are projected out; and canonical aliases are removed before
fingerprinting and dispatch. Illness severity now has a real `null` storage and
cross-client contract instead of a hidden score of 5. A managed PostgreSQL
migration and matching Web/API types are part of the same release. Fresh exact-
commit safety and code reviews are still mandatory before G4 may pass.

Fresh safety and code reviews of exact commit `ed073c499` returned NO-GO and no
deployment was attempted. The twelfth remediation replaces the remaining
surface patches with relation-aware authority: later corrections supersede the
old target, source ownership and hypothetical/report scope cross clause
boundaries, and explicit values survive only through one canonical payload.
Retry identity is computed after canonicalization. Paired migrations and a
target-aware live-data probe make nullable severity safe in both forward
migration and old-code rollback. New independent reviews of the next exact
commit are mandatory before G4 may pass.

Fresh safety and code reviews of exact commit `bc4906d26` returned NO-GO and no
deployment was attempted. They demonstrated actual dispatch across reported,
deferred, revoked and arbitrary-subject frames, plus payload identity gaps in
water and supplement writes and an API nullability mismatch for illness status.
The thirteenth remediation resolves grammatical owner/provenance relations
before compilation, projects numeric and supplement writes into exact
adapter-consumed payloads, and makes PATCH status optional but non-null. A clean
G3 rerun and two brand-new exact-commit reviewers are mandatory; neither prior
review can be reused.

A fresh code review of exact commit `56e35be86` returned NO-GO before push or
deployment. Direct-object forms such as `记录张三体重71kg` bypassed ownership by
placing the third-party name after the action and before the health predicate.
Failure-first tests reproduced real Gateway dispatch. The fourteenth
remediation validates action initiator and target subject separately, carries
ownership across clauses, rechecks every health predicate, and retains current-
user direct, object-fronted, contrast, historical-backfill and attribute
continuation positives. A new commit and two brand-new reviewers are required.

Latest main is now integrated before that final review. The merged policy keeps
the fourteenth ownership boundary and main's atomic correction/delete evidence
boundary in one deterministic choke point. Post-merge G3 is green; two
brand-new reviewers must review the forthcoming merge commit itself, and any
NO-GO still stops push and deployment.

The two brand-new reviews of exact merge commit `69f7d0301` both returned
NO-GO. Safety review showed that `health_manage.update` could substitute an
unrelated owner-scoped record and patch, and that posterior declarations such as
`这是小明的` or `实际上是妈妈的` did not reliably revoke the preceding write.
Code review showed that exercise, symptom, excretion, sleep, mood, goal and
reminder payloads could preserve model-invented persisted fields. No push or
deployment was attempted.

The fifteenth remediation makes authorization an exact server-owned mutation
plan. Updates bind record type, owner-scoped record identity and exact patch;
unsupported update semantics fail closed. Record creation projects every
adapter-consumed field from the user's utterance, frozen turn context or an
opaque server-side derivation marker, so a proposed tool-call payload cannot
grant itself authority. Later third-party ownership retracts preceding current-
user authority. Real Gateway and executor regressions cover both negative
attacks and legitimate water, illness, meal-estimate, sleep-start and reminder
continuation controls. The clean G3 aggregate is green; a new exact commit and
two different independent reviewers remain mandatory before G4 may pass.

Fresh safety and code reviews of exact commit `b7f88e64e` both returned NO-GO
before push or deployment. The safety review reproduced update dispatch across
quoted, hypothetical, third-party and arbitrary-ID frames, plus a shadow-mode
health-write bypass and false revocation of explicit current-user ownership.
The code review reproduced missing rhinitis/event/remember/supplement-group
writes, stale reminder continuation, substring illness identity, partial
recovery overclaim, dropped exercise selectors and a test fixture that bypassed
the real Gateway.

The sixteenth remediation closes those findings at the semantic choke point.
Updates require direct current-user authorization, owner-scoped identity and an
exact projected patch; the same hard denial applies in shadow mode. Reminder
continuations require adjacent user and assistant turns and derive authority
only from the user's request. Supported non-numeric record families now receive
server-owned deterministic payloads, and real Gateway/executor tests replace
the bypassing fixture. The clean 3,681-test G3 aggregate and latest-main release
checks are green. A new exact commit and two brand-new reviewers are mandatory;
neither reviewer of `b7f88e64e` may be reused.

Fresh code and safety reviews of exact commit `aa766b59c` both returned NO-GO
before push or deployment. The code review reproduced an overclaim from
`好了一丢丢`, false denials for the public medicine-batch, memory and event
contracts, and insufficient executor-path coverage. The safety review
reproduced update dispatch from `原文如下`, `要是…会怎样`, third-party wishes,
`先保持原样`, superseded values and posterior `这杯水属于小明` ownership; quoted
text reached a real PUT in both enforce and shadow modes.

The seventeenth remediation compiles update authority from the user's final,
direct, current-user speech act rather than the presence of an update phrase.
Quoted/metalinguistic, hypothetical, third-party, revoked and posterior-owner
frames cannot authorize dispatch; an explicit correction binds only its final
value. Subjectless public record phrases receive narrowly typed deterministic
payloads and named third-party variants fail closed. Real Gateway and executor
adapter tests cover both directions. The clean 3,707-test G3 aggregate is green;
a new exact commit and two brand-new reviewers who did not review
`aa766b59c` are mandatory before G4 may pass.

Fresh safety and code reviews of exact commit `5e385effc` both returned NO-GO
before push or deployment. The safety review crossed the real executor with
additional quote, metalinguistic, conditional, posterior-owner and revocation
forms, showed two shorthand corrections could write the superseded value, and
showed a blocked `health_manage` call still dispatched in shadow. It also
created implicit events from quoted examples. The code review reproduced
uncertain recovery as resolved, inverted third-party preference ownership and
false denials for natural variants of the three public record contracts.

The eighteenth remediation treats those as relations rather than independent
keywords. Provenance and quotation scope, hypothetical result framing,
posterior ownership, revocation and correction supersession all participate in
the same authorization decision. Any blocked health mutation is hard in shadow;
an incomplete correction is non-authorizing. Deterministic helpers accept
narrow current-user paraphrases but reject named or inverted third-party
subjects. Real Gateway plus executor tests cover every reported attack and
positive contract. The clean 3,771-test G3 aggregate is green; a new exact
commit and two brand-new reviewers who did not review `5e385effc` are mandatory
before G4 may pass.

### G5 Deployment Health: PENDING

Backend deploy and health checks have not started.

### G6 Production Verification: PENDING

Requires a read-only production query showing an illness tool call and no
write attempt. No health record may be created for the drill.

## Rollback

Rollback is the prior Backend and Web release. The migration only relaxes the
illness severity column and removes its default. The immutable target-runtime
probe inspects live rows while sockets and writers are stopped; an older target
whose model requires non-null severity is rejected if any null row exists.
Historical score 5 rows are preserved because old-default provenance is not
recoverable. Rollback must never silently recreate or backfill 5 as a health
fact.
