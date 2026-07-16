# Mobile Fast Feedback Loop Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Reduce mobile inner-loop feedback to seconds, cached physical-device acceptance to under a minute when feasible, and OTA publication to one verified command with automatic transient retry.

**Architecture:** Keep three explicit feedback layers. A small Expo Updates state machine and root provider own foreground download and explicit apply; shell scripts accelerate changed-file tests and cached USB Release builds; the existing OTA script gains narrow retry and result verification without weakening its clean-main guards.

**Tech Stack:** React Native 0.83, Expo SDK 55, `expo-updates`, Jest, Testing Library, TypeScript incremental builds, Bash, Python subprocess tests, Xcode, `devicectl`, EAS Update.

---

### Task 1: Expo Update State Machine

**Files:**
- Create: `mobile/services/appUpdate.ts`
- Create: `mobile/services/__tests__/appUpdate.test.ts`

**Step 1: Write failing service tests**

Cover these outcomes with an injected Expo Updates adapter:

- disabled/dev runtime returns `disabled` without network calls;
- no compatible update returns `current`;
- available update checks, fetches, and returns `ready`;
- check or fetch failure returns a typed failure and preserves the error;
- apply delegates to `reloadAsync` only after a downloaded update exists.

**Step 2: Run the focused test and verify RED**

Run:

```bash
cd mobile
npx jest services/__tests__/appUpdate.test.ts --runInBand
```

Expected: FAIL because `services/appUpdate.ts` does not exist.

**Step 3: Implement the minimal adapter-backed service**

Export:

```ts
export type AppUpdateCheckResult = 'disabled' | 'current' | 'ready';
export type AppUpdateAdapter = Pick<typeof Updates,
  'isEnabled' | 'checkForUpdateAsync' | 'fetchUpdateAsync' | 'reloadAsync'>;

export async function downloadAvailableUpdate(
  adapter?: AppUpdateAdapter,
): Promise<AppUpdateCheckResult>;

export async function applyDownloadedUpdate(
  adapter?: AppUpdateAdapter,
): Promise<void>;
```

Do not hide exceptions in the service. The provider decides how to present them.

**Step 4: Run the focused test and verify GREEN**

Run the same Jest command. Expected: PASS.

**Step 5: Commit**

```bash
git add mobile/services/appUpdate.ts mobile/services/__tests__/appUpdate.test.ts
git commit -m "feat(mobile): add explicit OTA update service"
```

### Task 2: Foreground Download and Explicit Apply UI

**Files:**
- Create: `mobile/hooks/useAppUpdate.tsx`
- Create: `mobile/hooks/__tests__/useAppUpdate.test.tsx`
- Create: `mobile/components/updates/AppUpdateBanner.tsx`
- Create: `mobile/components/updates/__tests__/AppUpdateBanner.test.tsx`
- Modify: `mobile/app/_layout.tsx`

**Step 1: Write failing provider and banner tests**

Assert:

- provider checks once after mount and again on a later active transition after the throttle window;
- duplicate active events inside the throttle window do not recheck;
- a downloaded update exposes `ready`;
- the banner renders only for `ready` and has `立即更新` plus `稍后`;
- tapping `立即更新` invokes explicit apply;
- dismissing hides the current banner without disabling future checks;
- failures remain non-blocking and can be retried manually.

**Step 2: Verify RED**

```bash
cd mobile
npx jest hooks/__tests__/useAppUpdate.test.tsx components/updates/__tests__/AppUpdateBanner.test.tsx --runInBand
```

Expected: FAIL because provider and banner do not exist.

**Step 3: Implement provider and banner**

The provider exposes:

```ts
type AppUpdateContextValue = {
  status: 'idle' | 'checking' | 'downloading' | 'ready' | 'applying' | 'failed';
  error: string | null;
  checkNow(): Promise<AppUpdateCheckResult | 'failed'>;
  applyUpdate(): Promise<void>;
  dismissReady(): void;
};
```

Use a five-minute foreground throttle. Fetch silently, never call `reloadAsync` automatically, and use a compact full-width banner below the router stack.

**Step 4: Integrate at the root**

Wrap `AppContent` with `AppUpdateProvider` inside existing root providers and render `AppUpdateBanner` next to the current notification/network banners.

**Step 5: Verify GREEN and TypeScript**

```bash
cd mobile
npx jest hooks/__tests__/useAppUpdate.test.tsx components/updates/__tests__/AppUpdateBanner.test.tsx --runInBand
npx tsc --noEmit
```

Expected: all commands exit 0.

**Step 6: Commit**

```bash
git add mobile/hooks/useAppUpdate.tsx mobile/hooks/__tests__/useAppUpdate.test.tsx mobile/components/updates/AppUpdateBanner.tsx mobile/components/updates/__tests__/AppUpdateBanner.test.tsx mobile/app/_layout.tsx
git commit -m "feat(mobile): download OTA updates on foreground"
```

### Task 3: Settings Update Control and Real Version

**Files:**
- Modify: `mobile/app/settings.tsx`
- Modify: `mobile/app/__tests__/settings.test.tsx`

**Step 1: Write failing settings tests**

Assert the settings screen:

- shows `Constants.nativeAppVersion` and `nativeBuildVersion`, not hard-coded `1.0.0`;
- exposes `检查更新`;
- reports current, ready, disabled, and failed outcomes with concise alerts;
- does not trigger two checks while one is active.

**Step 2: Verify RED**

```bash
cd mobile
npx jest app/__tests__/settings.test.tsx --runInBand
```

**Step 3: Implement minimal settings integration**

Use `useAppUpdate()` and `expo-constants`; do not create a second update state machine.

**Step 4: Verify GREEN**

Run the same focused Jest command.

**Step 5: Commit**

```bash
git add mobile/app/settings.tsx mobile/app/__tests__/settings.test.tsx
git commit -m "feat(mobile): add manual update check"
```

### Task 4: Changed-File Fast Test Command

**Files:**
- Create: `scripts/mobile-fast-test.sh`
- Create: `scripts/test_mobile_fast_feedback_scripts.py`

**Step 1: Write failing subprocess tests**

Use a dry-run environment to assert:

- changed Mobile TS/TSX files produce related Jest, changed-file ESLint, incremental TypeScript, and diff-check commands;
- unrelated backend/doc changes do not trigger Mobile Jest or ESLint;
- `--all` produces the full Mobile release checks;
- command failures propagate their real exit code.

**Step 2: Verify RED**

```bash
python3 -m pytest scripts/test_mobile_fast_feedback_scripts.py -q
```

Expected: FAIL because the script does not exist.

**Step 3: Implement the script**

Default changed files come from staged, unstaged, and untracked paths under `mobile/`. Support `MOBILE_FAST_TEST_CHANGED_FILES` for deterministic tests and `--all` for the release gate. Use:

```text
Jest --findRelatedTests --runInBand --passWithNoTests
ESLint only changed JS/TS files
tsc --noEmit --incremental --tsBuildInfoFile .cache/tsc/fast.tsbuildinfo
git diff --check
```

Do not pipe test commands through `tail`.

**Step 4: Verify GREEN and measure warm runtime**

Run the pytest command, then run `./scripts/mobile-fast-test.sh` twice and record both durations.

**Step 5: Commit**

```bash
git add scripts/mobile-fast-test.sh scripts/test_mobile_fast_feedback_scripts.py
git commit -m "feat(tooling): add mobile changed-file test loop"
```

### Task 5: Cached USB Device Release Command

**Files:**
- Create: `scripts/mobile-fast-device.sh`
- Modify: `scripts/test_mobile_fast_feedback_scripts.py`
- Modify: `scripts/mobile-local-device.sh`

**Step 1: Extend failing subprocess tests**

Dry-run assertions:

- connected physical iPhone data is read from `devicectl` JSON;
- Release builds use persistent DerivedData and never run `rm -rf`, `expo prebuild --clean`, or `pod install --repo-update`;
- build, bundle verification, install, and launch commands are emitted in order;
- a locked-device launch failure is reported as installed-but-needs-unlock;
- `metro` mode starts the development client server without rebuilding.

**Step 2: Verify RED**

Run the script-test pytest command and confirm the new assertions fail.

**Step 3: Implement `release` and `metro` modes**

`release` is the default. Use:

- `xcrun devicectl list devices --json-output` for CoreDevice ID and Xcode UDID;
- a persistent path such as `${HOME}/Library/Developer/Xcode/DerivedData/RevaFastDevice`;
- existing `mobile/ios/*.xcworkspace` and scheme;
- `xcodebuild -configuration Release -destination id=<udid>` without cleaning;
- `devicectl device install app`, then launch;
- exact bundle ID verification before installation.

`metro` runs `npx expo start --dev-client --lan`; support `--tunnel` when local network routing is unavailable.

Update `mobile-local-device.sh` guidance so clean prebuild is documented as first-time/native-fingerprint setup only, not the daily loop.

**Step 4: Verify GREEN and real device behavior**

Run subprocess tests, then execute a cold Release build once and a warm build once on the connected iPhone. Record build/install/launch duration and actual installed version.

**Step 5: Commit**

```bash
git add scripts/mobile-fast-device.sh scripts/mobile-local-device.sh scripts/test_mobile_fast_feedback_scripts.py
git commit -m "feat(tooling): add cached USB mobile install"
```

### Task 6: Verified OTA with Narrow Automatic Retry

**Files:**
- Modify: `scripts/mobile-ota.sh`
- Modify: `scripts/test_mobile_fast_feedback_scripts.py`

**Step 1: Add failing script tests**

Assert:

- an asset-processing/upload timeout retries exactly once;
- authentication, runtime mismatch, dirty tree, or bundling failures never retry;
- success without an iOS update ID fails verification;
- successful output records the commit anchor only after verification;
- channel mode uses the configured channel and preserves preview/production environments.

**Step 2: Verify RED**

Run the script-test pytest command.

**Step 3: Implement minimal retry and verification**

Capture each EAS attempt to a log while preserving terminal output and exit status. Retry once only when the failed log contains a known transient upload/asset-processing timeout. Require published output to contain both an update group ID and an iOS update ID before writing `.last-ota-commit`.

Keep the existing clean-main and dirty-Mobile guards unchanged.

**Step 4: Verify GREEN**

Run script tests and `bash -n scripts/mobile-ota.sh scripts/mobile-fast-test.sh scripts/mobile-fast-device.sh`.

**Step 5: Commit**

```bash
git add scripts/mobile-ota.sh scripts/test_mobile_fast_feedback_scripts.py
git commit -m "fix(release): retry and verify mobile OTA"
```

### Task 7: Integrated Gates and Production Evidence

**Files:**
- Modify: `docs/dossiers/2026-07-15-mobile-fast-feedback-loop.md`
- Modify: `docs/plans/2026-07-15-mobile-fast-feedback-loop-design.md` only if implementation materially changes the design

**Step 1: Run focused and full Mobile gates**

```bash
./scripts/mobile-fast-test.sh --all
python3 -m pytest scripts/test_mobile_fast_feedback_scripts.py -q
git diff --check
```

Expected: all exit 0 with no swallowed failures.

**Step 2: Run cached USB validation**

```bash
./scripts/mobile-fast-device.sh release
```

Verify build succeeded, bundle ID matches, install succeeded, and the unlocked iPhone launches.

**Step 3: Validate update UI on the physical iPhone**

Publish a compatible preview update, foreground the app, verify the ready banner, apply it, and confirm diagnostics report the expected update ID. Do not publish production until this passes.

**Step 4: Publish or republish production OTA**

Use the verified update group for production promotion where possible. Record group ID, iOS update ID, runtime, commit, and dashboard URL.

**Step 5: Update the dossier and commit**

Set G3/G5 evidence and leave G6 pending until the user confirms the physical-device path.

```bash
git add docs/dossiers/2026-07-15-mobile-fast-feedback-loop.md
git commit -m "docs(mobile): record fast feedback verification"
git push origin main
```
