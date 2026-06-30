# Dossier: GenUI Health Chart Coverage

| 字段 | 值 |
|---|---|
| slug | `genui-health-chart-coverage` |
| 创建日期 | 2026-06-30 |
| 当前阶段 | S7 上线验证 |
| 状态 | released |
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

- [x] T1 Backend RED: 覆盖血压、腰围、体脂、血糖、SpO2 识别与 `metric_line_chart`。
- [x] T2 Backend RED: 数据不足返回 `metric_empty_state`, 不触达普通 LLM。
- [x] T3 Backend GREEN: 扩展 allowlist、DB fetch 和空态 block。
- [x] T4 Client RED/GREEN: Web/Mobile 解析并渲染 `metric_empty_state`。
- [x] T5 Verification: focused backend/frontend/mobile tests + Web build。

## G3 测试

- `DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai backend/venv/bin/pytest backend/tests/test_genui_chart.py -q` -> PASS, 66 passed。
- `npm --prefix frontend test -- --run src/components/assistant/__tests__/MarkdownRenderer.test.tsx` -> PASS, 3 passed。
- `npm --prefix frontend run build` -> PASS, compiled successfully; 存量 lint warnings 未新增阻断。
- `pnpm --dir mobile exec jest mobile/utils/__tests__/revaUiBlocks.test.ts mobile/components/chat/cards/__tests__/registry.test.tsx --runInBand` -> PASS, 35 passed。
- `pnpm --dir mobile exec tsc --noEmit` -> PASS。
- `git diff --check` -> PASS。
- 裁决: PASS。

## G4 安全

- 本切片只读生成图表/空态, 不写健康数据、不诊断、不处方。
- 图表数值来自 DB allowlist 字段; 数据不足时显式 `metric_empty_state`, 不让 LLM 补点或画 ASCII 图。
- 旧端只声明 `genui-v1` 且数据不足时保持历史 fall through, 避免未知组件破坏兼容。
- 裁决: PASS。

## S6/S7 部署与上线验证

- 代码提交: `7fce54e7 feat(genui): support common health metric charts`。
- Web/backend: 从临时干净 worktree 执行 `./deploy.sh --all -y`。
- 部署结果: 前端 PM2 `health-frontend` online; 后端 `health-backend.service` active (running)。
- 部署健康度: `60/60 PASS`。
- Skills manifest: 本地 22 = 线上 22。
- Mobile OTA: `scripts/mobile-ota.sh production "GenUI common health metric charts"`。
- OTA 结果: production branch, runtime `1.3.1`, update group `da747a51-d62e-43fb-91a8-26db0afac5e7`, iOS update `019f191b-1ac8-7df6-ad85-ebe88c77e202`。
- 裁决: PASS。
