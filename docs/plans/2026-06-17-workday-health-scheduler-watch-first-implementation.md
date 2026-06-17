# Workday Health Scheduler Watch-first Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make Apple Watch the first execution surface for workday micro-movement health actions, starting with one-tap completion for training/activity HealthProtocol items.

**Architecture:** Use the existing HealthProtocol -> Health Agenda -> WatchSummary -> Watch App one-tap completion chain. The first slice changes only the Watch completion contract and tests; later slices add WorkdayHealthScheduler, calendar/location triggers, snooze/skip, and medication/supplement/diet scheduling depth.

**Tech Stack:** FastAPI, SQLAlchemy, pytest, Swift Package tests for WatchCompanionCore, watchOS SwiftUI.

---

### Task 1: Document Watch-first Product Contract

**Files:**
- Create: `docs/plans/2026-06-17-workday-health-scheduler-watch-first-design.md`
- Create: `docs/plans/2026-06-17-workday-health-scheduler-watch-first-implementation.md`

**Step 1: Write the design document**

Create the design file with:

- Watch-first positioning.
- Adaptive micro-movement instead of fixed hourly push-ups.
- HealthProtocol as the v1 execution object.
- Safety boundaries for readiness red/yellow/green.
- Phasing from Watch completion to WorkdayHealthScheduler.

**Step 2: Write this implementation plan**

Keep the first batch small:

- Watch Core completion contract.
- Backend summary test.
- Swift tests.

**Step 3: Commit**

Run:

```bash
git add docs/plans/2026-06-17-workday-health-scheduler-watch-first-design.md docs/plans/2026-06-17-workday-health-scheduler-watch-first-implementation.md
git commit -m "docs(watch): plan workday health scheduler"
```

Expected: commit succeeds. If code changes are already included, commit once at the end instead.

### Task 2: Extend Watch Core Completion Contract

**Files:**
- Modify: `apps/watch/Sources/WatchCompanionCore/WatchSummary.swift`
- Test: `apps/watch/Tests/WatchCompanionCoreTests/WatchCompanionCoreTests.swift`

**Step 1: Write failing Swift tests**

Add tests:

```swift
func testTrainingProtocolActionIsCompletable() throws {
    let data = Data("""
    {"status":{"light":"green","readiness_score":80,"headline":"h"},
     "top_action":{"title":"到公司后俯卧撑 12 个","kind":"training","time_window":"morning",
                   "action_id":"agenda-health_protocol-8",
                   "source":{"object_type":"health_protocol","object_id":8}},
     "agenda":{"total":1,"pending":1},"quick_actions":[],"push_items":[],"generated_at":"x"}
    """.utf8)
    let s = try WatchSummary.decode(data)
    XCTAssertEqual(s.topAction?.isCompletable, true)
}
```

Keep the existing non-protocol training decision test and ensure it remains false.

**Step 2: Run test to verify it fails**

Run:

```bash
cd apps/watch && swift test --filter WatchSummaryTests/testTrainingProtocolActionIsCompletable
```

Expected: FAIL because `training` is not in `watchCompletableKinds`.

**Step 3: Implement minimal contract**

Change `WatchSummary.swift`:

- Add `training`, `activity`, and `exercise` to `watchCompletableKinds`.
- Require `source.object_type == "health_protocol"` in `isCompletable`.

**Step 4: Run Swift tests**

Run:

```bash
cd apps/watch && swift test
```

Expected: all tests pass.

### Task 3: Add Backend Watch Summary Regression

**Files:**
- Modify: `backend/tests/test_watch_summary.py`
- Existing code path: `backend/app/services/watch_summary.py`

**Step 1: Write backend test**

Add a test that a pending training HealthProtocol appears as `top_action` with:

- `kind == "training"`
- `action_id == "agenda-health_protocol-7"`
- `source.object_type == "health_protocol"`
- leverage metadata present

**Step 2: Run test**

Run:

```bash
cd backend && source venv/bin/activate && pytest tests/test_watch_summary.py -q --no-cov
```

Expected: pass. The backend already includes all pending health_protocol items in actionable candidates; this test locks the contract.

### Task 4: Verification

**Files:**
- All files touched above.

**Step 1: Run focused backend tests**

```bash
cd backend && source venv/bin/activate && pytest tests/test_watch_summary.py tests/test_watch_action_concurrency.py -q --no-cov
```

Expected: pass.

**Step 2: Run Watch tests**

```bash
cd apps/watch && swift test
```

Expected: pass.

**Step 3: Run formatting drift check**

```bash
git diff --check
```

Expected: no output.

### Task 5: Commit and Push

**Files:**
- Stage only files changed in this slice.
- Do not stage unrelated local changes such as `mobile/native/watch/WatchPhoneBridge.swift`.

**Step 1: Review diff**

```bash
git diff -- docs/plans/2026-06-17-workday-health-scheduler-watch-first-design.md docs/plans/2026-06-17-workday-health-scheduler-watch-first-implementation.md apps/watch/Sources/WatchCompanionCore/WatchSummary.swift apps/watch/Tests/WatchCompanionCoreTests/WatchCompanionCoreTests.swift backend/tests/test_watch_summary.py
```

**Step 2: Commit**

```bash
git add docs/plans/2026-06-17-workday-health-scheduler-watch-first-design.md docs/plans/2026-06-17-workday-health-scheduler-watch-first-implementation.md apps/watch/Sources/WatchCompanionCore/WatchSummary.swift apps/watch/Tests/WatchCompanionCoreTests/WatchCompanionCoreTests.swift backend/tests/test_watch_summary.py
git commit -m "feat(watch): complete movement health actions"
```

**Step 3: Push**

```bash
git push
```

Expected: push succeeds.
