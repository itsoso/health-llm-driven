# 2026-06-30 Mobile GenUI Line Chart 承接计划

## 目标

把后端已经上线的 `reva-ui` `line_chart` 确定性图表块接入 Mobile 阿衡对话页。用户在对话里说“绘制最近半年的 HRV 曲线”时，Mobile 必须声明 `genui-v1` 能力，并把后端基于真实数据生成的图表块渲染为原生卡片，而不是显示 fenced JSON。

## 范围

- Mobile `streamChat` 请求增加 `X-Reva-Client-Caps: genui-v1`。
- 新增 `reva-ui` fenced block parser，只接受 `v=1` 且 `component=line_chart` 的白名单组件。
- ChatBubble 在 assistant 文本内联渲染 `line_chart` 卡片，并从可见 markdown、分享、TTS、保存记忆等文本路径剥离 raw JSON。
- Chat 卡片注册表新增 `line_chart` renderer；保留既有 `metric_chart` 旧协议。

## 不做

- 不让 LLM 填图表数值。
- 不新增医疗诊断、处方或阈值判断。
- 不扩展到 table/timeline/comparison 组件目录。
- 不改后端 GenUI 数据构建器。

## 验收

- `streamChat` 声明 `genui-v1`。
- `reva-ui` `line_chart` block 被抽为 `line_chart` card descriptor。
- ChatBubble 不显示 raw ````reva-ui` 或 JSON。
- Mobile 原生卡片显示 title、series legend、data note 和健康管理边界。

## 测试

- `mobile/services/__tests__/chatStream.test.ts`
- `mobile/utils/__tests__/revaUiBlocks.test.ts`
- `mobile/components/chat/__tests__/ChatBubbleRevaUi.test.tsx`
- `mobile/components/chat/cards/__tests__/registry.test.tsx`
- `mobile/components/chat/__tests__/ChatBubbleStructuredSummary.test.tsx`
- `mobile` TypeScript

