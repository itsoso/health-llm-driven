# Health Correction Atomicity Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make health-record corrections atomic: an update intent can only update the selected record, malformed object-shaped arguments can be safely normalized, destructive fallbacks are blocked, and receipts show the actual action.

**Architecture:** Add a narrow representation repair in the central tool validator, then enforce exact intent/operation agreement in the Agent Kernel before dispatch. Extend the verified receipt contract with a backward-compatible action field and render it in Mobile; because Build 241 cannot render the new field, produce and validate Build 242 before App Review.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, pytest, React Native/Expo, TypeScript, Jest, EAS iOS Store Build, PostgreSQL.

---

### Task 1: Normalize object-shaped `health_manage.update.data`

**Files:**
- Modify: `backend/app/services/llm/tool_validator.py:21-29,826-837`
- Test: `backend/tests/test_tool_validator.py:488-505`

**Step 1: Write the failing tests**

Add cases proving that a JSON object string is normalized while arrays, scalars, invalid JSON, and empty objects stay rejected:

```python
def test_health_manage_update_parses_json_object_string(self):
    result = validate_tool_call("health_manage", {
        "record_type": "water",
        "operation": "update",
        "record_id": "718",
        "data": '{"amount": 350}',
    })
    assert result["error"] is None
    assert result["data"]["record_id"] == 718
    assert result["data"]["data"] == {"amount": 350}

@pytest.mark.parametrize("data", ('[350]', '350', 'not-json', '{}'))
def test_health_manage_update_rejects_non_object_or_empty_json(self, data):
    result = validate_tool_call("health_manage", {
        "record_type": "water",
        "operation": "update",
        "record_id": 718,
        "data": data,
    })
    assert result["error"]
```

**Step 2: Run the focused tests and verify RED**

Run:

```bash
cd backend
venv/bin/python -m pytest tests/test_tool_validator.py -k 'health_manage_update' -vv
```

Expected: the object-string test fails with `data 必须是对象`.

**Step 3: Implement the minimal normalization**

Import `json`. In `_validate_health_manage`, parse only string values and accept only a decoded dictionary:

```python
if operation == "update":
    raw_data = args.get("data")
    if isinstance(raw_data, str):
        try:
            decoded_data = json.loads(raw_data)
        except (json.JSONDecodeError, TypeError, ValueError):
            decoded_data = None
        if isinstance(decoded_data, dict):
            raw_data = decoded_data
            args["data"] = decoded_data
    data = raw_data or {}
    if not isinstance(data, dict):
        return "Error: health_manage.update 的 data 必须是对象."
    if not data:
        return "Error: health_manage.update 必须提供 data 补丁字段."
    args["data"] = data
```

Do not infer fields or coerce arrays/scalars.

**Step 4: Run tests and verify GREEN**

Run the focused command above, then:

```bash
cd backend
venv/bin/python -m pytest tests/test_tool_validator.py tests/test_agent_health_manage.py -q
```

Expected: all selected tests pass.

**Step 5: Commit**

```bash
git add backend/app/services/llm/tool_validator.py backend/tests/test_tool_validator.py
git commit -m "fix(agent): normalize health update object arguments"
```

### Task 2: Block destructive fallback when intent is update

**Files:**
- Modify: `backend/app/services/agent_kernel/capability_policy.py:233-257`
- Modify: `backend/app/services/agent_kernel/tool_gateway.py:80-92`
- Test: `backend/tests/test_agent_kernel_capability_policy.py:56-90`
- Test: `backend/tests/test_agent_kernel_tool_gateway.py:326-365`

**Step 1: Write the failing policy tests**

```python
def test_update_turn_blocks_health_manage_delete():
    decision = decide_tool_capability(
        _snapshot("把刚才 300ml 改成 350ml"),
        _request("health_manage", {
            "record_type": "water",
            "operation": "delete",
            "record_id": 718,
        }),
    )
    assert decision.action == "block"
    assert decision.reason == "manage_operation_mismatch"

def test_update_turn_allows_health_manage_update():
    decision = decide_tool_capability(
        _snapshot("把刚才 300ml 改成 350ml"),
        _request("health_manage", {
            "record_type": "water",
            "operation": "update",
            "record_id": 718,
            "data": {"amount": 350},
        }),
    )
    assert decision.action == "allow"
```

Add an executor-level test whose `_exec_health_manage` raises if called, proving the blocked delete never crosses the dispatch boundary.

**Step 2: Run the tests and verify RED**

```bash
cd backend
venv/bin/python -m pytest \
  tests/test_agent_kernel_capability_policy.py \
  tests/test_agent_kernel_tool_gateway.py \
  -k 'health_manage and (operation or update or delete)' -vv
```

Expected: update intent currently allows delete because both are classified only as generic mutations.

**Step 3: Require exact operation agreement**

Replace the broad mutation check with an exact match:

```python
if operation in MANAGE_WRITE_OPERATIONS:
    if primary == "mutate" and snapshot.intent.operation == operation:
        return _decision(...)
    if primary == "mutate" and snapshot.intent.operation in MANAGE_WRITE_OPERATIONS:
        return _decision(
            "block",
            "manage_operation_mismatch",
            tool_name,
            args,
            receipt_required=True,
        )
```

Add deterministic recovery guidance for `manage_operation_mismatch`: preserve the existing record and retry only the user-requested operation.

**Step 4: Run focused and related guard tests**

Run the focused command above, then:

```bash
cd backend
venv/bin/python -m pytest \
  tests/test_agent_kernel_capability_policy.py \
  tests/test_agent_kernel_tool_gateway.py \
  tests/test_agent_write_authority.py \
  tests/test_agent_simple_record_goal_guard.py -q
```

Expected: all pass; explicit delete still works in a delete turn.

**Step 5: Commit**

```bash
git add \
  backend/app/services/agent_kernel/capability_policy.py \
  backend/app/services/agent_kernel/tool_gateway.py \
  backend/tests/test_agent_kernel_capability_policy.py \
  backend/tests/test_agent_kernel_tool_gateway.py
git commit -m "security(agent): keep correction operations non-destructive"
```

### Task 3: Prove retry truthfulness and atomicity end to end

**Files:**
- Test: `backend/tests/test_agent_executor_completion_status.py:3340-3715`
- Modify only if the new regression remains red: `backend/app/services/agent_executor.py:3493-3690,12440-12515,12930-12960`

**Step 1: Add the production-trajectory regression**

Model the exact sequence: list record #718, emit malformed update data, retry with a delete, then attempt a correct update. Assert that delete dispatch is blocked, update receives a verified receipt, the old rejection is cleared, and the final reply does not say `这次没有写入`.

The fake business adapter must record dispatched operations:

```python
dispatched = []

async def fake_health_manage(_base, _headers, args):
    dispatched.append(args["operation"])
    if args["operation"] == "list":
        return '[{"id":718,"amount":300,"record_date":"2026-08-08"}]'
    return '{"id":718,"amount":350,"resource_type":"water_record"}'

assert "delete" not in dispatched
assert dispatched[-1] == "update"
assert done["data"]["completion_status"] == "complete"
assert len(done["data"]["write_receipts"]) == 1
assert "这次没有写入" not in rendered
```

**Step 2: Run the new test and verify its initial result**

```bash
cd backend
venv/bin/python -m pytest \
  tests/test_agent_executor_completion_status.py::test_update_retry_never_deletes_and_reports_verified_update \
  -vv
```

Expected before Tasks 1-2: fail because delete reaches the adapter or stale rejection wins. After Tasks 1-2 it should pass. If it remains red only because a same-target old validation error is retained, make the smallest change to `_clear_repaired_write_rejections`; do not clear unrelated or same-round failures.

**Step 3: Run rejection-scope regressions**

```bash
cd backend
venv/bin/python -m pytest \
  tests/test_agent_executor_completion_status.py \
  tests/test_agent_multi_model.py \
  tests/test_agent_write_adapter_rejections.py -q
```

Expected: pass, including independent partial-failure tests.

**Step 4: Commit**

```bash
git add backend/tests/test_agent_executor_completion_status.py
git add backend/app/services/agent_executor.py  # only if changed
git commit -m "test(agent): cover atomic health correction retries"
```

### Task 4: Add action-aware verified receipts

**Files:**
- Modify: `backend/app/services/agent_executor.py:3818-3898`
- Test: `backend/tests/test_write_receipt_identity.py:340-380`
- Modify: `mobile/services/writeReceipt.ts:1-75`
- Modify: `mobile/components/chat/ChatBubble.tsx:1465-1490`
- Test: `mobile/services/__tests__/writeReceipt.test.ts`
- Test: `mobile/components/chat/__tests__/ChatBubbleStructuredSummary.test.tsx:1090-1160`

**Step 1: Write failing backend receipt tests**

Assert:

```python
assert create_receipt["action"] == "create"
assert update_receipt["action"] == "update"
assert delete_receipt["action"] == "delete"
```

Only the verified tool arguments may supply this action.

**Step 2: Run backend tests and verify RED**

```bash
cd backend
venv/bin/python -m pytest tests/test_write_receipt_identity.py -k 'health_manage or health_record' -vv
```

**Step 3: Add the backward-compatible backend action field**

In `_write_receipt_from_tool_result` derive:

```python
receipt_action = (
    str(args.get("operation") or "").strip().lower()
    if tool_name == "health_manage"
    else "create" if tool_name == "health_record" else None
)
if receipt_action in {"create", "update", "delete"}:
    receipt["action"] = receipt_action
```

Do not change `operation_id`, resource identity, or success classification.

**Step 4: Write failing Mobile normalization and rendering tests**

Add optional action parsing with a strict whitelist and assert labels:

```typescript
expect(getByText('已更新 · 健康数据 #718')).toBeTruthy();
expect(getByText('已删除 · 健康数据 #718')).toBeTruthy();
```

Legacy receipts without action must still render `已写入`.

**Step 5: Implement Mobile receipt action support**

Add:

```typescript
export type WriteReceiptAction = 'create' | 'update' | 'delete';
action?: WriteReceiptAction;
```

Normalize only the three allowed values. In `formatWriteReceipt`, choose `已更新` and `已删除` for those actions; preserve current diet-specific create text and legacy behavior.

**Step 6: Run backend and Mobile tests**

```bash
cd backend
venv/bin/python -m pytest tests/test_write_receipt_identity.py tests/test_agent_executor_completion_status.py -q

cd ../mobile
npm test -- --runInBand \
  services/__tests__/writeReceipt.test.ts \
  components/chat/__tests__/ChatBubbleStructuredSummary.test.tsx
npx tsc --noEmit
```

Expected: all pass.

**Step 7: Commit**

```bash
git add \
  backend/app/services/agent_executor.py \
  backend/tests/test_write_receipt_identity.py \
  mobile/services/writeReceipt.ts \
  mobile/services/__tests__/writeReceipt.test.ts \
  mobile/components/chat/ChatBubble.tsx \
  mobile/components/chat/__tests__/ChatBubbleStructuredSummary.test.tsx
git commit -m "fix(chat): label verified health receipt actions"
```

### Task 5: Run G3, update the release dossier, and obtain G4

**Files:**
- Modify: `docs/dossiers/2026-08-05-ios-1-3-3-app-store-release.md`

**Step 1: Run focused security and behavior suites**

Run all commands without piping to `tail`:

```bash
cd backend
venv/bin/python -m pytest \
  tests/test_tool_validator.py \
  tests/test_agent_kernel_capability_policy.py \
  tests/test_agent_kernel_tool_gateway.py \
  tests/test_agent_executor_completion_status.py \
  tests/test_agent_multi_model.py \
  tests/test_write_receipt_identity.py -q

cd ../mobile
npm test -- --runInBand \
  services/__tests__/writeReceipt.test.ts \
  components/chat/__tests__/ChatBubbleStructuredSummary.test.tsx \
  hooks/__tests__/useChatEngine.test.ts
npx tsc --noEmit
```

**Step 2: Run release and drift gates**

```bash
cd ..
backend/venv/bin/python scripts/check_doc_drift.py
backend/venv/bin/python scripts/check_app_store_release_pack.py
backend/venv/bin/python scripts/check_ios_app_store_submission.py
```

Expected: all pass. If the final submission checker fails only because Build 242 does not yet exist, record it as the expected T7 blocker rather than bypassing it.

**Step 3: Update the dossier**

Record the production root cause, affected record #718 without personal credentials, chosen repair, test evidence, Build 241 supersession, and current Gate status. Keep App Review blocked.

**Step 4: Commit dossier evidence**

```bash
git add docs/dossiers/2026-08-05-ios-1-3-3-app-store-release.md
git commit -m "docs(release): record atomic correction blocker"
```

**Step 5: Request independent safety review**

Use the project `safety-gate` protocol. The reviewer must inspect intent/operation matching, pre-dispatch non-destruction, receipt truthfulness, cross-user isolation, and production recovery steps. A `NO-GO` blocks deployment; resolve all findings and repeat focused tests before continuing.

### Task 6: Push, deploy the backend, and restore the approved synthetic record

**Files:**
- No source changes unless deployment verification finds a real defect.

**Step 1: Verify a clean, reviewed commit set**

```bash
git status --short
git log --oneline --decorate -8
```

Expected: clean worktree; only reviewed commits are ahead.

**Step 2: Push the branch**

```bash
git push origin codex/ios-1-3-3-app-store-release
```

**Step 3: Deploy backend through the project entrypoint**

Run `deploy.sh -b` from a clean workspace with the controlled production environment present. Do not copy secrets into the worktree and do not print credentials.

**Step 4: Verify deployment health**

Verify backend revision, HTTP health, PostgreSQL, Redis/Celery, and absence of new error bursts. Confirm the deployed capability policy rejects `update`→`delete` mismatch before dispatch.

**Step 5: Restore the user-approved record through the authenticated application API**

Mint or obtain a short-lived server-side user token without printing it, then call the normal water create endpoint for review user 52 with the original local date and `amount: 350`. Do not write directly to PostgreSQL. Query the endpoint and database read-only afterward; require exactly one restored 350ml record and no resurrected 300ml row.

**Step 6: Record non-sensitive production evidence**

Update the dossier with timestamp, deployed revision, new resource ID, and read-back result. Never record the review password or bearer token.

### Task 7: Build and validate iOS Build 242

**Files:**
- Modify release evidence files only as required by existing checkers and EAS output.
- Modify: `docs/dossiers/2026-08-05-ios-1-3-3-app-store-release.md`

**Step 1: Confirm production OTA remains frozen**

Do not ship the Mobile receipt-label change as OTA. Build 241 is superseded because it cannot render action-aware receipts.

**Step 2: Produce a new Store build**

Use the existing production EAS Store Build workflow with remote auto-increment. Require version 1.3.3, Build 242 or later, runtime 1.3.3, and the reviewed source commit.

**Step 3: Validate the exact IPA**

Run the existing IPA toolchain/version/build/commit checks, signing verification, entitlement checks, and TestFlight processing checks. Record EAS build ID, source commit, fingerprint, IPA SHA-256, Xcode/SDK versions, and ASC processing status.

**Step 4: Run the safe physical-iPhone automated subset**

Use the already manually logged-in review account. Do not pass credentials to XCUITest. Require the existing 6/6 safe subset to pass on the exact Build 242.

**Step 5: Run manual correction acceptance**

On the physical iPhone:

1. Create a disposable water record.
2. Say “改成 350ml”.
3. Verify the old row remains and is updated in place.
4. Verify the receipt reads `已更新`, not `已写入` or `已删除`.
5. Explicitly delete the disposable record.
6. Verify the receipt reads `已删除` and no extra record is created.

Query production read-only after each step and correlate resource ID, operation, and final amount. No screenshots may expose credentials.

**Step 6: Re-run final release gates**

```bash
backend/venv/bin/python scripts/check_app_store_release_pack.py
backend/venv/bin/python scripts/check_ios_app_store_submission.py
```

Expected: pass for the exact Build 242 candidate.

**Step 7: Commit final evidence**

```bash
git add docs/dossiers/2026-08-05-ios-1-3-3-app-store-release.md docs/release/app-store
git commit -m "docs(release): verify Build 242 correction flow"
git push origin codex/ios-1-3-3-app-store-release
```

Do not bind the build or submit App Review until G3, independent G4, backend deployment health, exact IPA checks, and physical-iPhone acceptance are all green.
