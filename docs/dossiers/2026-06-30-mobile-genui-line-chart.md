# Dossier: Mobile GenUI Line Chart

| 字段 | 值 |
|---|---|
| slug | `mobile-genui-line-chart` |
| 创建日期 | 2026-06-30 |
| 当前阶段 | S5 实现 |
| 状态 | implemented-local-gate |
| 负责 | Codex |
| 反馈环 | TDD / mobile Jest / backend contract test / OTA |

## S0 Intake

用户要求继续按照规划执行；当前主干刚合入后端 `reva-ui` 图表短路能力，但 Mobile 仍未声明 `genui-v1` 能力，也不能把 assistant 文本里的 ````reva-ui` 图表块渲染成原生 UI。

## S1 Discovery

- `backend/app/services/genui/chart_builder.py` 已确定性生成 `component=line_chart`，数据来自 Garmin/Weight DB，不走 LLM。
- `backend/app/api/agent.py` 仅在客户端声明 `X-Reva-Client-Caps: genui-v1` 后返回 ````reva-ui` block。
- `mobile/services/chat.ts` 现状未声明该 cap。
- `mobile/components/chat/cards/MetricChartCard.tsx` 已有旧 `metric_chart` 卡，但不支持新 `line_chart` block。
- `mobile/components/chat/ChatBubble.tsx` 会直接显示 fenced block raw JSON。

## G1 准入

- 对象: `ChatMessage`、`DynamicUICard`、`HealthSignalChart`。
- 核心循环: 对话提问 -> 真实数据查询 -> 动态 UI 卡片 -> 用户理解趋势。
- safety_level: read_only_health_management。
- autonomy_tier: no_write。
- spec_required: no，本切片接入既有 GenUI 契约，不新增写路径或医疗安全行为。
- 裁决: PASS。

## S2/S3 计划

见 `docs/plans/2026-06-30-mobile-genui-line-chart-plan.md`。

## G2 可行性 + 安全

- 可行性: Mobile 已有 `react-native-svg`，可复用卡片注册表渲染原生折线。
- 安全: parser 只接受白名单 `line_chart`，不执行代码；坏块和未知组件不泄露 raw JSON。
- 裁决: PASS。

## S4/S5 实现任务

- [x] T1 RED: `streamChat` 必须声明 `genui-v1`。
- [x] T2 RED: `reva-ui` fenced block 必须抽为 `line_chart` descriptor。
- [x] T3 RED: ChatBubble 必须渲染图表卡，不显示 raw fenced JSON。
- [x] T4 GREEN: 新增 parser、请求头、`line_chart` renderer 和 ChatBubble 内联渲染。
- [ ] T5 G3 验证、提交、发布 OTA。

## G3 测试

待最终验证后回写。

## G4 安全

本切片只读展示真实数据图表；不新增写操作、处方、剂量或诊断。parser 白名单 + JSON parse fail-closed。

## S6/S7 部署与上线验证

待 OTA 发布后回写。
