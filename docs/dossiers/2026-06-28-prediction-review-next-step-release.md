# Dossier: Prediction Review 下一步与多端发布

| 字段 | 值 |
|---|---|
| slug | `prediction-review-next-step-release` |
| 创建日期 | 2026-06-28 |
| 当前阶段 | S8 沉淀 |
| 状态 | released |
| 负责 | Codex |
| 反馈环 | backend deploy / web deploy / Mac package / Watch package tests / Mobile local QR |

## S0 · 用户需求(逐字)

> 完成之后发版，包括web mac watch mobile，mobile采用二维码方式发版

- 谁用 / 解决什么 / 现在怎么绕过: 用户已经能看到预测回测和时间线，但还缺“下一步做什么、为什么不确定、信心怎么变化”的复盘闭环；目前需要自己读时间线推断。
- 锚点用户相关性: 35-55 高强度用户需要低摩擦复盘和下一步行动，而不是只看指标 dashboard。

## S1 · Discovery(现状勘察)

- 已有可复用:
  - `backend/app/services/health_operating_review.py` 已有 `prediction_backtest_v1` 和 `prediction_timeline`。
  - `mobile/app/my-progress.tsx` 已展示 Daily Plan 复盘、预测回测和时间线。
  - `frontend/src/app/my-progress/page.tsx` 仍主要展示 action-card progress，未消费 operating review。
  - `apps/watch` 已消费 watch summary runtime context，适合短提示，不适合复杂复盘。
  - `apps/mac` 有 sidebar/command palette/SwiftPM 测试和 API client 模式。
- 缺什么:
  - `prediction_backtest.results` 缺 `inconclusive_reason`、`next_step` 和 `confidence_change/history`。
  - Web/Mac 还缺用户可见的 Review 下一步。
  - Watch 只需要保持极短提示，避免把小屏变成报告页。
- 硬约束 / 平台·安全边界:
  - 不新增诊断、处方、剂量、临床治疗预测。
  - 不新增写路径，不改变 ActionRanker 排序，不做 autonomous write。
  - 所有预测复盘保持 observation/non-causal wording。

## G1 · 准入裁决(governance §8 RequirementAdmission)

- first_class_objects: `InterventionCycle`, `ExecutionEvent`, `HealthAgendaItem`, `HealthTwin`
- core_loop_step: Execution event -> outcome review -> next action
- target_surface / safety_level / autonomy_tier: Backend + Mobile + Web + Mac + Watch / medical_boundary / none
- spec_required(§8.1): yes，新跨端只读 contract 与用户可见复盘行为
- smallest_end_to_end_slice: 后端新增 review next-step contract，Mobile/Web/Mac 展示，Watch 保留短提示，发版验证。
- stale_surface_to_remove: 不删除旧页面；Web `/my-progress` 增强为 operating review。
- 裁决: PASS —— 直接增强既有核心循环，不新增医疗写入。
- 用户确认: 用户已要求完成后多端发版。

## S2 · PRD

- 链接: 引用 `docs/prd/2026-06-27-code-derived-product-prd-and-10m-goal.md` Pillar 2/5/6/9，不新建完整 PRD。
- 边界(不做): 新 ML model、诊断/处方/剂量、自动重排、IoT、补剂下单。
- 验收 Gate:
  - 后端 review payload 返回 next-step / inconclusive reason / confidence change。
  - Mobile/Web/Mac 用户可见 Review 下一步。
  - Watch 不承载复杂报告，仅解码兼容。
  - 多端验证与发布。
- 未决问题: 无。

## S3 · 规划

- 链接: 接续 `docs/plans/2026-06-27-health-runtime-governance-plan.md` G0.3 后续。
- 任务:
  - T1 后端 contract + tests。
  - T2 Mobile Review 展示 + tests。
  - T3 Web Review 展示。
  - T4 Mac Review client/view + tests。
  - T5 Watch decode/summary兼容 + tests。
  - T6 验证、提交、push、部署、二维码发版。

## G2 · 可行性 + 安全压测

- 评审方式: Codex 自查 + safety-gate 条件评估。
- 硬阻断: 无；只读复盘 contract，保持非因果边界。
- 待拍板分叉: 无。
- 裁决: PASS。

## S4 · 研发任务分解

- 跨端 API 契约:
  - `prediction_backtest.results[]` additive fields:
    - `inconclusive_reason: string | null`
    - `next_step: { action: string, label: string, reason: string, replan_hint?: string, requires_clinician?: boolean }`
    - `confidence_change: { before: string, after: string, direction: "up"|"down"|"same" }`
    - `confidence_history: [{ stage: string, confidence: string, reason: string }]`
- 任务表:
  - [x] T1 Backend review contract
  - [x] T2 Mobile Review UI
  - [x] T3 Web Review UI
  - [x] T4 Mac Review UI
  - [x] T5 Watch compatibility
  - [x] T6 Release all surfaces
- 并发检查: `git status --short --branch` clean, `main...origin/main` aligned.

## S5 · 实现

- 分支/commit: `main` / 本提交
- 后端:
  - `backend/app/services/health_operating_review.py` 给 ready `prediction_backtest.results[]` 增加 `inconclusive_reason`、`next_step`、`confidence_change`、`confidence_history`。
  - 保持 `attribution = prediction_backtest_not_causation` 和 observation/non-causal boundary。
- Mobile:
  - `mobile/services/healthOperatingReview.ts` 增加 next-step 类型与 `predictionNextStepSummary()`。
  - `mobile/app/my-progress.tsx` 在 Daily Plan 复盘卡展示下一步、不确定原因和 replan hint。
- Web:
  - `frontend/src/services/api/healthOperatingReview.ts` 增加 `/daily-plan/review` client 与 next-step summary helper。
  - `frontend/src/app/my-progress/page.tsx` 在进展页顶部展示 Daily Plan 复盘下一步。
- Mac:
  - `apps/mac/Sources/HealthAgentMacCore/HealthOperatingReviewClient.swift` 增加解码模型/client/presentation helper。
  - `apps/mac/Sources/HealthAgentMac/Features/Review/HealthOperatingReviewView.swift` 新增 sidebar Review 页面。
  - `SidebarDestination`、`DesktopCommandPalette`、`AppRootView`、`AppServices` 接入 Review。
- Watch:
  - 不新增复杂报告 UI；随 Mobile QR iOS archive 的 Watch target 构建发布，保留腕上一句话行动策略。

## G3 · 测试闸

- PASS:
  - `DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai backend/venv/bin/python -m pytest backend/tests/test_health_operating_review.py backend/tests/test_inline_cards_runtime_agenda.py -q --no-cov` -> 11 passed。
  - `cd mobile && npm test -- --runTestsByPath services/__tests__/healthOperatingReview.test.ts --runInBand` -> 5 passed。
  - `cd frontend && npm test -- src/services/api/healthOperatingReview.test.ts` -> 1 passed。
  - `swift test --package-path apps/mac --filter HealthOperatingReviewClientTests` -> 2 passed。
  - `swift test --package-path apps/watch` -> 56 passed。
  - `backend/venv/bin/python -m compileall -q backend/app/services/health_operating_review.py` -> pass。
  - `cd mobile && npx tsc --noEmit` -> pass。
  - `cd frontend && npx tsc --noEmit` -> pass。
  - `swift build --package-path apps/mac` -> pass。
  - `cd frontend && npm run build` -> pass，存在既有 lint/config warnings。
  - `python3 scripts/dump_system_map.py && python3 scripts/check_doc_drift.py` -> pass。
  - `python3 backend/scripts/check_dossier_consistency.py` -> pass。
  - `bash -n scripts/mobile-local-qr.sh` -> pass。
  - `git diff --check` -> pass。

## G4 · 安全闸

- 触发: 对外健康复盘建议 wording，需 safety review 自查；不新增写路径。
- PASS:
  - 新增字段为只读 Review payload，不写入用户健康行为、不触发 autonomous action。
  - 文案固定包含“观察性,非因果”或既有 claim boundary。
  - 不新增诊断、处方、剂量、药物调整或临床治疗预测。
  - `requires_clinician` 时 next step 为 `clinician_review`，不把临床问题转成自助行动。
  - Watch 不新增复杂复盘报告，避免小屏过度解释健康结论。

## S6 · 部署

- backend: `./deploy.sh -b` -> pass；生产服务同步到 `53985eab`，DB backup 成功，迁移无新增，KB reindex 完成，health check `60/60 PASS`。
- web: `./deploy.sh -f` -> pass；Next build pass，PM2 `health-frontend` online。
- mac: `apps/mac/scripts/package-app.sh --install --open` -> pass；已安装并启动 `/Applications/健康 Agent.app`。
- mobile/watch: `./scripts/mobile-local-qr.sh` -> pass；生成 iOS QR 安装包并注入 Watch target。
  - build id: `20260628-102842-53985eab`
  - signing: `development`, `automatic`, team `QA2U724DAN`
  - install page: `https://health.executor.life/mobile-install/ios/20260628-102842-53985eab/install.html`
  - ipa: `artifacts/ios-local-install/20260628-102842-53985eab/HealthPilot-20260628-102842-53985eab.ipa`
  - qr: `artifacts/ios-local-install/20260628-102842-53985eab/qr.png`

## G5 · 部署健康闸

- PASS:
  - `curl -fsS https://health.executor.life/api/v1/health` -> `{"status":"healthy","services":{"api":"running","database":"connected","redis":"connected","celery":"connected"}}`
  - `curl -fsSI https://health.executor.life/my-progress` -> HTTP 200。
  - `curl -fsSI https://health.executor.life/mobile-install/ios/20260628-102842-53985eab/install.html` -> HTTP 200。
  - `curl -fsSI https://health.executor.life/mobile-install/ios/20260628-102842-53985eab/manifest.plist` -> HTTP 200。
  - `curl -fsSI https://health.executor.life/mobile-install/ios/20260628-102842-53985eab/HealthPilot-20260628-102842-53985eab.ipa` -> HTTP 200。
  - `pgrep -fl "HealthAgentMac|健康 Agent"` -> `/Applications/健康 Agent.app/Contents/MacOS/HealthAgentMac` running。

## S7 · 上线验证

- PASS:
  - 未登录访问 `https://health.executor.life/api/v1/daily-plan/review?window_days=7` -> HTTP 401，权限边界正常。
  - Mobile QR install artifacts public reachable；本次不走 TestFlight。
  - Watch target 已随 iOS archive 构建和嵌入；不新增复杂 Watch review UI。

## G6 · 验证闸(人在环)

- PASS(agent-verifiable):
  - Web/backend/Mac/Mobile QR/Watch packaging 均完成。
  - 手机端真实安装仍需用户用已纳入 development signing 的设备扫码验证；若 iOS 拒绝安装，优先检查设备 UDID 是否在签名 profile 内。

## S8 · 沉淀

- `docs/plans/2026-06-27-health-runtime-governance-plan.md` 已记录 G0.3 Review 下一步与置信度历史完成。
- 下一批按计划进入 `Specialist` / `Problem` attachment、持久化 prediction index、跨周期 confidence calibration。
