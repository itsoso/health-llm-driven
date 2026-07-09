# Chat Write Closure Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make mobile chat write actions feel closed-loop by showing a durable local confirmation message and making the next-turn context source visible.

**Architecture:** Keep the behavior client-side in the mobile chat screen. `ChatBubble` already emits completed card actions; `mobile/app/(tabs)/chat.tsx` will convert those events into a local-only assistant status message and a structured `extraContext` payload for the next user send.

**Tech Stack:** React Native, Expo Router, Jest, existing `useChatEngine` message state.

---

### Task 1: Status Message Builder

**Files:**
- Modify: `mobile/app/(tabs)/chat.tsx`
- Test: `mobile/app/(tabs)/__tests__/chat.test.tsx`

**Step 1: Write the failing test**

Add a test that simulates `onCardActionCompleted` from the mocked `ChatBubble` with a successful `diet_record.create` result and expects a local assistant message containing `已保存午餐` and `620 kcal`.

**Step 2: Run test to verify it fails**

Run:

```bash
cd mobile
./node_modules/.bin/jest --runInBand app/(tabs)/__tests__/chat.test.tsx -t "shows a local saved diet confirmation"
```

Expected: FAIL because the page only sets context banner state today and does not append a message.

**Step 3: Write minimal implementation**

Add a small builder in `chat.tsx`:

```ts
function buildCardActionStatusMessage(event): UIMessage | null
```

For diet records, produce a local-only assistant message like:

```text
已保存午餐 · 620 kcal
可在饮食页修正；下条消息会基于这条记录和今日饮食记录回答。
```

Append it in `handleCardActionCompleted`.

**Step 4: Run test to verify it passes**

Run the same Jest command and expect PASS.

### Task 2: Context Transparency

**Files:**
- Modify: `mobile/app/(tabs)/chat.tsx`
- Test: `mobile/app/(tabs)/__tests__/chat.test.tsx`

**Step 1: Write the failing test**

Add a test that simulates the same diet card completion and expects the context banner to show `刚保存午餐 + 今日饮食记录`.

**Step 2: Run test to verify it fails**

Run:

```bash
cd mobile
./node_modules/.bin/jest --runInBand app/(tabs)/__tests__/chat.test.tsx -t "shows saved diet context source"
```

Expected: FAIL because the current badge is only `刚保存午餐`.

**Step 3: Write minimal implementation**

Update `buildCardActionExtraContext` to use a more explicit badge and payload:

```json
{
  "source": "chat_card_action",
  "event": "diet_record_saved",
  "sources": ["刚保存的午餐记录", "今日饮食数据库"],
  "record": {}
}
```

**Step 4: Run test to verify it passes**

Run the same Jest command and expect PASS.

### Task 3: Verification And Release

**Files:**
- Modified files from Tasks 1-2.

**Step 1: Run focused tests**

```bash
cd mobile
./node_modules/.bin/jest --runInBand app/(tabs)/__tests__/chat.test.tsx components/chat/__tests__/ChatBubbleStructuredSummary.test.tsx
```

**Step 2: Run typecheck**

```bash
cd mobile
./node_modules/.bin/tsc --noEmit
```

**Step 3: Commit, push, OTA**

Commit the mobile-only change, push to `main`, then run:

```bash
./scripts/mobile-ota.sh production "improve chat write closure"
```
