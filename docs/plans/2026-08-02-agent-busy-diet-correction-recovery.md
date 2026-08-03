# Agent Busy And Diet Correction Recovery Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make Mobile truthfully queue Backend-busy follow-up turns and make a numeric-fraction diet correction complete once, without inventing nutrition or looping on ambiguity.

**Architecture:** The Mobile XHR adapter exposes non-2xx responses as a sanitized typed error; `useChatEngine` maps only the known 409 busy contract into its existing FIFO queue and retries one stable turn ID with one bounded timer. The Backend extends its deterministic fraction parser, creates safe update data for nutrition-poor records, and terminates unresolved selection before another LLM/tool round.

**Tech Stack:** React Native/Expo, TypeScript, Jest, Python 3, FastAPI service layer, pytest, SQLAlchemy test fixtures.

---

### Task 1: Make Mobile stream HTTP failures explicit

**Files:**
- Modify: `mobile/services/chat.ts:305-405`
- Test: `mobile/services/__tests__/chatStream.test.ts`

**Step 1: Write the failing transport test**

Add a case that sets the mock XHR to status 409 with a JSON body and calls
`onload`. Assert that the first iterator read rejects with an exported
`ChatStreamHttpError`, status `409`, and the safe Backend detail.

```ts
it('rejects a busy JSON response instead of parsing it as SSE', async () => {
  const first = streamChat('晚餐只吃了 1/2 修改记录', undefined, undefined,
    undefined, undefined, 'typed', 'turn-busy-1').next();
  await Promise.resolve();
  const xhr = MockXMLHttpRequest.instances[0];
  xhr.status = 409;
  xhr.responseText = JSON.stringify({ detail: '上一条消息仍在处理，请稍后重试' });
  xhr.onload?.();
  await expect(first).rejects.toMatchObject({
    name: 'ChatStreamHttpError',
    status: 409,
    detail: '上一条消息仍在处理，请稍后重试',
  });
});
```

**Step 2: Run the test and confirm RED**

Run:

```bash
cd mobile
npx jest --runInBand --runTestsByPath services/__tests__/chatStream.test.ts
```

Expected: FAIL because status 409 currently completes as an empty SSE stream.

**Step 3: Implement the typed HTTP error**

Add an exported error carrying only `status` and sanitized `detail`. Parse the
response body defensively and use a generic fallback for malformed or unsafe
details. In `xhr.onload`, check `status < 200 || status >= 300` before appending
response text to SSE chunks, assign the typed error, mark done, and wake the
generator.

```ts
export class ChatStreamHttpError extends Error {
  readonly status: number;
  readonly detail?: string;
  constructor(status: number, detail?: string) {
    super(detail || `请求失败 (status: ${status})`);
    this.name = 'ChatStreamHttpError';
    this.status = status;
    this.detail = detail;
  }
}
```

Do not retain response headers, request body, token, prompt or image bytes.

**Step 4: Run the focused test and confirm GREEN**

Run the Task 1 command again. Expected: all `chatStream` tests pass.

**Step 5: Commit Task 1**

```bash
git add mobile/services/chat.ts mobile/services/__tests__/chatStream.test.ts
git commit -m "fix(mobile): surface agent stream HTTP errors"
```

### Task 2: Requeue known Backend-busy turns with bounded backoff

**Files:**
- Modify: `mobile/hooks/useChatEngine.ts:1-20,480-510,655-675,1150-1230,1930-2080`
- Test: `mobile/hooks/__tests__/useChatEngine.test.ts`

**Step 1: Write failing queue tests**

Import/mock `ChatStreamHttpError`, use fake timers, and add tests covering:

- first attempt throws the known 409, then the retry succeeds;
- `sendMessage` resolves `true` for a text-only turn once it is locally queued;
- the assistant placeholder reads `上一条仍在处理，本条已排队。`;
- retry is not immediate and occurs only after the scheduled delay;
- both calls use exactly the same `client_turn_id` argument;
- reconciliation does not poll the never-admitted turn on a classified 409;
- repeated 409 responses create only one timer/pump and keep queue depth one;
- cancel/new-chat/unmount clears the busy timer and settles pending image
  acceptance as false;
- image acceptance remains pending until a retry emits `request_persisted`.

Representative assertion:

```ts
expect(mockStreamChat.mock.calls[1][6]).toBe(mockStreamChat.mock.calls[0][6]);
expect(result.current.messages).toEqual(expect.arrayContaining([
  expect.objectContaining({
    role: 'assistant',
    content: '上一条仍在处理，本条已排队。',
  }),
]));
expect(mockGetAgentTurnStatus).not.toHaveBeenCalled();
```

**Step 2: Run the hook tests and confirm RED**

```bash
cd mobile
npx jest --runInBand --runTestsByPath hooks/__tests__/useChatEngine.test.ts
```

Expected: new cases fail because 409 currently follows generic transport-loss
reconciliation and returns false.

**Step 3: Add minimal queue metadata and one timer**

Extend `QueuedChatTurn` with `busyAttempt` and `busyStartedAt`. Add constants for
`[1000, 2000, 4000, 8000, 15000, 30000]` backoff and the existing ten-minute
TTL. Add one timer ref plus helpers to clear/schedule it. Timers must be cleared
on unmount, `newChat`, and cancellation of the relevant queued turn.

Add a busy classifier that requires `ChatStreamHttpError`, status 409 and the
known busy detail. Other 409 responses remain ordinary failures.

**Step 4: Requeue from the catch path**

Before conversation recovery and status reconciliation, handle a known busy
error. Reuse the already-created optimistic IDs and the same `turnId`, update
the assistant bubble to the queued copy, push the turn at the FIFO head or tail
without duplication, and schedule the pump. Set a local flag so `finally` does
not immediately pump the same item.

For text-only turns call `settleAcceptance(true)` after local enqueue. For image
turns retain the existing acceptance callback/promise until a later persisted
event. On TTL exhaustion mark the assistant turn `completionStatus: 'error'`,
settle false, and leave it recoverable.

**Step 5: Run focused Mobile verification**

```bash
cd mobile
npx jest --runInBand --runTestsByPath services/__tests__/chatStream.test.ts hooks/__tests__/useChatEngine.test.ts components/chat/__tests__/ChatInputBar.test.tsx
npx tsc --noEmit
```

Expected: all tests and TypeScript pass; the existing draft-preservation tests
remain green.

**Step 6: Commit Task 2**

```bash
git add mobile/hooks/useChatEngine.ts mobile/hooks/__tests__/useChatEngine.test.ts
git commit -m "fix(mobile): queue server-busy chat turns"
```

### Task 3: Parse numeric meal fractions and build truthful updates

**Files:**
- Modify: `backend/app/services/agent_executor.py:4570-4785`
- Test: `backend/tests/test_health_manage_date_normalize.py:330-570`

**Step 1: Write failing parser and update tests**

Add cases for `1/2`, whitespace around `/`, invalid `0/2`, `2/1` and `1/0`.
Assert the valid correction contains both `consumed_fraction == 0.5` and
`consumed_fraction_label == "1/2"`, with no `food_items` replacement.

Change the unique no-nutrition regression to expect an update:

```python
assert json.loads(calls[0]["function"]["arguments"]) == {
    "record_type": "diet",
    "operation": "update",
    "record_id": 830,
    "data": {
        "meal_type": "lunch",
        "food_items": "牛肉面（按实际食用1/3计）",
    },
}
```

Add a repeat-correction case proving a prior generated suffix is replaced, not
appended twice. Keep the existing nutrient-scaling case as a positive control
and assert no new nutrition key is added when all are absent.

**Step 2: Run the focused Backend tests and confirm RED**

```bash
cd backend
venv/bin/python -m pytest tests/test_health_manage_date_normalize.py -q --no-cov
```

Expected: numeric input is misparsed and the nutrition-poor record remains a
read-only lookup.

**Step 3: Implement one shared fraction parser**

Create a narrow helper returning `(float, canonical_label)` for both the known
Chinese tokens and numeric `numerator/denominator`. Require a partial-
consumption signal and reject questions, negation, zero denominators, non-finite
values and fractions outside `(0, 1]`. Reuse it from the explicit correction
parser while keeping contextual photo parsing behavior unchanged.

**Step 4: Implement nutrition-poor update data**

When at least one scalable field exists, preserve the current scaling logic.
When none exists, normalize the existing `food_items` by removing only the
runtime-generated `（按实际食用…计）` suffix and append the current label. Return
`None` if the record has no safe food text rather than fabricating content.

**Step 5: Run the focused test and confirm GREEN**

Run the Task 3 pytest command again. Expected: all tests pass.

**Step 6: Commit Task 3**

```bash
git add backend/app/services/agent_executor.py backend/tests/test_health_manage_date_normalize.py
git commit -m "fix(agent): apply numeric diet portion corrections"
```

### Task 4: Terminate unresolved diet selection after one lookup

**Files:**
- Modify: `backend/app/services/agent_executor.py:2610-2640,9150-9190,11120-11240,12140-12165,16439-16570`
- Create: `backend/tests/test_agent_diet_correction_terminal.py`

**Step 1: Write the failing end-to-end runtime test**

Use the existing `db` and authenticated-user fixtures. Mock one model round that
asks for a diet list/update, mock the owner-scoped internal lookup to return two
candidates, and make tool execution raise if called. Collect `run_stream` and
assert:

```python
assert len(model_rounds) == 1
assert tool_execute.await_count == 0
assert "找到多条" in visible_text
assert "暂时没有修改" in visible_text
assert done["data"]["completion_status"] == "error"
assert not done["data"].get("write_receipts")
```

Add sibling cases for zero candidates and lookup failure. Each must terminate
after the first lookup with distinct truthful text and no write receipt.

**Step 2: Run the new test and confirm RED**

```bash
cd backend
venv/bin/python -m pytest tests/test_agent_diet_correction_terminal.py -q --no-cov
```

Expected: current code performs the rewritten read tool and enters another LLM
round.

**Step 3: Add deterministic terminal messages**

Introduce distinct unresolved reasons for `target_not_found`,
`ambiguous_target`, `lookup_failed`, and the defensive
`record_has_no_scalable_nutrition` fallback. Map them to content-free,
user-facing messages in one helper.

After the owner-scoped lookup proves no safe unique update, raise the existing
typed terminal control exception before any redundant tool execution. Add the
same explicit terminal catch to the normal stream path that the multi-model
path already uses. Persist and stream the deterministic text through the normal
reply-finalization path, with an error completion status and no success receipt.

**Step 4: Run Backend correction regressions**

```bash
cd backend
venv/bin/python -m pytest tests/test_agent_diet_correction_terminal.py tests/test_health_manage_date_normalize.py tests/test_agent_stream_no_false_record_claim.py tests/test_agent_executor_tool_round_limit.py -q --no-cov
venv/bin/python -m compileall -q app/services/agent_executor.py
```

Expected: all focused tests pass and ambiguous corrections invoke the model once.

**Step 5: Commit Task 4**

```bash
git add backend/app/services/agent_executor.py backend/tests/test_agent_diet_correction_terminal.py
git commit -m "fix(agent): stop unresolved diet correction loops"
```

### Task 5: Complete repository gates and independent safety review

**Files:**
- Modify: `docs/dossiers/2026-08-02-agent-busy-diet-correction-recovery.md`

**Step 1: Run Mobile gates**

```bash
cd mobile
npx jest --runInBand --runTestsByPath services/__tests__/chatStream.test.ts hooks/__tests__/useChatEngine.test.ts components/chat/__tests__/ChatInputBar.test.tsx
npx tsc --noEmit
npm run lint
```

Expected: all commands exit zero. Record the exact test counts.

**Step 2: Run Backend gates**

```bash
cd backend
venv/bin/python -m pytest tests/test_agent_diet_correction_terminal.py tests/test_health_manage_date_normalize.py tests/test_agent_runtime_api.py tests/test_agent_stream_no_false_record_claim.py tests/test_agent_executor_tool_round_limit.py -q --no-cov
venv/bin/python -m ruff check app/services/agent_executor.py tests/test_agent_diet_correction_terminal.py tests/test_health_manage_date_normalize.py
venv/bin/python -m compileall -q app/services/agent_executor.py
```

Expected: all commands exit zero. Expand to the project-required integrated
gate if focused changes expose shared-runtime regressions.

**Step 3: Run repository gates**

```bash
cd ..
python3 backend/scripts/check_dossier_consistency.py
python3 scripts/check_system_map_drift.py
git diff --check
git status --short
```

Expected: all gates pass and status contains only this feature plus the known
unrelated user-owned files.

**Step 4: Request independent G4 review**

Provide the reviewer the approved spec/design, exact diff and test evidence.
Require explicit review of:

- owner scoping and wrong-record prevention;
- no inferred nutrition;
- success receipt truthfulness;
- retry idempotency and duplicate-turn risk;
- queue timer cleanup and image-draft lifecycle;
- health/prompt content leakage.

Address every blocking finding with a failing regression before changing code.

**Step 5: Update and commit gate evidence**

Record G3 counts and the independent G4 verdict in the Dossier.

```bash
git add docs/dossiers/2026-08-02-agent-busy-diet-correction-recovery.md
git commit -m "docs(agent): record busy-turn recovery gates"
```

### Task 6: Push, deploy Backend, publish Mobile, and verify production

**Files:**
- Modify: `docs/dossiers/2026-08-02-agent-busy-diet-correction-recovery.md`

**Step 1: Confirm release provenance**

```bash
git status --short
git log -5 --oneline
git fetch origin main
git rev-list --left-right --count origin/main...main
```

Expected: only known unrelated user files are dirty, main is not behind, and
all feature commits are present.

**Step 2: Push exact commits**

```bash
git push origin main
```

Expected: remote `main` advances to the verified feature SHA.

**Step 3: Deploy Backend asynchronously**

Run the project release entry point without piping its output:

```bash
./deploy.sh -b
```

Expected: backup/preflight, service health and revision gates all pass. On any
red gate, stop and record the rollback/blocked state.

**Step 4: Verify Backend production**

Verify the deployed SHA, service health and protected route behavior. Use a
safe authenticated product-flow correction only when the user-owned target is
known; never print meal content or auth material in deployment logs.

**Step 5: Publish Mobile OTA asynchronously**

```bash
scripts/mobile-ota.sh production "fix: recover busy chat diet corrections"
```

Expected: the script returns a production update/group ID and anchors it to the
verified commit. If EAS asset processing fails, keep the last-known-good anchor
and mark Mobile G6 blocked rather than claiming publication.

**Step 6: Verify the user-visible flow**

On the production app:

1. start a deliberately slow first turn;
2. submit a second text turn while it is active;
3. confirm the queued copy appears and no network alert is shown;
4. confirm the same second turn runs once after the first completes;
5. use a safe test meal to verify `1/2` scales known nutrition or annotates a
   nutrition-poor record without invented values;
6. verify an ambiguous target asks once and does not keep processing.

**Step 7: Finalize the Dossier and commit/push**

Record G5/G6 artifacts, production SHA/update ID, evidence and any remaining
blocker. Mark complete only if both Backend and Mobile production verification
pass.

```bash
git add docs/dossiers/2026-08-02-agent-busy-diet-correction-recovery.md
git commit -m "docs(agent): record busy-turn production verification"
git push origin main
```
