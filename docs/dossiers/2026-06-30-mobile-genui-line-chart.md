# Dossier: Mobile GenUI Line Chart

| 字段 | 值 |
|---|---|
| slug | `mobile-genui-line-chart` |
| 创建日期 | 2026-06-30 |
| 当前阶段 | S7 上线验证 |
| 状态 | deployed |
| 负责 | Codex |
| 反馈环 | TDD / mobile Jest / backend contract test / OTA |

## S0 Intake

用户要求继续按照规划执行；当前主干刚合入后端 `reva-ui` 图表短路能力，但 Mobile 仍未声明 `genui-v1` 能力，也不能把 assistant 文本里的 ````reva-ui` 图表块渲染成原生 UI。

后续用户反馈指出: 当前实现没有通用化，只能画固定曲线；“绘制最近半年的心率曲线”仍落到 LLM 文本/ASCII，动态 UI 组件能力未实现。本轮切片把能力从固定 `line_chart` 升级为协商式 `metric_line_chart` 动态组件，同时保留旧端兼容。

## S1 Discovery

- `backend/app/services/genui/chart_builder.py` 已确定性生成 `component=line_chart`，数据来自 Garmin/Weight DB，不走 LLM。
- `backend/app/api/agent.py` 仅在客户端声明 `X-Reva-Client-Caps: genui-v1` 后返回 ````reva-ui` block。
- `mobile/services/chat.ts` 现状未声明该 cap。
- `mobile/components/chat/cards/MetricChartCard.tsx` 已有旧 `metric_chart` 卡，但不支持新 `line_chart` block。
- `mobile/components/chat/ChatBubble.tsx` 会直接显示 fenced block raw JSON。
- `backend/app/services/genui/chart_builder.py` 原检测不覆盖自然说法“心率”，也未覆盖 `sleep_score` / `steps` / `body_battery`。
- 后端只知道 `genui-v1`，无法按客户端能力返回显式 schema 的通用动态组件。

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

- 可行性: Mobile 已有 `react-native-svg`，可复用卡片注册表渲染原生折线；后端已有 Garmin/Weight 日级真数据源。
- 安全: parser 只接受白名单 `line_chart` / `metric_line_chart`，不执行代码；坏块和未知组件不泄露 raw JSON。
- 裁决: PASS。

## S4/S5 实现任务

- [x] T1 RED: `streamChat` 必须声明 `genui-v1`。
- [x] T2 RED: `reva-ui` fenced block 必须抽为 `line_chart` descriptor。
- [x] T3 RED: ChatBubble 必须渲染图表卡，不显示 raw fenced JSON。
- [x] T4 GREEN: 新增 parser、请求头、`line_chart` renderer 和 ChatBubble 内联渲染。
- [x] T5 RED: 新 cap `genui-components-v1` 下后端必须返回 `metric_line_chart`。
- [x] T6 GREEN: 后端支持 `metric_line_chart` schema，并扩展自然指标识别: 心率、睡眠评分、步数、身体电量。
- [x] T7 GREEN: Mobile parser / registry 支持 `metric_line_chart` 动态组件，同时保留 `line_chart`。
- [x] T8 G3 类型检查、提交、部署、发布 OTA。

## G3 测试

- `DATABASE_URL='sqlite:///:memory:' TZ=Asia/Shanghai backend/.venv/bin/python -m pytest backend/tests/test_genui_chart.py` → 55 passed。
- `pnpm --dir mobile exec jest mobile/utils/__tests__/revaUiBlocks.test.ts mobile/services/__tests__/chatStream.test.ts mobile/components/chat/__tests__/ChatBubbleRevaUi.test.tsx mobile/components/chat/cards/__tests__/registry.test.tsx --runInBand` → 4 suites / 39 tests passed。
- `pnpm --dir mobile exec tsc --noEmit` → passed。

## G4 安全

本切片只读展示真实数据图表；不新增写操作、处方、剂量或诊断。parser 白名单 + JSON parse fail-closed。血压等双序列/高敏指标暂不纳入单指标折线。

## S6/S7 部署与上线验证

- Git: `2114a2c6 feat(genui): support generic metric line charts` pushed to `origin/main`。
- Backend: `./deploy.sh -b` from clean deploy worktree → health score `55/60 PASS`; skills manifest `22 = 22`。
- Production route check: `POST /api/v1/agent/stream` without auth → `401`; GET route shape → `405`。
- Mobile OTA: production branch, runtime `1.3.1`, update group `43d96c67-936f-440b-9ca5-9a7c0bdd2a1c`, iOS update `019f17a5-cd15-7ba7-bfdb-9077fa27994a`。
