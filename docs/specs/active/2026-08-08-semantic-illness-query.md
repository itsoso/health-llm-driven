# Feature Spec: Semantic Illness Query

> Status: implemented_g4_pending
> Owner: Codex
> Updated: 2026-08-10
> Related PRD/PDD: `docs/plans/2026-08-08-semantic-illness-query-design.md`
> Related code: `backend/app/services/agent_kernel/health_semantics.py`, `backend/app/services/agent_kernel/goal_spec.py`, `backend/app/services/agent_kernel/capability_policy.py`, `backend/app/services/write_intent_scope.py`, `backend/app/services/utterance_intent_classifier.py`, `backend/app/services/tool_schema_registry.py`, `backend/app/services/health_read.py`, `backend/app/services/agent_executor.py`

## 1. Decision

Add an owner-scoped illness query dimension and make read/write authorization
depend on the semantic speech act rather than the presence of the word `记录`.

## 2. Problem

Chat users asking when an illness last occurred or which historical records
exist can be routed into the write flow. `口腔溃疡` is not typed by the current
classifier, and the query tool cannot read illness episodes. An invented
`symptom` query dimension is silently changed to `comprehensive`, exposing
unrelated wearable facts such as sleep instead of failing or re-planning.

If unchanged, users cannot trust that a question is read-only or that an answer
comes from the requested health record family.

## 3. Requirement Admission

```yaml
RequirementAdmission:
  request: "系统应理解‘我上一次口腔溃疡是什么时候，最近半年有哪些记录’，再决定后续操作"
  classification: agent_semantic_query_infrastructure
  first_user_fit: high
  core_loop_step: review_and_converse
  first_class_objects:
    - ExecutionEvent
  target_surface:
    - Backend Agent
    - Mobile Chat
    - Mac Chat
    - Web Chat
  source_of_truth: owner-scoped IllnessEpisode records through canonical health read
  safety_level: L3 health data; read/write authorization boundary
  prescription_or_causal_verdict: no
  autonomy_tier: read_only; existing illness writes remain manual_confirm
  evidence_provenance: structured IllnessEpisode rows with dates and status
  claim_hedging: report only persisted matching records; no chat-history inference
  verification_window: before backend deployment and one production read-only drill
  success_metric: exact query and paraphrases execute zero writes and return only matching illness episodes
  added_user_burden: none for clear queries
  burden_justification: clarification only when entity or requested action is genuinely ambiguous
  non_goals:
    - diagnosis, treatment or causal analysis
    - migration of every health record family in this slice
    - autonomous illness creation or modification
  smallest_end_to_end_slice: read-only oral-ulcer query -> typed illness plan -> canonical owner-scoped rows -> answer
  stale_surface_to_remove_or_archive: silent invalid-dimension fallback to comprehensive
  spec_required: yes
```

## 4. Non-Goals

- Do not diagnose oral ulcers or recommend treatment.
- Do not infer an illness occurrence from conversation history when the database
  query has no match.
- Do not change confirmation rules for illness create/update/delete.
- Do not add a new client screen or database table.
- Do not migrate generic symptom history in this slice.

## 5. Product Object Mapping

| Object | Change |
|---|---|
| `ExecutionEvent` | Read turns carry an illness-domain intent and executed query evidence rather than a false write attempt. |
| `WriteIntent` | No object is created for a read-only historical-record question. Existing illness mutations retain their confirmation boundary. |

## 6. User Flow

```text
user asks for latest + six-month oral-ulcer history
  -> shared intent frame identifies a read speech act
  -> deterministic semantics resolve cancellation, ownership and references
  -> entity/domain projection binds the turn to illness and its exact window
  -> LLM arguments are treated as a proposal and reconciled to that binding
  -> capability policy authorizes only the matching read-only tool call
  -> owner-scoped IllnessEpisode rows are returned newest first
  -> answer states latest occurrence and lists matching persisted episodes
```

### 6.1 Semantic Authorization Architecture

The authorization boundary is a staged semantic compiler, not one keyword
classifier and not an LLM verdict:

```text
speech act and cancellation
  -> current-user ownership
  -> durable entity versus unresolved discourse reference
  -> health entity and record domain
  -> exact server-owned query projection
  -> tool capability and owner-scoped execution
```

`health_semantics.py` is the shared contract for illness terminology,
third-party ownership and unresolved health references. Goal compilation and
CapabilityPolicy consume that same contract, so direct, memory and fallback
routes do not maintain separate disease or owner regexes. The terminology set
is an authorization vocabulary rather than a diagnostic ontology: known
ambiguous eponyms are explicit, medically shaped open-vocabulary entities are
accepted, and non-health roots cannot gain illness authority merely by ending
in words such as `异常` or `疼痛`.

The shared contract is versioned and content-digested. Its resolver returns a
typed semantic outcome before authorization, and the capability payload exposes
both version and digest. A change to read verbs, cancellation, ownership,
references, illness morphology, medical-exam identifiers or clause connectors
therefore changes one observable contract rather than silently diverging across
GoalSpec and CapabilityPolicy.

The digest covers every module-level authorization grammar, including nested
regex collections used by record identity, mutation and delete evidence. Illness
recognition combines an explicit terminology set with a closed compositional
grammar: a suffix such as `炎`, `癌` or `异常` grants no authority unless every
preceding span is a recognized clinical modifier or medical body token. Exact
canonical disease tails also define an owner boundary, so an arbitrary Unicode
name or unknown relationship concatenated before a valid disease cannot be
reinterpreted as part of the current user's illness.

Every read surface uses the same Backend decision. A model-selected tool or
dimension is only a proposal; the server projects illness and medical-exam
queries from the active user clause, binds user-facing `health_manage(list)` to
the domain actually named in the turn, and fails closed for third-party,
cancelled, observational or unresolved-reference input.

Internal mutation lookup is not inferred from model-supplied operation fields,
mutation-looking text or the broad intent classifier. GoalSpec first compiles a
typed `health_manage_mutation` goal with exact current-turn authority, record
family, target and receipt postconditions. The server then binds an opaque,
non-JSON lookup marker to that goal. CapabilityPolicy accepts the owner-scoped
lookup only while that marker is present and strips it before adapter dispatch.
Observation-only phrases therefore become neither reads nor mutation lookups.

Read speech-act resolution is clause structured. It identifies withdrawal,
deferment, completed narration and an explicitly restarted active clause before
ownership or entity resolution. The shared illness extractor also serves
mutation targeting, so reads and writes accept the same valid long-tail disease
vocabulary instead of a finite mutation-only list. Indicators such as blood
pressure or glucose followed by `异常` remain metric entities, not illnesses;
biomedical modifiers such as `HLA-B27`, `BCR::ABL1`, `IgG4`, `anti-NMDA` and
`β2` are preserved without allowing arbitrary names to borrow a disease tail.

Published authorization digests cover behavior as well as grammar constants.
The semantic, GoalSpec and CapabilityPolicy payloads fingerprint selected
function bytecode plus the authoritative write-intent grammar/functions, so a
logic-only authorization change is observable even when no regex changes.

## 7. Surface Contract

| Surface | Responsibility | Contract |
|---|---|---|
| Mobile | Submit and render the shared Agent turn. | No local record-keyword routing. |
| Mac | Submit and render the shared Agent turn. | Same Backend semantics and evidence as Mobile. |
| Web | Submit and render the shared Agent turn. | Same Backend semantics and evidence as Mobile. |
| Backend | Authorize speech act, compile query and read owner data. | A read question cannot execute a write tool; invalid dimensions fail loudly. |

## 8. Data Contract

```yaml
apis:
  - existing Agent APIs unchanged
events:
  - existing Agent turn and tool events unchanged
models:
  - IllnessEpisode (read path plus nullable severity contract for exact writes)
fields:
  - health_query.dimension gains illness
  - health_query.keyword applies to illness name
  - health_query.days applies to illness start-date window
  - illness days accepts 1..36500 without silently changing the requested window
  - omitted health_query.days means full history for illness only
  - IllnessEpisode.severity is nullable; omitted means unknown and must not become 5
enums:
  - health_query.dimension: add illness
backward_compatibility:
  - all existing valid dimensions retain behavior
  - health_manage illness CRUD retains confirmation and owner-scope boundaries
  - explicit current-user illness status updates and exact-record deletes compile a mutation goal before lookup or dispatch
  - health_query_batch rejects illness until its subquery shape can preserve keyword and full-history semantics
migration: paired managed PostgreSQL/SQLite migration drops the illness severity default and NOT NULL
```

## 9. Safety, Privacy, And Medical Boundary

This feature reads L3 illness history. Every query must include the authenticated
`user_id`; no cross-user fallback or unscoped query is permitted. It makes no
medical claim and triggers no prescription behavior.

The deterministic capability gate remains authoritative: a read intent cannot
execute `health_record` or mutating `health_manage` operations. Invalid semantic
dimensions return an error instead of querying a different domain. User text and
health results must not be added to new plaintext logs. Database failures return
a fixed user-safe error and log only a content-free error type.

Write authorization is positive and fail-closed: it requires a current, direct,
affirmative request speech act or a concrete observation fact; the bare presence
of `记录`, or the absence of a recognized veto, is never sufficient. A shared
clause/scope parser separates action-local polarity, request modals, read verbs,
product-capability questions, completed/result checks, attributed or quoted
speech, hypotheticals and historical references across every registered
write-action synonym. The classifier and kernel write gate consume the same
positive authorization result, so helper phrases cannot open a gap between
routing and actual dispatch.

The frame treats denial control predicates (`禁止/拒绝/停止/未授权`), contextual
scope introducers (`不要执行：…`) and adversative boundaries (`…但请记录`) as
structure rather than flat substrings. Completion may follow the recorded
object (`保存口腔溃疡了吗`). Past-time words before an action remain historical
queries, while an explicit dated backfill and a command to record a just-observed
event remain writes under the existing confirmation contract.

In mixed or multi-action turns, the parser returns an ordered set of concrete
positive clauses rather than a whole-turn boolean. The final capability gate
binds every model request to one member of that authorized target set. A later
positive action can supersede an earlier denial without authorizing the denied
target, while two separate direct commands can each authorize their exact
write. Binding includes record type, effective date and the deterministic
selectors available for the record family, including meal/food, illness name,
numeric value, sleep/reminder time, goal title and medication name/dose.
Top-level argument aliases and nested `data` aliases are checked together.
Thus a weight authorization cannot write illness, dinner cannot write lunch,
and `记录体重71kg` cannot write another weight value. Mixed polarity with an
unresolvable positive target fails closed to clarification. Object-fronted
direct commands such as `把口腔溃疡记录下来` remain writable; read requests such
as `请查询口腔溃疡记录` do not.

The target-set boundary also treats deferred conditions (`确诊后再记录`),
third-party subjects and composed revocations as non-authorizing. Argument
aliases are canonicalized before validation and the same normalized payload is
then dispatched, so a field cannot be accepted under one alias and ignored by
the adapter. User-supplied illness status, severity and notes are bound exactly.
When a model fills an optional severity that the user never stated, the gate
projects that field out before dispatch rather than persisting an invented
health fact or rejecting the otherwise exact write. Non-default status,
end-date, entity, quantity and date drift still fail closed.

The projected payload has one canonical spelling for each consumed field;
source aliases are removed before retry fingerprinting and dispatch. Medication
actual dose and observed strength use the same alias parser in policy and
executor. A date-only symptom is stored with the authorized server date and no
model-authored clock; an explicit clock is rebuilt using the frozen user-local
timezone. Explicit supplement dosage and timing are bound and preserved for
auto-created definitions; only fields absent from the user's request are
discarded. Unknown illness severity remains database `null`, is exposed as
nullable in generated API types, and is rendered as `未记录` rather than a
fabricated score.

Attribution is grammatical rather than source-allowlisted: arbitrary subjects
such as `朋友/同事/体检报告` plus a reporting predicate do not gain current-user
authority. This applies equally to commands and observation facts such as
`朋友说我喝了300ml水`. Common trailing pause/revocation language invalidates the
preceding authority. Polite conditions such as `如果可以，请记录体重71kg` remain
direct requests rather than being flattened into hypothetical examples.

The ownership check is not limited to known roles: the subject governing a
health predicate must reduce to the current user before a trailing helper can
authorize a write. Names and previously unseen relations therefore fail closed
without a growing person-word list. Colon-introduced attribution, deferred
conditions, withdrawal and correction relations are resolved before the
authorized target set is compiled. Direct compound requests such as
`计算热量和营养并记录饮食` remain positive current-user actions.

For a direct command, the parser validates both the initiator before the action
and the subject between the action and every health predicate. A write verb is
not itself proof of current-user ownership. Therefore `记录我的体重71kg` and
`把我的体重71kg记录下来` remain valid, while `记录张三体重71kg`,
`医生建议我记录体重71kg` and a second named subject in a compound observation
fail closed without a name or relationship list. Denied observations and
notes/attribute continuations do not contaminate a later legitimate target.

For numeric record families, equivalent top-level and nested aliases collapse
to one adapter-consumed field and one retry identity; contradictory values are
blocked before collapse. The gate projects only authorized fields, so a model
cannot smuggle an invented water type or other unused field through a payload
the adapter interprets differently. Supplement name, compact dose and timing
use the same exact projection. Illness PATCH status is optional but non-null:
omission preserves the stored status, while explicit JSON null is rejected.

Illness windows use the Agent turn's frozen user-local date, not the service
process date. This keeps Web, Mobile and Mac results aligned at timezone day
boundaries. The same date is also an inclusive upper bound, so a future-dated
episode cannot become the reported latest occurrence.

## 10. AI Behavior

The LLM may infer that `口腔溃疡` is an illness entity, that `上一次` requests the
newest result and that `最近半年` requests a bounded history. It expresses that
meaning only through the registered query schema.

The LLM must not authorize a write, invent a query dimension, infer a missing
database record from prior chat, or claim a mutation occurred. Deterministic
validation, query compilation, owner filtering and receipt policy run outside
the model. Failure degrades to an explicit no-match/error or clarification.

## 11. Acceptance Criteria

```gherkin
Given a user asks "我上一次口腔溃疡是什么时候 最近半年分别有哪些记录"
When the shared classifier processes the turn
Then it is read-only and no write tool is authorized

Given a historical question begins with "记录" such as "记录过口腔溃疡吗"
When the shared classifier processes the turn
Then the question remains read-only and health_record is blocked before dispatch

Given Mobile speech transcription omits punctuation in "记录过口腔溃疡没有"
When the classifier and ToolGateway process the turn
Then the completed historical frame cannot dispatch health_record

Given matching oral-ulcer episodes belong to the current user
When health_query runs with dimension illness and a six-month window
Then it returns only the current user's matching episodes newest first

Given a matching episode is dated after the Agent turn's frozen user-local date
When health_query reads bounded or full illness history
Then the future-dated episode is excluded

Given the user asks only for the last oral-ulcer episode without a time window
When health_query omits days
Then the illness reader searches the user's full persisted illness history

Given another user has a newer matching episode
When the current user runs the same query
Then the other user's episode is absent

Given a model submits health_query dimension symptom
When the validator processes the call
Then it returns an invalid-dimension error and does not substitute comprehensive

Given a model submits illness through health_query_batch
When the batch validator processes the plan
Then it fails before fetching and directs the model to single health_query

Given a user says "记录体重70kg"
When the classifier processes the turn
Then the existing explicit write behavior remains authorized

Given a user politely asks "能帮我记录体重70kg吗"
When the classifier processes the turn
Then it remains an explicit write and follows the existing confirmation policy

Given a user combines bounded request words in "我想请你帮忙记录口腔溃疡，可以吗"
When the classifier processes the turn
Then it remains an explicit write and follows the existing confirmation policy

Given a user says "请不要再帮我记录口腔溃疡"
When the classifier and capability gate process the turn
Then no write tool is authorized

Given a negation contains an arbitrary bridge such as "不要让系统帮我记录口腔溃疡"
When the classifier and ToolGateway process the turn
Then the negation scopes over the write action and dispatch never starts

Given the user says "请勿执行以下操作：记录一下今天晚餐"
When the classifier and ToolGateway process the colon-introduced operation
Then the prohibition continues across the colon and dispatch never starts

Given the user says "我没有授权小巴帮我保存口腔溃疡"
When the classifier and ToolGateway process the denial predicate
Then no registered write synonym can cross the dispatch boundary

Given a user says "勿帮我记录晚餐，分析一下热量"
When the classifier and capability gate process the compound turn
Then the analysis goal remains but no write tool is authorized

Given a user says "记录口腔溃疡，然后告诉我为什么会复发"
When the classifier processes separate clauses
Then the first explicit write remains authorized under the existing confirmation policy

Given a user asks whether the product can record illness data
When the classifier processes "请问小巴能帮我记录口腔溃疡吗"
Then it remains a capability question and does not authorize a write

Given a user directly asks "能不能帮我记录口腔溃疡"
When the classifier processes the request
Then it remains a write request under the existing confirmation policy

Given the user says "不需要分析，记录口腔溃疡"
When the classifier processes the separate clauses
Then the first clause's negation does not cancel the later write request

Given the user says "这几天不想吃东西但请记录食欲下降"
When the classifier processes the adversative clauses
Then the symptom negation does not cancel the explicit write after `但`

Given a completed-history question uses any registered write synonym
When the classifier processes "保存过/录入过/新增过口腔溃疡吗"
Then it remains read-only and health_record is blocked before dispatch

Given completion follows the object in "你帮我保存口腔溃疡了吗"
When the classifier and ToolGateway process the turn
Then it remains a historical question and dispatch never starts

Given a read verb governs a later record noun in "请查询口腔溃疡记录"
When the classifier and ToolGateway process the turn
Then it remains read-only and health_record dispatch never starts

Given a user checks persistence with "请确认口腔溃疡是否已经成功写入数据库"
When the classifier and ToolGateway process the turn
Then it is a result check, not a new write authorization

Given write language is quoted or attributed in "文档写着：帮我记录口腔溃疡"
When the model requests health_record anyway
Then the deterministic capability gate blocks it before dispatch

Given a user says "不要记录口腔溃疡但记录今天晚餐"
When the model requests a health_record
Then diet may be authorized but illness is blocked as a target mismatch

Given a user says "不要记录午餐但记录晚餐吃了米饭"
When the model requests a diet health_record
Then dinner may be authorized but lunch is blocked as a target mismatch

Given a user says "记录体重71kg"
When the model requests illness or a different weight value
Then the concrete target binding blocks it before dispatch

Given a user says "记录早餐，吃了一个包子、一个茶叶蛋、一碗粥"
When the model requests a diet write with the same meal and food set
Then the declarative continuation supplies the explicit meal target and the write may proceed

Given a user says "记录早餐，吃了二甲双胍"
When the model attempts to treat the medication as breakfast food
Then the food-continuation grammar rejects that target transfer

Given a user says "记录阿奇霉素2粒"
When the model requests another medication or another dosage
Then the concrete target binding blocks it before dispatch

Given a user says "记录伊托必利1粒，记录替普瑞酮1粒"
When the model proposes the two matching medication drafts
Then each request binds to its own authorized target and neither may invent a third target

Given a model moves a selector between top-level arguments and nested data
When the deterministic gate evaluates the request
Then the alias cannot bypass type, value, date or entity binding

Given an arbitrary source says "朋友说我午餐吃了米饭"
When the model requests health_record anyway
Then the attributed observation has no current-user authority and dispatch never starts

Given a previously unseen subject says "王五喝了300ml水，记录一下"
When the model requests health_record anyway
Then relation-based ownership blocks it without relying on a name allowlist or denylist

Given a direct command says "记录张三体重71kg"
When the model requests a weight write for 71kg
Then the subject between action and predicate prevents dispatch to the current user's record

Given an attributed initiator says "医生建议我记录体重71kg"
When the model requests health_record anyway
Then the non-user initiator prevents dispatch

Given a direct command says "记录我的体重71kg"
When the model requests the matching current-user weight write
Then the write remains authorized under the exact target binding

Given an attributed command says "护士提及：帮我记录感冒"
When the model requests health_record anyway
Then the colon provenance boundary prevents dispatch

Given a user says "记录饮水300ml，当我没说"
When the model requests health_record anyway
Then withdrawal removes the prior authority and dispatch never starts

Given a user says "记录体重71kg，口误，是70kg"
When the model requests a health_record
Then only the corrected 70kg target can dispatch

Given equivalent water arguments use data.amount, data.amount_ml or a top-level amount
When the deterministic gate accepts the request
Then all forms dispatch the same canonical data.amount payload and retry identity

Given a water proposal includes an unrequested drink_type
When the deterministic gate accepts the authorized amount
Then the unrequested field is removed before dispatch

Given a user says "记录鱼油2粒晚上吃"
When the model requests a supplement write
Then canonical name, dosage and timing survive together in the dispatched payload

Given a user submits illness PATCH with status null
When request validation runs
Then it returns a validation error and does not mutate the non-null status column

Given a user asks "计算热量和营养并记录饮食"
When the positive speech-act parser processes the compound request
Then the diet write remains authorized under its exact target binding

Given a user says "记录体重71kg，算了吧"
When the classifier and ToolGateway process the trailing revocation
Then the preceding write authority is revoked and dispatch never starts

Given a user says "如果可以，请记录体重71kg"
When the positive speech-act parser processes the polite condition
Then it remains a direct current request and may write only weight 71kg

Given a user says "把口腔溃疡记录下来"
When the positive speech-act parser processes the object-fronted request
Then it remains a direct write under the existing confirmation policy

Given the user explicitly supplies a past event and concrete onset date
When the classifier processes "请记录我上一次口腔溃疡，发作日期是7月1日"
Then it remains a dated backfill write under the existing confirmation policy

Given a user asks for a two-year illness window
When health_query validates days=730
Then it preserves 730 rather than silently changing the query to seven days

Given a user says "把我的克雅氏病状态改成已康复"
When GoalSpec and CapabilityPolicy process the turn
Then an exact owner-scoped illness lookup may bind the requested record and only
that record's status may be patched

Given a user says "别查了" or "先不用继续查口腔溃疡记录"
When the model proposes any illness read or manage-list call
Then cancellation wins and dispatch never starts

Given a user says "我的血压异常记录有哪些"
When semantic projection resolves the requested record family
Then `异常` does not reclassify the metric as an illness

Given more than 100 illness episodes match
When the canonical reader returns the newest 100
Then the result explicitly states that it was truncated
```

## 12. Verification Plan

```bash
# Backend focused behavior
/Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin/python -m pytest -q --no-cov \
  tests/test_write_intent_scope.py \
  tests/test_utterance_intent_classifier.py \
  tests/test_health_read_illness.py \
  tests/test_tool_validator.py \
  tests/test_agent_executor_reads_in_process.py \
  tests/test_agent_executor_fast_routing.py

# Static and repository gates
/Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin/python -m ruff check \
  app/services/utterance_intent_classifier.py \
  app/services/tool_schema_registry.py \
  app/services/health_read.py \
  app/services/llm/tool_validator.py \
  app/services/agent_executor.py
git diff --check
python scripts/check_doc_drift.py
```

Model evaluation uses anonymized query/write contrast cases and qwen-max-3.7.
If credentials or the requested registry entry are unavailable, this is a
reported G3/G6 blocker rather than a silently skipped check.

## 13. Rollout And Rollback

Deploy the paired managed migration before the Backend release, then deploy
the generated-contract-compatible Web release after focused/full regression and
safety review. Verify one read-only production turn and inspect executed tool
metadata.

Rollback to the previous Backend/Web release if invalid-dimension errors or
illness query selection regress. The staged target-runtime schema probe checks
live data against that target's non-null contracts before any socket or writer
starts; it must block an old release when null-severity rows exist. Historical
scores of 5 are preserved because their old-default provenance cannot be
reliably inferred. Never invent or silently backfill a score to make rollback
pass.

## 14. Open Questions

- Which record family should be the second canonical semantic-query slice:
  generic symptoms or medication intake logs?
- Should a future cross-record `health_search` replace dimension-specific query
  plans after at least two canonical readers demonstrate a stable common shape?

These questions do not block the illness slice.

## 15. Changelog

| Date | Change | Reason |
|---|---|---|
| 2026-08-08 | Initial approved spec | User approved hybrid semantic planning with deterministic execution. |
| 2026-08-08 | Hardened write grammar and time-window fidelity | Independent reviews found unpunctuated history, negated compound and long-window boundary gaps. |
| 2026-08-08 | Unified write speech-act scope | Independent reviews found finite helper lists diverged between routing and ToolGateway enforcement. |
| 2026-08-08 | Added clause-semantic contrasts | Fresh reviews found denial controls, post-object completion, colon scope, capability paraphrases and dated-backfill contrasts. |
| 2026-08-08 | Made write authorization positive and action-scoped | Fresh reviews proved that finite veto matching still dispatched reads, result checks, reported speech and trailing revocations. |
| 2026-08-08 | Bound authority to the concrete clause and target | Fresh reviews proved that arbitrary reports, observation facts and denied sibling targets could inherit whole-turn write authority. |
| 2026-08-09 | Upgraded authorization to an exact target set | Fresh reviews found multi-target, alias, meal/date/entity and medication-dose gaps in single-clause binding. |
| 2026-08-09 | Canonicalized and projected the dispatch payload | Fresh exact-commit reviews found composed revocation, deferred/third-party authority, adapter-alias, date, reminder, meal and model-invented-field gaps. |
| 2026-08-09 | Made ownership relational and payload aliases adapter-exact | Fresh exact-commit reviews found arbitrary subjects, attribution/revocation/correction gaps, water/supplement payload drift and non-null PATCH status mismatch. |
| 2026-08-09 | Bound both initiator and direct-object subject | Fresh review found arbitrary names between a write action and health predicate inherited current-user authority. |
| 2026-08-09 | Versioned the shared semantic authorization contract | Fresh v38 reviews found duplicate grammars, arbitrary-owner read/write bypasses, long-tail false denials, suffix false positives, unresolved references and observation-only manage-list leakage. |
| 2026-08-09 | Made semantic ownership compositional and fully fingerprinted | Fresh v39 reviews found arbitrary Unicode owner prefixes, postpositive cancellation, completed-narration list reads, long-tail/Unicode false denials and authorization grammar omitted from published digests. |
| 2026-08-10 | Bound mutation lookup to a typed server-owned goal | Fresh v40 reviews found mutation-text lookup bypasses, incomplete cancellation/completion scope, indicator collisions, long-tail/biomedical false denials and behavior omitted from published digests. |
