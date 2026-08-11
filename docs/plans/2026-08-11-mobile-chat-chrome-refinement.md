# Mobile Chat Chrome Refinement Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the Mobile Agent header and conditional context strip quieter, clearer, and more robust without changing chat behavior, health semantics, or write paths.

**Architecture:** Reuse `ChatHeader`, header-mode `LlmModelPicker`, and `ChatTodayFocusCard`. Keep all callbacks and source data unchanged; refine presentation through tested React Native styles, explicit pressed states, a composed new-conversation glyph, long-title handling, and live-region accessibility. The first slice is Mobile-only and OTA-compatible, but production OTA remains paused while iOS 1.3.3 is waiting for App Review.

**Tech Stack:** Expo, React Native, TypeScript, Ionicons, Jest, Testing Library React Native.

---

### Task 1: Simplify the conditional context strip

**Files:**
- Modify: `mobile/components/chat/ChatTodayFocusCard.tsx`
- Test: `mobile/components/chat/__tests__/ChatTodayFocusCard.test.tsx`

1. Write failing tests that require normal/caution rows to omit the redundant clock wrapper, use a 40pt visual rail with 4pt hit slop, allow the title to wrap to two lines, and expose changing Agent status through a polite live region.
2. Run `pnpm test -- --runInBand components/chat/__tests__/ChatTodayFocusCard.test.tsx` and confirm the assertions fail for the old 44pt/icon/single-line implementation.
3. Implement the minimum presentation change. Preserve the alert icon for risk and error states.
4. Run the focused test and confirm it passes.

### Task 2: Redesign the new-conversation action and interaction feedback

**Files:**
- Modify: `mobile/components/chat/ChatHeader.tsx`
- Test: `mobile/components/chat/__tests__/ChatHeader.test.tsx`

1. Write failing tests for a composed `chatbubble-outline` plus `add` badge, a subtle green primary surface, `ellipsis-horizontal` for the more-actions menu, and pressed-state feedback implemented with `Pressable`.
2. Run the focused header test and confirm RED for the current pencil/settings/TouchableOpacity implementation.
3. Implement a 40pt visible control with 4pt hit slop and stable accessibility labels. Keep history neutral and all callbacks unchanged.
4. Run the focused test and confirm GREEN.

### Task 3: Rebalance the Xiaoba identity

**Files:**
- Modify: `mobile/components/chat/ChatHeader.tsx`
- Modify: `mobile/components/chat/LlmModelPicker.tsx`
- Test: `mobile/components/chat/__tests__/ChatHeader.test.tsx`
- Test: `mobile/components/chat/__tests__/LlmModelPicker.test.tsx`

1. Write failing tests for a 22pt avatar, 20pt/25pt title, and 12pt chevron while retaining a minimum 44pt model trigger.
2. Run both focused suites and confirm RED.
3. Implement the exact static proportions without changing the model-selection flow.
4. Run both suites and confirm GREEN.

### Task 4: Verification and integration

**Files:**
- Update: `docs/dossiers/2026-07-13-xiaoba-health-advisor-chat-ui.md`
- Update: `docs/specs/active/2026-07-16-mobile-chat-context-strip.md`

1. Run the three focused Jest suites, targeted ESLint, `pnpm exec tsc --noEmit`, `pnpm design:check`, and `git diff --check`.
2. Review the rendered hierarchy on an iPhone simulator if available. Verify short/long context, active status, risk status, new conversation, history, and more actions.
3. Record G3/G4 and review-hold status in the existing Dossier.
4. Commit exact files, rebase onto the latest `origin/main`, rerun focused verification, and push.
5. Do not publish another production OTA while App Store submission 1.3.3 (256) remains waiting for review. Production release is a later explicit G5 action.

### Explicit non-goals

- No backend, model routing, health claim, safety rule, write path, or database change.
- No new native module or macOS target.
- No production OTA during the current App Review wait.
- Mac keyboard shortcuts and native hover/tooltips remain a separate Mac-workbench slice.
