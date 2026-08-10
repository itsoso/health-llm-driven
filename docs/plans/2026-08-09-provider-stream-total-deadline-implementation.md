# Provider Stream Total Deadline Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Prevent a keepalive-but-nonterminal LLM stream from occupying an Agent conversation until the outer runtime deadline, while preserving stable fallback and no-duplicate partial-output behavior.

**Architecture:** Add one 120-second wall-clock budget around complete provider stream iteration in `AgentExecutor`. Reuse that same bounded iterator for the selected provider and its streaming stable fallback, leaving Mobile, non-streaming bridges, health-write receipts, and database contracts unchanged.

**Tech Stack:** Python 3.12, asyncio async generators, pytest, pytest-asyncio, FastAPI Backend deployment tooling.

---

### Task 1: Reproduce the selected-provider stall

**Files:**
- Modify: `backend/tests/test_agent_executor_failover_gate.py`
- Test: `backend/tests/test_agent_executor_failover_gate.py`

**Step 1: Write the failing no-content timeout test**

Add a fake selected streaming provider whose `chat_stream` continuously yields
reasoning events without a terminal event. Monkeypatch
`_LLM_STREAM_ATTEMPT_TIMEOUT_S` to a few milliseconds and replace
`_stable_fallback_provider` with a fake stable provider that emits one content
event and one stop finish event.

Assert that:

```python
assert fallback_calls == 1
assert visible_content == "稳定回复"
assert events[-1] == {"type": "finish", "finish_reason": "stop"}
```

Wrap the drain with a short outer `asyncio.wait_for` only as a test watchdog so
the pre-fix test fails quickly instead of hanging.

**Step 2: Run the exact test to verify RED**

Run:

```bash
cd backend
venv/bin/pytest tests/test_agent_executor_failover_gate.py::test_stream_total_deadline_falls_back_after_reasoning_only_stall -v
```

Expected: FAIL because `_LLM_STREAM_ATTEMPT_TIMEOUT_S` or the bounded iterator
does not yet exist, or because the outer watchdog expires without fallback.

**Step 3: Write the failing partial-content invariant test**

Add a fake selected provider that emits `{"type": "content", "text": "部分"}`
and then emits nonterminal events forever. Assert that the final event is one
error finish, the stable fallback is never called, and visible content is exactly
`部分`.

**Step 4: Run the exact partial-content test to verify RED**

Run:

```bash
cd backend
venv/bin/pytest tests/test_agent_executor_failover_gate.py::test_stream_total_deadline_does_not_fallback_after_partial_content -v
```

Expected: FAIL because the selected provider stream is not yet wall-clock bounded.

### Task 2: Bound primary and fallback provider streams

**Files:**
- Modify: `backend/app/services/agent_executor.py`
- Modify: `backend/tests/test_agent_executor_failover_gate.py`
- Test: `backend/tests/test_agent_executor_failover_gate.py`

**Step 1: Add the attempt budget and bounded iterator**

Near the executor's other timeout constants, add:

```python
_LLM_STREAM_ATTEMPT_TIMEOUT_S = 120.0
```

Add a small async-generator helper:

```python
@staticmethod
async def _iterate_provider_stream_with_deadline(provider, stream_kwargs):
    async with asyncio.timeout(_LLM_STREAM_ATTEMPT_TIMEOUT_S):
        async for event in provider.chat_stream(**stream_kwargs):
            yield event
```

Do not catch the timeout in this helper. Let the selected-provider and fallback
call sites apply their existing failure semantics.

**Step 2: Route the selected provider through the helper**

Replace the direct `provider.chat_stream(...)` iteration in `_call_llm_stream`
with `_iterate_provider_stream_with_deadline(...)`. Preserve the existing
`emitted_content` tracking and exception branches byte-for-byte except for a
sanitized timeout-specific warning/fallback reason if needed.

**Step 3: Route the streaming stable fallback through the helper**

Replace the direct fallback `fb.chat_stream(...)` iteration in
`_stream_via_stable_fallback` with the same helper. Keep the current catch that
emits exactly one error finish when the fallback fails.

**Step 4: Run the two selected-provider tests to verify GREEN**

Run:

```bash
cd backend
venv/bin/pytest \
  tests/test_agent_executor_failover_gate.py::test_stream_total_deadline_falls_back_after_reasoning_only_stall \
  tests/test_agent_executor_failover_gate.py::test_stream_total_deadline_does_not_fallback_after_partial_content \
  -v
```

Expected: 2 passed.

**Step 5: Add and run the fallback-timeout regression**

Add a selected provider that fails before content and a streaming stable fallback
that yields only nonterminal events forever. Assert the call returns promptly and
ends with exactly one `{"type": "finish", "finish_reason": "error"}`.

Run:

```bash
cd backend
venv/bin/pytest tests/test_agent_executor_failover_gate.py::test_stable_fallback_stream_has_its_own_total_deadline -v
```

Expected: PASS.

**Step 6: Run the focused failover suite**

Run:

```bash
cd backend
venv/bin/pytest tests/test_agent_executor_failover_gate.py -v
```

Expected: all tests passed.

**Step 7: Commit the implementation**

Stage only:

```bash
git add backend/app/services/agent_executor.py backend/tests/test_agent_executor_failover_gate.py
git commit -m "fix(agent): bound provider stream attempts"
```

### Task 3: Record the release blocker and run Backend gates

**Files:**
- Modify: `docs/dossiers/2026-08-05-ios-1-3-3-app-store-release.md`

**Step 1: Update the dossier**

Record content-free production evidence, root cause, approved design, regression
tests, and the fact that G5 remains blocked until production deploy and physical
iPhone photo retest pass. Do not include the user's image, health text, account,
credentials, token, or raw prompt.

**Step 2: Run repository hygiene and relevant Backend tests**

Run without `tail`:

```bash
git diff --check
PATH="$PWD/backend/venv/bin:$PATH" python3 scripts/check_doc_drift.py
PATH="$PWD/backend/venv/bin:$PATH" python3 backend/scripts/check_dossier_consistency.py
cd backend
venv/bin/pytest tests/test_agent_executor_failover_gate.py tests/test_llm_provider.py -v
venv/bin/python -m compileall -q app/services/agent_executor.py
```

Expected: every command exits 0 and all tests pass.

**Step 3: Commit and push the release evidence**

Stage only the dossier, commit, then push the branch HEAD to `main`:

```bash
git add docs/dossiers/2026-08-05-ios-1-3-3-app-store-release.md
git commit -m "docs(release): record provider stream blocker repair"
git push origin HEAD:main
```

### Task 4: Deploy the Backend repair

**Files:**
- No repository changes expected.

**Step 1: Confirm the candidate is clean and synchronized**

Run:

```bash
git status --short --branch
git rev-parse HEAD
git rev-parse origin/main
```

Expected: clean worktree and identical HEAD/origin main revisions.

**Step 2: Deploy only the Backend through the repository workflow**

Run the documented Backend-only mode of `deploy.sh` from the clean candidate.
Do not publish a Mobile OTA and do not submit App Review.

Expected: backup, recovery probe, schema/runtime checks, exact revision check,
and Backend health score all pass.

**Step 3: Verify production health and revision**

Use the repository's read-only deployment verification to confirm the health
endpoint and deployed revision. Inspect only sanitized operational logs for the
new timeout/fallback marker; never print health content or secrets.

### Task 5: Re-run the physical iPhone photo acceptance

**Files:**
- Modify: `docs/dossiers/2026-08-05-ios-1-3-3-app-store-release.md`
- Test artifact only: `/tmp/reva-t8-sensors-256`

**Step 1: Reset the App Review fixture**

Use the supported release reset workflow and verify its fixed, content-free
acceptance counts. Do not mutate production data directly.

**Step 2: Repeat the Build 256 photo flow**

On the connected, unlocked physical iPhone:

- open the camera attachment;
- capture or reuse a non-sensitive test meal photo;
- send the meal-record request;
- wait for a terminal assistant response;
- force-terminate and relaunch the App;
- verify the conversation and resulting safe receipt/card remain visible.

**Step 3: Verify the server released the conversation**

Confirm the admitted run reached a terminal state and that a subsequent safe
turn is not trapped in a repeated 409 loop. Use content-free identifiers and
status counts only.

**Step 4: Update, verify, commit, and push the dossier**

Record the Build 256 physical-device result and artifact paths without sensitive
content. Run dossier consistency and `git diff --check`, then commit and push only
the dossier.

### Task 6: Continue the remaining App Store release gates

**Files:**
- Modify as evidence requires: `docs/dossiers/2026-08-05-ios-1-3-3-app-store-release.md`

**Step 1: Finish remaining physical-device checks**

Complete real voice, system share/cancel, and health create/correct/delete on the
same Build 256 candidate using the approved safe fixtures.

**Step 2: Capture release screenshots and final evidence**

Retain only non-sensitive screenshots/result bundles. Record exact candidate,
device, test counts, and any residual warnings.

**Step 3: Re-run final G3/G4/G5/G6 checks**

Do not carry a failure or BLOCK forward. App Review submission stays blocked until
all required tests, safety review, deployment health, and end-to-end verification
are green.

**Step 4: Stop before irreversible submission if any gate is not green**

Only when the dossier shows all gates green may the already-bound Build 256 move
to App Review. Production OTA remains frozen throughout this release.
