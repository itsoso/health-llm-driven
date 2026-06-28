# Dossier: Home Daily Artifact Runtime 化

| 字段 | 值 |
|---|---|
| slug | `home-daily-artifact-runtime` |
| 创建日期 | 2026-06-28 |
| 当前阶段 | S6 部署前验证 |
| 状态 | implementation-complete |
| 负责 | Codex |
| 反馈环 | backend deploy + mobile OTA |

## S0 · 用户需求

> 按 PRD 完整执行，先对比 PRD/Plan/Code，走 product-pipeline，直接实现、验证、发布，并回写计划状态。

- 目标用户: 每天打开 Reva 首页的普通用户，尤其是慢病、代谢、恢复风险和高压力用户。
- 要解决的问题: 首页 Daily Artifact 已有“一件事”UI，但后端仍从旧 `smart_today` 派生，尚未接入“滚动 7 天健康运行时编排”，导致 Home、Agenda、Chat、Watch 后续无法共用同一个运行时对象。

## S1 · Discovery

- PRD 锚点: `docs/prd/2026-06-27-code-derived-product-prd-and-10m-goal.md` 要求做强 Daily Artifact，并让 Mobile Today、Watch 和 Chat 共用同一 Daily Artifact。
- Plan 锚点: `docs/plans/2026-06-27-health-runtime-governance-plan.md` §12 将 “Home Daily Artifact 直接消费 runtime projection” 列为 `runtime` 首个切片之后的未完成项。
- 代码现状:
  - `backend/app/services/daily_artifact_service.py` 已有 Daily Artifact 合同，但 source 是 `agenda.smart_today`。
  - `backend/app/services/agenda_service.py` 已有 `runtime_range_view`。
  - `mobile/app/(tabs)/index.tsx` 首页已渲染 `DailyArtifactCard`。
  - `mobile/services/dailyArtifact.ts` 已有 service，但默认查询窗口仍是 14 天且未保留 `runtime_context`。

## G1 · 准入裁决

- first_class_objects: `DailyArtifact`, `HealthAgendaItem`, `HealthTrajectory`, `ExecutionEvent`, `SafetyGuardian`。
- core_loop_step: 状态判断 -> 一个 top action -> 执行/跳过 -> 后续验证。
- target_surface / safety_level / autonomy_tier: Backend + Mobile Home / medical_boundary / manual_confirm。
- smallest_end_to_end_slice: `/daily-artifact/me` 由 7 天 runtime projection 派生，并让 Mobile Home telemetry 带上 runtime source。
- 裁决: PASS。该切片收敛既有首页，不新增页面，不新增写路径。

## S2 · PRD

- 用户可见合同:
  - Daily Artifact 只展示一个 primary next action。
  - 返回状态、why now、do now、verify by、最多 3 个 evidence、confidence/freshness/safety boundary。
  - source 必须能说明它来自 `agenda.runtime_range`，为 Chat/Watch 复用打基础。
- 不做范围:
  - 不做 autonomous write。
  - 不做药物剂量、临床诊断或补剂购买建议。
  - 不做 Chat/Watch 卡片渲染；它们进入下一切片。

## S3 · 规划

- 关联计划: `docs/plans/2026-06-27-health-runtime-governance-plan.md`。
- 关联 spec: `docs/specs/active/2026-06-28-rolling-7-day-health-runtime.md`。
- 发布路由: backend deploy + Mobile OTA production。

## G2 · 可行性 + 安全压测

- 风险: 首页 top action source 从 `smart_today` 切到 `runtime_range_view` 后，可能改变 artifact date/source/freshness。
- 缓解:
  - TDD 先锁定 API 默认 7 天和 `agenda.runtime_range` source。
  - 保留完成/跳过写路径: complete 仍走 `/agenda/complete`，skip 仍写 Daily Artifact event。
  - safety boundary 继续优先使用 action `claim_boundary`，缺省才用 runtime context 或默认边界。
- 裁决: PASS。

## S4 · 研发任务分解

- [x] T1 后端 Daily Artifact 测试从 `smart_today` 改成 `runtime_range_view`。
- [x] T2 后端 `build_daily_artifact` 默认 7 天 runtime projection。
- [x] T3 API Query 默认窗口改为 7 天、最大 14 天。
- [x] T4 Mobile DailyArtifact service 默认 7 天并保留 `runtime_context`。
- [x] T5 Mobile Home telemetry 写入 `generated_by`、`source_kind`、`runtime_horizon_days`、`replan_reason`。
- [x] T6 生成 system-map 并修复文档漂移。

## S5 · 实现

- 分支: `codex/rolling-runtime-next-slice`
- 实现文件:
  - `backend/app/api/daily_artifact.py`
  - `backend/app/services/daily_artifact_service.py`
  - `backend/tests/test_daily_artifact.py`
  - `mobile/services/dailyArtifact.ts`
  - `mobile/services/__tests__/dailyArtifact.test.ts`
  - `mobile/app/(tabs)/index.tsx`
  - `docs/_generated/system-map.json`
  - `docs/ARCHITECTURE.md`
  - `docs/system-map/INDEX.md`

## G3 · 测试闸

- TDD 红灯:
  - 后端 Daily Artifact 测试: 2 failed，证明旧实现仍走 `smart_today`。
  - Mobile service 测试: 1 failed，证明默认仍是 14 天。
- 当前验证:
  - `pytest backend/tests/test_daily_artifact.py`: 3 passed。
  - `pytest backend/tests/test_daily_artifact.py backend/tests/test_agenda_range_complete.py`: 12 passed。
  - `npm test -- --runTestsByPath services/__tests__/dailyArtifact.test.ts services/__tests__/agenda.test.ts --runInBand`: 10 passed。
  - `npx tsc --noEmit --pretty false`: passed。
  - `python -m compileall -q backend/app/api/daily_artifact.py backend/app/services/daily_artifact_service.py`: passed。
  - `python scripts/check_doc_drift.py`: passed。
- 裁决: PASS。

## G4 · 安全闸

- 写路径: 未新增。
- 健康边界: 仍返回 `safety_boundary`，不诊断、不处方、不自动执行真实世界动作。
- 数据隔离: API 仍依赖 `get_current_user_required`。
- 裁决: PASS。

## S6 · 部署

- 状态: pending。
- 计划:
  - 提交并推送到 `main`。
  - 后端 deploy。
  - Mobile OTA production。
  - 生产 user_id=3 smoke `/api/v1/daily-artifact/me`。

## G5/G6 · 部署健康与上线验证

- 状态: pending。

## S8 · 沉淀

- 状态: pending deploy result。
