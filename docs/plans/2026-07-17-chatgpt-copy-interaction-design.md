# ChatGPT-Style Message Copy Interaction Design

**Date:** 2026-07-17

## Goal

让 Mobile、Web 和 Mac Agent 回复的复制入口遵循同一套 ChatGPT 式交互：复制属于消息操作栏，成功状态原位反馈，不弹出会打断阅读的提示，也不改变对话滚动位置。

## Design

### Mobile

- 完成且有内容的 assistant 回复，在回复底部保留紧凑操作栏中的复制图标。
- 复制入口只显示图标，不显示“复制”文字；使用 `copy-outline`，复制成功后短暂切换为 `checkmark`。
- 复制状态由消息气泡本地维护，约 1.5 秒后恢复，状态切换不触发导航或列表滚动。
- 长按菜单继续保留“复制全文”文字入口，作为触控设备上的备用路径。
- 失败时恢复复制图标并显示现有轻量 toast，不能清空消息内容。

### Web

- 完成的 assistant 回复在消息级操作栏中显示复制按钮，默认隐藏，消息行 hover 或键盘聚焦时出现。
- 点击后同一个按钮切换为勾选图标和“已复制”辅助标签，约 1.5 秒后恢复。
- 使用 `navigator.clipboard.writeText`；不可用或失败时不改变成功状态，并提供可访问的失败反馈。

### Mac

- 沿用 WebView 内的消息操作栏和现有 `copy` message handler，由原生层写入 `NSPasteboard`。
- 复制按钮的成功态在 WebView 内完成，Swift bridge 只负责传递 message ID，不重复弹提示。
- 消息更新和复制状态解耦，流式消息结束后的增量同步不得清除已显示的短暂成功态，普通 setMessages 重建时允许自然恢复。

## Shared interaction contract

1. 复制只针对 assistant 完成消息展示；流式中不显示。
2. 复制文本使用消息原文，不使用截断后的展示摘要。
3. 成功反馈必须与原复制按钮同位，且是可访问的 `已复制` 状态。
4. 失败不得伪装成成功，也不能让消息行跳到顶部。
5. 三端按钮均保持最小视觉权重，不新增独立卡片或永久 toast。

## Implementation boundaries

- Mobile 修改 `ChatBubble` 的完成态复制操作栏和对应测试。
- Web 修改 `ChatView` 的消息级复制按钮，抽出短暂状态处理并增加组件测试。
- Mac 修改 `Resources/chat-transcript.html` 的复制按钮渲染与状态切换，并在 `ChatTranscriptHTML` 测试中锁定 envelope/复制契约；Swift bridge API 不变。
- 不改变消息存储、复制内容格式、分享链路或长按多选逻辑。

## Verification

- Mobile：ChatBubble streaming/structured tests，类型检查。
- Web：ChatView message action tests，TypeScript/lint。
- Mac：ChatTranscriptHTMLTests，以及 macOS Swift package/app build 能力可用时执行构建。
- 全部修改完成后运行 `git diff --check`，并确认未触碰无关工作区改动。
