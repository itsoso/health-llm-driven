# 小巴连续输入 Interaction Sessions Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 让 Mobile 和 Mac 上的小巴在思考、流式回复、ASR 转写、动态 UI 生成和 action 执行期间，键盘与语音输入仍可继续使用；用户可以连续输入、连续说话、连续追加任务，而不是被上一轮回复锁住。

**Architecture:** 把当前“全局单线程对话锁”拆成 per-turn `InteractionSession` / `TurnRun`。Composer 只关心本地输入资源是否可用；Agent 回复、ASR、动态卡片和执行动作各自挂到独立 session。第一阶段采用“前端连续接收输入 + 同一 conversation 内 FIFO 派发”的保守方案，避免同一会话多条后端 stream 并发写入造成顺序和回执错乱；后续再按只读查询 / 写入动作分级放开真正并发。

**Tech Stack:** Expo React Native 0.83, TypeScript, Jest, Testing Library, SwiftUI, Swift Concurrency, XCTest, FastAPI `/agent/stream`, existing `client_turn_id`, `/chat/transcribe`, WriteIntent / deterministic action gates.

---

## 0. Product Decision

当前产品名是 **小巴**。本规划、实现和测试中用户可见文案统一使用“小巴”，不再引入旧称。

本需求不是把小巴改成通用多窗口聊天工具，而是补齐 Agent Native 体验里的基础交互能力：

- 用户说完一条后，不必等小巴回复完才能继续说下一条。
- 用户打字时，上一轮小巴可以继续思考和流式输出。
- 语音 ASR、Agent 回复、动态 UI patch、action 执行各自有状态，不互相锁死输入区。
- 写健康记录、补剂/用药确认、计划变更等高风险写入仍然串行、幂等、可审计。

## 1. Current Blocking Points

### Mobile

**Files:**
- `mobile/components/chat/ChatInputBar.tsx`
- `mobile/components/chat/composerState.ts`
- `mobile/hooks/useChatEngine.ts`
- `mobile/hooks/useRealtimeDictation.ts`
- `mobile/hooks/useVoiceRecording.ts`

Observed locks:

- `useChatEngine.sendMessage` 在 `isStreaming` 为 true 时直接 `return false`。
- `ChatInputBar` 的 `canSend` 依赖 `!isStreaming`，导致正在回复时键盘输入不能发送。
- `ChatInputBar.handleRealtimeMicPress` 在 `isStreaming` 时直接 return，导致小巴回复期间不能继续开麦。
- `composerState.submit` 会把 `dictationEnabled` 置 false，提交动作和麦克风可用性耦合过强。
- 当前只有一个 `abortRef` / `streamingRef` / `activeTurn`，天然假设一次只有一个运行中的 turn。

### Mac

**Files:**
- `apps/mac/Sources/HealthAgentMacCore/AgentChatViewModel.swift`
- `apps/mac/Sources/HealthAgentMac/FeatureViews.swift`
- `apps/mac/Tests/HealthAgentMacCoreTests/AgentStreamClientTests.swift`

Observed locks:

- `AgentChatViewModel.canSubmit(_:)` 要求 `!isStreaming`。
- `AgentChatViewModel.submit(_:)` 会先 `streamingTask?.cancel()`，新提交会取消上一轮。
- `AgentChatViewModel` 只有一个 `streamingTask` 和一个 `isStreaming`。
- `FeatureViews.composerSendButton` 在 streaming 时把发送按钮替换成 Stop，用户不能在同一个 composer 继续发送。

### Backend Contract

Backend 已有 `client_turn_id` 和按 turn 查找/恢复的能力。第一阶段不要求后端支持同一 conversation 多 stream 并行落库，只要求前端能连续接收输入并排队派发；后端写入安全继续走现有确认、幂等和 WriteIntent 边界。

## 2. Recommended Approach

### Option A: True Parallel Streams Per Conversation

同一 conversation 同时开多个 `/agent/stream`。

Pros:
- 体感最快。
- 真正意义的多线程 Agent。

Cons:
- 同一会话消息顺序、conversation title、dynamic card 插入位置、write receipt、history reload 都会复杂化。
- 写入动作如果并发完成，可能出现同一餐 / 同一补剂 / 同一 agenda item 的重复确认风险。

Decision: 不作为第一阶段。

### Option B: Continuous Composer + Per-Conversation FIFO Queue

用户可以持续输入和开麦；每次输入立刻生成一个 `InteractionSession`，展示为“已提交 / 排队中 / 小巴处理中”。同一 conversation 后端 stream 仍按 FIFO 一条条执行。

Pros:
- 立刻解决“键盘和语音被禁用”的用户体验问题。
- 复用现有 `/agent/stream`、`client_turn_id`、history recovery 和 write gate。
- 不引入后端并发写入风险。
- 后续可以在同一模型上逐步开放只读 turn 并行。

Cons:
- 第二条消息可能显示“排队中”，不是立即流式返回。
- 用户如果期望“打断上一轮”，需要明确 Stop 当前 turn 或“新消息是否自动带上上一条未完成上下文”的策略。

Decision: 第一阶段采用。

### Option C: One Conversation Per Task

每条新输入都开新 conversation，实现最简单。

Pros:
- 避免同一 conversation 并发顺序问题。

Cons:
- 破坏小巴连续上下文。
- 用户会看到历史碎片化。
- 与 Health OS “同一行动链路继续追问/修正”的目标冲突。

Decision: 不采用。

## 3. Target Interaction Model

### 3.1 Composer Resource Rules

键盘:

- 永远可编辑，除非当前本地 TextInput / TextEditor 正在销毁或页面不可见。
- 发送按钮只由“草稿是否为空 / 本地提交中瞬间防抖”决定，不由小巴是否在回复决定。

语音:

- 小巴回复中仍可开始语音输入。
- 同一设备麦克风一次只能被一个本地录音 session 占用：hold-to-talk、实时听写、未来 Mac 语音输入互斥。
- ASR 上传/转写阶段不占用麦克风，不能继续禁用下一次录音。
- ASR 结果回填为可编辑 voice draft；用户可以改，也可以直接作为新 `InteractionSession` 发送。

Agent stream:

- 一个 turn 的 Stop 只停止该 turn，不关闭 composer。
- 正在执行的 turn、排队 turn、ASR 任务、action 执行分别显示状态。

Action execution:

- 可并发展示，但同一 resource 的写入必须串行。
- 所有写入使用幂等键：`client_turn_id + action_id + resource_key`。
- Medication / supplement / clinical-adjacent writes 保持 manual_confirm。

### 3.2 UI Behavior

Mobile:

- 输入框、键盘和麦克风按钮不因 `isStreaming` 变 disabled。
- 如果小巴正在回复，发送新消息后消息流中立即出现用户消息和 “排队中” 占位。
- 顶部或消息流轻量显示：`小巴处理中 · 1 个回复中 / 1 个排队`。
- 当前 active turn 的 assistant 气泡内显示 Stop；composer 右侧仍保留 Send。

Mac:

- TextEditor 始终可编辑。
- 流式时 composer 右侧仍显示 Send；Stop 迁移到状态条或当前 assistant 消息工具区。
- `Command-Return` 在 streaming 时仍发送当前 draft，生成 queued turn。
- 如果未来加入 Mac 语音，入口必须复用同一 `InteractionSession` 和 `/chat/transcribe` 云端 ASR 合同。

## 4. Data Model

### Mobile Type Shape

Create or adapt:

```ts
export type InteractionSessionStatus =
  | 'drafting'
  | 'asr_recording'
  | 'asr_transcribing'
  | 'queued'
  | 'streaming'
  | 'action_pending'
  | 'completed'
  | 'failed'
  | 'cancelled';

export interface InteractionSession {
  id: string;
  clientTurnId: string;
  conversationId?: number;
  userMessageId: string;
  assistantMessageId?: string;
  channel: 'typed' | 'voice' | 'siri';
  text: string;
  imageUris?: string[];
  extraContext?: string;
  status: InteractionSessionStatus;
  queuedAt: number;
  startedAt?: number;
  completedAt?: number;
  errorCode?: string;
}
```

Keep `client_turn_id` as the server-facing id. `InteractionSession.id` may equal `client_turn_id` unless a local ASR task exists before send.

### Mac Type Shape

Create:

```swift
public enum AgentTurnRunStatus: Equatable, Sendable {
    case queued
    case streaming
    case completed
    case failed(String)
    case cancelled
}

public struct AgentTurnRun: Identifiable, Equatable, Sendable {
    public let id: UUID
    public let clientTurnID: String
    public let userMessageID: UUID
    public let assistantMessageID: UUID
    public var status: AgentTurnRunStatus
    public var queuedAt: Date
    public var startedAt: Date?
}
```

Mac can keep `isStreaming` as a computed compatibility property:

```swift
public var isStreaming: Bool {
    turnRuns.contains { $0.status == .streaming }
}
```

But `canSubmit(_:)` must not depend on it.

## 5. Implementation Tasks

### Task 1: Mobile Failing Tests For Continuous Input

**Files:**
- Modify: `mobile/hooks/__tests__/useChatEngine.test.ts`
- Modify: `mobile/components/chat/__tests__/ChatInputBar.test.tsx`
- Modify: `mobile/components/chat/__tests__/composerState.test.ts`

**Step 1: Add failing tests**

Add coverage:

- `useChatEngine.sendMessage` accepts a second message while the first turn is streaming.
- second message appends a user bubble immediately with queued status.
- `ChatInputBar` keeps the text input editable and Send available while `isStreaming=true`.
- realtime mic press calls `startDictation()` even while `isStreaming=true`.
- `composerState.submit` does not permanently disable dictation after an accepted send.

**Step 2: Verify RED**

Run:

```bash
cd mobile
npm test -- --runInBand hooks/__tests__/useChatEngine.test.ts components/chat/__tests__/ChatInputBar.test.tsx components/chat/__tests__/composerState.test.ts
```

Expected:

- useChatEngine test fails because `isStreaming` rejects the second send.
- ChatInputBar test fails because mic and Send are blocked by `isStreaming`.

### Task 2: Mobile Turn Queue In `useChatEngine`

**Files:**
- Modify: `mobile/hooks/useChatEngine.ts`
- Modify: `mobile/services/chat.ts` only if request metadata needs a new field.

**Step 1: Add local queue state**

Introduce:

- `queuedTurnsRef`
- `runningTurnRef`
- `turnAbortControllersRef`
- `pumpTurnQueue()`

`sendMessage()` should:

1. validate non-empty input;
2. allocate `clientTurnId`;
3. append user message immediately;
4. append assistant placeholder with status `queued` if another turn is active;
5. enqueue turn;
6. return accepted=true without waiting for current stream.

**Step 2: Preserve current recovery semantics**

Keep existing `client_turn_id` recovery logic. Only one active stream per conversation in Phase 1, so `conversationId` updates remain deterministic.

**Step 3: Move stream loop into `runTurn(turn)`**

`runTurn` owns:

- its own `AbortController`;
- assistant message id;
- thinking steps;
- dynamic cards insertion filtered by that `clientTurnId`;
- terminal event emission.

**Step 4: Update global selectors**

Expose:

```ts
isStreaming: boolean;      // compatibility: any turn streaming
queuedCount: number;
runningTurnId?: string;
cancelTurn(turnId: string): void;
cancelActiveTurn(): void;
```

Do not use `isStreaming` to disable composer.

**Step 5: Verify GREEN**

Run the focused tests from Task 1.

### Task 3: Mobile Composer Unlock

**Files:**
- Modify: `mobile/components/chat/ChatInputBar.tsx`
- Modify: `mobile/components/chat/composerState.ts`
- Modify: `mobile/components/chat/__tests__/ChatInputBar.test.tsx`
- Modify: `mobile/components/chat/__tests__/composerState.test.ts`

**Step 1: Decouple sendability from Agent streaming**

Change `canSend` to depend on:

- input/image presence;
- local composer phase not being `hold_starting`, `hold_recording`, `hold_transcribing`, or a brief submit debounce;
- not on Agent `isStreaming`.

**Step 2: Allow mic during Agent streaming**

Remove `if (isStreaming) return` from `handleRealtimeMicPress`.

Keep these guards:

- cannot start realtime dictation while hold-to-talk owns mic;
- cannot start hold-to-talk while realtime dictation owns mic;
- backgrounding cancels active mic session.

**Step 3: Split Stop from Send**

Composer Send remains Send. Active turn Stop moves to:

- current assistant message toolbar, or
- a small status pill above the composer.

**Step 4: Verify**

Run:

```bash
cd mobile
npm test -- --runInBand components/chat/__tests__/ChatInputBar.test.tsx hooks/__tests__/useRealtimeDictation.test.ts hooks/__tests__/useVoiceRecording.test.ts
npx tsc --noEmit
```

### Task 4: Mobile Status Presentation

**Files:**
- Modify: `mobile/app/(tabs)/chat.tsx`
- Modify: `mobile/components/chat/ChatInputBar.tsx`
- Create or modify: `mobile/components/chat/TurnQueueStatus.tsx`
- Test: `mobile/components/chat/__tests__/TurnQueueStatus.test.tsx`

**Step 1: Write failing UI tests**

Assert:

- one running turn shows `小巴处理中`;
- queued turns show count;
- composer remains rendered and enabled;
- cancelling active turn does not discard queued drafts.

**Step 2: Implement small status strip**

Keep it compact. No full-width card. This is operational chrome, not content.

**Step 3: Verify**

Run:

```bash
cd mobile
npm test -- --runInBand components/chat/__tests__/TurnQueueStatus.test.tsx
```

### Task 5: Mac Failing Tests For Continuous Keyboard Input

**Files:**
- Modify: `apps/mac/Tests/HealthAgentMacCoreTests/AgentStreamClientTests.swift`
- Modify or create: `apps/mac/Tests/HealthAgentMacTests/AgentChatViewTests.swift` if UI-level coverage exists.

**Step 1: Add failing model tests**

Assert:

- `AgentChatViewModel.canSubmit("下一条")` is true while one stream is active.
- `submit("第二条")` does not cancel the first stream.
- two submitted prompts append two user messages immediately.
- second assistant placeholder is queued until first stream completes.

**Step 2: Verify RED**

Run:

```bash
cd apps/mac
swift test --filter AgentStreamClientTests
```

Expected: fail because current `canSubmit` and `submit` are globally streaming-locked.

### Task 6: Mac Turn Queue In `AgentChatViewModel`

**Files:**
- Modify: `apps/mac/Sources/HealthAgentMacCore/AgentChatViewModel.swift`
- Test: `apps/mac/Tests/HealthAgentMacCoreTests/AgentStreamClientTests.swift`

**Step 1: Introduce run queue**

Replace single `streamingTask` with:

```swift
@ObservationIgnored private var turnTasks: [UUID: Task<Void, Never>] = [:]
private var turnRuns: [AgentTurnRun] = []
private var pendingTurnIDs: [UUID] = []
private var activeTurnID: UUID?
```

**Step 2: Change `canSubmit`**

```swift
public func canSubmit(_ text: String) -> Bool {
    !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
}
```

**Step 3: Change `submit`**

Do not cancel existing task. Enqueue a turn and call `pumpTurnQueue()`.

**Step 4: Extract `runTurn`**

Move the existing `send(_:)` stream body into a per-turn function that receives:

- prompt;
- assistant message id;
- turn id;
- optional context snapshot;
- attachment snapshot.

Snapshot attachments/context at submission time so later typing or file changes do not mutate a queued turn.

**Step 5: Verify GREEN**

Run the focused Swift tests.

### Task 7: Mac Composer UI Unlock

**Files:**
- Modify: `apps/mac/Sources/HealthAgentMac/FeatureViews.swift`
- Test: `apps/mac/Tests/HealthAgentMacTests/*` if snapshot/UI tests exist.

**Step 1: Keep send button visible during streaming**

Composer Send should always reflect `viewModel.canSubmit(draft)`.

**Step 2: Move Stop**

Show Stop as:

- a compact active-run chip in the header, or
- an inline control on the streaming assistant message.

Do not replace Send with Stop.

**Step 3: Keyboard shortcut**

`Command-Return` should submit even while another turn is streaming.

**Step 4: Verify**

Run:

```bash
cd apps/mac
swift test
```

### Task 8: Backend Safety Review

**Files:**
- Inspect: `backend/app/services/agent_executor.py`
- Inspect: `backend/app/services/agent_turn_service.py` or equivalent turn persistence service.
- Modify only if needed.

**Step 1: Confirm existing idempotency**

Verify `client_turn_id` prevents duplicate user/assistant messages for retries.

**Step 2: Confirm write safety**

For dynamic actions and write receipts, confirm duplicate execution is keyed by operation/resource id, not by current UI streaming state.

**Step 3: Add backend tests only if Phase 1 uncovers gaps**

If the client remains FIFO per conversation, backend changes should be minimal or unnecessary.

## 6. Rollout Strategy

### Slice 1: Mobile Text Continuity

Allow keyboard typing and sending while small bar is replying. Queue second turn locally.

Acceptance:

- User can type and send during streaming.
- First response continues.
- Second turn shows queued and runs after first completes.

### Slice 2: Mobile Voice Continuity

Allow realtime mic and hold-to-talk during Agent streaming.

Acceptance:

- User can tap mic while小巴 is replying.
- ASR uses cloud path and returns voice draft.
- Sending voice draft queues another turn.
- Mic itself remains single-owner.

### Slice 3: Mac Keyboard Continuity

Allow Mac TextEditor and `Command-Return` while streaming.

Acceptance:

- User can type and submit during streaming.
- Existing stream is not cancelled.
- Stop controls active turn only.

### Slice 4: Shared Turn Status Polish

Unify status copy and telemetry:

- `queued`
- `streaming`
- `completed`
- `failed`
- `cancelled`

Acceptance:

- Mobile and Mac both show concise queue/running count.
- No user-facing copy says the input is disabled because小巴 is thinking.

## 7. Telemetry

Add or reuse client events:

- `chat_turn_queued`
- `chat_turn_stream_started`
- `chat_turn_terminal`
- `voice_asr_terminal`
- `composer_input_while_streaming`

Useful dimensions:

- surface: `mobile` / `mac`
- channel: `typed` / `voice`
- queue_depth_at_submit
- active_turn_duration_bucket
- accepted: boolean
- rejection_reason, if any

Do not log raw transcript or health content in telemetry.

## 8. Verification Matrix

### Automated

Mobile:

```bash
cd mobile
npm test -- --runInBand hooks/__tests__/useChatEngine.test.ts components/chat/__tests__/ChatInputBar.test.tsx components/chat/__tests__/composerState.test.ts hooks/__tests__/useRealtimeDictation.test.ts hooks/__tests__/useVoiceRecording.test.ts
npx tsc --noEmit
npm run lint
```

Mac:

```bash
cd apps/mac
swift test
```

Backend, only if touched:

```bash
cd backend
pytest tests/path/to/agent_turn_tests.py -q
```

### Manual

Mobile:

1. Ask小巴 a long question.
2. While the answer streams, type another question and send.
3. While the answer streams, tap mic, speak, stop, confirm the text is inserted.
4. Confirm no keyboard collapse or disabled mic state persists after ASR.
5. Stop the active turn; confirm queued turn remains.

Mac:

1. Ask小巴 a long question.
2. While the answer streams, keep typing in the composer.
3. Press `Command-Return`; confirm the first stream is not cancelled.
4. Confirm second turn appears queued and runs next.
5. Press Stop; confirm it cancels only the active turn.

## 9. Non-Goals

- Do not implement true same-conversation parallel backend execution in Phase 1.
- Do not bypass safety gates or write confirmations.
- Do not make action execution parallel for the same health resource.
- Do not rename小巴.
- Do not reintroduce fixed dashboard pages to solve queue/status UI.

## 10. Open Questions For Implementation

1. Should a new queued turn include unfinished previous assistant content as context, or only committed conversation history? Recommended Phase 1: only committed history plus visible user text; queued turn runs after previous completion, so server history will include the completed answer by execution time.
2. Should user sending a new turn during streaming default to “continue after current” or “interrupt current”? Recommended Phase 1: continue after current; Stop remains explicit.
3. Should readonly questions eventually run in parallel while write-capable turns stay FIFO? Recommended Phase 2: yes, after backend can classify readonly/write before stream execution.

## 11. Definition Of Done

- Mobile keyboard and voice input are usable while小巴 is streaming.
- Mac keyboard input is usable while小巴 is streaming.
- Existing active response is not cancelled by submitting another message.
- Queued turns are visible and cancellable.
- Stop is per-turn, not composer-global.
- ASR and Agent stream can overlap; microphone capture itself stays single-owner.
- Health writes remain deterministic, confirmed, and idempotent.
- All new user-facing copy says小巴.
