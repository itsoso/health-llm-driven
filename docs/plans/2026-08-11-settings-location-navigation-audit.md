# Settings Location And Navigation Audit Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make automatic GPS city display truthful and fresh, verify every production settings entry, and repair high-confidence settings layout defects.

**Architecture:** Keep `/location` as the only location editor and permission prompt surface. Add pure presentation helpers for deterministic city/mode selection, refresh profile when Settings regains focus, and drive settings navigation from an exported production entry registry so UI and route tests share one source. Preserve the root `useGPSAutoRefresh` flow and add observable refresh state without changing the backend contract.

**Tech Stack:** Expo Router, React Native, TanStack Query, expo-location, Jest, React Native Testing Library, TypeScript.

---

### Task 1: Reproduce The Incorrect City Label

**Files:**
- Modify: `mobile/app/__tests__/settings.test.tsx`
- Modify: `mobile/app/settings.tsx`

**Step 1: Write the failing tests**

- Change the existing automatic-location assertion for `{ city: '杭州', region: '浙江' }` from `浙江` to `杭州`.
- Add cases proving an enabled manual city wins and region is only used when detected city is absent.

**Step 2: Run the focused test and verify RED**

Run: `npm test -- --runInBand app/__tests__/settings.test.tsx`

Expected: FAIL because the current `useMemo` selects `detected_location.region` before `detected_location.city`.

**Step 3: Implement the minimal pure selector**

- Export a typed `getSettingsLocationLabel(profile)` helper from `mobile/app/settings.tsx` or a small adjacent module.
- Implement priority: active manual city → detected city → detected region with administrative suffix trimmed → legacy profile city → `未设置`.

**Step 4: Run the focused test and verify GREEN**

Run: `npm test -- --runInBand app/__tests__/settings.test.tsx`

Expected: PASS.

**Step 5: Commit only Task 1 files**

```bash
git add mobile/app/settings.tsx mobile/app/__tests__/settings.test.tsx
git commit -m "fix(settings): show detected GPS city"
```

### Task 2: Refresh Settings After Location Changes

**Files:**
- Modify: `mobile/app/__tests__/settings.test.tsx`
- Modify: `mobile/app/settings.tsx`
- Modify: `mobile/applib/queryKeys.ts` only if a shared GPS state key is required

**Step 1: Write the failing focus test**

- Mock Expo Router `useFocusEffect` and capture its callback.
- Assert entering/regaining focus invalidates `queryKeys.profile` and triggers a profile refetch.
- Assert a cached city remains visible while refetching, rather than flashing `未设置`.

**Step 2: Run and verify RED**

Run: `npm test -- --runInBand app/__tests__/settings.test.tsx`

Expected: FAIL because Settings currently relies on a ten-minute stale profile query and has no focus refresh.

**Step 3: Implement minimal focus refresh**

- Use Expo Router `useFocusEffect` with a stable callback.
- On focus, invalidate/refetch `queryKeys.profile`; do not clear cached data.
- Keep the root GPS hook as the only automatic coordinate updater.

**Step 4: Run and verify GREEN**

Run: `npm test -- --runInBand app/__tests__/settings.test.tsx`

Expected: PASS.

**Step 5: Commit Task 2 files**

```bash
git add mobile/app/settings.tsx mobile/app/__tests__/settings.test.tsx mobile/applib/queryKeys.ts
git commit -m "fix(settings): refresh location on focus"
```

### Task 3: Make GPS State Truthful

**Files:**
- Modify: `mobile/hooks/__tests__/useGPSAutoRefresh.test.ts`
- Modify: `mobile/hooks/useGPSAutoRefresh.ts`
- Modify: `mobile/app/__tests__/settings.test.tsx`
- Modify: `mobile/app/settings.tsx`
- Create if needed: `mobile/services/gpsRefreshStatus.ts`

**Step 1: Write failing state tests**

- Permission denied/undetermined records `permission_required` without prompting.
- Refresh start records `refreshing`.
- Successful backend update records `ready` with timestamp and clears an old error.
- Location/API failure records `error` while retaining the last successful city.
- Settings maps these states to `需开启定位`, `正在更新`, `GPS 自动`, or `更新失败`.

**Step 2: Run and verify RED**

Run: `npm test -- --runInBand hooks/__tests__/useGPSAutoRefresh.test.ts app/__tests__/settings.test.tsx`

Expected: FAIL because refresh state is currently silent and not exposed to Settings.

**Step 3: Implement minimal persisted status**

- Store only status, failure reason category, and last-success timestamp; never store a new copy of health/profile data.
- Read status on Settings focus and update the GPS row semantic color/accessibility label.
- Do not request permission from the background hook.

**Step 4: Run and verify GREEN**

Run: `npm test -- --runInBand hooks/__tests__/useGPSAutoRefresh.test.ts app/__tests__/settings.test.tsx`

Expected: PASS.

**Step 5: Commit Task 3 files**

```bash
git add mobile/hooks/useGPSAutoRefresh.ts mobile/hooks/__tests__/useGPSAutoRefresh.test.ts mobile/app/settings.tsx mobile/app/__tests__/settings.test.tsx mobile/services/gpsRefreshStatus.ts
git commit -m "fix(location): expose automatic refresh state"
```

### Task 4: Cover Every Production Settings Entry

**Files:**
- Modify: `mobile/app/settings.tsx`
- Modify: `mobile/app/__tests__/settings.test.tsx`
- Create: `mobile/scripts/check-settings-routes.mjs`
- Modify: `mobile/package.json`

**Step 1: Write the failing navigation matrix**

- Define the production-visible route labels and destinations in the test.
- Click every entry and assert exactly one correct router call.
- Add a filesystem route check for every declared destination.
- Cover action-only rows separately so they are not mistaken for navigation.

**Step 2: Run and verify RED**

Run: `npm test -- --runInBand app/__tests__/settings.test.tsx && npm run check:settings-routes`

Expected: RED until all production entries expose stable accessibility labels and the route checker exists.

**Step 3: Make UI and registry testable**

- Export a production settings route registry or add stable accessibility labels/test IDs without duplicating user-visible strings.
- Keep release-capability-gated rows out of the production matrix.

**Step 4: Run and verify GREEN**

Run: `npm test -- --runInBand app/__tests__/settings.test.tsx && npm run check:settings-routes`

Expected: PASS for every visible navigation row and every target route.

**Step 5: Commit Task 4 files**

```bash
git add mobile/app/settings.tsx mobile/app/__tests__/settings.test.tsx mobile/scripts/check-settings-routes.mjs mobile/package.json
git commit -m "test(settings): verify every production entry"
```

### Task 5: Repair Settings Row Layout

**Files:**
- Modify: `mobile/app/__tests__/settings.test.tsx`
- Modify: `mobile/app/settings.tsx`

**Step 1: Write failing structural assertions**

- Each grouped row receives `isLast` and the final row has no divider.
- GPS status is not constrained to a fixed 74pt width.
- Long values use one-line truncation while the title retains priority.
- Every actionable row keeps a minimum 48pt target.

**Step 2: Run and verify RED**

Run: `npm test -- --runInBand app/__tests__/settings.test.tsx`

Expected: FAIL against current fixed-width status and unconditional dividers.

**Step 3: Implement minimal layout corrections**

- Add group-aware last-row styling.
- Replace the fixed status width with max width/flex shrink.
- Add `numberOfLines={1}` and correct flex properties.
- Preserve existing typography and information architecture.

**Step 4: Run and verify GREEN**

Run: `npm test -- --runInBand app/__tests__/settings.test.tsx`

Expected: PASS.

**Step 5: Commit Task 5 files**

```bash
git add mobile/app/settings.tsx mobile/app/__tests__/settings.test.tsx
git commit -m "style(settings): refine rows and location status"
```

### Task 6: Automated And Simulator Verification

**Files:**
- Modify: `docs/plans/2026-08-11-settings-location-navigation-audit.md` with a verification appendix if defects are found
- Modify only defect-related files discovered by the audit, following a fresh RED/GREEN cycle for each defect

**Step 1: Run the focused suites**

Run: `npm test -- --runInBand app/__tests__/settings.test.tsx hooks/__tests__/useGPSAutoRefresh.test.ts`

Expected: all tests pass.

**Step 2: Run static gates**

Run: `npm run typecheck`

Run: `npm run lint`

Run: `npm run check:settings-routes`

Expected: all exit 0.

**Step 3: Build and launch iOS Release in the simulator**

- Use the repository's existing iOS simulator build workflow.
- Confirm the settings screen renders with production release capabilities.

**Step 4: Execute the click matrix manually**

- For every production-visible row: tap, confirm first screen, capture errors, return.
- For location: set a simulator location, open Settings, verify city and state update without manual profile editing.
- For destructive/action rows: verify dialogs and cancel; do not delete the account or log out during the matrix.

**Step 5: Fix each discovered defect through its own failing test**

- Do not bundle speculative refactors.
- Repeat until every matrix item passes.

### Task 7: Review, Integrate, And Release

**Files:**
- Update: the active dossier if one exists or create a focused verification record

**Step 1: Review the complete diff**

Check for unrelated files, secrets, silent failures, accessibility regressions, and native dependency changes.

**Step 2: Run final verification from a clean branch**

Run focused Jest, typecheck, lint, route checker, and iOS Release simulator build without truncating output or hiding exit codes.

**Step 3: Commit and push**

Stage only files from this feature and use project commit-message conventions.

**Step 4: Publish only if OTA-compatible**

If no native/config/backend change was required, publish with:

```bash
./scripts/mobile-ota.sh production "fix settings GPS city and verify navigation"
```

Record the runtime, commit, update group ID, and iOS update ID.

**Step 5: Verify on the production app**

- Apply the OTA, reopen Settings, confirm city display and two representative routes.
- Preserve the EAS previous update as the rollback point.
