# Diet Photo Slice Guard Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Allow legitimate owner-bound meal-photo drafts containing food names such as `萝卜片` to be confirmed without weakening explicit medication and supplement rejection.

**Architecture:** Keep the backend intake classifier as the authoritative defense and narrow the Mobile preflight exception to the one ambiguous signal: the bare Chinese character `片`. The exception applies only to owner-bound photo drafts and only when removing that ambiguous marker leaves no other medication or supplement signal. Add the exact production meal as a cross-layer regression case.

**Tech Stack:** React Native/TypeScript/Jest, FastAPI/Python/Pytest, Expo EAS Update.

---

### Task 1: Reproduce the production failure

**Files:**
- Modify: `mobile/utils/__tests__/dietIntakeGuard.test.ts`
- Modify: `mobile/services/__tests__/chatCardActions.test.ts`
- Modify: `backend/tests/test_diet.py`

1. Add the exact eight-item meal containing `萝卜片 少量` as an owner-bound photo draft.
2. Assert the Mobile guard permits it and the card action reaches `POST /diet/records`.
3. Assert the REST endpoint accepts the same legitimate food string.
4. Run the focused tests and record the Mobile RED result before implementation.

### Task 2: Narrow the Mobile ambiguity rule

**Files:**
- Modify: `mobile/utils/dietIntakeGuard.ts`

1. Replace the numeric-slice-only exception with an owner-bound bare-`片` ambiguity check.
2. Re-run all strong medication/supplement negative cases to prove they remain blocked.
3. Run focused Mobile and backend tests to GREEN.

### Task 3: Verify and release

**Files:**
- Verify only: changed files and release scripts.

1. Run focused Jest/Pytest, Mobile TypeScript, scoped lint, and diff checks.
2. Commit only the plan, implementation, and regression tests; push to `main`.
3. Publish an iOS production OTA from a clean committed tree.
4. Verify the OTA update evidence and ask the user to cold-start and retry the preserved draft.
