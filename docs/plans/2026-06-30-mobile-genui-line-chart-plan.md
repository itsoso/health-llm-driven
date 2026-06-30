# 2026-06-30 Mobile GenUI Metric Line Chart 承接计划

## 目标

把后端已经上线的 `reva-ui` 图表能力接入 Mobile 阿衡对话页，并从“固定 `line_chart`”升级为“通用指标趋势组件”。用户在对话里说“绘制最近半年的心率/HRV/睡眠评分/步数曲线”时，Mobile 必须声明 `genui-v1, genui-components-v1` 能力，后端基于真实数据生成 `metric_line_chart`，前端按动态 UI registry 原生渲染，而不是显示 fenced JSON 或让 LLM 吐 ASCII 图。

## 范围

- Mobile `streamChat` 请求增加 `X-Reva-Client-Caps: genui-v1, genui-components-v1`。
- 后端保留旧 `line_chart`，新客户端协商后返回 `component=metric_line_chart`、`schema=reva.metric_line_chart.v1`、`metric`、`range`。
- 新增/扩展 `reva-ui` fenced block parser，只接受 `v=1` 且 component 在白名单里的组件。
- ChatBubble 在 assistant 文本内联渲染图表卡片，并从可见 markdown、分享、TTS、保存记忆等文本路径剥离 raw JSON。
- Chat 卡片注册表新增 `metric_line_chart` renderer；保留既有 `line_chart` 与 `metric_chart` 旧协议。
- 后端确定性指标识别扩展到: `hrv`、`resting_hr`(含自然说法“心率”)、`stress`、`sleep`、`sleep_score`、`steps`、`body_battery`、`weight`。

## 不做

- 不让 LLM 填图表数值。
- 不新增医疗诊断、处方或阈值判断。
- 不扩展到 table/timeline/comparison 组件目录。
- 暂不把血压塞进单指标折线；血压需要 SBP/DBP 双序列与更强安全边界。

## 验收

- `streamChat` 声明 `genui-v1, genui-components-v1`。
- `reva-ui` `metric_line_chart` block 被抽为 `metric_line_chart` card descriptor。
- ChatBubble 不显示 raw ````reva-ui` 或 JSON。
- Mobile 原生卡片显示 title、series legend、data note 和健康管理边界。
- 后端 `/agent/stream` 收到新 cap 后不调用 LLM，直接返回真实数据 `metric_line_chart`。

## 测试

- `mobile/services/__tests__/chatStream.test.ts`
- `mobile/utils/__tests__/revaUiBlocks.test.ts`
- `mobile/components/chat/__tests__/ChatBubbleRevaUi.test.tsx`
- `mobile/components/chat/cards/__tests__/registry.test.tsx`
- `mobile/components/chat/__tests__/ChatBubbleStructuredSummary.test.tsx`
- `mobile` TypeScript
