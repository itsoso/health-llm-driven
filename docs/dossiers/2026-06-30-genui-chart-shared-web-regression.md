# Dossier: GenUI Chart Shared Web Regression

| 字段 | 值 |
|---|---|
| slug | `genui-chart-shared-web-regression` |
| 创建日期 | 2026-06-30 |
| 当前阶段 | S5 实现完成 |
| 状态 | tested |
| 负责 | Codex |
| 反馈环 | TDD / backend contract test / frontend Vitest / Next build |

## S0 Intake

线上分享页 `726d42db0f8b8ddf2b2bd971ca1d3566` 中, 用户 prompt 为:

> 最近一周睡眠时长曲线 以及评估睡眠

实际回复回落到普通 LLM, 输出了 ASCII 文本图和 markdown 表格, 没有遵循 Reva GenUI 图表契约。

## S1 Discovery

- 后端 `detect_chart_request` 只识别“图表动词 + 图表名词 + 指标”, 漏掉“最近一周睡眠时长曲线”这类省略动词的自然表达。
- 后端图表范围只支持 `1m/3m/6m`, 不支持 `7d/最近一周`。
- Web `agentApi.streamMessage` 未声明 `X-Reva-Client-Caps: genui-v1, genui-components-v1`, 因此 Web 对话不会进入确定性 GenUI 短路。
- Web/分享页共用的 `MarkdownRenderer` 不识别 `reva-ui` fenced block, 即使后端返回图表块也会当作代码块显示。

## G1 准入

- 对象: `ChatMessage`、`DynamicUICard`、`HealthSignalChart`。
- 核心循环: 对话提问 -> 真实数据查询 -> 动态 UI 卡片 -> 用户理解趋势。
- safety_level: read_only_health_management。
- autonomy_tier: no_write。
- spec_required: no, 属于既有 GenUI 图表能力的线上回归修复, 不新增医疗写路径。
- 裁决: PASS。

## S2/S3 计划

- 后端扩展图表意图: 允许“明确 range + 图表名词 + 支持指标”的无动词请求。
- 后端扩展范围: `7d` 使用日级点, 保持 `1m/3m/6m` 现有分桶语义。
- Web 请求 `/agent/stream` 时声明 GenUI 能力。
- Web/分享页共用 MarkdownRenderer 支持受控 `line_chart` / `metric_line_chart` SVG 卡片渲染。

## G2 可行性 + 安全

- 可行性: Mobile 已有同类 `reva-ui` parser; Web 可在现有 MarkdownRenderer 内做同样的受控 parser。
- 安全: 图表数值仍只来自后端确定性 DB builder; 前端只解析白名单 JSON block, 不执行代码。
- 裁决: PASS。

## S4/S5 实现任务

- [x] T1 RED: 线上 prompt 必须命中 `sleep + 7d`。
- [x] T2 RED: `/agent/stream` 在 GenUI caps 下必须返回 `metric_line_chart`, 不触达普通 LLM。
- [x] T3 RED: Web stream 请求必须声明 GenUI caps。
- [x] T4 RED: Web MarkdownRenderer 必须把 `reva-ui` 渲染成卡片, 不泄露 raw JSON。
- [x] T5 GREEN: 后端支持 `7d` 和无动词图表请求。
- [x] T6 GREEN: Web 请求头 + 共享/对话页图表渲染。

## G3 测试

- `DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai backend/venv/bin/pytest backend/tests/test_genui_chart.py -q` -> 58 passed。
- `npm --prefix frontend test -- --run src/services/api/ai.test.ts src/components/assistant/__tests__/MarkdownRenderer.test.tsx` -> 3 passed。
- `npm --prefix frontend run build` -> passed。存在既有 lint warnings 和 Next config warning, 非本次新增阻断。
- 裁决: PASS。

## G4 安全

本切片只读展示真实数据图表; 不新增写操作、处方、剂量、诊断或用药建议。共享页仍使用既有敏感内容 reveal gate。

- 裁决: PASS。

## S6/S7 部署与上线验证

- Git: 待提交。
- Backend/Web: 待 `./deploy.sh --all -y`。
- Production 验证: 待检查共享页和 `/agent/stream` 健康。
