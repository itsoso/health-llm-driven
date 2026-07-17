# Watch Reminder Delivery Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make Agent-created reminders honestly available on Apple Watch as dynamic tasks, without claiming direct Watch delivery before a real receipt exists.

**Architecture:** Keep iOS APNs as the notification path and Watch Summary as the verifiable Watch task path. `SmartReminder` remains the storage object; `/watch/summary` projects due/upcoming reminders into `due_items`/`push_items`, and `/watch/actions/{action_id}` can complete, skip, or snooze `agenda-smart_reminder-{id}`.

**Tech Stack:** FastAPI, SQLAlchemy, pytest, Swift WatchCompanionCore, XCTest.

---

### Task 1: Reminder Delivery Contract

**Files:**
- Modify: `backend/app/api/smart_reminder.py`
- Test: `backend/tests/test_reminder_create_api.py`

**Step 1: Write the failing test**

Add assertions that `/api/v1/reminders/me` and `/api/v1/reminders/me/window` return a `delivery_status` object:

- `agent_claim == "created_not_device_delivered"`
- `iphone_notification.status == "will_attempt_when_due"`
- `watch.route == "watch_summary_due_item"`
- `watch.delivery_confirmed is False`

**Step 2: Run test to verify it fails**

Run: `DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai backend/venv/bin/python -m pytest backend/tests/test_reminder_create_api.py -q --no-cov`

Expected: FAIL because `delivery_status` is missing.

**Step 3: Implement minimal contract**

Add one helper in `smart_reminder.py` and include it in both create responses.

**Step 4: Verify**

Run the same pytest command and expect PASS.

### Task 2: Project SmartReminder Into Watch Summary

**Files:**
- Modify: `backend/app/services/watch_summary.py`
- Test: `backend/tests/test_watch_summary.py`

**Step 1: Write the failing test**

Create a pending `SmartReminder` for “定时饮水提醒” due in the current user day. Assert `build_watch_summary` includes it as:

- `due_items[].source.object_type == "smart_reminder"`
- `action_id == "agenda-smart_reminder-{id}"`
- `kind == "hydration"`
- `delivery_status.watch.route == "watch_summary_due_item"`

**Step 2: Run test to verify it fails**

Run: `DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai backend/venv/bin/python -m pytest backend/tests/test_watch_summary.py -q --no-cov`

Expected: FAIL because SmartReminder rows are not projected.

**Step 3: Implement projection**

Add a small reminder mapper that pulls today’s pending reminders, caps the list, infers hydration for water reminders, and merges them with runtime items before ranking.

**Step 4: Verify**

Run the same pytest command and expect PASS.

### Task 3: Watch Actions For SmartReminder

**Files:**
- Modify: `backend/app/api/watch.py`
- Test: `backend/tests/test_watch_actions.py`

**Step 1: Write failing tests**

Add tests for:

- `POST /watch/actions/agenda-smart_reminder-{id}/complete` marks the reminder fired and is idempotent.
- `skip` cancels the current reminder.
- `snooze` updates `remind_at`.

**Step 2: Run test to verify it fails**

Run: `DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai backend/venv/bin/python -m pytest backend/tests/test_watch_actions.py -q --no-cov`

Expected: FAIL because `smart_reminder` is not supported.

**Step 3: Implement minimal handlers**

Branch before existing protocol completion. Enforce user ownership, avoid duplicate completion, and schedule the next recurrence when appropriate.

**Step 4: Verify**

Run the same pytest command and expect PASS.

### Task 4: Watch Core Completableness

**Files:**
- Modify: `apps/watch/Sources/WatchCompanionCore/WatchSummary.swift`
- Test: `apps/watch/Tests/WatchCompanionCoreTests/WatchCompanionCoreTests.swift`

**Step 1: Write failing XCTest**

Decode a `due_items` hydration row with `source.object_type="smart_reminder"` and assert `isCompletable == true`.

**Step 2: Run test to verify it fails**

Run: `cd apps/watch && swift test`

Expected: FAIL because only `health_protocol` is considered completable.

**Step 3: Implement minimal Watch Core change**

Allow `smart_reminder` source items to be completable when they carry a valid `action_id` and known kind.

**Step 4: Verify**

Run `cd apps/watch && swift test` and expect PASS.

### Task 5: Final Regression

Run:

- `DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai backend/venv/bin/python -m pytest backend/tests/test_reminder_create_api.py backend/tests/test_watch_summary.py backend/tests/test_watch_actions.py -q --no-cov`
- `cd apps/watch && swift test`

Only after both pass, report exact status and remaining limitation: no direct Watch APNs receipt exists; Watch availability is via dynamic summary plus iOS notification mirroring.

### Task 6: Agent Delivery Wording Boundary

**Files:**
- Modify: `backend/app/services/agent_executor.py`
- Modify: `backend/skills/reminder-setter/SKILL.md`
- Test: `backend/tests/test_agent_fast_record_reply.py`
- Test: `backend/tests/test_agent_executor_record_card.py`
- Test: `backend/tests/test_health_manage_date_normalize.py`

**Goal:** When a reminder is created, Agent replies and record cards must translate `delivery_status` honestly: reminder created, phone will attempt notification at due time, Watch can execute it after today's summary refresh. The Agent must not say "sent/synced/delivered to Watch" unless a future client-side `delivery_confirmed=true` receipt exists.

**Verification:**

- `DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai backend/venv/bin/python -m pytest backend/tests/test_agent_fast_record_reply.py backend/tests/test_agent_executor_record_card.py backend/tests/test_health_manage_date_normalize.py -q --no-cov`
- `backend/venv/bin/python -m ruff check backend/app/services/agent_executor.py backend/tests/test_agent_fast_record_reply.py backend/tests/test_agent_executor_record_card.py backend/tests/test_health_manage_date_normalize.py`
