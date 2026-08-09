# Authenticated Conversation No-Store Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Prevent iOS and intermediary caches from replaying stale authenticated health conversation lists or details while keeping TestFlight Build 253 unchanged.

**Architecture:** Enforce the privacy and freshness contract at the FastAPI response boundary for both authenticated conversation GET routes. Keep response bodies and client behavior unchanged; the server-provided `Cache-Control: no-store` header protects all existing clients immediately.

**Tech Stack:** FastAPI, SQLAlchemy, pytest/TestClient, guarded `deploy.sh` production deployment, XCUITest physical-device acceptance.

---

### Task 1: Reproduce the missing cache contract in request tests

**Files:**
- Modify: `backend/tests/test_agent_conversations_api.py:190-218`
- Modify: `backend/tests/test_agent_conversations_api.py:902-923`

**Step 1: Write the failing list test assertion**

Add this assertion immediately after the existing list status assertion:

```python
assert res.headers.get("cache-control") == "no-store"
```

**Step 2: Write the failing detail test assertion**

Add the same assertion immediately after the existing detail status assertion:

```python
assert res.headers.get("cache-control") == "no-store"
```

**Step 3: Run the two tests to verify RED**

Run:

```bash
cd backend
/Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin/pytest -q \
  tests/test_agent_conversations_api.py::test_agent_conversations_list_returns_user_history_with_last_user_message \
  tests/test_agent_conversations_api.py::test_agent_conversation_detail_returns_messages
```

Expected: both tests fail because the response header is absent (`None != "no-store"`).

### Task 2: Add the minimal server-side no-store enforcement

**Files:**
- Modify: `backend/app/api/agent.py:2475-2535`
- Modify: `backend/app/api/agent.py:2540-2620`

**Step 1: Accept the FastAPI response object**

Add `response: Response` to both route signatures:

```python
async def list_conversations(
    response: Response,
    limit: int = Query(30, ge=1, le=100),
    ...
):
```

```python
async def get_conversation(
    conversation_id: int,
    response: Response,
    ...
):
```

**Step 2: Set the no-store header before reading data**

Add to each handler:

```python
response.headers["Cache-Control"] = "no-store"
```

Do not change sorting, response bodies, authorization, database queries, or mobile code.

**Step 3: Run the two tests to verify GREEN**

Run the exact command from Task 1.

Expected: 2 passed.

**Step 4: Run the complete conversation API regression file**

Run:

```bash
cd backend
/Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin/pytest -q \
  tests/test_agent_conversations_api.py
```

Expected: all tests pass with no new warnings or errors.

**Step 5: Commit the fix**

```bash
git add backend/app/api/agent.py backend/tests/test_agent_conversations_api.py
git commit -m "fix(agent): prevent stale conversation response caching"
```

### Task 3: Verify and deploy the backend release fix

**Files:**
- Modify after verification: `docs/dossiers/2026-08-05-ios-1-3-3-app-store-release.md`

**Step 1: Run release checks**

Run:

```bash
/Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin/python \
  backend/scripts/check_dossier_consistency.py
/Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin/python \
  scripts/check_doc_drift.py
python3 scripts/check_ios_app_store_submission.py
python3 scripts/check_app_store_release_pack.py
git diff --check
```

Expected: every command exits 0.

**Step 2: Push the exact clean commit to main**

```bash
git push origin HEAD:main
```

Expected: the remote main branch advances to the local HEAD.

**Step 3: Deploy only the backend through the guarded release entry point**

```bash
./deploy.sh --backend --yes
```

Expected: deployment health, revision, schema, backup, restore rehearsal, runtime guards, and service health all pass.

**Step 4: Verify production headers without printing credentials or health content**

Authenticate using the controlled local release environment and inspect only
status plus cache headers for the list and detail endpoints.

Expected: both production responses return `Cache-Control: no-store`.

**Step 5: Reset and revalidate the deterministic review fixture**

```bash
./deploy.sh --reset-app-store-review
```

Then run the explicit production live demo-account validator.

Expected: guarded reset and live demo gate both pass without printing account,
password, token, or health content.

### Task 4: Clear the pre-fix device cache and close physical acceptance

**Files:**
- Modify after evidence is known: `docs/dossiers/2026-08-05-ios-1-3-3-app-store-release.md`

**Step 1: Remove and reinstall the exact TestFlight candidate once**

Delete `life.executor.health` from the physical iPhone, reinstall TestFlight
version 1.3.3 (253), and do not create a new conversation before acceptance.

Expected: a fresh app container is present for version 1.3.3 (253).

**Step 2: Run the credential-free physical-device suite**

```bash
scripts/run_ios_real_device_acceptance.sh \
  00008150-00112D220E32401C \
  /tmp/XiaobaAcceptance-TestFlight253-no-store-final.xcresult
```

Expected: 6 tests executed, 6 passed, 0 failed, 0 skipped.

**Step 3: Record only non-sensitive release evidence**

Update the release dossier with the root cause, production header verification,
fixture reset result, exact TestFlight build, and 6/6 aggregate. Do not commit
screenshots, hierarchy dumps, credentials, tokens, or synthetic health text.

**Step 4: Re-run dossier and release checks, then commit and push**

Stage only the dossier and plan files touched by this task, commit with a
`docs(release):` message, and push `HEAD:main`.

Expected: the worktree is clean and App Review remains blocked only by any
separate manual checklist items that have not yet been completed.
