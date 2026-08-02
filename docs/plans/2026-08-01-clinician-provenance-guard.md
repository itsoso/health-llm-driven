# Clinician Provenance Guard Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the rejected general ActionEvidence authorization parser with a narrow clinician provenance guard, then complete explicit clinician-feedback persistence, provenance-labelled recall and the original screenshot regression.

**Architecture:** A pure guard runs before broad symptom and legacy intent inference. It returns only clinician-context/advice, a narrowly proven doctor-feedback save, an ambiguous non-write action, or `none`; only `none` reaches the unchanged legacy classifier. The explicit write uses the existing Agent Kernel capability/receipt path and `ClinicalJournalEntry(created_by="doctor")`.

**Tech Stack:** Python, FastAPI service layer, SQLAlchemy, Pydantic-compatible function schemas, pytest/pytest-asyncio, existing Agent Kernel tool registry/capability/receipt infrastructure.

---

## Execution rules

- Work only in the existing `codex/clinical-context-intelligence` worktree.
- Use TDD for every behavior change: RED, minimal implementation, GREEN.
- Use a fresh implementer per task, then a fresh spec reviewer, then a code
  quality reviewer. Do not start the quality review before the spec review is
  compliant.
- Do not retain the rejected ActionEvidence parser as dead security-critical
  code or a second authorization path.
- Do not change Mobile, database schema or `HealthProblem`.
- Do not log raw clinician text.
- Run tests directly; never pipe test output through `tail`.
- Regenerate architecture facts only with the official generator.
- Commit only the files owned by the task.

## Task 1: Replace ActionEvidence with the provenance guard

**Files:**

- Create: `backend/app/services/clinician_provenance_guard.py`
- Create: `backend/tests/test_clinician_provenance_guard.py`
- Create: `backend/tests/fixtures/clinician_provenance_guard_safety_cases.json`
- Modify: `backend/app/services/utterance_intent_lexicon.py`
- Delete: `backend/app/services/utterance_action_evidence.py`
- Delete: `backend/tests/test_utterance_action_evidence.py`
- Delete: `backend/tests/fixtures/utterance_action_evidence_safety_cases.json`

### Step 1: Write the fixed safety corpus

Create a hand-authored JSON fixture. Do not derive cases from guard constants.
Each case records `text`, expected `kind`, and whether an explicit write is
authorized.

Required positive cases:

```text
请记录医生诊断：臀肌无力导致腰肌代偿
保存医生意见：建议减少负重训练
医生说是臀肌无力。请记录医生诊断：臀肌无力导致腰痛
```

Required non-write cases:

```text
医生诊断是大腿和臀部肌肉无力导致腰肌代偿进而导致腰肌痛
医生认为是臀肌无力，我该怎么办？
医生说是臀肌无力，帮我记录一下
医生建议休息然后请保存诊断记录
医生说需要复查并删除昨天的用药记录
医生诊断是腰肌劳损同时提醒我明天复查
请记录医生诊断
```

Include provider variants (`医生/医师/大夫/主治医生/康复师/物理治疗师`) and
clinician record-noun controls such as `查看医生诊断记录` and
`删除医生诊断记录`, which must return `kind=none` so the legacy classifier
retains ownership.

### Step 2: Write failing guard tests

Define the intended API in the test:

```python
decision = classify_clinician_turn(text)
assert decision.kind == expected_kind
assert decision.authorizes_feedback_write is expected_authorized
```

Also assert:

- decision dataclasses are frozen;
- raw spans slice back to exact text;
- write decisions have non-empty `content_span` and `command_span`;
- non-write decisions never expose an authorizing command span;
- no regular expression or LLM call is used;
- no general delete/update/sync/plan/reminder/media action enum exists.

### Step 3: Run the focused test and verify RED

Run:

```bash
DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai /Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin/python -m pytest -q --no-cov backend/tests/test_clinician_provenance_guard.py
```

Expected: import failure because the guard does not exist.

### Step 4: Implement the minimal guard

Use a small immutable decision type:

```python
ClinicianTurnKind = Literal[
    "none",
    "clinician_context",
    "clinician_advice",
    "explicit_doctor_feedback_write",
    "ambiguous_clinician_action",
]

@dataclass(frozen=True)
class ClinicianTurnDecision:
    kind: ClinicianTurnKind
    provider_start: int | None
    provider_end: int | None
    content_start: int | None
    content_end: int | None
    command_start: int | None
    command_end: int | None
    reason_code: str

    @property
    def authorizes_feedback_write(self) -> bool:
        return self.kind == "explicit_doctor_feedback_write"
```

Implement a deterministic character/token scan with these boundaries:

- clinician report predicates create clinician context;
- clinician record nouns alone do not;
- questions/advice requests become `clinician_advice`;
- a write requires one supported root command, one explicit clinician-feedback
  object and non-empty content in the same command segment;
- a post-report hard-boundary command is allowed only when it repeats command,
  clinician-feedback object and non-empty content;
- objectless, coordinated or mixed actions become
  `ambiguous_clinician_action`;
- no unknown shape defaults to write.

Keep shared provider/report/object vocabulary in
`utterance_intent_lexicon.py`. Remove all evidence-only action-family, target,
stance, scope and work-meter metadata that existed only for the rejected
parser. Preserve every classifier-facing legacy tuple value and order.

Delete the rejected parser, its tests and fixture in the same commit so there
is one clinician authorization path.

### Step 5: Run tests and verify GREEN

Run the Step 3 command, then legacy classifier tests:

```bash
DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai /Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin/python -m pytest -q --no-cov backend/tests/test_utterance_intent_classifier.py
```

Expected: guard corpus and existing classifier tests pass.

### Step 6: Run targeted lint and structure checks

```bash
/Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin/ruff check backend/app/services/clinician_provenance_guard.py backend/app/services/utterance_intent_lexicon.py backend/tests/test_clinician_provenance_guard.py
git diff --check
```

Confirm `rg -n "utterance_action_evidence|ActionEvidence" backend/app backend/tests`
has no runtime/test references.

### Step 7: Commit

```bash
git add backend/app/services/clinician_provenance_guard.py backend/app/services/utterance_intent_lexicon.py backend/tests/test_clinician_provenance_guard.py backend/tests/fixtures/clinician_provenance_guard_safety_cases.json
git add -u backend/app/services/utterance_action_evidence.py backend/tests/test_utterance_action_evidence.py backend/tests/fixtures/utterance_action_evidence_safety_cases.json
git commit -m "refactor(intent): narrow clinician action authorization"
```

### Step 8: Two-stage review

The spec reviewer verifies the approved design and absence of a second parser.
The quality reviewer attacks report-vs-record nouns, missing content, compound
actions, hard-boundary explicit saves and legacy vocabulary drift. Fix and
re-review all Critical/Important findings before Task 2.

## Task 2: Integrate the guard before legacy intent and fast record

**Files:**

- Modify: `backend/app/services/utterance_intent_classifier.py`
- Modify: `backend/app/services/agent_executor.py`
- Modify: `backend/tests/test_utterance_intent_classifier.py`
- Modify: `backend/tests/test_force_record_tool_choice.py`
- Modify: `backend/tests/test_agent_executor_fast_routing.py`

### Step 1: Write failing public intent tests

Assert these public frames:

```python
bare = classify_agent_utterance(SCREENSHOT_TEXT)
assert (bare.primary, bare.domain, bare.operation, bare.is_write) == (
    "chat", "clinical_context", "acknowledge", False
)
assert bare.requires_reliable_tool_model is True

save = classify_agent_utterance(
    "请记录医生诊断：臀肌无力导致腰肌代偿"
)
assert (save.primary, save.domain, save.operation, save.is_write) == (
    "write", "clinical_context", "create", True
)
```

Add advice and ambiguous compound cases. The latter must be non-write and use
the reason `ambiguous_clinician_action`.

Add conservation cases for ordinary diet, current symptoms, medication,
media, plan, reminder, `查看医生诊断记录` and `删除医生诊断记录`.

Add clinician-basis mutation cases such as `根据医生诊断删除昨天用药记录`,
`依据医生意见调整用药剂量` and `按照医生建议同步健康数据`. They are
compound clinician-bearing actions and must map to reliable non-write
clarification; the same mutations without the clinician-basis prefix must keep
their legacy behavior.

### Step 2: Write the legacy-authorizer canary

Monkeypatch legacy write/mutation/plan/reminder/media helpers to raise. Feed
clinician-context, clinician-advice, explicit feedback save and ambiguous
clinician-action cases. All must return through the guard mapping without
calling legacy whole-text authorizers.

Include clinician-basis mutations in this canary. They must not fall through to
the legacy mutation authorizer until the user restates the operation without
the clinician-basis clause.

Feed `kind=none` controls and assert the legacy helpers remain reachable.

### Step 3: Write fast-record boundary tests

For the screenshot, advice, clinician-basis mutations and ambiguous compound
cases assert:

- `_extract_clear_symptom_record` returns `None`;
- forced record tool choice is not requested;
- `_record_intent_needs_detail_message` is not selected;
- an explicit feedback save is not redirected to the symptom extractor.

### Step 4: Run focused tests and verify RED

```bash
DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai /Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin/python -m pytest -q --no-cov backend/tests/test_clinician_provenance_guard.py backend/tests/test_utterance_intent_classifier.py backend/tests/test_force_record_tool_choice.py backend/tests/test_agent_executor_fast_routing.py
```

Expected: public classifier and fast-record integration assertions fail.

### Step 5: Map guard decisions to the existing public intent

At the start of `classify_agent_utterance`, call the guard on raw text before
normalization and symptom inference.

Map:

```text
none                               -> existing classifier
clinician_context                  -> chat/clinical_context/acknowledge
clinician_advice                   -> advice/clinical_context/analyze
explicit_doctor_feedback_write     -> write/clinical_context/create
ambiguous_clinician_action         -> chat/clinical_context/acknowledge
```

All non-`none` decisions require the reliable model. Preserve the guard
`reason_code` in the existing intent reason field.

Remove the superseded clause/action-evidence clinician authorization functions
from the classifier. Do not retain two reducers.

At the fast-record choke points, treat every non-`none` clinician decision as
ineligible for symptom extraction. The explicit feedback write continues to
the normal Agent tool path rather than deterministic symptom persistence.

### Step 6: Run focused tests and verify GREEN

Run Step 4. Then run downstream outcome tests:

```bash
DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai /Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin/python -m pytest -q --no-cov backend/tests/test_agent_turn_outcome.py backend/tests/test_agent_kernel_capability_policy.py
```

### Step 7: Commit and review

```bash
git add backend/app/services/utterance_intent_classifier.py backend/app/services/agent_executor.py backend/tests/test_utterance_intent_classifier.py backend/tests/test_force_record_tool_choice.py backend/tests/test_agent_executor_fast_routing.py
git commit -m "fix(intent): guard clinician context before fast record"
```

Run fresh spec and quality reviews before Task 3.

## Task 3: Register the typed doctor-feedback capability

**Files:**

- Modify: `backend/app/services/tool_schema_registry.py`
- Modify: `backend/app/services/agent_kernel/tool_registry.py`
- Modify: `backend/app/services/agent_kernel/capability_policy.py`
- Modify: `backend/app/services/agent_executor.py`
- Modify: `backend/tests/test_agent_kernel_capability_policy.py`
- Modify: `backend/tests/test_agent_runtime_tool_operations.py`

### Step 1: Write failing schema, receipt and policy tests

Assert:

```python
spec = get_tool_spec("record_doctor_feedback")
assert spec.operation == "write"
assert spec.receipt_required is True
assert spec.reconciliation_resource_type({}) == "clinical_journal_entry"
```

The public schema exposes optional `summary`, `assessment`, `plan` and
`visit_date`, rejects extra properties, and states that only an explicit user
request to record clinician feedback may use it.

Policy cases:

- bare clinician report: blocked;
- clinician advice: blocked;
- ambiguous/compound clinician action: blocked;
- explicit doctor-feedback save: allowed;
- unrelated explicit write such as weight: blocked.

### Step 2: Run focused tests and verify RED

```bash
DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai /Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin/python -m pytest -q --no-cov backend/tests/test_agent_kernel_capability_policy.py backend/tests/test_agent_runtime_tool_operations.py
```

Expected: unknown tool and missing receipt contract.

### Step 3: Register the tool and explicit-write policy

Add the model-visible schema, fixed write tool spec, required positive integer
ID and `clinical_journal_entry` receipt type. Capability policy requires the
guard-derived `write / clinical_context / create` frame; generic `is_write`
from another domain is insufficient.

Add the fixed receipt map entry and a non-sensitive progress label in
`agent_executor.py`.

### Step 4: Verify GREEN, commit and review

Run Step 2, targeted Ruff and `git diff --check`.

```bash
git add backend/app/services/tool_schema_registry.py backend/app/services/agent_kernel/tool_registry.py backend/app/services/agent_kernel/capability_policy.py backend/app/services/agent_executor.py backend/tests/test_agent_kernel_capability_policy.py backend/tests/test_agent_runtime_tool_operations.py
git commit -m "feat(agent): register clinician feedback capability"
```

Run fresh spec and quality reviews before Task 4.

## Task 4: Implement the owner-scoped receipted adapter

**Files:**

- Modify: `backend/app/services/agent_executor.py`
- Modify: `backend/tests/test_agent_write_adapter_rejections.py`
- Reuse: `backend/app/services/doctor_report_service.py`

### Step 1: Write failing validation and isolation tests

Cover:

- all text fields blank;
- missing current user identity;
- invalid `visit_date`;
- persistence service exception and rollback;
- a successful write for one user with a second user remaining untouched.

For success assert one `ClinicalJournalEntry`, `created_by == "doctor"`, exact
assessment preservation, positive ID and
`resource_type == "clinical_journal_entry"`.

For failure assert an observable `Error:`, no success receipt and no raw
clinician text in logs.

### Step 2: Run focused tests and verify RED

```bash
DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai /Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin/python -m pytest -q --no-cov backend/tests/test_agent_write_adapter_rejections.py
```

### Step 3: Implement `_exec_record_doctor_feedback`

Normalize fields, require any non-empty text, require `_current_user_id`, parse
or default the visit date, delegate to
`doctor_report_service.record_doctor_feedback`, and return receipt JSON with
`message`, `id`, `resource_type`, `created_by`.

On failure roll back, log operation name plus exception class only, and return
an observable error. Do not create or update `HealthProblem`.

### Step 4: Verify GREEN, commit and review

Run Step 2 and `backend/tests/test_doctor_report.py`.

```bash
git add backend/app/services/agent_executor.py backend/tests/test_agent_write_adapter_rejections.py
git commit -m "feat(agent): persist explicit clinician feedback"
```

Run fresh spec and quality reviews before Task 5.

## Task 5: Recall recent clinician feedback with provenance

**Files:**

- Modify: `backend/app/services/health_context_lite_service.py`
- Modify: `backend/app/services/agent_executor.py`
- Modify: `backend/tests/test_health_context_lite.py`
- Modify: `backend/tests/test_agent_write_adapter_rejections.py`

### Step 1: Write failing full/minimal context tests

Create recent doctor entries, another user's entry and a non-doctor entry.
Assert full context includes only the current user's recent doctor entries,
labels each as `用户转述的医生意见`, enforces per-field/section/entry bounds,
and does not call it Reva's diagnosis.

Assert minimal knowledge-only context omits the section.

### Step 2: Write failing invalidation tests

Build and cache full context, persist a doctor entry, prove the cached value is
stale, call `invalidate_health_context(user_id)`, then prove the rebuilt value
contains it. Missing cache keys are a no-op.

### Step 3: Run focused tests and verify RED

```bash
DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai /Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin/python -m pytest -q --no-cov backend/tests/test_health_context_lite.py backend/tests/test_agent_write_adapter_rejections.py
```

### Step 4: Implement bounded recall and post-commit invalidation

In full context only, query a small fixed number of recent
`ClinicalJournalEntry` rows filtered by current `user_id` and
`created_by == "doctor"`. Render non-empty fields with provenance and bounds.

Add `invalidate_health_context(user_id)` for full/minimal keys. Call it only
after confirmed persistence. Invalidation is fail-safe and cannot turn a
committed write into an uncertain failure. Optional context-load warnings log
only the exception class.

### Step 5: Verify GREEN, commit and review

Run Step 3.

```bash
git add backend/app/services/health_context_lite_service.py backend/app/services/agent_executor.py backend/tests/test_health_context_lite.py backend/tests/test_agent_write_adapter_rejections.py
git commit -m "feat(agent): recall clinician feedback with provenance"
```

Run fresh spec and quality reviews before Task 6.

## Task 6: Align prompts and prove the user-visible turn

**Files:**

- Modify: `backend/app/services/agent_executor.py`
- Modify: `backend/tests/test_agent_stream_no_false_record_claim.py`
- Modify: `backend/tests/test_agent_runtime_tool_operations.py`
- Modify: the nearest existing prompt-contract test if a separate file owns it

### Step 1: Write failing stream and prompt tests

Use the existing fake reliable-model harness with the screenshot sentence.
Assert zero tool calls/receipts, no generic record-details fallback, a completed
non-retry turn, and a model response that preserves clinician attribution.

Add ambiguous compound input and assert the response asks for a separate
explicit command without claiming persistence.

Add an explicit save operation test proving tool selection, permission and
receipt reconciliation.

Prompt contracts must state:

- preserve `用户转述的医生判断/评估` attribution;
- do not endorse it as Reva's diagnosis;
- do not auto-save a bare statement;
- compound clinician actions require a separate explicit command;
- only the typed tool stores structured clinician feedback;
- do not redirect it to `remember`.

### Step 2: Run focused tests and verify RED

```bash
DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai /Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin/python -m pytest -q --no-cov backend/tests/test_agent_stream_no_false_record_claim.py backend/tests/test_agent_runtime_tool_operations.py
```

### Step 3: Update prompts and outcome handling

Update the normal system prompt, tool-decision prompt and ambiguous-action
guidance. Do not hardcode a medical response for the screenshot. Ensure the
non-write clinician decision bypasses record-failure/retry reconciliation.

### Step 4: Verify GREEN, commit and review

Run Step 2 and `backend/tests/test_agent_turn_outcome.py`.

```bash
git add backend/app/services/agent_executor.py backend/tests/test_agent_stream_no_false_record_claim.py backend/tests/test_agent_runtime_tool_operations.py
git commit -m "test(agent): cover clinician context turns end to end"
```

Run fresh spec and quality reviews before Task 7.

## Task 7: Regenerate architecture facts and pass delivery Gates

**Files:**

- Regenerate if changed: `docs/_generated/system-map.json`
- Modify: `docs/dossiers/2026-07-30-clinician-attributed-context.md`

### Step 1: Regenerate and inspect system-map output

```bash
/Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin/python scripts/dump_system_map.py
/Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin/python scripts/dump_system_map.py --check
```

Keep only generator-produced changes. Never hand-edit counts.

### Step 2: Run the focused integration Gate

```bash
DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai /Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin/python -m pytest -q --no-cov backend/tests/test_clinician_provenance_guard.py backend/tests/test_utterance_intent_classifier.py backend/tests/test_force_record_tool_choice.py backend/tests/test_agent_executor_fast_routing.py backend/tests/test_agent_kernel_capability_policy.py backend/tests/test_agent_runtime_tool_operations.py backend/tests/test_agent_write_adapter_rejections.py backend/tests/test_health_context_lite.py backend/tests/test_agent_stream_no_false_record_claim.py backend/tests/test_doctor_report.py
```

Record the exact result in the Dossier. Do not continue with a failure.

### Step 3: Run governance and lint Gates

```bash
/Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin/python scripts/check_doc_drift.py
/Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin/python backend/scripts/check_dossier_consistency.py
git diff --check origin/main...HEAD
```

Run targeted Ruff over every modified Python file.

### Step 4: Execute independent G4 medical/write review

The reviewer must inspect:

- bare statement and advice never write;
- compound/ambiguous clinician actions never write;
- exact save envelope is the only clinician write authority;
- owner isolation, receipt integrity, rollback and log redaction;
- provenance-labelled context and no diagnosis endorsement;
- no `HealthProblem` mutation;
- no stale full context after successful persistence;
- no abandoned ActionEvidence runtime path.

Any Critical/Important or safety BLOCK returns to the owning task.

### Step 5: Update Dossier and commit verification artifacts

Record S4/S5 completion, exact G3 evidence, G4 verdict and system-map result.

```bash
git add docs/dossiers/2026-07-30-clinician-attributed-context.md
git add docs/_generated/system-map.json
git commit -m "docs(agent): verify clinician provenance capability"
```

Omit the generated JSON when it has no diff.

### Step 6: Final verification, push and deploy

From a clean worktree, rerun the focused integration Gate and inspect:

```bash
git status --short
git diff --check origin/main...HEAD
```

Push the feature branch only after all Gates are green. Follow the repository
backend deployment contract; do not deploy from dirty main. Verify production
with:

1. the screenshot sentence: useful attributed response, no write, no retry;
2. one explicit save sentence: verified receipt and next-turn provenance recall;
3. one compound clinician action: clarification, zero write.

G6 closes only after the user confirms Mobile behavior.
