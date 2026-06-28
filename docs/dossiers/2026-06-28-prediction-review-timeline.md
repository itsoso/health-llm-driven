# Dossier: Prediction Review Timeline 最小闭环

| 字段 | 值 |
|---|---|
| slug | `prediction-review-timeline` |
| 创建日期 | 2026-06-28 |
| 当前阶段 | S6 部署 |
| 状态 | ready_to_ship |
| 负责 | Codex |
| 反馈环 | backend deploy + mobile OTA |

## S0 · 用户需求(逐字)

> 继续

- 上下文解释: 第十二切片已让 Chat 能下发 `operating_review` 复盘动态卡片。下一批按 Plan 中 G0.3 继续，把 prediction backtest 摘要升级成用户可读的“预测 -> 行动 -> 实际 -> 复盘”时间线。
- 谁用 / 解决什么 / 现在怎么绕过: 用户在 `/my-progress` 里能看到 prediction backtest 摘要和结果行，但看不到预测从哪里来、什么时候执行、什么时候观察到实际结果、如何形成复盘裁决；维护者也缺少稳定的 response contract 让后续 Review 时间线复用。

## S1 · Discovery(现状勘察)

- 已有可复用:
  - `backend/app/services/health_operating_review.py`: 已从 `InterventionEvent.action_snapshot.prediction` 派生 `prediction_backtest_v1`。
  - `backend/tests/test_health_operating_review.py`: 已覆盖 ready / low-confidence inconclusive / user scoped。
  - `mobile/services/healthOperatingReview.ts`: 已有 prediction backtest 类型和 summary helper。
  - `mobile/app/my-progress.tsx`: 已在 Daily Plan 复盘卡中展示 prediction backtest 摘要。
- 缺什么:
  - 后端缺少稳定 `prediction_timeline` 合同。
  - Mobile service 缺少 timeline 类型和 summary helper。
  - `/my-progress` 尚未把“预测 -> 行动 -> 实际 -> 复盘”作为时间线展示。
- 硬约束:
  - 不新增 DB schema。
  - 不新增 prediction 写路径或自动重排。
  - 时间线从已持久化的 `InterventionEvent.action_snapshot.prediction` 和窗口指标变化只读派生。
  - 文案保持 observation/backtest，不表达因果证明或医疗结论。

## G1 · 准入裁决(governance §8 RequirementAdmission)

- first_class_objects: `PersonalPrediction`, `ExecutionEvent`, `OutcomeReview`
- core_loop_step: Review -> Learn -> Replan
- target_surface / safety_level / autonomy_tier: Backend Review API + Mobile `/my-progress` / medical_boundary / suggest
- spec_required(§8.1): 复用 `docs/specs/active/2026-06-28-rolling-7-day-health-runtime.md`。
- smallest_end_to_end_slice: `/daily-plan/review` 返回 `prediction_timeline` -> Mobile service 归一化 -> `/my-progress` 展示 timeline。
- stale_surface_to_remove: 无。
- **裁决**: PASS

## S2 · PRD

- 链接: `docs/prd/2026-06-27-code-derived-product-prd-and-10m-goal.md`
- 引用的权威能力: 预测回测必须声明 horizon、expected signal、actual result、confidence change、claim boundary。
- 边界(不做): 不建新表、不新增 prediction 写入、不新增 ML、不新增诊断/处方/剂量、不改变行动排序。
- 验收 Gate: 一个 ready prediction backtest 能生成 predicted/action/outcome/review 四类 timeline 节点；Mobile 能展示前几条，并保留非因果边界。

## S3 · 规划

- 链接: `docs/plans/2026-06-27-health-runtime-governance-plan.md`
- 分阶段 + 反馈环路由:
  - 后端合同测试 RED/GREEN。
  - Mobile service helper 和 UI RED/GREEN。
  - backend deploy + mobile OTA。
- 长杆 / spike: 无新平台能力。

## G2 · 可行性 + 安全压测

- 评审方式: Codex self-challenge
- 硬阻断(已焊进范围): 不把 timeline 节点写成“证明有效”；不新增写入；只读派生，不改变用户计划。
- **待拍板分叉(STOP 问人)**: 无，用户已要求继续按计划直接执行。
- **裁决**: PASS

## S4 · 研发任务分解

- 跨端 API 契约: `HealthOperatingReview.prediction_timeline?: PredictionTimelineItem[]`。
- Timeline item 最小字段:
  - `id`
  - `prediction_id`
  - `event_type`: `prediction_created | action_executed | outcome_observed | review_verdict`
  - `occurred_at`
  - `title`
  - `summary`
  - `metric`
  - `status`
  - `confidence`
  - `boundary`
- 任务表:
  - [x] T1 RED: 后端 daily plan review 缺少 `prediction_timeline`。
  - [x] T2 RED: Mobile service 缺少 timeline 类型和 summary helper。
  - [x] T3 GREEN: 后端从 ready backtest results 派生 timeline。
  - [x] T4 GREEN: Mobile `/my-progress` 展示 timeline。
  - [ ] T5 验证、部署、OTA、文档回写。
- 并发检查: 已 `git fetch origin`；当前本地 main 包含并发 `70096c68 docs(pipeline): add quick flow correction protocol`，基于它继续。

## S5 · 实现

- 委托: Codex
- 分支: `main`
- 实现:
  - `backend/app/services/health_operating_review.py`: 对 ready `prediction_backtest.results` 展开 `prediction_created/action_executed/outcome_observed/review_verdict` 四类节点。
  - `mobile/services/healthOperatingReview.ts`: 增加 `PredictionTimelineItem` 类型与 `predictionTimelineSummary`。
  - `mobile/app/my-progress.tsx`: 在 Daily Plan 复盘卡内展示预测时间线摘要、前四个节点和非因果边界。
- commit: 待提交

## G3 · 测试闸

- RED:
  - `DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai backend/venv/bin/python -m pytest backend/tests/test_health_operating_review.py -q --no-cov` -> 1 failed, 5 passed; 缺 `prediction_timeline`。
  - `cd mobile && npm test -- --runTestsByPath services/__tests__/healthOperatingReview.test.ts --runInBand` -> 1 failed, 3 passed; 缺 `predictionTimelineSummary`。
- GREEN:
  - `DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai backend/venv/bin/python -m pytest backend/tests/test_health_operating_review.py -q --no-cov` -> 6 passed, 9 warnings。
  - `cd mobile && npm test -- --runTestsByPath services/__tests__/healthOperatingReview.test.ts --runInBand` -> 4 passed。
- 集成闸:
  - `DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai backend/venv/bin/python -m pytest backend/tests/test_health_operating_review.py backend/tests/test_inline_cards_runtime_agenda.py -q --no-cov` -> 10 passed, 9 warnings。
  - `cd mobile && npm test -- --runTestsByPath services/__tests__/healthOperatingReview.test.ts components/chat/cards/__tests__/registry.test.tsx --runInBand` -> 26 passed；保留既有 unknown card console.warn。
  - `cd mobile && npx tsc --noEmit` -> exit 0。
  - `backend/venv/bin/python -m compileall -q backend/app/services/health_operating_review.py` -> exit 0。

## G4 · 安全闸

- 触发?: medical_boundary 展示文案，但只读且复用既有 backtest boundary。
- 自查:
  - 不新增真实世界写动作。
  - 不新增诊断、处方、剂量或因果证明文案。
  - confidence 只随 observation backtest 解释，不驱动自动计划变更。
- **裁决**: PASS

## S6 · 部署

- 路由: backend deploy + mobile OTA。
- 部署 SHA / 回滚点: 待定。

## G5 · 部署健康闸

- 待定。

## S7 · 上线验证

- 待定。

## G6 · 验证闸

- 待定。

## S8 · 沉淀

- 待上线验证后回写计划状态。
