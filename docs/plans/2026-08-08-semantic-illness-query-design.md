# Semantic Illness Query Design

> Status: approved
> Date: 2026-08-08
> Owner: Codex
> Related spec: `docs/specs/active/2026-08-08-semantic-illness-query.md`
> Related dossier: `docs/dossiers/2026-08-08-semantic-illness-query.md`

## 1. Problem

The query `我上一次口腔溃疡是什么时候 最近半年分别有哪些记录` is a
read-only request with two projections over one entity:

1. latest occurrence of the illness `口腔溃疡`; and
2. all matching illness episodes in the last six months.

The current runtime produces a write clarification instead. The failure is not
one bad model answer. It is a contract mismatch across three layers:

- `utterance_intent_classifier` treats the token `记录` as a broad write signal;
- the same classifier cannot type `口腔溃疡`, so the question remains in the
  `unknown` domain and bypasses the data-question read branch; and
- `health_query` has no illness dimension. When a model invents
  `dimension=symptom`, `tool_validator` silently changes the invalid dimension
  to `comprehensive`, which reads wearable data and can surface sleep records.

## 2. Decision

Implement the first vertical slice of a hybrid semantic-query architecture:

```text
natural language
  -> shared deterministic clause/scope and write-authorization frame
  -> LLM semantic query plan expressed as typed health_query arguments
  -> deterministic query compiler and owner-scoped canonical reader
  -> structured facts
  -> LLM answer synthesis
```

The LLM may infer entity, time window and requested projection. It is not the
authority for mutation. A question without explicit write authorization is
read-only even when `记录` occurs as a noun. The executor accepts only registered
query dimensions, and semantic dimension errors fail loudly instead of being
rewritten to an unrelated data source.

For this slice, the typed query plan is:

```json
{
  "dimension": "illness",
  "keyword": "口腔溃疡",
  "days": 183
}
```

The canonical illness reader returns matching `IllnessEpisode` facts ordered by
`start_date` descending. That single result supports both “上一次” and “分别有
哪些记录”.

## 3. Why A Hybrid Architecture

### Rejected: add more record keywords

Adding `哪些记录` to a read list fixes only one phrase. It leaves paraphrases,
new disease names and invalid tool dimensions brittle.

### Rejected: let the LLM directly choose and execute any tool

This understands long-tail language but makes a probabilistic model the write
authority. It also preserves the current taxonomy problem: a model can invent a
dimension and the system may execute a semantically different query.

### Chosen: semantic inference with deterministic compilation and policy

The LLM is good at mapping language into typed query arguments. Deterministic
code is good at authorization, schema validation, owner isolation and exact data
retrieval. The boundary makes both responsibilities explicit and testable.

## 4. Semantic Contracts

### 4.1 Speech act and write authorization

- Health-record authorization is positive and fail-closed: the parser must find
  a current, direct, affirmative write speech act. Merely failing to recognize a
  veto is never authorization.
- Clauses are evaluated in order and the governing write action carries its own
  polarity. A later affirmative contrast can supersede an earlier refusal;
  trailing revocation applies to the preceding action.
- Read verbs, capability discussion, completed/result checks, attributed or
  quoted speech, examples, hypotheticals and other metalinguistic mentions are
  non-authorizing references. The same result is reused by the classifier and
  final ToolGateway preflight.
- The frame preserves relations that flat token matching loses: denial-control
  predicates, contextual colon scope, adversative boundaries, post-object
  completion, past-time position and object-fronted direct requests.
- Write actions come from one shared registry; intervening helper text must not
  change the scope of an earlier negation or turn a read verb into a write.
- `记录` followed by noun evidence such as `的/里/中/有哪些` is not write
  authorization.
- Explicit commands such as `记录体重70kg`, `帮我录入血压120/80` and factual
  intake observations retain their current write behavior. Object-fronted forms
  such as `把口腔溃疡记录下来` remain direct writes.
- Advice such as `该不该记录今天腰痛6分` remains advice, not a write.
- `记录刚才打了一个喷嚏` and a request with a concrete historical onset date
  remain writes; history protection must not suppress explicit backfill.
- Authorization produces a concrete governing clause rather than a whole-turn
  boolean. The final capability gate reclassifies only that clause and binds the
  selected `health_record` to its record type plus deterministic meal, named-
  illness and numeric selectors.
- For a mixed denied/positive turn, the positive clause cannot authorize the
  denied record type, meal or value. If the positive target cannot be resolved,
  the write fails closed to clarification.
- Arbitrary-source attributed commands and observation facts share the same
  non-authorizing provenance rule. Trailing pause/revocation invalidates the
  preceding clause; polite conditions remain direct requests.
- Ambiguity degrades to read-only or clarification, never mutation.

### 4.2 Semantic query plan

`health_query` gains a registered `illness` dimension. For named illness
queries, the model supplies `keyword`; `days` carries the requested window. The
tool description provides positive examples for latest and historical illness
queries.

### 4.3 Query compilation

`health_query(dimension=illness)` compiles to an in-process canonical read over
`IllnessEpisode`, not a localhost HTTP round-trip and not `health_manage`.

Required invariants:

- always filter by `IllnessEpisode.user_id == current_user_id`;
- include active, improving and resolved episodes;
- constrain `start_date` to the requested window;
- match the requested illness name when present;
- order newest first; and
- return only fields required for answering: id, name, start/end date, status,
  severity and notes.

### 4.4 Semantic validation

The validator may normalize syntax aliases such as `type -> dimension`. It must
not turn an unknown semantic dimension into `comprehensive`. A supplied invalid
dimension returns an explicit error so the model can re-plan using the
registered dimensions.

## 5. Failure Behavior

- No matching episode: state that no matching database record exists in the
  requested window; do not infer from chat history.
- Missing user identity: return an explicit owner-context error.
- Invalid query dimension: return an explicit registered-dimension error; do
  not query wearable data.
- Database failure: fail loudly and roll back the read session state where
  required; do not manufacture an answer.
- Model emits a write tool during this read turn: capability policy blocks it
  before execution.

## 6. Compatibility

No database migration or public client API change is required. Existing
`health_manage(record_type=illness)` update/delete flows remain unchanged.
Existing valid `health_query` dimensions and explicit recording utterances must
retain their current behavior.

This slice does not replace the whole health tool taxonomy. It establishes the
compiler boundary using illness episodes; later slices can migrate symptoms,
medication logs and other record families behind the same semantic plan.

## 7. Verification

Verification must include:

- failure-first classifier tests for the exact screenshot query and paraphrases;
- positive regression tests for real record commands;
- owner-isolated canonical illness reads with matching/non-matching users;
- validator proof that invalid `symptom` no longer becomes `comprehensive`;
- executor proof that illness queries never call wearable/sleep endpoints;
- an end-to-end tool-loop regression with a model-provided semantic query plan;
- qwen-max-3.7 evaluation over query/write/negation/advice contrasts using
  anonymized fixtures; and
- a system-level model challenge proving that a model-selected write for quoted
  speech is still blocked by deterministic policy, while an explicit direct
  write remains available through the forced write-tool path;
- a real ToolGateway matrix covering arbitrary reports and every registered
  command synonym, attributed observations, target/value mismatch and trailing
  revocation without entering dispatch;
- a generated negation × bridge × write-action matrix plus positive modal and
  cross-clause controls;
- repository drift, lint and focused/full regression gates required by the
  project pipeline.

## 8. Rollout

Ship the new dimension and fail-loud validator in one backend release. The
change is backward compatible for valid calls. Production verification uses a
read-only synthetic illness fixture or an explicitly authorized owner account;
no health record is created during the read drill.

Rollback is the prior backend release. Because there is no schema migration,
rollback requires no data repair.
