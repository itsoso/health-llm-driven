# Interactive Chat Cards Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make Chat dynamic cards support safe user interactions for quick records and next actions.

**Architecture:** Extend the existing allowlisted card action contract instead of creating a new execution path. Mobile renders confirmation/disabled/loading states, while backend only emits existing safe actions (`route.open`, `agenda.complete`, `write_intent.confirm`, `write_intent.dismiss`) with manual-confirm metadata.

**Tech Stack:** FastAPI/Python backend card builders, Expo React Native card registry, Jest, pytest.

**Current status (2026-07-01):** Tasks 1-3 and the generic `record` action protocol are implemented, verified, deployed to backend, and published through Mobile OTA. `diet_draft` now supports inline edit, save-and-confirm from edit mode, in-card completion feedback after `diet_record.create` succeeds, and post-confirm nutrition estimation/backfill when macros are missing. Release evidence is tracked in `docs/dossiers/2026-06-30-interactive-chat-cards.md`.

---

### Task 1: Extend Mobile Action Metadata

**Files:**
- Modify: `mobile/components/chat/cards/types.ts`
- Modify: `mobile/components/chat/cards/registry.tsx`
- Test: `mobile/components/chat/cards/__tests__/registry.test.tsx`

**Step 1: Write failing tests**

Add tests that assert:

- A write action with `confirmation` renders and calls `onAction` only after confirmation handling.
- A write action with `disabled_reason` renders disabled and does not call `onAction`.
- An unsafe write action without `requires_manual_confirm=true` is still filtered.

**Step 2: Run tests**

Run:

```bash
pnpm --dir mobile exec jest mobile/components/chat/cards/__tests__/registry.test.tsx --runInBand
```

Expected: new tests fail.

**Step 3: Implement**

- Add optional `confirmation`, `optimistic`, `disabled_reason` fields to `ChatCardActionDescriptor`.
- Render disabled buttons when `disabled_reason` exists.
- Keep `normalizeCardActions` fail-closed.

**Step 4: Verify**

Run the same Jest command. Expected: pass.

### Task 2: Add Confirmation Flow In ChatBubble

**Files:**
- Modify: `mobile/components/chat/ChatBubble.tsx`
- Test: `mobile/components/chat/__tests__/ChatBubbleStructuredSummary.test.tsx` or create focused action test.

**Step 1: Write failing test**

Render a card with a `write_intent.confirm` action and `confirmation`; press the button; assert an Alert is requested before dispatcher execution.

**Step 2: Implement**

- In `handleCardAction`, if action has `confirmation` and is not `route.open`, show `Alert.alert`.
- On confirm, call existing `dispatchChatCardAction`.
- Preserve current route/open behavior.

**Step 3: Verify**

Run focused ChatBubble tests.

### Task 3: Backend Runtime Agenda Actions

**Files:**
- Modify: `backend/app/services/inline_cards.py`
- Test: create or extend `backend/tests/test_inline_cards.py`

**Step 1: Write failing tests**

Seed/patch runtime agenda payload so `build_cards()` returns `runtime_agenda` with:

- `route.open` to `/agenda`
- `agenda.complete` only when next action includes a valid source object.
- `disabled_reason` when completion source is missing.

**Step 2: Implement**

- Include `source` in `_build_runtime_agenda().next_action` when available.
- Add `agenda.complete` action with `requires_manual_confirm=true` and `confirmation`.
- If source missing, include disabled complete action with `disabled_reason`.

**Step 3: Verify**

Run:

```bash
DATABASE_URL='sqlite:///:memory:' TZ=Asia/Shanghai backend/.venv/bin/python -m pytest backend/tests/test_inline_cards.py
```

### Task 4: Quick Record Card Protocol

**Files:**
- Modify: `mobile/components/chat/cards/RecordCard.tsx`
- Modify: `mobile/components/chat/cards/registry.tsx`
- Test: `mobile/components/chat/cards/__tests__/registry.test.tsx`
- Optional backend: `backend/app/services/inline_cards.py`

**Step 1: Write failing tests**

Assert a `record` descriptor with `actions` renders:

- `确认记录`
- `修改`
- `忽略`

and dispatches only safe actions.

**Step 2: Implement**

- Keep `RecordCardView` as display component.
- Let registry action bar render the buttons; do not bake execution into the card.
- If backend already emits write-intent actions for tool results, consume them; otherwise leave local card read-only until backend provides IDs.

**Step 3: Verify**

Run focused registry tests.

### Task 5: Docs, Verification, Release

**Files:**
- Modify: `docs/plans/2026-06-30-interactive-chat-cards-design.md`
- Modify: `docs/plans/2026-06-30-interactive-chat-cards-implementation-plan.md`
- Create or update: `docs/dossiers/2026-06-30-interactive-chat-cards.md`

**Verify:**

```bash
pnpm --dir mobile exec jest mobile/components/chat/cards/__tests__/registry.test.tsx mobile/components/chat/__tests__/ChatBubbleStructuredSummary.test.tsx --runInBand
pnpm --dir mobile exec tsc --noEmit
DATABASE_URL='sqlite:///:memory:' TZ=Asia/Shanghai backend/.venv/bin/python -m pytest backend/tests/test_inline_cards.py
```

**Release:**

- Commit code.
- Push `main`.
- Backend deploy if backend card builder changes.
- Mobile OTA if Mobile JS changed.
