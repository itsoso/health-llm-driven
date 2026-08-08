# Feature Spec: Semantic Illness Query

> Status: approved_for_implementation
> Owner: Codex
> Updated: 2026-08-08
> Related PRD/PDD: `docs/plans/2026-08-08-semantic-illness-query-design.md`
> Related code: `backend/app/services/utterance_intent_classifier.py`, `backend/app/services/tool_schema_registry.py`, `backend/app/services/health_read.py`, `backend/app/services/agent_executor.py`

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

Given a user asks whether the product can record illness data
When the classifier processes "小巴能记录口腔溃疡吗"
Then it remains a capability question and does not authorize a write
```

## 12. Verification Plan

```bash
# Backend focused behavior
/Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin/python -m pytest -q --no-cov \
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
