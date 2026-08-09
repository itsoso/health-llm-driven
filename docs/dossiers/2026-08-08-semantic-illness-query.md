# Semantic Illness Query

| Field | Value |
|---|---|
| date | 2026-08-08 |
| status | in_progress |
| current_stage | G3 PASS on mainline-synced tree; new exact-commit G4 pending |
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
- Fresh code and safety reviews of exact merge commit `bc36e13af` both returned
  NO-GO before push or deployment. They reproduced a partial-recovery overclaim,
  posterior and named third-party public-record writes, false denial of natural
  current-user public phrases, quoted/metalinguistic/hypothetical/revoked update
  dispatch, ambiguous multi-record update targeting and shadow-mode PUT/POST
  attempts. Failure-first Gateway and real Executor tests cover every reported
  case in both enforce and shadow modes.
- The nineteenth remediation versions the boundary as
  `agent-capability-policy-v15` / `authorized-target-set-v11` /
  `record-update-evidence-v6`. Update authority now resolves quote/provenance,
  hypothetical result, revocation, final correction, exact target cardinality
  and current-user ownership before an owner-scoped patch can dispatch. Clock
  colons are range-validated so numeric provenance cannot masquerade as time;
  full parenthetical commands are non-authorizing while ordinary measurement
  parentheses remain usable. Public supplement-batch, memory and lifecycle-event
  writes bind narrow current-user forms and retract provisional authority when
  a later clause assigns the fact or trip to another person. Uncertain
  `一点点好了` remains `improving`.
- The clean single-process related compatibility run passes 3,830/3,830 Backend
  tests in 189.08 seconds. It includes the original illness query, classifier,
  semantic scope parser, exact capability policy, ToolGateway, real Executor,
  query readers, migrations, runtime schema checks, receipts and behavioral
  battery. Targeted Ruff, Python compilation and `git diff --check` also pass.
  System-map drift and all 102 Dossier consistency checks also pass. Two fresh
  exact-commit G4 reviews remain required before release.
- Fresh code and safety reviews of exact commit `b2daa542a` both returned
  NO-GO before push or deployment. Real Executor probes found that source,
  beneficiary, revocation and multi-target update frames could still reach PUT;
  colon/message/log fragments and named subjects could reach event POST; water
  corrections could retain the superseded value or wrong litre unit; uncertain
  and relapsed illness states could be overclaimed; and one ordinary current-
  user event plus explicit record-ID update were falsely denied.
- The latest remediation replaces negative phrase accumulation with positive
  authorization evidence. A water update must be a full direct current-user
  request bound to either an exact owner-scoped record ID or a unique recent
  owner-scoped value, plus one deterministic final amount. Illness updates bind
  the exact owner record name and a narrow recovery-state compiler; negated,
  relapsed or contradictory recovery fails closed. Implicit lifecycle events
  cannot borrow authority from a message, log, example or another person's
  subject. Goal destination language such as `达到` is structurally separated
  from an arrival event. The code contract is
  `agent-capability-policy-v16` / `authorized-target-set-v12` /
  `record-update-evidence-v7`.
- Failure-first coverage includes every new code/safety counterexample through
  the real Gateway and Executor in both enforce and shadow modes, final-value
  correction and litre-to-millilitre projection, exact/shorthand multi-ID
  rejection, direct record-ID updates, negated illness recovery and positive
  current-user event controls. The core policy/Gateway/scope group passes
  1,786/1,786 tests; adjacent intent/write groups pass 842/842. The final
  single-process integration aggregate passes 3,953/3,953 Backend tests in
  210.47 seconds under the production `Asia/Shanghai` calendar basis. Targeted
  Ruff, Python compilation and `git diff --check` pass on the same tree.
- The requested live `qwen3.7-max` evaluation used synthetic text, the real
  production tool schema and zero database I/O. It selected the intended tool
  family in 6/6 cases: exact/paraphrased/negated illness history stayed on
  `health_query`, quoted update text did not write, direct correction selected
  owner-scoped `health_manage.list`, and explicit illness creation selected
  `health_record`. In the create contrast it invented a `start_date`, which is
  retained as evidence that model JSON is only a proposal and must be projected
  by the deterministic gate. Strict automatic tool mode passed; forced
  `tool_choice` returned endpoint `400 invalid_parameter_error`, an endpoint
  limitation rather than a model or product inference failure.
- Fresh exact-commit code and safety reviews of `f4f8bde35` both returned
  NO-GO, so it was not pushed or deployed. Through the real Gateway and
  Executor in both policy modes they reproduced: visible illness record IDs
  falling back to a different named owner record; negated, worsening and
  recurrent illness being persisted as recovery; a write verb erasing a named
  event owner; message and parenthetical-trip provenance reaching event POST;
  negated water values or a correction back to the persisted value reaching
  PUT; and false denial of `我的饮水记录`, clear active illness, and Chinese
  arrival-time forms.
- The next remediation versions the boundary as
  `agent-capability-policy-v17` / `authorized-target-set-v13` /
  `record-update-evidence-v8`. Visible identity is checked before name fallback.
  Illness state uses an ordered closed compiler: relapse/worsening and
  contradiction precede recovery, while an exact `还没好` remains a supported
  active state. Event parsing removes only the request/action scaffold and then
  resolves the remaining subject; external provenance and parenthetical owner
  transfer govern the entire semantic segment. Water correction syntax now
  distinguishes `不，是…` from `不是…`, and a final value equal to the verified
  persisted amount is a non-dispatched no-op. Current-user possessives and
  Chinese time-of-day/numeral clocks remain positive controls.
- Failure-first coverage reproduced 39 review findings before implementation.
  The post-remediation policy/Gateway/scope group passes 1,848/1,848 tests;
  adjacent intent/write groups pass 842/842; and the final single-process
  integration aggregate passes 4,006/4,006 Backend tests in 172.72 seconds on
  the production `Asia/Shanghai` calendar basis. Targeted Ruff, Python
  compilation and `git diff --check` pass. Repository structural gates and two
  fresh reviews of the next exact SHA remain mandatory.
- Fresh exact-commit code and product-safety reviews of `00a63b19d` both
  returned NO-GO, so it was not pushed or deployed. They reproduced generic
  illness identifiers written as `记录编号/ID` falling back to a different
  record, locally negated recovery (`并无/尚无/绝非/算不上/…不了`) reaching
  PUT, external event provenance (`摘录自/据消息/据日志`) and bare
  parenthetical ownership reaching POST, and false denial of the current-user
  possessive `我自己的`, the positive state `明显改善`, and Chinese clock forms
  such as `三点半/三点一刻/零点`.
- The current remediation versions the deterministic boundary as
  `agent-capability-policy-v18` / `authorized-target-set-v14` /
  `record-update-evidence-v9`. Record identity now parses a structured generic
  identifier marker independently of the illness name. Recovery compiles only
  after local polarity and relapse checks; positive improvement predicates are
  retained. Current-user possessives use one compositional owner grammar.
  Event authority separately resolves source provenance, bare owner resources,
  and Chinese numeral clock suffixes. Failure-first tests cover the reported
  forms through the real Gateway and Executor in both enforce and shadow modes,
  with positive controls for `我的行程` and explicit improvement. The updated
  policy/Gateway/scope group passes 1,902/1,902 tests and the changed adjacent
  execution/query/intent surface passes 1,633/1,633 tests.
- A wider repository run exposed a stable compatibility regression in the
  existing meal-photo contract: the newly classified hypothetical
  `假设这餐吃了1/2` remained non-writing but received a generic read-only prompt
  instead of the deterministic fraction-rejection reason. The same 31-case
  subset passed on clean `origin/main`, proving it was branch-introduced. The
  prompt compiler now gives an explicit safety-gate rejection precedence over
  a generic read/advice classification; the complete meal-photo file passes
  103/103. The final single-process feature integration aggregate passes
  3,836/3,836 tests in 153.75 seconds on the production `Asia/Shanghai`
  calendar basis. Structural gates and two new exact-commit G4 reviews remain
  mandatory.
- Latest clean `origin/main` commit `a26477b30` was merged before G4. Its three
  commits affect only mobile chat-header presentation, the iPhone acceptance
  harness and planning documents; no Backend file overlaps this remediation.
  On the merged tree, the Backend policy/Gateway/scope plus meal-photo
  compatibility group passes 2,005/2,005, the changed mobile component suites
  pass 8/8, and the iPhone acceptance harness passes 12/12. A new exact-commit
  dual review remains mandatory before push or deployment.
- Fresh code and product-safety reviews of exact commit `d857d9020` both
  returned NO-GO, so push and deployment remained stopped. Real
  Executor/Gateway probes exposed locally negated or uncertain illness states,
  two additional visible record-ID shapes, sourced and third-party travel
  ownership, long-tail or multi-entity illness reads, incorrect/missing read
  windows, colloquial Chinese quarter/half-hour clocks and ambiguous related
  event times.
- The v20 remediation versions the boundary as
  `agent-capability-policy-v20` / `authorized-target-set-v16` /
  `record-update-evidence-v11`. Illness predicates are compiled from local
  grammatical polarity and epistemic certainty; explicit visible IDs never
  fall through to another owner record. Parenthetical/source provenance and
  resource ownership use structural relations across `行程/旅程/出行`, including
  Latin-script names. Numeric and Chinese half/quarter-hour clocks normalize to
  one value, while multiple related clocks fail closed. Illness read syntax
  projects one exact long-tail entity and year window from the current turn,
  corrects a conflicting model proposal for known illness terms, and requires
  clarification for multiple entities.
- The final v20 policy/Gateway/scope group passes 2,091/2,091 tests. All 25
  changed Backend feature-test files pass 3,724/3,724 in one process on the
  production `Asia/Shanghai` calendar basis, and the adjacent meal-photo
  compatibility file passes 103/103. Targeted Ruff, formatting, Python
  compilation and `git diff --check` pass on the same tree. Repository
  structural checks and two fresh exact-commit G4 reviews remain mandatory.
- Fresh code and product-safety reviews of exact commit `fbd0b6314` both
  returned NO-GO, so it was not pushed or deployed. Real Executor/Gateway
  probes found more epistemic and relapse illness forms, bare/parenthetical
  record IDs, source and owner relation variants, midnight/evening conversion,
  long-tail query word order, and shadow-mode read blocks that still dispatched.
  They also found one legitimate explicit current-user water correction was
  falsely denied.
- Latest `origin/main` commits `6a54bd054` and `72b678d32` were merged before
  final review. They change only the separate iOS build-253 release-evidence
  Dossier and do not overlap Backend runtime or tests.
- The v21 remediation versions the boundary as
  `agent-capability-policy-v21` / `authorized-target-set-v17` /
  `record-update-evidence-v12`. A clause-local epistemic grammar now makes
  uncertain recovery/active-state predicates non-authorizing, and broader
  relapse morphology takes precedence over recovery. Generic visible `ID`
  syntax remains an exact constraint. Event source and ownership are parsed as
  source/owner/resource relations across determiners, ownership verbs and
  owner-noun forms. Daypart normalization maps `凌晨十二点` to hour 00 and
  `昨晚` to PM. Illness-query syntax supports entity-before-window and direct
  history forms, uses conservative illness morphology when the model proposes
  another domain, splits additional multi-entity connectors, and makes
  clarification a hard denial in both enforce and shadow. Explicit owner-bound
  water corrections may include a verified old value.
- The final v21 policy/Gateway/scope group passes 2,190/2,190 tests. All 25
  changed Backend feature-test files pass 3,823/3,823 in one process on the
  production `Asia/Shanghai` calendar basis, and the adjacent meal-photo file
  passes 103/103. The 268-case focused real-boundary matrix, targeted Ruff,
  formatting, Python compilation and `git diff --check` also pass. Repository
  structural checks and two fresh exact-commit reviews remain mandatory.
- Fresh code and product-safety reviews of exact commit `0cc687a2e` both
  returned NO-GO, so it was not pushed or deployed. Real Executor/Gateway
  probes found that uncertain or recurrent illness could still inherit a
  recovery substring, generic visible ID forms could fall back to record 71,
  sourced or third-party travel facts could reach POST, midnight/evening clocks
  could be shifted by twelve hours, and arbitrary long-tail or multi-entity
  illness reads could follow a conflicting model dimension.
- The v22 remediation replaces the remaining negative-vocabulary approach with
  closed positive authority. An illness update is compiled only from one
  supported final state assertion; unknown qualifiers and extra clauses fail
  closed, while a later explicit assertion governs both state and date. Any
  generic visible identifier is an exact target constraint. Event segments may
  contain only a current-user arrival/write relation and trusted time context;
  unmodelled source, owner or parenthetical clauses cannot authorize POST.
  Query syntax extracts an arbitrary single history entity from the user's
  turn, projects it only through the illness reader, hard-blocks conflicting
  model dimensions and requires clarification before any multi-entity read.
  Dayparts use explicit night/afternoon categories, including `午夜十二点` and
  `昨晚一点`. The boundary is versioned as `agent-capability-policy-v22` /
  `authorized-target-set-v18` / `record-update-evidence-v13`.
- The final v22 policy/Gateway/scope group passes 2,298/2,298 tests. All 25
  changed Backend feature-test files pass 3,931/3,931 in one process on the
  production `Asia/Shanghai` calendar basis, and the adjacent meal-photo file
  passes 103/103. Ruff, focused formatting, Python compilation and
  `git diff --check` pass. Repository structural checks and two new reviews of
  the next exact SHA remain mandatory.
- Fresh code and product-safety reviews of exact commit `3f3119834` both
  returned NO-GO, so it was not pushed or deployed. They found that a generic
  non-illness history could be projected into illness, natural read wrappers
  and additional multi-entity relations could fall through to the model scope,
  symptom-write recovery could pollute a read payload, and supported exact-ID,
  latest-state, current-user parenthetical and early-evening forms were falsely
  denied or normalized incorrectly. Their real-chain matrices used only
  synthetic owner records and fake adapters in enforce and shadow modes.
- The v23 remediation reduces the complete history request to one residual
  entity expression before considering model JSON. A known non-illness entity
  conflicts with an illness or missing-dimension proposal; an unknown single
  long-tail entity may project only when the model proposes illness; any
  coordination relation or punctuation that yields multiple entities is a
  hard clarification block. Symptom-field recovery is tool-local to
  `health_record`, so a read payload cannot acquire write fields. One shared
  visible-ID parser now both constrains the owner record and removes the ID from
  the final-state assertion. Direct update scope may carry adversative clauses,
  but only the closed final-state compiler can produce the exact patch. Trusted
  ID colons, current-user event parentheticals and the night/early-evening clock
  boundary are separately modeled. The contract is
  `agent-capability-policy-v23` / `authorized-target-set-v19` /
  `record-update-evidence-v14`.
- Failure-first coverage reproduced 59 review failures in a 163-case real
  Gateway/Executor boundary group; the group now passes 163/163. The complete
  policy/Gateway/scope group passes 2,367/2,367 tests. All 25 changed Backend
  feature-test files pass 4,003/4,003 in one process on the production
  `Asia/Shanghai` calendar basis, and the adjacent meal-photo file passes
  103/103. Ruff, focused formatting, Python compilation and `git diff --check`
  pass. Repository structural checks and two new reviews of the next exact SHA
  remain mandatory.
- Latest clean `origin/main` commit `32a216cb6` was merged before final review.
  It adds authenticated conversation no-store headers and changes only
  `backend/app/api/agent.py`, its 55-case API test file and two separate design
  documents; it does not overlap the v23 semantic boundary. On the merged tree,
  the conversation API suite passes 55/55 and the 163-case real semantic
  boundary group remains 163/163. The merged SHA itself must receive both fresh
  G4 reviews before push or deployment.

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

Fresh code and safety reviews of exact commit `bc36e13af` both returned NO-GO,
so push and deployment again remained stopped. The code review found
`一点点好了` overclaimed resolution, posterior ownership could still write the
wrong person's supplement, preference or travel event, and three ordinary
current-user paraphrases were falsely denied. The safety review demonstrated
real PUTs from additional quote delimiters, metalinguistic and hypothetical
frames, third-party beneficiaries, final no-op/revocation clauses and an
ambiguous two-ID request; it also demonstrated real third-party event and
supplement POSTs in enforce and shadow modes.

The nineteenth remediation resolves those structures before payload binding.
Quotation and full parenthetical scope, colon provenance, hypothetical result,
revocation, final correction, update target cardinality and owner/beneficiary
relations are all non-transferable authority. Numeric colons must be valid
24-hour clock values instead of merely digit-delimited text. Posterior owners
can retract a provisional event or health-record target, while an explicit
current-user owner preserves it. Natural current-user supplement, preference
and arrival variants compile to the same server-owned public contract, and
named/inverted third-party variants perform no POST. Embedded measurement
parentheses and ordinary current-user update phrasing remain valid controls.
The contract is now `agent-capability-policy-v15` /
`authorized-target-set-v11` / `record-update-evidence-v6`; the clean 3,830-test
G3 run is green. Two fresh reviews of the forthcoming exact commit are still
mandatory before G4 may pass.

Fresh code and safety reviews of exact commit `b2daa542a` both returned NO-GO,
so push and deployment remained stopped. The reviews crossed the real Executor
with delegated/source/revoked and multi-ID updates, superseded correction
values, quoted and attributed events, named third-party arrivals and uncertain
illness recovery. They also caught false denials of a temporal current-user
event and a natural explicit record-ID correction.

The latest remediation makes direct positive evidence the authority rather
than a growing blacklist. The model may choose a semantic tool, but only the
deterministic policy may establish the current owner, exact record, operation
and canonical patch. Exact visible IDs and uniquely resolved recent records are
both supported; third-party, quotation, provenance, revocation and ambiguous
target frames cannot satisfy the positive grammar. Illness and lifecycle-event
state are compiled separately from the tool proposal. A new exact commit and
two fresh independent reviews of that SHA are mandatory before G4 may pass.

Fresh code and safety reviews of exact commit `f4f8bde35` both returned NO-GO,
so push and deployment again remained stopped. Both reviewers used the real
Executor/Gateway with fake local adapters and no production data. Their
findings crossed four authority relations rather than isolated wording:
explicit identity could lose to name fallback; negative/contradictory disease
state could lose to a positive substring; a write verb or later sourced text
could grant event ownership; and correction syntax could turn a denial or
return-to-current-value into a mutation. They also found legitimate current-
user possessive, active-state and Chinese-time expressions were over-blocked.

The v17 remediation gives each relation one deterministic owner. User-visible
record IDs are authoritative constraints; the disease state compiler has
priority-ordered terminal outcomes; event subject/provenance is evaluated over
the whole semantic segment after removing only action scaffolding; and water
correction compiles a unique changed value or no mutation at all. The clean
4,006-test G3 aggregate is green. A new exact commit and two fresh independent
reviews are mandatory; neither prior NO-GO can be reused.

Fresh code and safety reviews of exact commit `ceb8ae78c` both returned NO-GO,
so push and deployment again remained stopped. The reviewers reproduced
negative, uncertain, relapsed and contradictory illness language being written
as recovery; additional visible-ID forms falling back to another record;
third-party or sourced travel facts reaching POST; and Chinese event clocks
being discarded. They also showed that a model proposal omitting the illness
keyword/window could broaden the original read to all illness history, while
ordinary first-person water-owner phrases were falsely denied.

The v19 remediation compiles local predicate polarity before selecting an
illness state, including explicit negation of worsening followed by a positive
recovery assertion. Uncertain recovery remains non-authorizing. Generic record
identity accepts the reviewed number forms but never falls back when an
explicit ID conflicts. Illness reads are projected from the current turn to an
exact `dimension + keyword + optional window` plan regardless of model JSON.
Arrival facts and write actions may span clauses, but a clock is merged only
when one trusted arrival clause names the same destination as the event title
and contains one unique clock. Current-user water ownership and event
third-party/provenance grammar are resolved independently of write verbs. The
core policy/Gateway/scope suite passes 1,964/1,964 tests; all 25 changed feature
test files pass 3,597/3,597; and the adjacent meal-photo compatibility file
passes 103/103. A new exact commit and two fresh independent reviews of that
SHA remain mandatory before G4 may pass.

Fresh code and product-safety reviews of exact commit `d857d9020` both returned
NO-GO, so it was not pushed or deployed. The findings crossed the same four
server-owned relations: illness-state polarity/certainty, exact visible record
identity, event provenance/ownership/time and illness-read entity/window
projection. The v20 remediation resolves those relations before adapter
dispatch, adds failure-first real Executor coverage in enforce and shadow
modes, and preserves positive controls for explicit current-user facts and
unambiguous recovery. The clean G3 evidence is green; a new exact commit and two
fresh independent reviews of that exact SHA are mandatory before G4 may pass.

Fresh code and product-safety reviews of exact commit `fbd0b6314` both returned
NO-GO, so push and deployment again remained stopped. They reproduced actual
PUT/POST or broadened read dispatch for additional disease uncertainty/relapse,
ID, event provenance/ownership, daypart and long-tail/multi-entity query forms;
shadow mode executed an illness-query clarification block. Failure-first tests
reproduced 47 boundary failures. The v21 remediation resolves each relation
before dispatch and adds the reviewers' positive water/time/query controls. A
new exact commit and two fresh independent reviews of that exact SHA are
mandatory before G4 may pass.

Fresh code and product-safety reviews of exact commit `0cc687a2e` both returned
NO-GO, so push and deployment again remained stopped. They crossed the real
Executor/Gateway with synthetic owner-scoped records and fake adapters in both
policy modes. The remaining failures were architectural: open-ended recovery
substring inference, identifier-shape fallthrough, event clauses that retained
unmodelled provenance or ownership, daypart conversion by blanket PM shifting,
and long-tail illness reads that still trusted a conflicting model dimension.

The v22 remediation makes every one of those relations positive and closed.
The model proposes a semantic operation, but the deterministic compiler grants
authority only to a supported final illness state, exact visible record,
current-user event relation, normalized clock and one user-stated query entity.
Unknown write clauses and conflicting or multi-entity reads are hard denials in
both enforce and shadow. The clean G3 evidence is green; a new exact commit and
two fresh independent reviews of that exact SHA are mandatory before G4 may
pass.

Fresh code and product-safety reviews of exact commit `3f3119834` both returned
NO-GO, so push and deployment again remained stopped. Their independent real
Executor/Gateway matrices agreed that generic history extraction still trusted
an illness proposal too early, natural read wrappers and coordination relations
could bypass the intended entity plan, symptom recovery was not bound to a
write tool, and several legitimate exact-ID, latest-state, current-user event
and early-evening controls were over-blocked or mis-normalized.

The v23 remediation makes the history frame, known domain, entity cardinality
and model proposal separate evidence. A proposed tool can no longer choose a
dimension that conflicts with a known entity, omit the user's long-tail entity,
or carry symptom-write fields into a read. Exact ID syntax and state-prefix
stripping share one parser; a broadened direct speech-act frame still cannot
write until the closed final-state compiler matches the exact canonical patch.
Current-user event ownership and daypart conversion retain explicit positive
controls. The clean G3 evidence is green; a new exact commit and two fresh
independent reviews of that exact SHA are mandatory before G4 may pass.

Fresh code and product-safety reviews of exact commit `9e7707565` both returned
NO-GO, so it was not pushed or deployed. Their independent real
Executor/Gateway matrices reproduced the same architectural gaps in enforce
and shadow modes: natural request wrappers polluted the illness entity;
coordination and punctuation could collapse several illnesses into one query;
long-tail disease names containing words such as `睡眠`, `运动`, `药物` or
`饮食` were mistaken for another data dimension; arbitrary model fields could
reach the read adapter; and narrow valid ID, recovery-time and current-user
event-owner forms were falsely denied.

The v24 remediation removes those residual substring decisions. History
entities are now extracted structurally from their position relative to the
explicit time window and `记录/历史` frame, with a compositional request-prefix
grammar and exact entity decorators. Known non-illness dimensions require a
closed exact-entity or `dimension + metric descriptor` match; disease names
merely containing another dimension word remain illnesses when the model
proposes the illness reader. A closed atomicity grammar hard-blocks coordinated
or punctuated multi-entity reads before any adapter call. Every `health_query`
proposal is normalized and projected to the
public schema (`dimension`, `days`, `indicator`, `keyword`, `uploaded_days`,
`uploaded_since`) in both the shared normalizer and the capability policy, so
write-shaped or invented fields cannot cross the read boundary. Visible IDs,
illness time placement and explicit current-user event parentheticals use
equally narrow positive grammars. The contracts are now
`agent-capability-policy-v24` / `authorized-target-set-v20` /
`record-update-evidence-v15`.

Failure-first evidence reproduced 51 failures in the then-188-case focused
matrix; the expanded remediated matrix passes 196/196. The core
policy/Gateway/scope suite passes 2,435/2,435. All 26 changed and adjacent
Backend feature-test files pass 4,081/4,081 in one process on the production
`Asia/Shanghai` calendar basis;
query normalization passes 13/13 and the adjacent meal-photo compatibility file
passes 103/103. Targeted Ruff, focused formatting, Python compilation and
`git diff --check` pass on the same tree. A new exact commit and two fresh
independent reviews of that SHA are mandatory before G4 may pass.

Fresh code and product-safety reviews of exact commit `8344a02ca` both returned
NO-GO, so it was not pushed or deployed. Both real-chain matrices confirmed all
prior `9e7707565` blockers were fixed, but exposed new structural gaps. Most
critically, the single-query schema projector was also applied to
`health_query_batch` read fingerprints, collapsing distinct nested plans to the
same empty-argument dedup key. The remaining findings were multi-window or
post-`记录` query scopes, additional coordination symbols/relations and request
wrappers, over-blocking of valid registered dimensions, and narrow positive
illness-update or current-user event-owner forms.

The v25 remediation separates single-query canonicalization from batch-plan
identity: batch fingerprints retain the complete nested plan, while each batch
subquery still uses the batch validator's own canonicalizer. History reads now
model scope cardinality separately from entity cardinality; multiple windows or
multiple history frames require plan decomposition before dispatch. A
post-history container form can still project one exact entity. Registered
non-illness dimensions are allowed after schema validation unless a closed
positive dimension grammar proves a conflict or the entity has an illness
morphology; this preserves activity, heart-rate, HRV, SpO2, body-battery,
supplement, diet and workout reads without reintroducing substring collisions.
The request scaffold, atomicity, exact-ID/time/state and current-user event
grammars cover the independently reviewed relations. The contracts are now
`agent-capability-policy-v25` / `authorized-target-set-v21` /
`record-update-evidence-v16`.

The fresh failure-first review matrix reproduced 70 failures; the remediated
expanded matrix passes 267/267. The core policy/Gateway/scope/read-dedup suite
passes 2,508/2,508. All 27 changed and adjacent Backend feature-test files pass
4,154/4,154 in one process on the production `Asia/Shanghai` calendar basis,
and the adjacent meal-photo compatibility file passes 103/103. Targeted Ruff,
focused formatting, Python compilation and `git diff --check` pass. A new exact
commit and two fresh independent reviews of that SHA remain mandatory before G4
may pass.

Fresh code and product-safety reviews of exact commit
`c5450a72341ee7b7fee5c0e6f645461412f87e22` both returned NO-GO, so it was not
pushed or deployed. The code review proved that `health_query_batch` bypassed
the single-query turn/entity binding, equivalent batch aliases produced
different convergence fingerprints, and unknown history entities still fell
through to arbitrary non-illness dimensions. The safety review independently
reproduced false dispatch for HRV, breakfast and MRI history when the model
proposed illness, plus disease names beginning with ordinary metric words. Both
reviews also found natural single-scope history phrasing, four coordination
relations and one explicit current-user event-owner form that were incorrectly
handled.

The v26 remediation makes semantic scope one pre-dispatch contract for both
single and batch reads. A positive closed mapping binds recognized non-illness
entities to their canonical dimension; an unrecognized history entity cannot
fall through to a model-selected metric. Known illness and long-tail illness
reads continue through the exact illness projector. Batch plans must match the
complete set of entities stated by the user, and an explicit turn time window
overwrites model-proposed days for both single and batch reads. Valid nested
batch aliases canonicalize before read convergence while distinct plans retain
distinct fingerprints. Natural `历史记录` / `历史中……有哪些记录` frames remain
one scope; separate scopes remain closed. The reviewed request wrappers,
coordination relations and `我的这次行程` current-user ownership form are
covered by real ToolGateway tests in enforce and shadow modes. The contracts
are now `agent-capability-policy-v26` / `authorized-target-set-v22` /
`record-update-evidence-v17`.

Failure-first coverage reproduced 44 failures across the new query, batch,
fingerprint, time-window and event-owner matrix. The remediated Gateway matrix
passes 44/44 and the read-fingerprint group passes 4/4. The
complete 27-file related Backend regression run passes 4,199/4,199 in one
process with `TZ=Asia/Shanghai`, and the adjacent meal-photo compatibility file
passes 103/103. The earlier requested live `qwen3.7-max` six-case synthetic
evaluation remains green with zero database I/O: exact/paraphrased/negated
illness history chose the illness reader, quoted update did not write, direct
update chose list-first management, and explicit illness create chose the
write tool. Targeted Ruff, focused formatting, Python compilation,
`git diff --check`, generated system-map drift and Dossier consistency checks
pass. A new exact commit and two fresh independent reviews of that SHA remain
mandatory before G4 may pass.

Fresh code and product-safety reviews of exact commit
`bcce47b98465d1c784743af1f5567cf51cf172bc` both returned NO-GO, so it was not
pushed or deployed. Their independent real Executor/Gateway matrices agreed
that the remaining problem was structural rather than a list of missing disease
names. Ordinary metric questions without `记录/历史` could still trust a wrong
model dimension; batch comparison used set equality and therefore lost omitted,
duplicated or same-dimension entities; valid registered multi-window comparisons
were rejected or had every child query overwritten with the first window; and
natural wrappers, history containers, negated-write/read compounds, line breaks,
em dashes and additional disease coordination relations could pollute or collapse
the exact entity frame. The safety matrix passed 312/330 executions with zero
writes but retained nine unique read failures; the companion 95-case matrix in
both policy modes reproduced 38 failures. Release remained stopped.

The v27 remediation promotes history extraction into one deterministic health-
query frame. A normal question such as `我近一个月的HRV是多少` now binds the
same exact entity/window contract as a `记录` query. Line breaks remain entity
boundaries instead of disappearing during whitespace normalization. A negated
write followed by an explicit read contributes only the read clause, while
`病史中…有哪些记录`, `历史中找出…记录` and `记录里…有几条记录` remain one
scope. Batch authorization now compares cardinality-preserving
`(dimension, days)` bindings: omitted and duplicated children are blocked;
unrepresentable breakfast+dinner, MRI+CT and run+cycle filters are not broadened;
and representable 7-day/30-day comparisons remain available with each child
bound to its own window. The contracts are now
`agent-capability-policy-v27` / `authorized-target-set-v23` /
`record-update-evidence-v18`.

Failure-first coverage reproduced all 42 newly encoded review boundaries before
implementation. The remediated focused matrix passes 42/42, the complete
ToolGateway file passes 1,131/1,131, and the 27-file related Backend integration
gate passes 4,241/4,241 in one process with `TZ=Asia/Shanghai`. The adjacent
meal-photo compatibility file passes 103/103. Targeted Ruff, focused formatting,
Python compilation and `git diff --check` pass. The earlier requested live
`qwen3.7-max` six-case synthetic evaluation remains the latest model evidence;
it used the production schema with zero database I/O and already demonstrated
why model JSON is a proposal rather than authority. A new exact commit, mainline
sync and two fresh independent reviews of the resulting exact SHA remain
mandatory before G4 may pass.

The latest clean `origin/main` commits `83d8403ed` and `359d6b819` were merged
before final review. They restore Mobile chat history after cold launch and
atomically clear stale turn recovery; their seven changed files do not overlap
the Backend semantic-query boundary. On the merged tree, the three affected
Mobile Jest suites pass 99/99 using the repository's pinned dependency tree,
and the iOS acceptance-harness test passes. The pre-existing React test
`act(...)` console warnings remain visible and are not treated as a silent pass.
The 42-case real Gateway boundary group is rerun on the merged tree, and two
fresh reviewers must inspect the final documentation commit SHA rather than
either parent.

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
