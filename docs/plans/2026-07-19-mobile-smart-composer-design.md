# Mobile Smart Composer Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 让 Mobile 聊天输入框在点击后进入类似阿福/DeepSeek 的智能输入态，同时保留文字输入、阿里云实时 ASR 和可编辑草稿。

**Architecture:** 保留现有 `ChatInputBar` 与 `useRealtimeDictation` 的云端 ASR 链路，不新增原生语音识别或新的后端协议。输入框点击只负责聚焦并展开多行输入态；麦克风按钮是明确的实时 ASR 入口，识别结果回填当前草稿，发送仍复用现有 `onSend`。

**Tech Stack:** React Native, Expo, TypeScript, Jest, React Native Testing Library, Reanimated。

---

## 交互设计

1. 默认态保持当前紧凑的“按住说话”入口。
2. 点击“切换到键盘输入”或输入区域后，输入框进入 `text` 模式并自动聚焦键盘。
3. 文本模式的输入容器使用更明确的展开态：支持多行、保留已输入文字、右侧突出显示麦克风按钮。
4. 点击麦克风后使用现有阿里云实时 ASR；显示“正在听”和动态波形，点击同一按钮停止并将最终文字保留在输入框。
5. 已有文字时，语音结果追加到文字末尾；识别结果仍可编辑，编辑会停止实时识别并以文字渠道发送。
6. 有文字或图片时显示发送按钮；无内容时显示附件按钮。键盘回车继续发送，不改变现有行为。
7. 不在点击输入框时自动开始录音，避免误触收音和权限惊扰；语音必须由用户点击麦克风明确触发。

## Implementation Tasks

### Task 1: Lock the composer interaction contract

**Files:**
- Modify: `mobile/components/chat/__tests__/ChatInputBar.test.tsx`
- Test: `mobile/components/chat/__tests__/composerState.test.ts`

**Steps:**
1. Add failing tests for click-to-focus/expanded text mode, microphone visibility, transcript insertion, and existing-text append.
2. Run the focused tests and verify they fail for the missing expanded interaction.
3. Keep the tests scoped to user-visible behavior and accessibility labels.

### Task 2: Implement expanded smart text mode

**Files:**
- Modify: `mobile/components/chat/ChatInputBar.tsx`
- Modify: `mobile/components/chat/composerState.ts` only if a state transition is required.

**Steps:**
1. Add a small `textInputExpanded` presentation state driven by focus/content without creating a second composer mode.
2. Make the text input container expand on focus and maintain the current cloud microphone action.
3. Keep `onPressIn`/`onPressOut` long-press dictation behavior race-safe and avoid starting dictation from ordinary tap.
4. Add a visible “正在听”/wave state using the existing `realtimeActive` state and preserve editable transcript behavior.
5. Keep keyboard submit, attachment actions, photo staging, and draft persistence unchanged.

### Task 3: Verify and release

**Files:**
- Modify: `docs/specs/active/2026-07-06-mobile-wechat-voice-composer.md` if the final interaction contract needs a wording update.

**Steps:**
1. Run focused `ChatInputBar` and composer state tests.
2. Run Mobile TypeScript and lint checks for affected files.
3. Run the broader Mobile test suite and record any existing open-handle behavior separately from assertion results.
4. Commit only the design, implementation, and tests for this feature.
5. Publish Mobile JS OTA on the production channel; no native rebuild is required.

## Acceptance Criteria

- 点击键盘输入入口后，键盘出现，输入容器进入展开态且不会自动录音。
- 输入框右侧麦克风入口清晰可见，点击后走阿里云实时 ASR。
- ASR 中间结果可见，停止后最终文字回填并可修改。
- 原有文字与语音结果能正确追加，发送渠道和草稿恢复行为不回归。
- 长按输入框、按住说话、拍照记餐、附件菜单和回车发送保持可用。

