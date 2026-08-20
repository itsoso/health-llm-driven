# Diet Confirmation And Access Log Hardening Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make every recognized diet item inspectable before confirmation and prevent signed upload capabilities or user-specific paths from entering production HTTP access logs.

**Architecture:** Mobile keeps the first four ingredients as the compact summary and adds local disclosure state for the remainder. Backend replaces Uvicorn raw request-target logging with a small pure-ASGI middleware that emits only resolved route templates and bounded operational fields; the systemd unit and transactional drop-in disable Uvicorn's access logger together.

**Tech Stack:** React Native, React Native Testing Library, TypeScript, FastAPI/Starlette ASGI, pytest, systemd, Uvicorn.

---

### Task 1: Record lifecycle and acceptance boundaries

**Files:**
- Create: `docs/dossiers/2026-08-19-diet-confirmation-access-log-hardening.md`

**Step 1: Create the dossier**

Record the approved decision, privacy boundary, G1/G2 PASS, and G3-G6 pending.
The dossier must explicitly say that no recognition, nutrition, write-intent, API,
or database contract changes are in scope.

**Step 2: Run document checks**

Run: `backend/venv/bin/python -m pytest -q --no-cov --tb=short scripts/test_dossier_consistency.py`

Expected: PASS.

**Step 3: Commit**

```bash
git add -- docs/plans/2026-08-19-diet-confirmation-access-log-hardening.md docs/dossiers/2026-08-19-diet-confirmation-access-log-hardening.md
git commit -m "docs(p0): plan diet and access log hardening"
```

### Task 2: Add an explicit compact ingredient disclosure

**Files:**
- Modify: `mobile/components/chat/cards/__tests__/registry.test.tsx`
- Modify: `mobile/components/chat/cards/DietDraftCard.tsx`

**Step 1: Write the failing Mobile test**

Add one focused diet-draft test with eight distinct `food_items`. Assert:

```typescript
expect(getByText('已识别 8 项，可直接调整份量')).toBeTruthy();
expect(getByText('查看其余 4 项')).toBeTruthy();
expect(queryByText('萝卜片 少量')).toBeNull();
fireEvent.press(getByText('查看其余 4 项'));
expect(getByText('萝卜片 少量')).toBeTruthy();
fireEvent.press(getByText('收起'));
expect(queryByText('萝卜片 少量')).toBeNull();
```

Also add or extend a case with four items to assert that no `查看其余` control is
rendered.

**Step 2: Run the test to verify RED**

Run:

```bash
cd mobile
npm test -- --runInBand components/chat/cards/__tests__/registry.test.tsx
```

Expected: FAIL because the expansion control is absent and the fifth item never
renders.

**Step 3: Implement the minimal disclosure**

In `DietDraftCardView`, add local `showAllIngredients` state and derive:

```typescript
const compactIngredients = chips.length > 0 ? chips : [draftFood || '待确认餐食'];
const hiddenIngredientCount = Math.max(0, compactIngredients.length - 4);
const visibleIngredients = showAllIngredients
  ? compactIngredients
  : compactIngredients.slice(0, 4);
```

Render `visibleIngredients`. When `hiddenIngredientCount > 0`, render an
accessible `Pressable` whose visible label toggles between `查看其余 N 项` and
`收起`. Add only the styles required for the compact disclosure row.

**Step 4: Run the focused Mobile tests to verify GREEN**

Run the command from Step 2.

Expected: PASS.

**Step 5: Commit**

```bash
git add -- mobile/components/chat/cards/DietDraftCard.tsx mobile/components/chat/cards/__tests__/registry.test.tsx
git commit -m "fix(mobile): disclose every recognized diet item"
```

### Task 3: Add route-template-only application access logging

**Files:**
- Create: `backend/app/middleware/safe_access_log.py`
- Create: `backend/tests/test_safe_access_log.py`
- Modify: `backend/main.py`

**Step 1: Write failing privacy contract tests**

Build a small FastAPI app with a route such as
`/files/{owner_id}/{filename}` and install `SafeAccessLogMiddleware`. Use
`caplog` and `TestClient` to request a raw path containing a private filename
and `?expires=...&signature=...`. Assert the log includes:

```text
http_access method=GET route=/files/{owner_id}/{filename} status=200
```

Assert it excludes the concrete owner id, filename, query keys, and values.
Add an unmatched-route case that requires `route=<unmatched>` and excludes the
raw target. Add an exception case that proves the exception is re-raised while
the middleware records status 500 without the exception text.

**Step 2: Run the tests to verify RED**

Run:

```bash
backend/venv/bin/python -m pytest -q --no-cov --tb=short backend/tests/test_safe_access_log.py
```

Expected: FAIL because `SafeAccessLogMiddleware` does not exist.

**Step 3: Implement the minimal pure-ASGI middleware**

Create `SafeAccessLogMiddleware` using `time.perf_counter()`. Wrap `send` to
capture `http.response.start`, call the downstream application, then read the
resolved route object from `scope["route"]`. Log only method, safe route
template or `<unmatched>`, integer status, and rounded duration. Re-raise all
exceptions.

Register it once in `backend/main.py`. Do not include request URLs, path
parameters, query parameters, headers, client addresses, user identifiers,
bodies, or exception text.

**Step 4: Run the tests to verify GREEN**

Run the command from Step 2.

Expected: PASS.

**Step 5: Commit**

```bash
git add -- backend/app/middleware/safe_access_log.py backend/tests/test_safe_access_log.py backend/main.py
git commit -m "security(backend): log only sanitized route templates"
```

### Task 4: Disable Uvicorn raw access logging in every production artifact

**Files:**
- Modify: `infra/systemd/health-backend.service`
- Modify: `infra/systemd/dropins/health-backend-runtime-state.conf`
- Modify: `scripts/test_infrastructure_security.py`
- Modify: `scripts/test_runtime_state_release_transaction.py`

**Step 1: Write the failing infrastructure contract**

Extend `test_backend_keeps_process_local_garmin_mfa_challenges_on_one_worker`
or add a focused test that requires `--no-access-log` in both ExecStart
artifacts. Update the exact runtime-state candidate expectation only after the
new assertion has failed.

**Step 2: Run the tests to verify RED**

Run:

```bash
backend/venv/bin/python -m pytest -q --no-cov --tb=short \
  scripts/test_infrastructure_security.py::test_backend_keeps_process_local_garmin_mfa_challenges_on_one_worker
```

Expected: FAIL because neither ExecStart contains `--no-access-log`.

**Step 3: Update both production ExecStart artifacts**

Append `--no-access-log` to the base unit and the transactional runtime-state
drop-in. Update the exact candidate assertion in
`scripts/test_runtime_state_release_transaction.py`.

**Step 4: Run the infrastructure tests to verify GREEN**

Run:

```bash
backend/venv/bin/python -m pytest -q --no-cov --tb=short \
  scripts/test_infrastructure_security.py \
  scripts/test_runtime_state_release_transaction.py::test_dropins_enforce_minimal_external_writable_boundaries
```

Expected: PASS.

**Step 5: Commit**

```bash
git add -- infra/systemd/health-backend.service infra/systemd/dropins/health-backend-runtime-state.conf scripts/test_infrastructure_security.py scripts/test_runtime_state_release_transaction.py
git commit -m "security(infra): disable raw backend access logs"
```

### Task 5: Verify the combined change and update the dossier

**Files:**
- Modify: `docs/dossiers/2026-08-19-diet-confirmation-access-log-hardening.md`
- Regenerate only if required: `docs/_generated/system-map.json`
- Regenerate only if required: `docs/_generated/system-map-agent-context.md`

**Step 1: Run focused and adjacent regression checks**

```bash
cd mobile
npm test -- --runInBand components/chat/cards/__tests__/registry.test.tsx
npx tsc --noEmit
./node_modules/.bin/eslint --no-cache components/chat/cards/DietDraftCard.tsx components/chat/cards/__tests__/registry.test.tsx

cd ..
backend/venv/bin/python -m pytest -q --no-cov --tb=short \
  backend/tests/test_safe_access_log.py \
  scripts/test_infrastructure_security.py \
  scripts/test_runtime_state_release_transaction.py::test_dropins_enforce_minimal_external_writable_boundaries
backend/venv/bin/python -m py_compile backend/app/middleware/safe_access_log.py backend/main.py
./scripts/system-map-check.sh
git diff --check
```

Expected: every command exits 0. If the system-map check reports drift, run its
documented generator, review the generated-only diff, and re-run the check.

**Step 2: Update lifecycle evidence**

Record exact G3 command results and G4 privacy review conclusions. Leave G5/G6
pending until deployment and production verification complete.

**Step 3: Commit the verified implementation state**

```bash
git add -- docs/dossiers/2026-08-19-diet-confirmation-access-log-hardening.md
git commit -m "docs(p0): record diet and logging verification"
```

### Task 6: Integrate, deploy, and verify production

**Files:**
- No source changes expected.

**Step 1: Reconcile with current main**

Fetch `origin/main`, require a clean worktree, rebase or fast-forward as needed,
and re-run the focused checks if the source SHA changes.

**Step 2: Push the exact verified commit**

Push only the current branch tip to `origin/main`; do not force push.

**Step 3: Deploy Backend**

Read `.claude/skills/backend-deploy/SKILL.md`, run the guarded Backend-only
deployment from the clean exact-main worktree, and verify the deployed source
revision, systemd effective ExecStart, service state, and public health.

**Step 4: Prove production log privacy**

Send a benign health request with a unique sentinel query value. Inspect only
new Backend logs. Require a structured `http_access` entry for the route
template and require the sentinel/raw query to be absent.

**Step 5: Publish Mobile OTA**

Read `.claude/skills/mobile-ota/SKILL.md` and run:

```bash
./scripts/mobile-ota.sh production "显示全部饮食识别项"
```

Require exact source/channel/runtime evidence and a published update group.

**Step 6: Update and commit final dossier state**

Record G5/G6 evidence only after the live checks pass. If any gate fails, stop
and leave the dossier BLOCKED rather than claiming completion.
