# 2026-06-30 Chat Thinking Stream Design

## 目标

让阿衡对话页在回复生成过程中展示“阿衡正在做什么”的流式进度,降低用户等待焦虑,也让工具调用型回答更透明。

## 边界

- 不展示模型原始 chain-of-thought。
- 不展示工具参数、用户隐私字段或后端技术细节。
- 只展示由现有 SSE 事件映射出的安全摘要,例如“正在理解你的问题”“读取健康数据”“已取得健康数据”。
- 最终回答正文仍只显示用户可用的健康建议、记录结果或动态 UI 卡片。

## 设计

Mobile 复用现有 `/agent/stream` SSE 事件:

- `agent_start` -> `thought: 正在理解你的问题`
- `tool_call` -> `thought: 读取{安全数据标签}`
- `tool_result success=true` -> `thought: 已取得{安全数据标签}`
- `tool_result success=false` -> `thought: {安全数据标签}暂时不可用`

`useChatEngine` 将这些摘要累积到当前 streaming assistant message 的 `thinkingSteps`。`ChatBubble` 在 assistant 正文上方渲染一个低噪音的“思考中”面板。面板只显示最近 4 条,消息状态最多保留 8 条,避免长工具链撑爆对话页。

## UI

- 位置: assistant 气泡内部、正文上方。
- 样式: 浅绿色面板 + 小圆点步骤流,贴合阿衡当前 UI。
- 流式期仍保持 plain text 渲染策略,不引入 Markdown 整树重渲。

## 验收

- 后端现有事件无需变更即可驱动 Mobile 思考摘要。
- start/tool/result 事件不会混入 assistant 正文。
- streaming 时可见“思考中”面板和步骤。
- 最终回答 Markdown 渲染行为不回退。
- 测试覆盖 SSE 解析、chat engine 状态和 ChatBubble 渲染。
