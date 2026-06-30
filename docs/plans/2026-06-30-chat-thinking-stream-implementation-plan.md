# Chat Thinking Stream Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Show safe, streaming “thinking progress” summaries in the Aheng chat page while preserving final answer streaming and dynamic UI cards.

**Architecture:** Reuse existing backend SSE events instead of adding a new backend event stream. Mobile maps `agent_start`, `tool_call`, and `tool_result` into sanitized `thought` strings, stores them on the current assistant `UIMessage.thinkingSteps`, and renders them in `ChatBubble`.

**Tech Stack:** Expo React Native, existing XMLHttpRequest SSE parser, `useChatEngine`, Jest, TypeScript.

---

### Task 1: Stream Parser Contract

**Files:**
- Modify: `mobile/services/chat.ts`
- Test: `mobile/services/__tests__/chatStream.test.ts`

**Step 1: Write failing test**

Assert that:

- `agent_start` yields a `start` event with `thought: "正在理解你的问题"`.
- `tool_call` for `health_query` yields `thought: "读取健康数据"`.
- `tool_result success=true` for `health_query` yields `thought: "已取得健康数据"`.

**Step 2: Implement**

Add `thought?: string` to `StreamEvent` and map known tool names to user-safe labels.

**Step 3: Verify**

Run:

```bash
pnpm --dir mobile exec jest mobile/services/__tests__/chatStream.test.ts --runInBand
```

### Task 2: Chat Engine State

**Files:**
- Modify: `mobile/hooks/useChatEngine.ts`
- Test: `mobile/hooks/__tests__/useChatEngine.test.ts`

**Step 1: Write failing test**

Assert that thought-bearing events append to the streaming assistant message as `thinkingSteps` and do not alter answer `content`.

**Step 2: Implement**

Add `thinkingSteps?: string[]`, initialize the streaming assistant message with the first safe step, dedupe consecutive repeated steps, and cap retained steps.

**Step 3: Verify**

Run:

```bash
pnpm --dir mobile exec jest mobile/hooks/__tests__/useChatEngine.test.ts --runInBand
```

### Task 3: Chat Bubble UI

**Files:**
- Modify: `mobile/components/chat/ChatBubble.tsx`
- Test: `mobile/components/chat/__tests__/ChatBubbleStreaming.test.tsx`

**Step 1: Write failing test**

Assert that a streaming assistant message with `thinkingSteps` renders a “思考中” panel above the plain streaming text and still avoids rich Markdown during streaming.

**Step 2: Implement**

Add a small `ThinkingStepsPanel` component using existing Reva theme colors and `StyleSheet.create`.

**Step 3: Verify**

Run:

```bash
pnpm --dir mobile exec jest mobile/components/chat/__tests__/ChatBubbleStreaming.test.tsx --runInBand
```

### Task 4: Release Gate

Run:

```bash
pnpm --dir mobile exec jest mobile/services/__tests__/chatStream.test.ts mobile/hooks/__tests__/useChatEngine.test.ts mobile/components/chat/__tests__/ChatBubbleStreaming.test.tsx --runInBand
pnpm --dir mobile exec tsc --noEmit
git diff --check
```

Then commit, push `main`, and publish Mobile OTA because this is a JS/TS UI-only change.
