# Semantic Illness Query Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make historical illness questions compile into owner-scoped canonical reads while preserving explicit health-record writes and failing loudly on invalid semantic dimensions.

**Architecture:** The shared utterance classifier remains the deterministic write-authorization boundary and gives interrogative speech acts read priority unless an explicit write command exists. The LLM expresses entity/time meaning through `health_query(dimension="illness", keyword=..., days=...)`; validation accepts only registered dimensions, and `health_read` compiles illness queries directly to an owner-filtered `IllnessEpisode` query. Existing Agent tool execution and answer synthesis remain unchanged.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy, Pydantic tool schemas, pytest, Ruff, existing AgentExecutor/ToolGateway.

---

### Task 1: Lock the read/write speech-act contract

**Files:**
- Modify: `backend/tests/test_utterance_intent_classifier.py`
- Modify: `backend/app/services/utterance_intent_classifier.py`

**Step 1: Write the failing contrast tests**

Add parameterized tests proving all historical-record questions remain read-only:

```python
@pytest.mark.parametrize(
    "message",
    (
        "我上一次口腔溃疡是什么时候 最近半年分别有哪些记录",
        "我以前有没有口腔溃疡记录？",
        "最近半年口腔溃疡有哪些记录",
        "上一次感冒记录是什么时候？",
    ),
)
def test_historical_record_questions_are_read_only(message):
    intent = classify_agent_utterance(message)
    assert intent.primary == "read"
    assert intent.is_write is False
```

Retain positive controls for `记录体重70kg`, `记录午餐吃了牛肉面`, a current
symptom fact and the existing compound write/advice cases.

**Step 2: Run the exact tests and observe RED**

Run:

```bash
/Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin/python -m pytest -q --no-cov \
  tests/test_utterance_intent_classifier.py -k 'historical_record_questions or real_record_command'
```

Expected: the screenshot query fails with `primary == "write"` before production
code changes.

**Step 3: Implement the minimal speech-act fix**

In `classify_agent_utterance`, make a question without
`_has_explicit_write_command(normalized)` enter the read frame even when the
domain is `unknown`. Keep the earlier advice, mutation and explicit compound
write branches authoritative. Do not add phrase-specific `哪些记录` patches.

The final predicate must express this invariant:

```python
question_without_write_command = has_question and not has_write_command
```

and compose it with the existing read/data-question branch before the broad
`has_write` fallback.

**Step 4: Run focused and full classifier tests**

Run:

```bash
/Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin/python -m pytest -q --no-cov \
  tests/test_utterance_intent_classifier.py
```

Expected: all classifier tests pass; positive write controls remain writes.

**Step 5: Commit the speech-act slice**

```bash
git add backend/tests/test_utterance_intent_classifier.py \
  backend/app/services/utterance_intent_classifier.py
git commit -m "fix(intent): keep historical record questions read only"
```

### Task 2: Register the typed illness query and reject semantic fallbacks

**Files:**
- Modify: `backend/tests/test_tool_validator.py`
- Modify: `backend/app/services/tool_schema_registry.py`
- Modify: `backend/app/services/llm/tool_validator.py`

**Step 1: Write failing schema/validator tests**

Add assertions that:

```python
def test_illness_query_dimension_is_registered():
    v = validate_tool_call(
        "health_query",
        {"dimension": "illness", "days": 183, "keyword": "口腔溃疡"},
    )
    assert v["error"] is None
    assert v["data"] == {
        "dimension": "illness",
        "days": 183,
        "keyword": "口腔溃疡",
    }

def test_unknown_query_dimension_fails_loudly():
    v = validate_tool_call("health_query", {"dimension": "symptom"})
    assert "未知" in (v["error"] or "")
    assert v["data"]["dimension"] == "symptom"
    assert v["data"]["dimension"] != "comprehensive"
```

Keep the existing alias tests (`medical_records`, `mri`, diet aliases) and the
missing-dimension default test. Update only the old unknown-dimension coercion
expectation.

**Step 2: Run tests and observe RED**

Run:

```bash
/Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin/python -m pytest -q --no-cov \
  tests/test_tool_validator.py -k 'illness_query or unknown_query or enum_registry'
```

Expected: illness is rejected and `symptom` is changed to `comprehensive`.

**Step 3: Implement the typed schema and fail-loud validation**

- Add `illness` to the `health_query.dimension` schema and `_QUERY_DIMENSIONS`.
- Document that `keyword` filters `IllnessEpisode.name` for illness queries.
- Add worked examples for latest and six-month illness history.
- Preserve alias normalization before enum validation.
- If a non-empty supplied dimension remains outside `_QUERY_DIMENSIONS` after
  alias normalization, return an explicit error listing registered dimensions.
- Preserve missing-dimension default `comprehensive`; this is syntactic defaulting,
  not semantic repair.

Do not change `health_analysis` enum behavior in this slice.

**Step 4: Run validator regression**

Run:

```bash
/Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin/python -m pytest -q --no-cov \
  tests/test_tool_validator.py
```

Expected: all tool validator tests pass.

**Step 5: Commit the query contract**

```bash
git add backend/tests/test_tool_validator.py \
  backend/app/services/tool_schema_registry.py \
  backend/app/services/llm/tool_validator.py
git commit -m "feat(agent): register semantic illness queries"
```

### Task 3: Add the owner-scoped canonical illness reader

**Files:**
- Create: `backend/tests/test_health_read_illness.py`
- Modify: `backend/app/services/health_read.py`

**Step 1: Write failing canonical-reader tests**

Create real ORM fixtures for two users and multiple `IllnessEpisode` rows. Cover:

```python
def test_illness_read_filters_owner_keyword_window_and_orders_latest(db):
    # current user: two oral-ulcer rows inside window, one outside, one cold
    # other user: one newer oral-ulcer row
    out = health_read.canonical_read(
        db,
        current_user.id,
        "illness",
        days=183,
        keyword="口腔溃疡",
    )
    rows = json.loads(out)
    assert [row["id"] for row in rows] == [newer.id, older.id]
    assert other_user_episode.id not in {row["id"] for row in rows}
```

Also cover no match, no user identity, all statuses, and returned field shape.

**Step 2: Run the new file and observe RED**

Run:

```bash
/Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin/python -m pytest -q --no-cov \
  tests/test_health_read_illness.py
```

Expected: `canonical_read(..., "illness")` returns `None` before implementation.

**Step 3: Implement `read_illness_episodes`**

In `health_read.py`:

- dispatch `dimension == "illness"` to a dedicated reader;
- require a non-null `user_id`;
- clamp the query window using the existing `_window_days` helper;
- filter `IllnessEpisode.user_id == user_id` and
  `IllnessEpisode.start_date >= since`;
- add `IllnessEpisode.name.ilike(f"%{keyword}%")` only when keyword is non-empty;
- order by `start_date DESC, id DESC` and bound the result to 100 rows;
- serialize only `id`, `name`, `start_date`, `end_date`, `status`, `severity`,
  `notes`; and
- return an explicit no-match message or a structured JSON result. Use the
  existing fail-loud logging/rollback pattern without logging health content.

**Step 4: Run illness and existing canonical-read regression**

Run:

```bash
/Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin/python -m pytest -q --no-cov \
  tests/test_health_read_illness.py \
  tests/test_agent_executor_health_query_wearable.py
```

Expected: both files pass; wearable and medical readers remain unchanged.

**Step 5: Commit the canonical reader**

```bash
git add backend/tests/test_health_read_illness.py backend/app/services/health_read.py
git commit -m "feat(health-read): query owner illness episodes"
```

### Task 4: Prove executor compilation and no wearable fallback

**Files:**
- Modify: `backend/tests/test_agent_executor_reads_in_process.py`
- Modify: `backend/tests/test_agent_executor_fast_routing.py`
- Modify: `backend/evals/behavior/xiaoba_core.yaml`

**Step 1: Write failing executor tests**

Add a real-db executor test that calls:

```python
out = _run(
    executor._exec_health_query(
        "http://x/api/v1",
        {},
        {"dimension": "illness", "days": 183, "keyword": "口腔溃疡"},
    )
)
```

Patch `_api_get` to raise so the test proves the canonical query performs zero
HTTP/wearable calls. Assert the matching episode is returned and sleep data is
absent.

Add an Agent routing regression whose fake provider emits the typed illness
tool call for the exact screenshot query. Assert:

- the turn is not `_prefer_fast_record_model`;
- `health_record` is never executed;
- `health_query` executes with `dimension=illness`, the keyword and bounded
  window; and
- final metadata contains read evidence and no write receipt/pending write.

**Step 2: Run the new tests and observe RED**

Run the exact new test node IDs. Expected: illness is unregistered/unreadable
before Tasks 2-3 and the original query still takes the wrong route before Task 1.

**Step 3: Add behavior-eval contrasts**

Add anonymized cases to `xiaoba_core.yaml`:

- read latest + six-month illness history;
- read-only “有哪些记录” paraphrase;
- explicit `记录口腔溃疡` write contrast;
- negated `不要记录，只查历史` contrast.

The evaluator must require an illness read tool and forbid health-record writes
for read cases. Do not include real dates or real user records.

**Step 4: Run executor regressions**

Run:

```bash
/Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin/python -m pytest -q --no-cov \
  tests/test_agent_executor_reads_in_process.py \
  tests/test_agent_executor_fast_routing.py \
  tests/test_agent_executor_health_query_wearable.py
```

Expected: all files pass and no illness test reaches `_api_get`.

**Step 5: Commit runtime/eval coverage**

```bash
git add backend/tests/test_agent_executor_reads_in_process.py \
  backend/tests/test_agent_executor_fast_routing.py \
  backend/evals/behavior/xiaoba_core.yaml
git commit -m "test(agent): cover semantic illness query flow"
```

### Task 5: Run qwen-max-3.7 and safety regression gates

**Files:**
- Modify if needed: `backend/evals/behavior/xiaoba_core.yaml`
- Modify: `docs/dossiers/2026-08-08-semantic-illness-query.md`

**Step 1: Discover the registered qwen-max-3.7 evaluator command**

Use repository scripts and model registry only; do not invent a provider/model
name. Confirm that the selected model is exactly the user-approved qwen-max-3.7
entry and that prompts contain only anonymized fixtures.

**Step 2: Run the behavior battery**

Run the repository-supported behavior evaluator filtered to the new cases and
model. Expected:

- all read cases select illness query semantics;
- zero read cases select `health_record` or mutating `health_manage`;
- write contrast still selects the current confirmed illness write path; and
- no case selects comprehensive/sleep for the illness request.

If the model/credential is unavailable, record the exact blocker in G3 and do
not claim model evaluation passed.

**Step 3: Run focused safety and compatibility suites**

Run:

```bash
/Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin/python -m pytest -q --no-cov \
  tests/test_utterance_intent_classifier.py \
  tests/test_tool_validator.py \
  tests/test_health_read_illness.py \
  tests/test_agent_health_manage.py \
  tests/test_agent_executor_reads_in_process.py \
  tests/test_agent_executor_fast_routing.py \
  tests/test_agent_executor_health_query_wearable.py \
  tests/test_force_record_tool_choice.py \
  tests/test_agent_write_adapter_rejections.py
```

Expected: zero failures.

**Step 4: Run static and repository gates**

```bash
/Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin/python -m ruff check \
  backend/app/services/utterance_intent_classifier.py \
  backend/app/services/tool_schema_registry.py \
  backend/app/services/health_read.py \
  backend/app/services/llm/tool_validator.py \
  backend/app/services/agent_executor.py \
  backend/tests/test_health_read_illness.py
/Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin/python -m compileall -q \
  backend/app/services
PATH=/Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin:$PATH \
  python scripts/check_doc_drift.py
PATH=/Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin:$PATH \
  python backend/scripts/check_dossier_consistency.py
git diff --check
```

Expected: all commands exit 0.

**Step 5: Update G3/G4 evidence and commit**

Record exact test counts, model-eval result, owner-isolation evidence and any
remaining blocker in the dossier. Do not mark G4 PASS until an independent code
review or equivalent project safety review has no blocking finding.

```bash
git add docs/dossiers/2026-08-08-semantic-illness-query.md \
  docs/specs/active/2026-08-08-semantic-illness-query.md
git commit -m "docs(agent): record semantic illness query gates"
```

### Task 6: Integrate, deploy and verify

**Files:**
- Modify: `docs/dossiers/2026-08-08-semantic-illness-query.md`

**Step 1: Rebase onto latest clean `origin/main`**

Fetch and inspect upstream changes touching the classifier, validator,
`health_read` or AgentExecutor. Resolve semantically and rerun Task 5 gates.

**Step 2: Push and wait for required CI**

Push only this branch. Do not merge or deploy with a red required check.

**Step 3: Integrate using the repository's approved main workflow**

Because this repository defaults to `main`, integrate only after G3/G4 are
green. Confirm the deploy source is a clean main commit containing this slice.

**Step 4: Deploy through `deploy.sh` and verify health**

Use the root deployment script. Record deploy commit, service health and API
health. Any failed health check returns to implementation; do not continue to
G6.

**Step 5: Run a production read-only verification**

Submit the exact query or an owner-authorized equivalent. Verify executed tool
metadata shows an illness read, no `health_record`, no mutating
`health_manage`, and no wearable/sleep evidence. If there are no matching
records, the answer must say so explicitly.

**Step 6: Close the dossier**

Record G5/G6 evidence, rollback reference and final commit. Mark complete only
after production behavior is observed.
