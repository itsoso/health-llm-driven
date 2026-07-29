# AIGC Video Duration Options Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make every Xiaoba video confirmation card offer the truthful `5/8/15` second choices and submit the selected duration end to end.

**Architecture:** `aigc_media_capabilities.py` remains the backend source of truth. Backend confirmation projections expose its selection set, while Mobile mirrors the same values only as a compatibility fallback for historical cards that predate `duration_options`.

**Tech Stack:** Python, FastAPI, SQLAlchemy, pytest, React Native, TypeScript, Jest.

---

### Task 1: Backend capability contract

**Files:**
- Modify: `backend/tests/test_aigc_media_capabilities.py`
- Modify: `backend/app/services/aigc_media_capabilities.py`

**Step 1: Write the failing test**

Change the expected selectable duration tuple to:

```python
assert capability.selectable_duration_seconds == (5, 8, 15)
```

**Step 2: Run test to verify it fails**

Run:

```bash
cd backend
pytest tests/test_aigc_media_capabilities.py -q
```

Expected: FAIL because the capability still returns `(5, 10, 15)`.

**Step 3: Write minimal implementation**

Set:

```python
selectable_duration_seconds=(5, 8, 15)
```

Keep the native maximum at 15 seconds.

**Step 4: Run test to verify it passes**

Run the same pytest command. Expected: PASS.

### Task 2: Backend 8-second confirmation flow

**Files:**
- Modify: `backend/tests/test_aigc_media_confirmation.py`
- Verify: `backend/app/services/aigc_media_job_service.py`
- Verify: `backend/app/api/aigc_media.py`

**Step 1: Write the failing test**

Update the confirmation override test to submit 8 seconds and assert:

```python
assert provider.video_requests[0]["duration_seconds"] == 8
assert job.result_metadata["request"]["duration_seconds"] == 8
```

Keep the existing test that rejects 16 seconds.

**Step 2: Run test to verify it fails**

Run:

```bash
cd backend
pytest tests/test_aigc_media_confirmation.py -q
```

Expected: FAIL until the test fixture and expected projection use the new selection.

**Step 3: Implement only if needed**

The service already accepts every integer in the native `3–15` range. No service change is expected beyond the authoritative selection set.

**Step 4: Run test to verify it passes**

Run the same pytest command. Expected: PASS.

### Task 3: Mobile current and historical cards

**Files:**
- Modify: `mobile/components/chat/cards/__tests__/registry.test.tsx`
- Modify: `mobile/components/chat/cards/AIGCMediaConfirmationCard.tsx`

**Step 1: Write failing tests**

- Assert a current card renders `5 秒`, `8 秒`, and `15 秒`, with no `10 秒`.
- Assert a historical card without `duration_options` renders the same three choices.
- Select 8 seconds and assert:

```typescript
expect(api.post).toHaveBeenCalledWith(
  '/aigc/media/confirmations/aigc_confirm_duration/confirm',
  { duration_seconds: 8 },
);
```

**Step 2: Run tests to verify failure**

Run:

```bash
cd mobile
npx jest components/chat/cards/__tests__/registry.test.tsx --runInBand
```

Expected: FAIL because the fallback and fixture still use 10 seconds.

**Step 3: Write minimal implementation**

Change the compatibility fallback to `[5, 8, 15]`. Normalize the selected duration so a historical 10-second draft defaults to 5 seconds rather than displaying a selection outside the visible set.

**Step 4: Run tests to verify pass**

Run the same Jest command. Expected: PASS.

### Task 4: Regression, release evidence, and rollout

**Files:**
- Modify: `docs/dossiers/2026-07-23-aigc-video-spec-experience.md`

**Step 1: Run focused and static checks**

```bash
cd backend
pytest tests/test_aigc_media_capabilities.py tests/test_aigc_media_confirmation.py tests/test_aigc_media_api.py tests/test_aigc_media_job_service.py -q
```

```bash
cd mobile
npx jest components/chat/cards/__tests__/registry.test.tsx --runInBand
npx tsc --noEmit
npm run lint
```

```bash
python scripts/check_doc_drift.py
git diff --check
```

Expected: all commands exit 0; lint may contain only pre-existing warnings.

**Step 2: Record evidence**

Append root cause, final contract, test results, backend deployment, and production OTA identifiers to the existing AIGC Dossier.

**Step 3: Commit and push**

Stage only the files listed above, commit with a focused message, and push `main`.

**Step 4: Deploy**

Deploy the clean `main` commit using `./deploy.sh`, verify health gates, then publish a production Mobile OTA because the native runtime is unchanged.
