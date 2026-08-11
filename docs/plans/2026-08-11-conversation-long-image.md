# Conversation Long Image Export Fix Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make selected-message long-image export reliably wait for layout and capture complete off-screen content on iOS.

**Architecture:** Keep the existing off-screen branded share view, but replace the timer with an `onLayout` readiness signal and guard each export session against duplicate captures. Build platform-specific `react-native-view-shot` options so iOS uses its large-view rendering path, then clean up the temporary capture after sharing.

**Tech Stack:** React Native 0.83, Expo 55, TypeScript, `react-native-view-shot`, Jest, Testing Library.

---

### Task 1: Add failing long-image export regressions

**Files:**
- Modify: `mobile/app/(tabs)/__tests__/chat.test.tsx`
- Create: `mobile/components/chat/__tests__/ConversationShareImage.test.tsx`

**Step 1: Write the failing tests**

- Mock `captureRef`, `releaseCapture`, and `shareLocalImage` at the native/share boundaries.
- Select an over-screen user/assistant message pair and press “选中消息生成长图”.
- Assert capture has not started before a valid layout event.
- Fire the long-image layout event twice and assert capture/share happen once.
- Assert iOS capture options contain `useRenderInContext: true`.
- Assert the share component ignores zero-height layout and reports a positive layout once.

**Step 2: Run tests to verify RED**

Run:

```bash
cd mobile
npx jest 'app/(tabs)/__tests__/chat.test.tsx' 'components/chat/__tests__/ConversationShareImage.test.tsx' --runInBand
```

Expected: FAIL because the component has no readiness callback/test ID and the page still captures on a timer with default iOS options.

### Task 2: Implement layout-driven iOS long capture

**Files:**
- Modify: `mobile/components/chat/ConversationShareImage.tsx`
- Modify: `mobile/app/(tabs)/chat.tsx`

**Step 1: Add the minimal share-view readiness contract**

- Add an optional `onReady` prop.
- Attach `onLayout` and `testID="conversation-share-image"` to the captured canvas.
- Notify only for positive width and height.

**Step 2: Replace the timer with a guarded capture callback**

- Clicking “长图” only mounts the export view and resets the per-session capture guard.
- The readiness callback starts capture once.
- Use `{ format: 'png', quality: 1, result: 'tmpfile', useRenderInContext: true }` on iOS; omit `useRenderInContext` on Android.
- Track whether failure occurred during capture or share, log only stage/error metadata, and show the matching alert.
- Release the temporary capture in `finally`.

**Step 3: Run focused tests to verify GREEN**

Run the Task 1 Jest command.

Expected: PASS with no warnings or unhandled timers.

### Task 3: Verify mobile regression and artifact

**Files:**
- No production file changes expected.

**Step 1: Run the chat/share regression suites**

```bash
cd mobile
npx jest 'app/(tabs)/__tests__/chat.test.tsx' 'components/chat/__tests__/ConversationShareImage.test.tsx' 'utils/__tests__/share.test.ts' --runInBand
```

**Step 2: Run static and bundle checks**

```bash
cd mobile
npx tsc --noEmit
npm run lint
npx expo export --platform ios
```

Expected: all commands exit 0.

**Step 3: Perform iOS smoke**

- Open the current conversation in Simulator.
- Select a user message plus an assistant response whose combined layout exceeds one screen.
- Generate the long image and confirm the native share sheet opens with a nonblank, full-height PNG.

### Task 4: Commit, push, and publish OTA

**Files:**
- Stage only the two plan documents, the focused tests, and the two long-image production files.

**Step 1: Commit the implementation**

```bash
git add docs/plans/2026-08-11-conversation-long-image-design.md \
  docs/plans/2026-08-11-conversation-long-image.md \
  'mobile/app/(tabs)/__tests__/chat.test.tsx' \
  'mobile/app/(tabs)/chat.tsx' \
  mobile/components/chat/ConversationShareImage.tsx \
  mobile/components/chat/__tests__/ConversationShareImage.test.tsx
git commit -m "fix(mobile): make conversation long-image export reliable"
git push
```

**Step 2: Verify a clean release input and publish**

Run the project OTA script only if the target main branch and worktree pass its cleanliness/release gates:

```bash
./scripts/mobile-ota.sh production "修复对话长图生成失败"
```

Expected: command exits 0 and reports the production iOS update group/ID.
