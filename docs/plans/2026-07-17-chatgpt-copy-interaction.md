# ChatGPT-Style Message Copy Interaction Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make completed Agent reply copying feel consistent with ChatGPT across Mobile, Web, and Mac, with an in-place copied state and no scroll-disrupting toast.

**Architecture:** Keep each platform's existing message action boundary and clipboard bridge. Mobile owns a short-lived copied state inside `ChatBubble`; Web owns it inside the memoized `MessageRow`; Mac keeps the existing Swift `copy` bridge and adds state only in the WebView shell. The copied state is presentation-only and does not enter message persistence or synchronization payloads.

**Tech Stack:** React Native/Expo, Jest + React Native Testing Library, Next.js/React + Vitest, Swift/SwiftUI, WKWebView HTML/CSS/JavaScript.

---

### Task 1: Mobile copy action state

**Files:**
- Modify: `mobile/components/chat/ChatBubble.tsx:600-610, 990-1010, 2270-2285`
- Test: `mobile/components/chat/__tests__/ChatBubbleStreaming.test.tsx`

**Step 1: Write the failing test**

Add a completed assistant reply test that finds the compact copy action, asserts it starts with the copy accessibility label/icon, presses it, and asserts the same action changes to the copied label/icon without requiring a toast.

**Step 2: Run test to verify it fails**

Run: `pnpm --dir mobile exec jest --runInBand components/chat/__tests__/ChatBubbleStreaming.test.tsx -t "copied state"`

Expected: FAIL because the current action has no copied state and still exposes the text label `复制`.

**Step 3: Write minimal implementation**

Add a local `copied` state and a timeout ref in `ChatBubbleInner`. Make `handleCopy` await `Clipboard.setStringAsync`, set copied state only after success, and keep the existing long-press menu label `复制全文`. Replace the always-visible assistant copy row with an icon-only `Pressable` whose icon and accessibility label are `copy-outline`/`复制回答` or `checkmark`/`已复制`.

**Step 4: Run test to verify it passes**

Run: `pnpm --dir mobile exec jest --runInBand components/chat/__tests__/ChatBubbleStreaming.test.tsx -t "copied state"`

Expected: PASS.

**Step 5: Commit**

```bash
git add mobile/components/chat/ChatBubble.tsx mobile/components/chat/__tests__/ChatBubbleStreaming.test.tsx
git commit -m "feat(mobile): add in-place chat copy state"
```

### Task 2: Web copy action state

**Files:**
- Modify: `frontend/src/components/assistant/ChatView.tsx:300-315`
- Test: `frontend/src/components/assistant/__tests__/ChatViewMessageTime.test.tsx` or a new focused `ChatViewCopy.test.tsx`

**Step 1: Write the failing test**

Render a completed assistant message, dispatch a click on its copy button, and assert the button changes from `复制` to `已复制` with an accessible label. Test the rejection path leaves the button in the normal state.

**Step 2: Run test to verify it fails**

Run: `pnpm --dir frontend exec vitest run src/components/assistant/__tests__/ChatViewCopy.test.tsx`

Expected: FAIL because the current button has no state or failure boundary.

**Step 3: Write minimal implementation**

Add a small `copiedMessageId` state in `ChatView`, pass the state and a copy callback to `MessageRow`, and use a stable timeout cleanup. The callback awaits `navigator.clipboard.writeText`; only success marks the message copied. Keep the existing hover/focus action row and update button label/icon/title in place.

**Step 4: Run test to verify it passes**

Run: `pnpm --dir frontend exec vitest run src/components/assistant/__tests__/ChatViewCopy.test.tsx`

Expected: PASS.

**Step 5: Commit**

```bash
git add frontend/src/components/assistant/ChatView.tsx frontend/src/components/assistant/__tests__/ChatViewCopy.test.tsx
git commit -m "feat(web): add in-place chat copy state"
```

### Task 3: Mac WebView copy state

**Files:**
- Modify: `apps/mac/Sources/HealthAgentMac/Resources/chat-transcript.html:140-165, 980-1000, 1490-1510`
- Test: `apps/mac/Tests/HealthAgentMacCoreTests/ChatTranscriptHTMLTests.swift`

**Step 1: Write the failing test**

Extend the HTML rendering assertions to require a copy button with an accessible label and copied-state hook/class in the chat shell. Keep the Swift rendered-message envelope unchanged.

**Step 2: Run test to verify it fails**

Run: `xcodebuild test -scheme HealthAgentMac -project apps/mac/HealthAgentMac.xcodeproj -destination 'platform=macOS' -only-testing:HealthAgentMacCoreTests/ChatTranscriptHTMLTests`

Expected: FAIL because the resource shell does not expose the new copied-state behavior.

**Step 3: Write minimal implementation**

Update the resource shell button to use a copy icon/label, retain message ID in `data-message-id`, post the existing bridge message, and then toggle its icon/label/class for 1.5 seconds. Keep native `NSPasteboard` responsibility in `FeatureViews.swift` and do not add a second native notification.

**Step 4: Run test to verify it passes**

Run the same `xcodebuild test` command.

Expected: PASS.

**Step 5: Commit**

```bash
git add apps/mac/Sources/HealthAgentMac/Resources/chat-transcript.html apps/mac/Tests/HealthAgentMacCoreTests/ChatTranscriptHTMLTests.swift
git commit -m "feat(mac): add in-place chat copy state"
```

### Task 4: Cross-platform verification

**Files:**
- No new files.

**Step 1: Run Mobile tests and type check**

Run: `pnpm --dir mobile exec jest --runInBand components/chat/__tests__/ChatBubbleStreaming.test.tsx components/chat/__tests__/ChatBubbleStructuredSummary.test.tsx && pnpm --dir mobile exec tsc --noEmit`

Expected: PASS with zero test failures and zero TypeScript errors.

**Step 2: Run Web tests and checks**

Run: `pnpm --dir frontend exec vitest run src/components/assistant/__tests__/ChatViewCopy.test.tsx src/components/assistant/__tests__/ChatViewMessageTime.test.tsx && pnpm --dir frontend exec tsc --noEmit`

Expected: PASS with zero test failures and zero TypeScript errors.

**Step 3: Run Mac tests/build**

Run the focused Mac `xcodebuild test` command from Task 3, then the project’s normal macOS build command if available.

Expected: PASS; if Xcode/project configuration prevents execution, report the exact command and error.

**Step 4: Check the final diff**

Run: `git diff --check && git status --short`

Expected: no whitespace errors and only the intended three-platform files plus pre-existing unrelated worktree changes.

