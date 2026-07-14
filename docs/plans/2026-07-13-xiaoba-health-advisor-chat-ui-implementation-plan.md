# Xiaoba Health Advisor Chat UI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将小巴 Mobile 对话页收敛为健康参谋型混合对话：单一运行状态、无框普通回答、渐进披露辅助动作，并保持现有微信式语音输入区不变。

**Architecture:** 不改 `useChatEngine`、后端 SSE 和动态 UI schema，只在现有 `ChatHeader`、`ChatBubble` 与卡片呈现层调整信息层级。运行状态只由当前 assistant turn 渲染；普通回答使用无框 surface；复制、选择、分享和朗读进入长按菜单；结构化卡片保留原写入回调和回执。

**Tech Stack:** React Native、Expo、TypeScript、React Native Testing Library、Jest、现有 Reva theme tokens、production OTA。

---

## Task 1: 固化单一运行状态契约

**Files:**
- Modify: `mobile/components/chat/__tests__/ChatHeader.test.tsx`
- Modify: `mobile/components/chat/ChatHeader.tsx`

**Step 1: 写失败测试**

在 `ChatHeader.test.tsx` 增加：

```tsx
it('keeps streaming state inside the active assistant turn instead of the header', () => {
  const { queryByLabelText } = render(<ChatHeader {...baseProps} isStreaming />);
  expect(queryByLabelText('回复中')).toBeNull();
});
```

并把重复 props 提取为 `baseProps`，确保标题、模型选择、新建、历史和更多仍可访问。

**Step 2: 运行测试确认失败**

Run:

```bash
cd mobile && npm test -- --runInBand components/chat/__tests__/ChatHeader.test.tsx
```

Expected: FAIL，仍能找到 `回复中`。

**Step 3: 最小实现**

从 `ChatHeader` 删除 `streamingBadge` 的渲染和样式。保留 `isStreaming` prop 兼容调用端，但重命名解构为 `_isStreaming` 或不解构，避免扩大调用面；更新组件注释为“运行状态由当前消息负责”。

**Step 4: 运行测试确认通过**

运行 Task 1 的同一命令，Expected: PASS。

## Task 2: 把回复辅助动作收进长按菜单

**Files:**
- Modify: `mobile/components/chat/__tests__/ChatBubbleStreaming.test.tsx`
- Modify: `mobile/components/chat/__tests__/ChatBubbleStructuredSummary.test.tsx`
- Modify: `mobile/components/chat/__tests__/ChatBubbleSpeech.test.tsx`
- Modify: `mobile/components/chat/ChatBubble.tsx`

**Step 1: 写失败测试**

增加并调整以下断言：

```tsx
expect(queryByLabelText('发微信分享这条回复')).toBeNull();
expect(queryByLabelText('发小红书分享这条回复')).toBeNull();
expect(queryByLabelText('更多分享')).toBeNull();
expect(queryByLabelText('语音播报')).toBeNull();

fireEvent(getByLabelText('AI: 建议今天午后散步 10 分钟。'), 'longPress');
expect(getByLabelText('复制全文')).toBeTruthy();
expect(getByLabelText('选择这条消息')).toBeTruthy();
expect(getByLabelText('分享这条回复')).toBeTruthy();
expect(getByLabelText('语音播报')).toBeTruthy();
```

用户消息长按只显示“复制 / 选择 / 分享”，不显示朗读。分享测试先长按，再点击 `分享这条回复`；小红书精编文案保留在系统分享或后续更多菜单，不再占据常驻按钮。

**Step 2: 运行测试确认失败**

```bash
cd mobile && npm test -- --runInBand components/chat/__tests__/ChatBubbleStreaming.test.tsx components/chat/__tests__/ChatBubbleStructuredSummary.test.tsx components/chat/__tests__/ChatBubbleSpeech.test.tsx
```

Expected: FAIL，分享/朗读仍常驻，长按菜单缺少新动作。

**Step 3: 最小实现**

扩展 `renderMessageActions()`：

```tsx
const canShare = item.content.trim().length > 0 && item.completionStatus !== 'interrupted' && item.completionStatus !== 'error';
const canSpeak = !isUser && !!assistantTextForActions;
```

- 顺序固定为 `复制 -> 选择 -> 分享 -> 朗读`。
- `分享` 调用现有 `handleShare('more')`，关闭菜单后打开系统分享。
- `朗读` 调用现有 `handleSpeak`，保留播放/停止状态。
- 删除普通 assistant 回答底部 `metaRow` 内的微信、小红书、更多和朗读常驻按钮。
- 不删除 `buildXiaohongshuShareMessage` 和图片分享能力；卡片分享在 Task 4 处理。

**Step 4: 运行测试确认通过**

运行 Task 2 同一命令，Expected: PASS。

## Task 3: 普通回答改为无框内容层

**Files:**
- Modify: `mobile/components/chat/__tests__/ChatBubbleStreaming.test.tsx`
- Modify: `mobile/components/chat/ChatBubble.tsx`

**Step 1: 写失败测试**

为普通完成回复增加样式契约：

```tsx
const style = StyleSheet.flatten(getByTestId('assistant-message-surface').props.style);
expect(style.backgroundColor).toBe('transparent');
expect(style.shadowOpacity ?? 0).toBe(0);
expect(style.paddingHorizontal).toBe(0);
```

同时验证用户气泡仍为绿色，结构化卡片不受影响。

**Step 2: 运行测试确认失败**

```bash
cd mobile && npm test -- --runInBand components/chat/__tests__/ChatBubbleStreaming.test.tsx
```

Expected: FAIL，当前 `bubbleAI` 仍使用 `C.surface` 和 shadow。

**Step 3: 最小实现**

- 给 assistant 容器增加稳定 `testID="assistant-message-surface"`。
- 将 `bubbleAI` 改为透明背景、无阴影、无横向内边距，保留纵向节奏和最大宽度。
- 保留 `BrandCircle`、用户绿色气泡、图片圆角、动态卡片自己的 `CardShell`。
- selection mode 使用轻量底色和边框显示选择，不依赖旧白卡阴影。

**Step 4: 运行测试确认通过**

运行 Task 3 同一命令，Expected: PASS。

## Task 4: 卡片分享改为渐进披露

**Files:**
- Modify: `mobile/components/chat/__tests__/ChatBubbleStructuredSummary.test.tsx`
- Modify: `mobile/components/chat/ChatBubble.tsx`

**Step 1: 写失败测试**

将卡片测试改成：

```tsx
expect(queryByTestId('assistant-card-share-actions')).toBeNull();
fireEvent(getByTestId('assistant-card-interaction-surface'), 'longPress');
expect(getByLabelText('保存卡片图片')).toBeTruthy();
expect(getByLabelText('分享卡片图片')).toBeTruthy();
expect(getByLabelText('分享卡片正文')).toBeTruthy();
```

继续验证截图保存失败、图片分享失败和系统分享正文的错误反馈。

**Step 2: 运行测试确认失败**

```bash
cd mobile && npm test -- --runInBand components/chat/__tests__/ChatBubbleStructuredSummary.test.tsx
```

Expected: FAIL，当前卡片底部仍常驻四个分享按钮。

**Step 3: 最小实现**

- 用可长按但不吞内部按钮点击的 interaction surface 包住 `assistant-card-capture-frame`。
- 长按后显示卡片上下文动作：保存图片、分享图片、分享正文、取消。
- 删除 `截图可直接发微信 / 小红书` 和常驻 `assistant-card-share-actions`。
- 保留 `captureRef`、`saveChatImageToLibrary`、`shareLocalImage`、`sharePlainText` 的原实现和显式失败提示。

**Step 4: 运行测试确认通过**

运行 Task 4 同一命令，Expected: PASS。

## Task 5: 思考面板收敛为一个清晰进度源

**Files:**
- Modify: `mobile/components/chat/__tests__/ChatBubbleStreaming.test.tsx`
- Modify: `mobile/components/chat/ChatBubble.tsx`

**Step 1: 写失败测试**

覆盖：

```tsx
expect(getAllByTestId('assistant-thinking-indicator')).toHaveLength(1);
expect(getByText('2 步')).toBeTruthy();
expect(getByText('读取健康数据')).toBeTruthy();
expect(queryByTestId('assistant-status-line')).toBeNull();
```

无 `thinkingSteps` 但仍在 streaming 时也只显示同一面板，不落到第二套裸 `ActivityIndicator`。

**Step 2: 运行测试确认失败**

```bash
cd mobile && npm test -- --runInBand components/chat/__tests__/ChatBubbleStreaming.test.tsx
```

Expected: FAIL，裸 loading fallback 没有统一 test contract。

**Step 3: 最小实现**

- 删除未使用的 `StatusLine`。
- 当 streaming 且尚无正文/步骤时，也给 `ThinkingStepsPanel` 一个默认状态“正在理解你的问题…”，不渲染独立裸 spinner。
- 思考面板只保留一个 `ActivityIndicator`，标记 `testID="assistant-thinking-indicator"`。
- 完成态继续折叠为“思考完成 · N 步”；错误由上游现有错误消息显式展示，不静默停在 loading。

**Step 4: 运行测试确认通过**

运行 Task 5 同一命令，Expected: PASS。

## Task 6: 回归、视觉验收与 OTA

**Files:**
- Modify: `docs/dossiers/2026-07-13-xiaoba-health-advisor-chat-ui.md`

**Step 1: 运行 Mobile 定向测试**

```bash
cd mobile && npm test -- --runInBand \
  components/chat/__tests__/ChatHeader.test.tsx \
  components/chat/__tests__/ChatBubbleStreaming.test.tsx \
  components/chat/__tests__/ChatBubbleStructuredSummary.test.tsx \
  components/chat/__tests__/ChatBubbleSpeech.test.tsx
```

Expected: PASS。

**Step 2: 运行类型和 lint 闸**

```bash
cd mobile && npx tsc --noEmit
cd mobile && npm run lint
```

Expected: TypeScript PASS；lint 0 errors，既有 warnings 单独记录，不冒充修复。

**Step 3: 验证输入区未漂移**

```bash
cd mobile && npm test -- --runInBand components/chat/__tests__/ChatInputBar.test.tsx app/'(tabs)'/__tests__/chat.test.tsx
```

Expected: PASS，微信式文字/语音输入、长按和布局测试不变。

**Step 4: iOS Simulator 视觉验收**

- 启动当前 Mobile App。
- 验证回答完成、思考中、含动态卡片三个状态。
- 截图检查：无重复 spinner、顶部不增高、普通回答无大白卡、分享动作不常驻、输入区视觉不变、无重叠和遮挡。

**Step 5: 更新 Dossier 并提交**

只暂存本任务文件，记录测试、截图、commit 与 Gate 裁决；不得暂存无关 PRD 草稿。

**Step 6: 发布 production OTA**

```bash
scripts/mobile-ota.sh production "refine Xiaoba health advisor chat UI"
```

Expected: OTA 成功，记录 update id、runtime version、commit 和回滚点。

**Step 7: G6 真机确认**

用户在安装版本冷启动后验证：顶部、思考状态、长按菜单、普通回答和动态卡片；未确认前 Dossier 保持 `shipping`，不标 `shipped`。
