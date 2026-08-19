# CI Stability and Security Waiver Review Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Restore `main` CI by removing two expired test fixtures and performing a bounded, visible re-review of the existing patched `image-size` advisories.

**Architecture:** Production behavior stays unchanged. Backend tests create data inside the real rolling windows, while the npm audit gate keeps fail-closed blocking and gains a non-blocking seven-day expiry warning for active, documented exceptions.

**Tech Stack:** Python 3.12, pytest, Node.js 22, `node:test`, npm audit, JSON policy.

---

### Task 1: Stabilize rolling-window backend fixtures

**Files:**
- Modify: `backend/tests/test_admin_llm_usage_dashboard.py:290-321`
- Modify: `backend/tests/test_life_events.py:211-236`

**Step 1: Preserve RED evidence**

Run the two existing nodes with the CI environment and confirm both fail because the fixed timestamps are outside the rolling 30-day windows.

**Step 2: Apply the minimal fixture correction**

- Set the TokenPlan usage row's `created_at` to `datetime.now(timezone.utc)` and use the current standard-price `qwen3.7-plus` path without cached tokens. Keep the expired-promotion arithmetic in its existing fixed-time unit test.
- Set only the life-event API integration message to a recent naive UTC timestamp, such as `datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)`.
- Leave `_ANCHOR` and `_MSG_CREATED_UTC` unchanged for deterministic parser and idempotency unit tests.

**Step 3: Verify GREEN**

Run both exact nodes and expect `2 passed`.

**Step 4: Run complete affected files**

Run `backend/tests/test_admin_llm_usage_dashboard.py` and `backend/tests/test_life_events.py` with CI environment variables and expect zero failures.

### Task 2: Add pre-expiry audit visibility

**Files:**
- Modify: `scripts/npm-audit-gate.test.mjs`
- Modify: `scripts/npm-audit-gate.mjs`

**Step 1: Write the failing test**

Add a test evaluating an active exception six days before expiry and assert the result contains a deterministic warning naming the advisory and expiry date.

**Step 2: Verify RED**

Run `node --test scripts/npm-audit-gate.test.mjs` and confirm the new warning assertion fails because no warning is returned.

**Step 3: Implement the minimal warning**

Track unique active exception leaves whose expiry is between now and seven days away. Return a sorted `warnings` array and print it to stderr from the CLI without changing the exit code.

**Step 4: Verify GREEN**

Run the complete Node test file and expect all tests to pass, including expired and unknown-advisory fail-closed cases.

### Task 3: Record the reviewed `image-size` exception

**Files:**
- Modify: `mobile/npm-audit-policy.json`

**Step 1: Update the bounded review date**

Set both existing advisory expiries to `2026-09-15` and update their reasons to record the current upstream state and mandatory local malicious-input tests.

**Step 2: Verify the security controls**

Run:

```bash
cd mobile
node scripts/image-size-security.node.js
node ../scripts/npm-audit-gate.mjs --policy npm-audit-policy.json
node --test ../scripts/npm-audit-gate.test.mjs
```

Expected: malicious parser guards pass, only the two reviewed advisories are allowed, and unknown/expired cases remain covered by green tests.

### Task 4: Run integration verification and publish

**Files:**
- Verify all files above plus the two plan documents.

**Step 1: Run Mobile static verification**

Run `npx tsc --noEmit` and `npm run check:settings-routes --silent` from `mobile`.

**Step 2: Run OTA workflow regression coverage**

Run `scripts/test_mobile_fast_feedback_scripts.py` with the fixed backend virtual environment and expect zero failures.

**Step 3: Validate repository scope**

Run `git diff --check` and `git status --short`; confirm only the planned files changed.

**Step 4: Commit and push**

Stage only the planned files, commit with `fix(ci): stabilize rolling windows and audit review`, and push `HEAD:main` without force.

**Step 5: Monitor exact-commit CI**

Follow the CI run for the pushed SHA. Do not claim overall green until all required jobs finish successfully; if another failure appears, return to root-cause investigation.
