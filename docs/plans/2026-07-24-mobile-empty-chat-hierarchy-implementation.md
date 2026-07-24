# Mobile Empty Chat Hierarchy Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the empty Mobile Agent conversation's three competing action layers with one contextual action layer and a compact, content-driven composer.

**Architecture:** Keep all backend contracts and existing send/ASR handlers intact. Normalize and deduplicate opener replies in `EmptyStateHome`, let `chat.tsx` own cross-component visibility using opener and keyboard state, and remove focused quick actions from `ChatInputBar`. Composer height becomes a presentation value derived from text content size rather than focus state.

**Tech Stack:** React Native, Expo, TypeScript, Jest, React Native Testing Library.

---

### Task 1: Normalize and deduplicate opener replies

**Files:**
- Modify: `mobile/components/chat/EmptyStateHome.tsx`
- Test: `mobile/components/chat/__tests__/EmptyStateHome.test.tsx`

**Step 1: Write the failing tests**

Add tests that render semantically duplicate replies such as `做到了` and
`已经完成`, and assert:

- only one visible `完成了` action remains;
- no more than three actions render;
- `换个话题` is appended only when fewer than three unique actions remain;
- action replies deduplicate by `action`, while retaining their existing local
  navigation handler.

**Step 2: Run the focused test and verify failure**

Run:

```bash
cd mobile
npx jest components/chat/__tests__/EmptyStateHome.test.tsx --runInBand
```

Expected: FAIL because normalized duplicate labels currently render twice.

**Step 3: Implement the reply projection**

Export a pure helper from `EmptyStateHome.tsx` that:

1. normalizes each label;
2. builds a stable identity from `action` or normalized label;
3. keeps the first occurrence;
4. appends `换个话题` only when capacity remains;
5. returns at most three visible actions.

Render replies from that projection and preserve the original raw reply text for
the existing send handler.

**Step 4: Run the test and verify pass**

Run the same focused Jest command.

Expected: PASS.

### Task 2: Collapse memory provenance and quiet the opener

**Files:**
- Modify: `mobile/components/chat/EmptyStateHome.tsx`
- Test: `mobile/components/chat/__tests__/EmptyStateHome.test.tsx`

**Step 1: Write the failing tests**

Update the opener test to assert:

- full memory content is not rendered inside an opener;
- one source affordance such as `依据 1 条医嘱` is rendered;
- pressing it still invokes `onOpenMemory`;
- setting the new action visibility prop to false removes all opener replies
  from the accessibility tree.

**Step 2: Run the focused test and verify failure**

Run the `EmptyStateHome` Jest file.

Expected: FAIL because the current component renders the full memory snippet and
has no action visibility contract.

**Step 3: Implement the quiet source row and opener styling**

- Replace the dense footnote with a single source row and chevron.
- Add `showReplyActions?: boolean` defaulting to true.
- Remove the opener bubble shadow and card-like border.
- Keep XiaoBa avatar, body typography, handlers, and accessibility targets.

**Step 4: Run the focused test and verify pass**

Run the same Jest command.

Expected: PASS.

### Task 3: Coordinate empty-state visibility at the page boundary

**Files:**
- Modify: `mobile/app/(tabs)/chat.tsx`
- Test: `mobile/app/(tabs)/__tests__/chat.test.tsx`

**Step 1: Write the failing integration tests**

Add tests for:

- an opener hides `ComposerSuggestionsRow`;
- keyboard visibility hides opener reply actions;
- no-opener, keyboard-closed state still renders the starter row.

Prefer assertions on accessibility labels and test IDs rather than component
internals.

**Step 2: Run the focused test and verify failure**

Run:

```bash
cd mobile
npx jest 'app/(tabs)/__tests__/chat.test.tsx' --runInBand
```

Expected: FAIL because starter suggestions currently ignore opener and keyboard
state.

**Step 3: Implement page-level coordination**

- Pass `showReplyActions={!keyboardVisible}` to `EmptyStateHome`.
- Render `ComposerSuggestionsRow` only when there is no opener and the keyboard
  is closed.
- Preserve onboarding and memory-only behavior.

**Step 4: Run the focused test and verify pass**

Run the same Jest command.

Expected: PASS.

### Task 4: Make the composer content-driven and remove the third action rail

**Files:**
- Modify: `mobile/components/chat/ChatInputBar.tsx`
- Test: `mobile/components/chat/__tests__/ChatInputBar.test.tsx`

**Step 1: Replace obsolete tests with the new contract**

Add or update tests asserting:

- focusing an empty composer keeps its 48-point compact height;
- `smart-composer-quick-actions` never appears on focus;
- one line of content stays compact;
- multiline content increases input height but caps at three lines;
- cloud ASR, microphone, send, and attachment controls remain available.

**Step 2: Run the focused test and verify failure**

Run:

```bash
cd mobile
npx jest components/chat/__tests__/ChatInputBar.test.tsx --runInBand
```

Expected: FAIL because focus currently forces a 72-point surface and exposes the
quick action rail.

**Step 3: Implement content-driven sizing**

- Remove `SMART_QUICK_ACTIONS`, `QuickComposerAction`, and the focused action
  rail.
- Track `TextInput` content height through `onContentSizeChange`.
- Clamp text height to one through three lines.
- Do not change composer mode, ASR state, send behavior, pending image behavior,
  or attachment actions.
- Keep the container's minimum height at 48 points and touch targets at least
  44 points.

**Step 4: Run the focused test and verify pass**

Run the same Jest command.

Expected: PASS.

### Task 5: Run Mobile verification

**Files:**
- Update: `docs/dossiers/2026-07-24-mobile-empty-chat-hierarchy.md`

**Step 1: Run focused tests together**

```bash
cd mobile
npx jest components/chat/__tests__/EmptyStateHome.test.tsx components/chat/__tests__/ChatInputBar.test.tsx 'app/(tabs)/__tests__/chat.test.tsx' --runInBand
```

Expected: all assertions pass.

**Step 2: Run TypeScript**

```bash
cd mobile
npx tsc --noEmit
```

Expected: exit code 0.

**Step 3: Run lint for the Mobile project**

```bash
cd mobile
npm run lint
```

Expected: exit code 0, or only explicitly documented pre-existing warnings.

**Step 4: Verify in the iOS simulator**

Launch the latest local Mobile build and capture:

1. empty conversation with opener and keyboard closed;
2. the same opener with keyboard open;
3. multiline draft at the three-line cap.

Expected: only one action layer is visible; keyboard-open state contains no
suggestion rows; composer height follows text content.

**Step 5: Update dossier gates**

Record G3 and G4 evidence. Keep G5/G6 pending until deployment and live
verification complete.

### Task 6: Commit, push, and release OTA

**Files:**
- Commit only the implementation, tests, design, plan, dossier, and generated
  docs required by drift checks.

**Step 1: Review the diff**

```bash
git status --short
git diff --check
git diff --stat
```

Expected: no unrelated changes or whitespace errors.

**Step 2: Commit**

```bash
git add <explicit changed paths>
git commit -m "fix(mobile): simplify empty chat hierarchy"
```

**Step 3: Push main**

```bash
git push origin main
```

Expected: push succeeds.

**Step 4: Publish production OTA**

```bash
scripts/mobile-ota.sh production "Simplify empty Agent conversation hierarchy"
```

Expected: production update completes successfully and returns an update ID.

**Step 5: Complete deployment gates**

Record the OTA update ID and production verification outcome in the dossier.

