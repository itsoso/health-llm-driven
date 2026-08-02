# Cross-Surface Chat Continuity Implementation Plan

**Goal:** Align Web and Mobile conversation resume/history behavior and make the
Mobile Agent shell edge-to-edge with a stronger “小巴” title hierarchy.

**Architecture:** Keep `GET /agent/conversations` and owner-scoped conversation
detail as the only durable source. Change only client selection/presentation:
explicit intent wins, active local work wins, otherwise newest `updated_at`
wins. No schema, message, model, or write-path change.

**Tech Stack:** Expo Router, React Native, TypeScript, Jest, Testing Library,
Next.js, Vitest, existing FastAPI Agent conversation endpoints.

## Design Decision

Three approaches were considered:

1. **Canonical latest durable conversation (selected).** Smallest safe slice,
   no migration, deterministic across devices.
2. **Server-owned active-conversation pointer (deferred).** Preserves an older
   manually selected thread across devices, but adds mutable cross-device state,
   schema/API work, and last-writer ambiguity.
3. **Physically merge all messages (rejected).** Breaks topic, deletion, sharing,
   pagination, and audit boundaries.

## Selection Precedence

```text
explicit deep link / history selection / explicit new chat
  -> active or recoverable local stream
  -> newest owner-scoped durable conversation by updated_at
  -> empty state
```

## Task 1 — Lock the continuity contract with failing tests

**Files:**

- `mobile/hooks/__tests__/useChatEngine.test.ts`
- `mobile/components/chat/__tests__/ConversationSheet.test.tsx`
- `frontend/src/app/ai-assistant/__tests__/page-url.test.tsx`

Add RED cases for Web no-query boot, Mobile stored-older/server-newer boot,
explicit intent precedence, and server-order history presentation. Run only the
focused tests and confirm the new assertions fail for the expected reason.

## Task 2 — Implement Mobile canonical resume and history order

**Files:**

- `mobile/hooks/useChatEngine.ts`
- `mobile/components/chat/ConversationSheet.tsx`

Fetch canonical conversation metadata before honoring the device-local id.
Load the server latest when it is newer/different; retain the stored id only as
a network/empty fallback and preserve existing active-stream generation guards.
Remove briefing/weekly client pinning so the sheet preserves backend order.
Keep explicit `newChat` and selected history behavior unchanged.

## Task 3 — Implement Web latest-conversation boot

**Files:**

- `frontend/src/app/ai-assistant/page.tsx`

On the one-time boot effect, load explicit valid `?c=` first. Without it, list
one owner-scoped conversation and load the first item. Invalid explicit ids
fail closed to a clean new state. The in-session New conversation action must
not trigger the boot effect again.

## Task 4 — Make Mobile shell edge-to-edge and rebalance the header

**Files:**

- `mobile/app/_layout.tsx`
- `mobile/app/(tabs)/_layout.tsx`
- `mobile/app/(tabs)/chat.tsx`
- `mobile/components/chat/ChatHeader.tsx`
- `mobile/components/chat/LlmModelPicker.tsx`
- relevant focused tests

Make the native stack/tab scene and chat root share the paper background; render
the chat root behind a translucent status bar; apply top inset to content rather
than stopping the root surface at the safe-area boundary. Preserve the existing
keyboard/home-indicator bottom behavior. Increase the avatar to 32 and title to
28 with a coordinated line height; ensure right-side controls retain effective
44pt targets and truncation works at narrow widths.

## Task 5 — Verification and release gates

Run focused tests, full Mobile/Web type checks, dossier consistency, doc drift,
and `git diff --check`. Review the diff for owner isolation, stale async boot
overwrites, and silent empty-state fallbacks. Because this changes health-message
presentation, run the project safety/privacy review before release.

Deployment route:

```text
clean origin/main commit
  -> frontend deploy through project deploy path
  -> production Mobile OTA (JS/TS only)
  -> Web + iPhone same-account continuity smoke
  -> iPhone full-screen/title screenshot
  -> user G6 confirmation
```

Rollback restores the previous frontend and OTA bundles. No data rollback is
needed because persisted conversations are not mutated.
