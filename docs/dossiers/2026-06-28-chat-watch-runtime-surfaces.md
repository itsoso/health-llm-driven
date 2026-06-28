# Dossier: Chat + Watch Runtime Surfaces

| 字段 | 值 |
|---|---|
| slug | `chat-watch-runtime-surfaces` |
| 创建日期 | 2026-06-28 |
| 当前阶段 | G3 测试闸 |
| 状态 | verified_pending_release |
| 负责 | Codex |
| 反馈环 | backend deploy + mobile OTA + Watch native model update |

## S0 · 用户需求

> 继续执行下两批。

- 解释: 继续执行滚动 7 天健康运行时编排计划中剩余的下一批两项。
- 两批范围:
  - Chat 动态 UI 卡片消费 runtime projection。
  - Watch summary 使用 runtime projection 的压缩行动合同。

## S1 · Discovery

- PRD 锚点: `Daily Artifact` 需要被 Home、Chat、Watch 复用；用户希望 Chat 上下文能动态生成 UI 卡片，手表只显示当前最该做的一件事。
- Plan 锚点: `docs/plans/2026-06-27-health-runtime-governance-plan.md` §12 将 Chat runtime card 与 Watch runtime summary 列为 Home Runtime 化之后的未完成项。
- 代码现状:
  - `backend/app/services/agenda_service.py` 已有 `runtime_range_view`。
  - `backend/app/services/inline_cards.py` 已有 SSE done cards 机制，但没有 runtime agenda card。
  - `mobile/components/chat/cards/registry.tsx` 已有 server card registry 和 action allowlist。
  - `backend/app/services/watch_summary.py` 仍消费旧 `agenda_service.today`。
  - `apps/watch/Sources/WatchCompanionCore/WatchSummary.swift` 没有 runtime/runtimeContext 解码模型。

## G1 · 准入裁决

- first_class_objects: `HealthAgendaItem`, `DailyArtifact`, `HealthTrajectory`, `ExecutionEvent`, `SafetyGuardian`。
- core_loop_step: Chat 解释 -> UI 卡片 -> 打开 Agenda；Watch 状态 -> 单一行动 -> 手动完成/跳过。
- target_surface / safety_level / autonomy_tier: Backend + Mobile Chat + Watch model / medical_boundary / manual_confirm。
- smallest_end_to_end_slice: Chat 查询未来 7 天时返回 `runtime_agenda` card；Watch summary 输出今日 runtime contract 和 `runtime_context`。
- 裁决: PASS。该切片只读投影，不新增写路径；Chat 动作只允许 `route.open`，Watch 完成仍走既有 action_id/manual path。

## S2 · PRD

- 用户可见合同:
  - Chat 能在对话结果中展示“7天健康运行时”动态卡片，包含下一步行动、重排原因、验证指标和打开 Agenda 的动作。
  - Watch summary 使用同一个 runtime projection，保留一句话 top action 和安全/验证上下文。
- 不做范围:
  - 不做 autonomous write。
  - 不做药物剂量、临床诊断或补剂购买建议。
  - 不做新的 Watch UI 发布包；本次更新 Watch shared model 和后端合同。

## S3 · 规划

- 关联计划: `docs/plans/2026-06-27-health-runtime-governance-plan.md`。
- 关联 spec: `docs/specs/active/2026-06-28-rolling-7-day-health-runtime.md`。
- 发布路由: backend deploy + Mobile OTA production；Watch native change 随下一次原生构建进入包。

## G2 · 可行性 + 安全压测

- 风险: Chat 卡片可能把记录意图误判成计划查询。
- 缓解: runtime card builder 明确跳过记录/打卡/服药/刚吃喝等记录意图。
- 风险: Watch summary 切换输入源后改变 top action 排序。
- 缓解: 仅替换输入源为 `runtime_range_view(days=1)`，排序仍走 `rank_agenda_actions` 和既有安全预算。
- 风险: 前端渲染模型下发动作。
- 缓解: Mobile registry 继续使用 action allowlist；本卡只下发 `route.open`。
- 裁决: PASS。

## S4 · 研发任务分解

- [x] T1 后端 inline card runtime agenda 合同测试。
- [x] T2 后端 `inline_cards` 接入 `agenda_service.runtime_range_view(days=7)`。
- [x] T3 Mobile `runtime_agenda` card 和 registry 测试。
- [x] T4 后端 Watch summary 改为 `runtime_range_view(days=1)` 并透传 `runtime_context`。
- [x] T5 Watch Swift model 解码 `runtime` 和 top action `runtime_context`。
- [x] T6 Plan/Spec/Dossier 回写。

## S5 · 实现

- 分支: `codex/rolling-runtime-next-slice`
- 实现文件:
  - `backend/app/services/inline_cards.py`
  - `backend/app/services/watch_summary.py`
  - `backend/tests/test_inline_cards_runtime_agenda.py`
  - `backend/tests/test_watch_summary.py`
  - `mobile/components/chat/cards/RuntimeAgendaCard.tsx`
  - `mobile/components/chat/cards/registry.tsx`
  - `mobile/components/chat/cards/index.ts`
  - `mobile/components/chat/cards/__tests__/registry.test.tsx`
  - `apps/watch/Sources/WatchCompanionCore/WatchSummary.swift`
  - `apps/watch/Tests/WatchCompanionCoreTests/WatchCompanionCoreTests.swift`

## G3 · 测试闸

- TDD 红灯:
  - 后端 inline/watch focused tests: 10 failed，证明旧实现缺 runtime card 且 Watch 仍走旧 agenda。
  - Mobile registry test: 2 failed，证明 `runtime_agenda` 未注册。
  - `swift test`: compile failed，证明 Watch model 缺 `runtime` / `runtimeContext`。
- 当前验证:
  - `pytest backend/tests/test_inline_cards_runtime_agenda.py backend/tests/test_watch_summary.py -q --no-cov`: 18 passed。
  - `npm test -- --runTestsByPath components/chat/cards/__tests__/registry.test.tsx --runInBand`: 21 passed。
  - `swift test`: 56 passed。
  - `npx tsc --noEmit --pretty false`: passed。
  - `python -m compileall -q ...`: passed。
  - `python scripts/check_doc_drift.py`: passed。
- 裁决: PASS。

## G4 · 安全闸

- 写路径: 未新增。
- Chat 动作: 仅 `route.open` 到 Agenda；不下发任意 endpoint。
- Watch 动作: 仍依赖 existing `action_id` 和 watch quick record/manual completion path。
- 健康边界: runtime context 保留 `safety_boundary`；不诊断、不处方、不自动执行真实世界动作。
- 裁决: PASS。

## S6 · 部署

- 状态: pending。
- 路由: backend deploy + mobile OTA production。

## G5/G6 · 部署健康与上线验证

- 状态: pending。

## S8 · 沉淀

- 状态: pending release。
