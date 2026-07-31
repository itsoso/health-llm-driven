# Clinician Action Evidence Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace clause-level medical-command authorization with action-occurrence evidence so every action independently carries its actor, target, polarity and modality.

**Architecture:** A new pure `utterance_action_evidence` module parses raw spans into ordered `ActionEvidence` values and reduces all action families through one target-aware stance model. `utterance_intent_classifier` maps the reduced evidence to the existing public `IntentFrame`; clinician-bearing input never returns to raw whole-text authorization.

**Tech Stack:** Python dataclasses and `Literal` types, the existing deterministic intent vocabulary, pytest, and the existing Agent Kernel intent consumers.

---

## Preconditions and invariants

- Work only in
  `/Users/liqiuhua/work/personal/health-llm-driven/.claude/worktrees/clinical-context-intelligence`
  on branch `codex/clinical-context-intelligence`.
- The current branch contains reviewed-but-rejected clause-frame commits through
  `d4a7f5c64`. Replace their authorization implementation in normal commits; do
  not reset or rewrite shared history.
- Follow @test-driven-development for every behavior change.
- Do not use regex or add a dependency.
- Do not change the public `IntentFrame`.
- Do not touch Mobile, persistence models or `HealthProblem`.
- Provider/provenance parsing must be independent of action recognition.
- Every action occurrence owns its own actor, target, polarity and modality.
- Clinician and ambiguous actions never authorize.
- Clinician-bearing input never falls back to raw whole-text write/mutation
  authorization.
- Tests must cover public classifier behavior as well as parser invariants.

## Task 1A: Create typed span and provider evidence primitives

**Files:**

- Create: `backend/app/services/utterance_action_evidence.py`
- Create: `backend/tests/test_utterance_action_evidence.py`

### Step 1: Write the failing import and type tests

Write tests that import:

```python
from app.services.utterance_action_evidence import (
    ActionEvidence,
    EvidenceParse,
    ProviderEvidence,
    parse_action_evidence,
)
```

Assert that `ActionEvidence` is frozen and exposes:

```text
start
end
action
actor
target
target_start
target_end
polarity
modality
provenance
```

Assert that `EvidenceParse` contains:

```text
text
clinician_bearing
providers
actions
```

### Step 2: Run the new test and verify RED

```bash
DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai /Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin/python -m pytest -q --no-cov backend/tests/test_utterance_action_evidence.py
```

Expected: collection fails because the module does not exist.

### Step 3: Add the typed data model

Use private or exported `Literal` aliases for:

```python
ActionKind = Literal[
    "read",
    "save",
    "update",
    "delete",
    "sync",
    "advice",
    "media",
    "plan",
    "reminder",
]
ActorKind = Literal["user", "clinician", "ambiguous"]
PolarityKind = Literal["positive", "negative"]
ModalityKind = Literal["command", "question", "statement"]
TargetKind = Literal[
    "clinician_content",
    "clinician_record",
    "symptom",
    "medication",
    "diet",
    "weight",
    "health_record",
    "media",
    "plan",
    "reminder",
    "unknown",
]
```

Use frozen dataclasses. Validate spans through construction helpers rather than
adding runtime dependencies.

### Step 4: Write failing raw-span and provider tests

Cover:

- Chinese and ASCII punctuation;
- newline;
- consecutive delimiters such as `，：` and `！：`;
- conjunction-bearing text without punctuation;
- provider spans for doctor, attending doctor, physician, rehabilitation
  professional and physical therapist terms;
- a clinician-bearing sentence with no known action;
- offsets slicing back to the exact raw substring.

Provider tests must not require a save/read/mutation word to be present.

### Step 5: Implement raw region and provider scanning

Use a deterministic character scan that preserves raw offsets and delimiter
runs. Provider evidence should contain its source span and whether surrounding
language is a report, a basis (`根据/依据/按照`) or unresolved.

Do not infer action authority in this task.

### Step 6: Run the unit tests and verify GREEN

Run the command from Step 2.

Expected: all primitive, span and provider tests pass.

### Step 7: Commit

```bash
git add backend/app/services/utterance_action_evidence.py backend/tests/test_utterance_action_evidence.py
git commit -m "refactor(agent): add typed action evidence primitives"
```

## Task 1B: Extract independent action occurrences

**Files:**

- Modify: `backend/app/services/utterance_action_evidence.py`
- Modify: `backend/tests/test_utterance_action_evidence.py`

### Step 1: Write a failing same-region multi-actor matrix

Assert the ordered evidence for:

```text
我想记录饮食但医生说要保存诊断
医生说要保存诊断但请记录今天腰痛6分
我想记录今天腰痛但医生说要保存检查结果
医生说要删除用药记录然后请记录今天腰痛6分
```

The first two examples must each produce two action occurrences with different
actors. Tests must inspect action spans and prove they slice to the intended
verb occurrence.

### Step 2: Write a failing noun-versus-action matrix

These noun spans must not create save evidence:

```text
医生诊断记录
查看医生诊断记录
把医生诊断记录删除
请记录饮食然后需要查看医生诊断记录
请记录今天腰痛随后需要分析医生诊断记录
```

The first two contain no save action. The delete example contains delete, not
save. The final two contain exactly one user save occurrence.

### Step 3: Write a failing actor property matrix

Cross provider-before-action structures:

```text
医生对我说要删除昨天用药记录
医生跟我说要同步健康数据
医生叫我记录每天腰痛情况
医生指示我删除昨天用药记录
医生的建议是删除昨天记录
医生给我的要求是记录每天腰痛
医生希望我保存检查结果
物理治疗师要求我记录每天疼痛
理疗师让我删除健康记录
医师嘱咐我同步健康数据
```

Every action actor is `clinician` or `ambiguous`, never `user`.

Cross explicit user-authority structures:

```text
根据医生建议删除昨天用药记录
依据医生建议调整用药剂量
按照医生建议同步健康数据
请依据医生说的内容调整用药
根据医生诊断生成一张康复图片
```

Every action actor is `user`. Tests should vary the provider term independently
from the connective so the implementation cannot pass by enumerating complete
sentences.

### Step 4: Write failing target-resolution tests

Assert actual target beats clinician basis:

```text
删除根据医生诊断生成的用药记录       -> medication
调整医生诊断中提到的用药剂量       -> medication
记录根据医生诊断出现的今天腰痛6分  -> symptom
根据医生诊断记录今天腰痛6分        -> symptom
根据医生诊断生成一张康复图片        -> media
根据医生诊断创建明天复查提醒        -> reminder
根据医生诊断制定一个康复计划        -> plan
```

Only use `clinician_record` when no more concrete action target exists.

### Step 5: Write failing polarity and modality properties

For every save synonym:

```text
记录 / 记一下 / 记下 / 录入 / 保存 / 写入 / 存下来
```

cross:

- a direct positive command;
- `要不要...？`;
- `是否需要...？`;
- `不要/不用/无需/先别/不想/没有必要`.

Each occurrence must independently expose the correct positive/negative
polarity and command/question modality.

Repeat representative positive/negative/question cases for delete, update and
sync.

### Step 6: Run the new tests and verify RED

```bash
DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai /Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin/python -m pytest -q --no-cov backend/tests/test_utterance_action_evidence.py
```

Expected: occurrence, actor, noun-span, target and stance assertions fail
because only primitive scanning exists.

### Step 7: Implement a single occurrence extractor

Build an ordered action-candidate sequence from the shared action vocabulary.
For each candidate:

1. reject candidates inside known noun spans;
2. preserve its exact raw span;
3. resolve actor from structurally scoped provider, user-command and basis
   evidence;
4. resolve target from a local target span, excluding basis/modifier spans;
5. resolve polarity and modality from the same local occurrence window.

Do not compute a clause-level actor. Do not parse save actions in a second
function with different rules.

### Step 8: Run the unit tests and verify GREEN

Run the command from Step 6.

Expected: all action-evidence properties pass.

### Step 9: Commit

```bash
git add backend/app/services/utterance_action_evidence.py backend/tests/test_utterance_action_evidence.py
git commit -m "refactor(agent): parse actor per action occurrence"
```

## Task 1C: Reduce evidence and integrate the public classifier

**Files:**

- Modify: `backend/app/services/utterance_action_evidence.py`
- Modify: `backend/app/services/utterance_intent_classifier.py`
- Modify: `backend/app/services/agent_executor.py` only if shared marker import
  changes
- Modify: `backend/tests/test_utterance_action_evidence.py`
- Modify: `backend/tests/test_utterance_intent_classifier.py`
- Modify: `backend/tests/test_force_record_tool_choice.py`

### Step 1: Write a failing target-aware stance matrix

At the evidence-reducer level, cover:

```text
请记录医生诊断。算了，不要保存
删除医生诊断记录。算了，不要删除
调整医生诊断记录。算了，不要调整
请记录医生诊断。不要记录饮食
请记录饮食。不要保存医生诊断
别忘了记录饮食但不要保存医生诊断
```

Later negative evidence cancels only a compatible target. Questions,
clinician actions and ambiguous actions never become active.

### Step 2: Write failing public same-sentence actor tests

Assert:

```text
我想记录饮食但医生说要保存诊断
  -> the user diet write remains; no clinician-feedback write

医生说要保存诊断但请记录今天腰痛6分
  -> write / symptom / create

把医生诊断记录删除
  -> mutate / clinical_context / delete
```

The public test must assert final primary/domain/operation/is_write, not only
private actor fields.

### Step 3: Write the raw-authorizer canary

For clinician-bearing input, monkeypatch legacy whole-text mutation/write/plan/
reminder helpers to raise if called. Exercise:

- quoted mutation plus user symptom write;
- quoted reminder plus user clinician save;
- clinician basis plus media/plan/reminder;
- clinician statement with no action.

Expected: the classifier returns through the evidence path without invoking any
legacy raw authorizer.

### Step 4: Write failing operation-conservation tests

Assert existing public behavior for:

- direct clinician-record read and delete;
- direct medication update;
- ordinary symptom/diet/weight save;
- media creation;
- plan creation;
- reminder creation;
- clinician-record advice requiring the reliable model;
- the exact screenshot statement;
- explicit clinician-feedback save;
- clinician advice question.

Keep all current tests; add missing reviewer sentences rather than replacing old
coverage.

### Step 5: Run focused tests and verify RED

```bash
DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai /Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin/python -m pytest -q --no-cov backend/tests/test_utterance_action_evidence.py backend/tests/test_utterance_intent_classifier.py backend/tests/test_force_record_tool_choice.py
```

Expected: reducer and classifier-integration assertions fail while the new
extractor unit tests remain green.

### Step 6: Implement one target-aware reducer

Return a typed reduction result, not `IntentFrame`, to avoid a circular import.
The reducer must:

- group stance-bearing evidence by compatible target;
- process occurrences in raw order;
- apply late cancellation to save/delete/update/sync uniformly;
- exclude clinician, ambiguous and question evidence from active authority;
- preserve clinician content so an adjacent objectless user save can target it;
- retain active user read/media/plan/reminder evidence;
- make no decision from raw whole-text keywords.

### Step 7: Map reduction to the existing `IntentFrame`

In `utterance_intent_classifier.py`:

- call `parse_action_evidence(raw_text)` before normalization loses spans;
- if `clinician_bearing`, use only the typed reduction to authorize actions;
- map the selected active evidence to the existing primary/domain/operation
  values and reliable-model flag;
- if no action is safely active, return a reliable non-write
  `clinical_context` frame;
- if no clinician evidence exists, retain the existing general path.

Remove the superseded clause-frame/action-stance implementation from the
classifier. Do not keep two evidence reducers.

### Step 8: Preserve the symptom-extractor boundary

Keep the exact screenshot and explicit clinician-save input out of deterministic
fast-record. Keep clinician attribution out of
`_extract_clear_symptom_record`. Reuse the shared provider vocabulary without a
circular import.

### Step 9: Run focused tests and verify GREEN

Run the command from Step 5.

Then run downstream consumers:

```bash
DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai /Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin/python -m pytest -q --no-cov backend/tests/test_agent_kernel_capability_policy.py backend/tests/test_agent_turn_outcome.py backend/tests/test_agent_stream_no_false_record_claim.py
```

If the stream file's existing fixtures require a narrower selection, run the
complete file and report the actual result; do not silently omit it.

### Step 10: Replay the reviewer corpus

Create a parametrized public-behavior corpus containing every Critical and
Important sentence from the clause-frame reviews:

- multiple actors/actions in one punctuation region;
- noun “记录” contamination;
- provider structural variants;
- save and mutation late cancellation;
- target-specific cancellation;
- basis before/after actual target;
- plan/reminder/media conservation.

Run it as part of the normal test file. Do not rely on a one-off script as the
only evidence.

### Step 11: Inspect the replacement

Run:

```bash
git diff --check
rg -n "_ClauseFrame|_SaveStance|_classify_clause|_reduce_clinician_clauses" backend/app/services/utterance_intent_classifier.py
```

Expected: no superseded clause-level authorization implementation remains.

Also confirm:

- clinician-bearing evidence is checked before legacy whole-text authorizers;
- no raw clinical text is logged;
- no public contract, Mobile file, persistence model or `HealthProblem` changed.

### Step 12: Commit

```bash
git add backend/app/services/utterance_action_evidence.py backend/app/services/utterance_intent_classifier.py backend/app/services/agent_executor.py backend/tests/test_utterance_action_evidence.py backend/tests/test_utterance_intent_classifier.py backend/tests/test_force_record_tool_choice.py
git commit -m "refactor(agent): authorize clinician turns from action evidence"
```

Omit `agent_executor.py` from `git add` if it has no diff.

### Step 13: Run two-stage review

Dispatch a fresh spec reviewer against Tasks 1A–1C. Only after it passes,
dispatch a fresh code-quality reviewer with the full base/head range. Any
Critical or Important finding returns to the relevant evidence task; do not
continue to the write tool.

After Task 1C passes both reviews, continue with Task 2 in
`docs/plans/2026-07-30-clinician-attributed-context.md`.

