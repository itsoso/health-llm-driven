# Feature Spec: Semantic Illness Query

> Status: approved_for_implementation
> Owner: Codex
> Updated: 2026-08-08
> Related PRD/PDD: `docs/plans/2026-08-08-semantic-illness-query-design.md`
> Related code: `backend/app/services/write_intent_scope.py`, `backend/app/services/utterance_intent_classifier.py`, `backend/app/services/tool_schema_registry.py`, `backend/app/services/health_read.py`, `backend/app/services/agent_executor.py`

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
  -> shared intent frame classifies the speech act as read-only
  -> LLM expresses entity/time semantics in registered health_query arguments
  -> deterministic compiler selects canonical illness reader
  -> owner-scoped IllnessEpisode rows are returned newest first
  -> answer states latest occurrence and lists matching persisted episodes
```

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
  - IllnessEpisode (read only)
fields:
  - health_query.dimension gains illness
  - health_query.keyword applies to illness name
  - health_query.days applies to illness start-date window
  - illness days accepts 1..36500 without silently changing the requested window
  - omitted health_query.days means full history for illness only
enums:
  - health_query.dimension: add illness
backward_compatibility:
  - all existing valid dimensions retain behavior
  - health_manage illness CRUD remains unchanged
  - health_query_batch rejects illness until its subquery shape can preserve keyword and full-history semantics
migration: none
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

In mixed contrast turns, the governing later action can supersede an earlier
denial without authorizing the denied target. When a deterministic goal supplies
a target record type, the final capability gate requires the model-selected
`health_record.record_type` to match it. Object-fronted direct commands such as
`把口腔溃疡记录下来` remain writable; read requests such as
`请查询口腔溃疡记录` do not.

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

Given a user says "把口腔溃疡记录下来"
When the positive speech-act parser processes the object-fronted request
Then it remains a direct write under the existing confirmation policy

Given the user explicitly supplies a past event and concrete onset date
When the classifier processes "请记录我上一次口腔溃疡，发作日期是7月1日"
Then it remains a dated backfill write under the existing confirmation policy

Given a user asks for a two-year illness window
When health_query validates days=730
Then it preserves 730 rather than silently changing the query to seven days

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

Deploy as a backward-compatible Backend release after focused/full regression
and safety review. No client release or schema migration is required. Verify one
read-only production turn and inspect executed tool metadata.

Rollback to the previous Backend release if invalid-dimension errors or illness
query selection regress. No data repair is needed because this slice performs no
writes.

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
