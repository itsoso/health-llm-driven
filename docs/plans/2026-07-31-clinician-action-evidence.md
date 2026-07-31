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

## Task 1B v2 correction: constrain families and assign actor scopes

This section supersedes Task 1B Steps 1–9 for all work after commit
`065f47220`. That commit did not pass specification review and must not be used
by Task 1C until this correction passes both review gates.

**Files:**

- Modify: `backend/app/services/utterance_intent_lexicon.py`
- Modify: `backend/app/services/utterance_action_evidence.py`
- Modify: `backend/app/services/utterance_intent_classifier.py` only to restore
  its pre-Task-1B imports/constants and behavior
- Modify: `backend/tests/test_utterance_action_evidence.py`
- Modify: `backend/tests/test_utterance_intent_classifier.py`
- Regenerate: `docs/_generated/system-map.json` only when the official
  generator reports a structural change

### Step 1: Freeze the legacy classifier contract

Restore the legacy values and ordering of `QUESTION_SIGNALS`,
`MUTATION_NEGATIONS` and the other classifier-facing tuples to their values at
`065f47220^`. Restore `_has_question_signal()` to its previous behavior.

Before implementation, add a golden compatibility matrix that proves Task 1B
does not change public classifier output for at least:

```text
删除用药记录么
勿删除用药记录
不再删除用药记录
该不该记录今天腰痛6分
今天我没吃那么多，晚餐的两千大卡只有吃了四分之一
```

The legacy view and the stricter evidence view live in the same lexicon module,
but the classifier must consume only the legacy view until Task 1C.

### Step 2: Define structured evidence vocabulary

Add immutable lexicon rows that preserve each surface verb's original family
membership instead of flattening all creation verbs into one set. At minimum:

```text
生成 -> media, plan
保存 -> save, plan
设置 -> reminder
制定 -> plan
制作 -> media
创建 -> reminder
```

Read candidates must derive from `READ_ACTIONS`; save, mutation, media, plan and
reminder candidates must derive from their shared tuples. Put evidence-only
question and negation cues in explicitly named evidence constants with their
prefix/suffix/terminal placement semantics. Do not copy a filtered tuple into
the parser or tests.

### Step 3: Write the family-conservation RED matrix

For every structured create lexeme:

- each listed allowed family gets a positive target example;
- every unlisted media/plan/reminder family gets a negative example;
- an incompatible target must not emit an authorizing evidence under another
  family;
- an action-like target noun such as “提醒” must not create a second candidate
  that launders the incompatible outer verb.

Pin these overlap cases:

```text
保存康复计划 -> plan
保存诊断记录 -> save
生成康复图片 -> media
生成康复计划 -> plan
生成复查提醒 -> no reminder authorization
设置康复计划 -> no plan authorization
制作复查提醒 -> no reminder authorization
创建康复图片 -> no media authorization
```

Replace the rejected all-verbs × all-targets success matrix. Assert that parser
candidate surfaces exactly cover the shared structured lexicon, including all
`READ_ACTIONS`.

### Step 4: Write the actor-scope RED matrix

Correct the same-region assertions:

```text
医生说要保存诊断但请记录今天腰痛6分
  -> 保存 clinician; 记录 user
医生说要删除用药记录然后请记录今天腰痛6分
  -> 删除 clinician; 记录 user
```

Cross the shared top-level transition cues with strict user-command cues.
Separately cross every supported quote pair with “请/帮我” and prove that a
provider-owned quote never switches to user. Also cover:

```text
医生说请记录腰痛 -> clinician
医生说要删除并保存记录 -> both clinician
医生说要保存诊断但「请记录腰痛」 -> both clinician/ambiguous
医生说要保存诊断。请记录腰痛 -> clinician; user
医生说要保存诊断但我想记录腰痛 -> clinician; user
```

The actor property matrix must derive transition and strict command cues from
the shared evidence lexicon.

### Step 5: Implement constrained candidates

Replace the single `verb -> action` table with candidates containing:

```text
raw span
verb
allowed_families
```

Use longest-surface matching and merge family membership for an identical
surface. Resolve the local governed target before choosing the final family.
The final media/plan/reminder family must be the intersection of the target
family and `allowed_families`. If the intersection is empty, fail closed and
emit no authorizing `ActionEvidence`. Do not expose a generic public
`action="create"` fallback.

Keep Task 1A span and ordering invariants. Preserve the working noun,
basis-modifier, target-conflict, polarity, modality, completed-aspect and
relative-clause behavior.

### Step 6: Implement one linear actor-scope pass

Replace per-candidate backward actor guessing with a left-to-right assignment
pass whose state distinguishes:

```text
user
unquoted provider report
provider-owned quote
clinician basis
```

Provider-owned quote scope has highest priority. In an unquoted provider report,
the first action and coordinated actions remain clinician/ambiguous. A switch to
user requires:

1. at least one prior clinician-owned action in the report;
2. a top-level transition or hard sentence boundary outside any owned quote;
3. an explicit user command cue before the new action.

An explicit first-person cue may reset at a top-level boundary. Coordination
markers alone never reset provider ownership.

### Step 7: Drive stance properties from the evidence lexicon

Delete handwritten `_SAVE_SYNONYMS`, selected question subsets and equivalent
test-only vocabularies. Parameterize the save, mutation, question, negation and
actor-transition matrices directly from the evidence constants. A lexicon
change must automatically add or remove the corresponding property cases.

### Step 8: Verify and review

Run:

```bash
DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai /Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin/python -m pytest -q --no-cov backend/tests/test_utterance_action_evidence.py backend/tests/test_utterance_intent_classifier.py backend/tests/test_force_record_tool_choice.py
```

Then run targeted Ruff, the official system-map generator/check,
`check_doc_drift.py`, dossier consistency and `git diff --check`.

Dispatch a fresh specification reviewer. Only after it reports full compliance
dispatch the existing Task 1B quality reviewer for a final adversarial review.
Any Critical or Important issue keeps Task 1B open and Task 1C blocked.

## Task 1B v3 correction: require authorization proof

This section supersedes Task 1B v2 after quality review of `2a8f57b07`.
Task 1A invariants and v2 family conservation remain valid. The v2 actor,
stance, action-role and target algorithms must not feed Task 1C.

**Files:**

- Modify: `backend/app/services/utterance_intent_lexicon.py`
- Replace internals: `backend/app/services/utterance_action_evidence.py`
- Modify: `backend/app/services/utterance_intent_classifier.py` only to import
  shared legacy vocabulary without changing public behavior
- Modify: `backend/tests/test_utterance_action_evidence.py`
- Modify: `backend/tests/test_utterance_intent_classifier.py`
- Add:
  `backend/tests/fixtures/utterance_action_evidence_safety_cases.json`
- Regenerate `docs/_generated/system-map.json` only if the official generator
  reports a code-structure change

### Step 1: Add the independent security corpus and prove RED

Create a fixed JSON corpus that does not import or derive from the lexicon. It
must include every Task 1B v2 quality finding and positive controls:

```text
医生说根据康复师建议删除用药记录
医生说依据物理治疗师诊断保存诊断记录
我说“根据医生建议‘请删除用药记录’”
根据医生建议应不应该删除用药记录
根据医生建议删除用药记录好不好
根据医生建议如果删除用药记录会怎么样
根据医生建议不应删除用药记录
根据医生建议不得删除用药记录
根据医生建议拒绝删除用药记录
不要删除再保存任何用药记录
根据医生建议查看删除前的用药记录
根据医生建议分析调整以前的用药剂量
根据医生建议我曾删除用药记录
根据医生建议查看用药删除记录
删除根据医生对用药的建议写成的诊断记录
删除根据医生对用药的建议整理的诊断记录
保存康复计划并诊断记录
根据医生建议保存康复计划和诊断记录
```

For each case, pin ordered action surface, actor, target, polarity, modality and
whether it is authorization-eligible. Add positive controls for top-level bare
imperative, `请/帮我/把/我要`, clinician basis command, provider-owned quote,
and an explicit user command after a completed clinician report.

Run the focused test and preserve the initial failure evidence.

### Step 2: Extend the typed primitives without changing public intent

Add private immutable structures for:

```text
lexical scan index
nested quote scope
nested provider report/basis scope
action draft and action group
command proof
target and stance resolution
```

Extend `ModalityKind` with `unknown`, or use an equivalent private
non-authorizing modality that cannot be confused with `command`. Keep the
public `ActionEvidence`, `ProviderEvidence` and `EvidenceParse` frozen/raw-span
invariants. Task 1B still does not map evidence to `IntentFrame`.

### Step 3: Build one lexical index

Use one deterministic character scan, with vocabulary bucketed by first
character and longest surface, to emit ordered events for:

- quote open/close;
- provider and report/basis predicate;
- action surface and allowed families;
- target head;
- stance/cue;
- hard/soft boundary and conjunction.

Build nested quote scopes with a stack. Unclosed quotes extend to end of input
and remain fail closed. Link provider scopes and event containment with ordered
cursors. Candidate processing must not call full-text `.find/.rfind` or rescan
quotes, targets or basis modifiers.

### Step 4: Build nested ownership scopes

Actor priority is:

```text
provider-owned quote
> any enclosing active clinician report
> other reported/quoted speech
> unresolved provider speech
> local clinician basis plus user command proof
> ordinary user command proof
```

An outer report cannot be replaced by a newer inner basis. Lower-priority
evidence may only tighten to clinician/ambiguous. Preserve the approved
unquoted report transition behavior: after at least one clinician action, a
top-level transition or hard boundary plus a strict user command proof can
start a new user action group outside an owned quote.

### Step 5: Require positive command proof

Only the following top-level shapes may return `modality=command`:

```text
ACTION [OBJECT]
请|帮我|麻烦|给我 + ACTION [OBJECT]
我要|我想|我需要 + ACTION [OBJECT]
[请...] 把 + OBJECT + ACTION
根据|依据|按照 + provider basis + ACTION [OBJECT]
proven command + top-level action coordination + ACTION [OBJECT]
```

All tokens between the governing boundary/cue and action must be consumed by a
known shape. An unknown prefix defaults to `unknown`/non-authorizing, never
`command`. Known question, negative, completed and conditional forms retain
their precise modality/polarity; missing a marker remains safe because it
cannot produce command proof. Negative coordination propagates within the same
action group unless a new explicit positive command proof starts.

### Step 6: Classify action structural roles

Before stance resolution, classify each action draft as:

- `governor`;
- valid top-level `coordinated`;
- `embedded` in another action's object/modifier;
- `noun` inside an action-like record/history phrase.

Only governor/coordinated drafts may receive command proof. This must block
inner mutations in relative/history/read phrases without enumerating every
possible suffix.

### Step 7: Resolve target heads and conflicts structurally

Use the action group and ordered events to define object windows. Soft
conjunctions do not end the window unless they introduce another action group.
Within an object:

- `X 的 Y` treats `X` as modifier and the right-hand `Y` as head regardless of
  the modifier verb;
- different target kinds joined at the same object level by
  `和/与/及/以及/并/、` set `conflicted=true` and `target=unknown`;
- same-kind coordinated heads may keep that kind;
- create family remains
  `allowed_families ∩ resolved_target_family`; an empty or conflicted result
  emits no authorization-eligible action evidence.

Delete the basis-modifier verb whitelist and raw separator target truncation.

### Step 8: Consolidate the lexicon without behavior drift

Move provider/report/basis/action/target/stance metadata into typed evidence
rows in `utterance_intent_lexicon.py`. Keep legacy tuple values and order
byte-compatible with the pre-Task-1B classifier. Public classifier golden tests
must remain unchanged.

Lexicon-derived property tests remain for vocabulary coverage only. They do not
replace the fixed security corpus.

### Step 9: Prove bounded scanning work

Add deterministic instrumentation or an internal work-unit count so a 16x
repeated-event input stays within a generous near-linear bound. Also assert:

- the lexical scan runs once;
- per-candidate code contains no full-text `.find/.rfind`;
- raw spans and ordering remain exact;
- no regex or new dependency is introduced.

The performance test should not rely on a fragile absolute wall-clock
threshold.

### Step 10: Verify and review

Run:

```bash
DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai /Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin/python -m pytest -q --no-cov backend/tests/test_utterance_action_evidence.py backend/tests/test_utterance_intent_classifier.py backend/tests/test_force_record_tool_choice.py
```

Then run targeted Ruff, the official system-map generator/check, doc drift,
dossier consistency and `git diff --check`.

Dispatch a fresh specification reviewer. After it passes, dispatch a fresh
quality reviewer with the complete fixed corpus plus independent probes. Any
Critical or Important issue keeps Task 1B open and Task 1C blocked.

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
