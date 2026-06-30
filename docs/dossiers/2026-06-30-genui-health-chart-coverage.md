# Dossier: GenUI Health Chart Coverage

| 字段 | 值 |
|---|---|
| slug | `genui-health-chart-coverage` |
| 创建日期 | 2026-06-30 |
| 当前阶段 | S3 规划 |
| 状态 | planning |
| 负责 | Codex |
| 反馈环 | TDD / backend contract test / Web build / Mobile Jest / OTA |

## S0 Intake

用户确认采用方案 A: 优先补齐阿衡对话动态图表通用能力, 让常见健康指标可以稳定出结构化 UI 卡片, 不再回落到 ASCII 文本图。

## S1 Discovery

- 现有 GenUI builder 支持 HRV、静息心率、压力、睡眠时长、睡眠评分、步数、身体电量、体重。
- 当前高频健康管理指标仍缺: 血压、腰围、体脂、血糖、SpO2。
- 数据不足时当前会 fall through 普通 LLM, 容易再次生成文本图。
- Web 已能渲染 `line_chart` / `metric_line_chart`; Mobile 已有同类 parser 和 registry。

## G1 准入

- 对象: `ChatMessage`、`DynamicUICard`、`HealthSignalChart`。
- 核心循环: 用户提问 -> 真实数据查询 -> 动态 UI 图表/空态 -> 继续追问或补数据。
- safety_level: read_only_health_management。
- autonomy_tier: no_write。
- spec_required: no, 本切片扩展既有只读 GenUI 图表契约。
- 裁决: PASS。

## S2/S3 计划

见 `docs/plans/2026-06-30-genui-health-chart-coverage.md`。

## G2 可行性 + 安全

- 可行性: 目标指标均已有表或日级字段; 前端沿用 `reva-ui` fenced block。
- 安全: 只读展示, 不诊断、不处方、不补点。数据不足显式空态, 不交给 LLM 编造曲线。
- 裁决: PASS。

## S4/S5 实现任务

- [ ] T1 Backend RED: 覆盖血压、腰围、体脂、血糖、SpO2 识别与 `metric_line_chart`。
- [ ] T2 Backend RED: 数据不足返回 `metric_empty_state`, 不触达普通 LLM。
- [ ] T3 Backend GREEN: 扩展 allowlist、DB fetch 和空态 block。
- [ ] T4 Client RED/GREEN: Web/Mobile 解析并渲染 `metric_empty_state`。
- [ ] T5 Verification: focused backend/frontend/mobile tests + Web build。

## G3 测试

待执行。

## G4 安全

待执行。

## S6/S7 部署与上线验证

待执行。
