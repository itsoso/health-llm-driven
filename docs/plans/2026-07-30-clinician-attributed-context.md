# Clinician-Attributed Context Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the Agent understand clinician-attributed health statements without treating them as incomplete symptom writes, while allowing an explicitly requested save to create a receipted clinician journal entry.

**Architecture:** Parse clinician-bearing input into ordered action-occurrence evidence before whole-text keyword classification, then reduce actor/target/polarity/modality into the existing public `IntentFrame` with fail-closed write semantics. Reuse `ClinicalJournalEntry(created_by="doctor")` through a capability-gated Agent tool, then recall recent entries only in full personalized context with an explicit “用户转述” label. Keep bare statements read-only and leave `HealthProblem` unchanged.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic tool schemas, pytest/pytest-asyncio, existing Agent Kernel capability and receipt infrastructure.

---

## Preconditions and invariants

- Work only in branch `codex/clinical-context-intelligence`.
- Use the repository worktree at
  `/Users/liqiuhua/work/personal/health-llm-driven/.claude/worktrees/clinical-context-intelligence`.
- Run backend tests with the existing project virtualenv:
  `/Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin/python`.
- Use `DATABASE_URL=sqlite:///:memory:` for focused unit tests because the
  sandbox cannot reach the local PostgreSQL listener.
- Do not add a migration or a new persistence model.
- Do not change Mobile code.
- Do not create or mutate `HealthProblem` from the free-text statement.
- A bare clinician-attributed statement must never dispatch a write tool.
- Every claimed explicit save must have a verified
  `clinical_journal_entry` receipt.
- Preserve clinician provenance in both storage and model context.
- Do not log clinician text or other L3 health data on failures.
- Do not hand-edit architecture counts; regenerate the system map if the tool
  registry changes the generated snapshot.

## Superseded Task 1: Clause-frame attempt — do not execute

This section is retained only as implementation history. It was invalidated by
the second Correction Block after three quality-review cycles showed that a
single clause can contain multiple actions with different actors.

The authoritative replacement is:

`docs/plans/2026-07-31-clinician-action-evidence.md`

**Files:**

- Modify: `backend/tests/test_utterance_intent_classifier.py`
- Modify: `backend/tests/test_force_record_tool_choice.py`
- Modify: `backend/app/services/utterance_intent_classifier.py`
- Modify: `backend/app/services/agent_executor.py`

### Step 1: Write the failing clause-boundary matrix

Add one parametrized test for valid “clinician statement, then user save”
sequences:

```python
@pytest.mark.parametrize(
    "text",
    [
        "医生说是臀肌无力。请记录医生诊断：臀肌无力导致腰痛",
        "医生说是臀肌无力，帮我记录一下",
        "医生说是臀肌无力！请记录医生诊断：臀肌无力导致腰痛",
        "医生说是臀肌无力\n请记录医生诊断：臀肌无力导致腰痛",
    ],
)
def test_user_save_clause_can_reference_adjacent_clinician_context(text):
    intent = classify_agent_utterance(text)

    assert intent.primary == "write"
    assert intent.domain == "clinical_context"
    assert intent.operation == "create"
    assert intent.is_write is True
    assert intent.requires_reliable_tool_model is True
```

Add a quoted-action fail-closed matrix:

```python
@pytest.mark.parametrize(
    "text",
    [
        "医生说要查看昨天用药记录",
        "医生说要记录每天疼痛情况",
        "医生说要调整用药",
        "医生建议删除昨天的用药记录",
        "医生说要同步最近的健康数据",
        "康复师说请记录每天的疼痛",
    ],
)
def test_quoted_clinician_action_never_becomes_user_authorization(text):
    intent = classify_agent_utterance(text)

    assert intent.primary == "chat"
    assert intent.domain == "clinical_context"
    assert intent.operation == "acknowledge"
    assert intent.is_write is False
```

Add high-frequency attribution tests:

```python
@pytest.mark.parametrize(
    "text",
    [
        "医生告诉我是臀肌无力导致腰痛",
        "主治医生告诉我是臀肌无力导致腰痛",
        "大夫告知是臀肌无力导致腰痛",
    ],
)
def test_clinician_telling_user_is_context_not_agent_read_command(text):
    intent = classify_agent_utterance(text)

    assert intent.primary == "chat"
    assert intent.domain == "clinical_context"
    assert intent.operation == "acknowledge"
    assert intent.is_write is False
```

Keep the existing tests introduced by commits `22b906037`, `451b48c0c` and
`65c05fb38`; they form the single-clause compatibility matrix.

### Step 2: Write user-command conservation tests

Parametrize existing direct user actions and assert their old behavior:

```python
[
    ("查看医生诊断记录", "read", "list"),
    ("医生诊断记录有哪些？", "read", "ask"),
    ("删除医生诊断记录", "mutate", "delete"),
    ("把用药剂量调整为每天两次", "mutate", "update"),
    ("今天腰痛 6 分", "write", "create"),
]
```

Keep these explicit clinician saves as write-positive cases:

```python
[
    "请记录医生诊断：臀肌无力导致腰痛",
    "我想记录医生诊断：臀肌无力导致腰痛",
    "医生诊断请帮我记录一下",
    "医生诊断，记一下",
    "医生的诊断帮我保存下来",
    "请把医生诊断记录下来",
    "把医生说的内容保存下来",
]
```

### Step 3: Run the new tests and verify RED

Run:

```bash
DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai /Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin/python -m pytest -q --no-cov backend/tests/test_utterance_intent_classifier.py backend/tests/test_force_record_tool_choice.py
```

Expected: the new multi-clause and “医生告诉我” cases fail for the reviewer-
observed reasons. Confirm the failures are behavior mismatches, not collection
or fixture errors.

### Step 4: Add private clause-frame types

In `utterance_intent_classifier.py`:

- define private enums or `Literal` aliases for clause source, action, actor and
  object;
- define a frozen private `_ClauseFrame` dataclass carrying:

```python
@dataclass(frozen=True)
class _ClauseFrame:
    text: str
    source: str
    action: str
    actor: str
    object_kind: str
```

Do not change the public `IntentFrame` contract. Do not add a dependency or use
regex; the existing source-level test forbids regex in this module.

### Step 5: Split raw text before normalization

Implement a character scanner:

```python
_CLAUSE_BOUNDARIES = frozenset("，,。；;：:！？!?\n")


def _split_clauses(raw_text: str) -> tuple[str, ...]:
    ...
```

Requirements:

- preserve newline as a boundary before `_normalize` removes it;
- return trimmed non-empty clauses;
- treat consecutive punctuation as one boundary;
- retain clause order;
- do not allocate or parse more than the existing input text.

Add direct unit tests for punctuation, newline, empty clauses and consecutive
boundaries. Run those tests and make them green before continuing.

### Step 6: Parse each clause once

Implement one `_classify_clause(text)` path that determines all four fields:

- quoted source markers include clinician/provider terms combined with
  “说/表示/认为/建议/告诉/告知/评估/诊断/检查提示”;
- a source marker before an action makes the action actor `clinician`;
- otherwise a recognized action actor is `user`;
- distinguish a clinician-content object from a clinician-record noun;
- `告诉我/告知我` inside a clinician-source clause is attribution, not a user
  read request;
- an unrecognized/ambiguous object remains `unknown`.

Reuse the existing action and domain vocabulary. Remove or collapse the
per-action position helpers added by the three previous commits when the clause
frame replaces them; do not keep two authorization algorithms.

### Step 7: Reduce clause frames to `IntentFrame`

Implement one reducer with these rules:

```text
clinician actor action
  -> chat / clinical_context / acknowledge / no write

user save + clinician object in same clause
  -> write / clinical_context / create

clinician content clause + immediately adjacent user save with omitted object
  -> write / clinical_context / create

user read/update/delete/sync
  -> preserve existing operation only when its object is explicit in that
     user clause

clinician provenance + ambiguous actor/object
  -> chat / clinical_context / acknowledge / no write

no clinician provenance
  -> existing general classifier path
```

Do not allow delete/update/sync to inherit an omitted object from a preceding
clinician clause. Preserve reliable-model routing for every `clinical_context`
frame.

### Step 8: Keep deterministic symptom extraction as a second boundary

In `agent_executor.py`, continue importing the shared clinician attribution
vocabulary used by `_SYMPTOM_NON_SELF_MARKERS`. Do not duplicate the provider
marker list and do not create a circular import.

In `test_force_record_tool_choice.py`, keep the exact screenshot and explicit
clinician-save cases out of fast-record. Keep attribution variants out of
`_extract_clear_symptom_record`.

### Step 9: Run focused tests and confirm GREEN

Run the command from Step 3.

Expected: every existing and new classifier/fast-record test passes, including
the previously reported `92 passed` baseline plus the new clause matrix.

Run the wider intent consumers:

```bash
DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai /Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin/python -m pytest -q --no-cov backend/tests/test_agent_kernel_capability_policy.py backend/tests/test_agent_turn_outcome.py
```

Expected: no downstream contract regression.

### Step 10: Inspect the replacement diff

Run:

```bash
git diff --check
git diff --stat 65c05fb38..HEAD
```

Confirm:

- the clause frame is the single actor-authorization path;
- obsolete positional helpers are removed;
- no public contract, Mobile file, database model or `HealthProblem` changed.

### Step 11: Commit

```bash
git add backend/app/services/utterance_intent_classifier.py backend/app/services/agent_executor.py backend/tests/test_utterance_intent_classifier.py backend/tests/test_force_record_tool_choice.py
git commit -m "refactor(agent): classify clinician commands by clause provenance"
```

## Task 2: Define the typed write capability and policy

**Files:**

- Modify: `backend/tests/test_agent_kernel_capability_policy.py`
- Modify: `backend/tests/test_agent_runtime_tool_operations.py`
- Modify: `backend/app/services/tool_schema_registry.py`
- Modify: `backend/app/services/agent_kernel/tool_registry.py`
- Modify: `backend/app/services/agent_kernel/capability_policy.py`
- Modify: `backend/app/services/agent_executor.py`

### Step 1: Write failing registry and receipt tests

In `test_agent_runtime_tool_operations.py`, assert:

```python
spec = get_tool_spec("record_doctor_feedback")
assert spec.operation == "write"
assert spec.receipt_required is True
assert spec.reconciliation_resource_type({}) == "clinical_journal_entry"
```

Also assert that the public function schema exists and exposes:

- `summary`
- `assessment`
- `plan`
- `visit_date`

The schema description must say that the tool is only for an explicit request
to record clinician or rehabilitation-professional feedback.

### Step 2: Write failing capability tests

Add these policy cases:

```python
# blocked: no explicit write intent
utterance = "医生诊断是臀肌无力导致腰肌代偿"
tool_name = "record_doctor_feedback"

# allowed: explicit write intent
utterance = "请记录医生诊断：臀肌无力导致腰肌代偿"
tool_name = "record_doctor_feedback"
```

Also test that an unrelated explicit write, such as “记录体重 71.4kg”, cannot
authorize `record_doctor_feedback`.

### Step 3: Run the focused tests and confirm RED

```bash
DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai /Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin/python -m pytest -q --no-cov backend/tests/test_agent_kernel_capability_policy.py backend/tests/test_agent_runtime_tool_operations.py
```

Expected failure: the tool is unknown and has no receipt contract.

### Step 4: Register the capability

In `tool_schema_registry.py`, add a model-visible function schema:

```python
{
    "name": "record_doctor_feedback",
    "description": (
        "仅当用户明确要求记录或保存医生/康复师反馈时使用；"
        "裸陈述或咨询不得调用。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "assessment": {"type": "string"},
            "plan": {"type": "string"},
            "visit_date": {
                "type": "string",
                "description": "YYYY-MM-DD 或可解析的相对日期",
            },
        },
        "additionalProperties": False,
    },
}
```

Do not mark one specific text field as JSON-schema-required; the adapter must
accept any non-empty combination and reject the all-empty case.

In `tool_registry.py`, add a fixed write tool using
`_exec_record_doctor_feedback`, require a receipt, allow only
`clinical_journal_entry`, and require a positive integer resource ID.

In `capability_policy.py`, place the new tool in the explicit-write-only group.
Require both:

- the utterance intent is `write / clinical_context`; and
- an explicit save command is present.

Do not allow a generic `is_write` result for another domain to authorize the
tool.

In `agent_executor.py`, add
`"record_doctor_feedback": "clinical_journal_entry"` to the fixed receipt map
and add a non-sensitive progress label such as “记录医生反馈…”.

### Step 5: Run focused tests and confirm GREEN

Run the command from Step 3.

Expected: registry, receipt and capability tests pass.

### Step 6: Commit

```bash
git add backend/app/services/tool_schema_registry.py backend/app/services/agent_kernel/tool_registry.py backend/app/services/agent_kernel/capability_policy.py backend/app/services/agent_executor.py backend/tests/test_agent_kernel_capability_policy.py backend/tests/test_agent_runtime_tool_operations.py
git commit -m "feat(agent): register clinician feedback capability"
```

## Task 3: Implement the receipted persistence adapter

**Files:**

- Modify: `backend/tests/test_agent_write_adapter_rejections.py`
- Modify: `backend/app/services/agent_executor.py`
- Reuse without changing unless a test exposes a contract gap:
  `backend/app/services/doctor_report_service.py`

### Step 1: Write failing adapter validation tests

Add async tests for:

1. `summary`, `assessment` and `plan` all blank → local rejection with no DB
   write.
2. missing current user identity → local rejection.
3. invalid `visit_date` → local rejection with correction guidance.

Use the existing `_assert_local_rejection` helper and verify that no success
receipt is returned.

### Step 2: Write a failing successful-persistence test

Arrange an owner-scoped executor and call:

```python
result = await executor._exec_record_doctor_feedback(
    "",
    {},
    {
        "assessment": "大腿和臀部肌肉无力导致腰肌代偿进而导致腰肌痛",
        "visit_date": "2026-07-30",
    },
)
```

Assert:

- exactly one `ClinicalJournalEntry` exists for that user;
- `created_by == "doctor"`;
- `assessment` is preserved without upgrading it to a Reva diagnosis;
- the persisted visit date is present in the service’s existing objective
  representation;
- returned JSON contains `resource_type == "clinical_journal_entry"`;
- returned ID is the positive database ID.

Add a second user and verify that the first user’s save does not create or
modify that user’s journal.

### Step 3: Write a failing persistence-error test

Monkeypatch the service to raise. Assert:

- the session is rolled back;
- returned text starts with an observable `Error:`;
- the log contains only the exception class/operation metadata and does not
  contain the clinician text;
- no success receipt is returned.

### Step 4: Run the focused tests and confirm RED

```bash
DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai /Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin/python -m pytest -q --no-cov backend/tests/test_agent_write_adapter_rejections.py
```

Expected failure: `_exec_record_doctor_feedback` does not exist.

### Step 5: Implement the adapter

Add `_exec_record_doctor_feedback` beside the other write adapters.

Implementation rules:

- normalize and trim the three text fields;
- reject when all are empty;
- require `_current_user_id`;
- normalize `visit_date` through the existing date helper and default to the
  Agent’s reference date when omitted;
- delegate to `doctor_report_service.record_doctor_feedback`;
- return JSON with `message`, `id`, `resource_type`, and `created_by`;
- on persistence failure, roll back, log only operation name and exception
  class, and return an observable error;
- do not swallow an uncertain commit;
- do not create a `HealthProblem`.

Cache invalidation is connected in Task 4. Until then, the adapter must not
claim anything about context freshness.

### Step 6: Run focused tests and confirm GREEN

Run the command from Step 4.

Expected: all adapter rejection, persistence and isolation tests pass.

### Step 7: Commit

```bash
git add backend/app/services/agent_executor.py backend/tests/test_agent_write_adapter_rejections.py
git commit -m "feat(agent): persist explicit clinician feedback"
```

## Task 4: Recall clinician feedback with provenance

**Files:**

- Modify: `backend/tests/test_health_context_lite.py`
- Modify: `backend/app/services/health_context_lite_service.py`
- Modify: `backend/app/services/agent_executor.py`

### Step 1: Write failing full-context recall tests

Create multiple `ClinicalJournalEntry` records, including:

- recent entries for the current user with `created_by="doctor"`;
- an entry for another user;
- a non-doctor entry for the current user.

Build full context and assert:

- only the current user’s doctor entries appear;
- each entry is labelled “用户转述的医生意见”;
- the text is length-bounded and a fixed recent-entry limit is enforced;
- no language promotes the content to Reva’s diagnosis.

### Step 2: Write a failing minimal-context test

Build minimal context for a knowledge-only request and assert that clinician
journal entries are omitted.

### Step 3: Write a failing cache invalidation test

1. Build and cache full context.
2. Add a clinician journal entry.
3. Confirm the already-cached value does not yet include it.
4. Call `invalidate_health_context(user_id)`.
5. Build context again and assert the new provenance-labelled entry appears.

Also call invalidation for a user with no cache and assert it is a no-op.

### Step 4: Run the focused tests and confirm RED

```bash
DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai /Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin/python -m pytest -q --no-cov backend/tests/test_health_context_lite.py
```

Expected failure: doctor entries are absent and the invalidation API does not
exist.

### Step 5: Implement bounded recall and invalidation

In `health_context_lite_service.py`:

- add `invalidate_health_context(user_id)` that evicts both full and minimal
  cache keys and never raises for a missing key;
- only in the full-context path, query a small fixed number of recent
  `ClinicalJournalEntry` rows where:
  - `user_id` matches;
  - `created_by == "doctor"`;
- render non-empty summary/assessment/plan fields with the provenance prefix;
- apply per-field and total-section bounds;
- log a warning with exception class only if this optional context section
  cannot be loaded.

In `_exec_record_doctor_feedback`, call the invalidator only after a confirmed
successful save. Keep invalidation fail-safe and do not turn a committed write
into an uncertain failure.

### Step 6: Run focused tests and confirm GREEN

Run the command from Step 4, then rerun the adapter tests:

```bash
DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai /Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin/python -m pytest -q --no-cov backend/tests/test_agent_write_adapter_rejections.py
```

Expected: recall, isolation, minimal-budget, bound and invalidation tests pass.

### Step 7: Commit

```bash
git add backend/app/services/health_context_lite_service.py backend/app/services/agent_executor.py backend/tests/test_health_context_lite.py backend/tests/test_agent_write_adapter_rejections.py
git commit -m "feat(agent): recall clinician feedback with provenance"
```

## Task 5: Align prompts and prove the original turn end-to-end

**Files:**

- Modify: `backend/tests/test_agent_stream_no_false_record_claim.py`
- Modify: the nearest existing Agent prompt contract test if present
- Modify: `backend/app/services/agent_executor.py`

### Step 1: Write a failing streaming regression

Use the existing fake streaming LLM harness with the exact sentence:

```text
医生诊断是大腿和臀部肌肉无力导致腰肌代偿进而导致腰肌痛
```

Make the fake reliable model return an acknowledgement that preserves
attribution and offers a useful next action. Assert:

- no tool call occurs;
- the model response is not replaced by
  `_record_intent_needs_detail_message`;
- no “你想记的是哪类、值是多少” text appears;
- the turn outcome is completed, not retryable/action-not-executed;
- no write receipt is emitted.

Add a companion explicit-save test in the existing operation harness proving
that the runtime selects/permits `record_doctor_feedback` and reconciles its
receipt.

### Step 2: Write prompt contract tests

Assert that the system/tool-decision prompts contain these behavioral rules:

- preserve clinician attribution;
- do not endorse user-reported clinician feedback as Reva’s diagnosis;
- do not auto-save a bare statement;
- only explicit save language may call `record_doctor_feedback`;
- do not use `remember` for structured medical facts.

### Step 3: Run focused tests and confirm RED

```bash
DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai /Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin/python -m pytest -q --no-cov backend/tests/test_agent_stream_no_false_record_claim.py backend/tests/test_agent_runtime_tool_operations.py
```

Expected failure: prompt contract and/or new streaming expectation is not yet
implemented.

### Step 4: Update prompts

In the normal system prompt and tool-decision prompt:

- distinguish “understand/use as context” from “persist”;
- tell the model to state “你转述的医生判断/评估” when reflecting causality;
- prohibit independent diagnosis confirmation;
- reserve `record_doctor_feedback` for explicit save commands;
- point structured clinician facts to the new typed tool, never `remember`.

Do not hardcode a canned medical answer for the screenshot. The intent frame
and prompt should improve the class of clinician-attributed inputs.

### Step 5: Run focused tests and confirm GREEN

Run the command from Step 3.

Expected: original sentence finishes as an ordinary intelligent response with
zero writes, and explicit save has a verified receipt.

### Step 6: Commit

```bash
git add backend/app/services/agent_executor.py backend/tests/test_agent_stream_no_false_record_claim.py backend/tests/test_agent_runtime_tool_operations.py
git commit -m "test(agent): cover clinician context turns end to end"
```

## Task 6: Regenerate architecture artifacts and pass Gates

**Files:**

- Regenerate if changed: `docs/_generated/system-map.json`
- Modify: `docs/dossiers/2026-07-30-clinician-attributed-context.md`
- Modify only if generator requires it: generated system-map companions

### Step 1: Regenerate the system map

Run the project generator, using the command documented by
`docs/system-map/INDEX.md`. If the documented command is:

```bash
/Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin/python scripts/dump_system_map.py
```

run it from the worktree root. Inspect the diff and keep only generated output
caused by the new tool/route architecture. Never type counts into docs.

### Step 2: Run the focused integration gate

```bash
DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai /Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin/python -m pytest -q --no-cov backend/tests/test_utterance_intent_classifier.py backend/tests/test_force_record_tool_choice.py backend/tests/test_agent_kernel_capability_policy.py backend/tests/test_agent_runtime_tool_operations.py backend/tests/test_agent_write_adapter_rejections.py backend/tests/test_health_context_lite.py backend/tests/test_agent_stream_no_false_record_claim.py backend/tests/test_doctor_report.py
```

Record the full pass/fail count in the Dossier. Do not pipe test output through
`tail`.

### Step 3: Run drift, lint and targeted security checks

Run the repository’s documented commands for:

- system-map drift;
- Dossier consistency;
- Python lint/type checks covering modified files;
- secret/sensitive-log checks if provided.

If a command fails, fix the cause and rerun the exact failing command before
proceeding.

### Step 4: Execute G4 medical/write-path review

Use the repository safety-gate protocol with an independent reviewer. The
review must explicitly inspect:

- no write from the bare statement;
- owner isolation;
- explicit-write capability authorization;
- receipt integrity;
- rollback and log redaction;
- clinician provenance;
- no diagnosis endorsement;
- no `HealthProblem` mutation;
- no stale cache after a successful write.

Any BLOCK or required fix returns to the relevant implementation task; do not
continue to deployment with a red Gate.

### Step 5: Update Dossier and commit verification artifacts

Update:

- S4 task completion;
- S5 implementation commits;
- G3 exact test evidence;
- G4 reviewer verdict and findings;
- S8 system-map/documentation result.

Commit only the generated and Dossier files owned by this feature:

```bash
git add docs/dossiers/2026-07-30-clinician-attributed-context.md docs/_generated/system-map.json
git commit -m "docs(agent): verify clinician context capability"
```

Omit `docs/_generated/system-map.json` from `git add` if regeneration produced
no diff.

### Step 6: Final pre-push verification

Run:

```bash
git status --short
git diff --check origin/main...HEAD
```

Then run the focused integration gate once more from a clean working tree.
Only after all checks pass:

```bash
git push -u origin codex/clinical-context-intelligence
```

Deployment and production smoke testing remain governed by G5/G6 and must not
start from the dirty main workspace.
