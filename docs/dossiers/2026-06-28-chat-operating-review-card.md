# Dossier: Chat 预测回测复盘动态卡片

| 字段 | 值 |
|---|---|
| slug | `chat-operating-review-card` |
| 创建日期 | 2026-06-28 |
| 当前阶段 | S8 沉淀 |
| 状态 | shipped |
| 负责 | Codex |
| 反馈环 | backend deploy + mobile OTA |

## S0 · 用户需求(逐字)

> 继续

- 上下文解释: 第十一切片已补齐 Mobile Home Daily Artifact 控制输入展示。按 PRD/Plan/Code 继续推进，G0.3 “预测与实际结果进入统一复盘闭环”已有后端 `health_operating_review` 和 Mobile `/my-progress` 基础，但 Chat 动态 UI 还不能在用户问“复盘/预测回测/效果怎么样”时直接展示结构化 Review 卡片。
- 谁用 / 解决什么 / 现在怎么绕过: 用户在 Chat 里自然询问近期效果时，需要看到“预测 -> 实际 -> 下一步”的结构化摘要；现在必须自己找到 `/my-progress`，或者只收到文字回复，动态 UI 没有承接复盘对象。

## S1 · Discovery(现状勘察)

- 已有可复用:
  - `backend/app/services/health_operating_review.py`: 已能基于 `InterventionEvent.action_snapshot.prediction` 和指标变化生成 `prediction_backtest_v1`，低置信/混杂降级为 `inconclusive`。
  - `backend/app/services/inline_cards.py`: Chat SSE done 事件服务端动态卡片构造器，已支持 `runtime_agenda`。
  - `mobile/components/chat/cards/registry.tsx`: Mobile Chat card registry 已支持服务端下发卡片和 allowlisted `route.open` action。
  - `mobile/app/my-progress.tsx`: 已展示 Daily Plan 复盘、prediction backtest 和 causal memory。
- 缺什么:
  - inline_cards 没有 `operating_review` builder。
  - Mobile Chat registry 没有 `operating_review` 卡片渲染器。
  - Plan 仍把 G0.3 描述成缺少统一 Review 时间线，未反映已有 backend/my-progress 基础。
- 硬约束:
  - 只读卡片，不新增写路径。
  - 不新增预测模型，不自动调整行动或计划。
  - 所有文案保持 observation/backtest，不表达因果证明或医疗结论。

## G1 · 准入裁决(governance §8 RequirementAdmission)

- first_class_objects: `PersonalPrediction`, `ExecutionEvent`, `OutcomeReview`, `HealthAgendaItem`
- core_loop_step: Review -> Learn -> Replan
- target_surface / safety_level / autonomy_tier: Mobile Chat dynamic card / medical_boundary / suggest
- spec_required(§8.1): 复用 `docs/specs/active/2026-06-28-rolling-7-day-health-runtime.md` 和 `docs/plans/2026-06-27-health-runtime-governance-plan.md`。
- smallest_end_to_end_slice: Chat 复盘 query -> backend `operating_review` card -> Mobile Chat 渲染 -> 打开 `/my-progress`。
- stale_surface_to_remove: 无。
- **裁决**: PASS

## S2 · PRD

- 链接: `docs/prd/2026-06-27-code-derived-product-prd-and-10m-goal.md`
- 引用的权威能力: Chat + 动态 UI 卡片融合；预测回测必须声明 horizon、expected signal、actual result、confidence change、claim boundary。
- 边界(不做): 不建新表、不新增 prediction record 写入、不新增 ML、不新增诊断/处方/剂量、不改变行动排序。
- 验收 Gate: Chat 里问复盘/预测回测时返回只读 `operating_review` card；卡片展示窗口、完成率、prediction summary、最多 2 条结果和 boundary，并可打开 `/my-progress`。

## S3 · 规划

- 链接: `docs/plans/2026-06-27-health-runtime-governance-plan.md`
- 分阶段 + 反馈环路由:
  - 后端 inline_cards 合同 RED/GREEN。
  - Mobile card registry/UI RED/GREEN。
  - backend deploy + mobile OTA。
- 长杆 / spike: 无新平台能力。

## G2 · 可行性 + 安全压测

- 评审方式: Codex self-challenge
- 硬阻断(已焊进范围): 不把 backtest 文案写成“证明有效”；不新增写入；只复用 `health_operating_review` 的 observation boundary。
- **待拍板分叉(STOP 问人)**: 无，用户已要求继续按计划直接执行。
- **裁决**: PASS

## S4 · 研发任务分解

- 跨端 API 契约: Chat SSE cards 新增 `{"type":"operating_review","data":{...},"actions":[route.open /my-progress]}`。
- 任务表:
  - [ ] T1 RED: 后端 inline_cards 复盘 query 不返回 `operating_review` card。
  - [ ] T2 RED: Mobile Chat registry 不渲染 `operating_review` card。
  - [ ] T3 GREEN: 后端 builder 调用 `build_health_operating_review()` 并输出紧凑只读 payload。
  - [ ] T4 GREEN: Mobile card 渲染窗口、完成率、预测摘要、结果行、boundary 和打开 `/my-progress` action。
  - [ ] T5 验证、部署、OTA、文档回写。
- 并发检查: 已 `git fetch origin`，从 `origin/main` 最新提交 `8a1acd93` 继续。

## S5 · 实现

- 委托: Codex
- 分支: `main`
- commit: `a84bd620b0271a0d52711ea3de411ffb4289d18c`
- 代码改动:
  - `backend/app/services/inline_cards.py` 新增 `operating_review` builder，复用 `build_health_operating_review()` 生成紧凑只读卡片。
  - Chat card action 只开放 `route.open` 到 `/my-progress`。
  - `mobile/components/chat/cards/OperatingReviewCard.tsx` 新增 Review 动态卡片渲染。
  - `mobile/components/chat/cards/registry.tsx` 注册 `OperatingReviewCardSpec`。

## G3 · 测试闸

- RED:
  - `DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai backend/venv/bin/python -m pytest backend/tests/test_inline_cards_runtime_agenda.py -q --no-cov` 先失败于 `calls == {}`，说明 inline card 还未调用 operating review builder。
  - `npm test -- --runTestsByPath components/chat/cards/__tests__/registry.test.tsx --runInBand` 先失败于 `unknown card type: operating_review`。
- GREEN:
  - `DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai backend/venv/bin/python -m pytest backend/tests/test_inline_cards_runtime_agenda.py -q --no-cov` -> `4 passed, 9 warnings`。
  - `npm test -- --runTestsByPath components/chat/cards/__tests__/registry.test.tsx --runInBand` -> `22 passed`。
- 集成闸:
  - `DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai backend/venv/bin/python -m pytest backend/tests/test_inline_cards_runtime_agenda.py backend/tests/test_health_operating_review.py -q --no-cov` -> `10 passed, 9 warnings`。
  - `npm test -- --runTestsByPath components/chat/cards/__tests__/registry.test.tsx services/__tests__/healthOperatingReview.test.ts --runInBand` -> `25 passed`。
  - `cd mobile && npx tsc --noEmit` -> exit 0。
  - `backend/venv/bin/python -m compileall -q backend/app/services/inline_cards.py backend/app/services/health_operating_review.py` -> exit 0。

## G4 · 安全闸

- 触发?: medical_boundary 展示文案，但只读且复用已有 backtest boundary。
- 自查:
  - 不新增真实世界写动作。
  - 不新增诊断、处方、剂量或因果证明文案。
  - route action 只允许打开 `/my-progress`。
- 结果: diff 只新增只读卡片和 route action；复用 `health_operating_review` 既有 boundary；没有新 DB schema、写路径、医疗结论或自动重排。
- **裁决**: GO

## S6 · 部署

- 路由: backend deploy + mobile OTA。
- 代码提交: `a84bd620b0271a0d52711ea3de411ffb4289d18c`。
- 后端部署 HEAD: `a84bd620b0271a0d52711ea3de411ffb4289d18c`。
- deploy.sh 回滚点: `bb08085e`。
- Mobile OTA:
  - branch/channel: `production`
  - runtime version: `1.3.1`
  - update group: `78bf1ba3-3a75-4aa7-a30a-5bee29b4f3c9`
  - iOS update id: `019f0db8-4e06-7d7c-a819-8bfaceeaf6d0`
  - EAS dashboard: `https://expo.dev/accounts/itsoso/projects/health-pilot/updates/78bf1ba3-3a75-4aa7-a30a-5bee29b4f3c9`

## G5 · 部署健康闸

- `./deploy.sh -b` 成功。
- 部署健康分: `60/60 ✅ PASS`。
- skills manifest: 本地 `22` = 线上 `22`。
- 生产服务 HEAD: `a84bd620b0271a0d52711ea3de411ffb4289d18c`。
- 生产 smoke:
  - `GET http://127.0.0.1:8000/api/v1/health` -> `200`。
  - `GET http://127.0.0.1:8000/api/v1/daily-plan/review?window_days=7` 未鉴权 -> `401`，说明复盘路由已注册。
  - 服务器本机只读调用 `build_cards(db, 3, "帮我做一次预测回测和近期复盘")` -> `count=1 types=['operating_review'] window_days=7 status=not_ready ready=0`。
- **裁决**: PASS

## S7 · 上线验证

- Mobile OTA `./scripts/mobile-ota.sh production "Chat shows prediction backtest review cards"` 成功发布。
- EAS 输出 iOS bundle `entry-45e7d729f9e28feec0f91aad3f41f645.hbc`，设备冷启动或后台 30s+ 后拉取。
- user_id=3 当前没有 ready prediction backtest，卡片正确显示 `not_ready` 数据边界，不假装预测准确性。

## G6 · 验证闸

- PASS。Chat 复盘类 query 现在能返回只读 `operating_review` 动态卡片:
  - 窗口与完成率；
  - prediction backtest 摘要；
  - 最多 2 条回测结果；
  - 指标变化；
  - observation/non-causal boundary；
  - 打开 `/my-progress` 查看复盘详情。
- 尚未完成: 统一 prediction record 写入合同和 Review 时间线中的完整“预测 -> 实际 -> 下一步”历史视图；保留到后续切片。

## S8 · 沉淀

- 已回写 `docs/specs/active/2026-06-28-rolling-7-day-health-runtime.md` 和 `docs/plans/2026-06-27-health-runtime-governance-plan.md`。
- 后续最高价值切片转向:
  - prediction record 持久化合同；
  - Review timeline 把 backtest、causal memory、program review 串成一条用户可读时间线；
  - provider provenance 覆盖 HealthKit/wearable/device key facts。
