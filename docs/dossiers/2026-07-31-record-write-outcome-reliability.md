# Dossier: 健康记录写入结果与重试可靠性

| 字段 | 值 |
|---|---|
| slug | `record-write-outcome-reliability` |
| 创建日期 | 2026-07-31 |
| 当前阶段 | S4 需求分解 |
| 状态 | building |
| 负责 | Codex |
| 反馈环 | Backend deploy + Mobile OTA + production smoke |

## Correct Course

- [x] Correction Block
  - 触发: 用户指出“记录信息无法使用”经常出现，不能只修单条饮水记录。
  - 旧基线: 单独修正 water `record_date`。
  - 新基线: 后端 typed write outcome + 历史日期持久化 + Mobile 权威终态/安全重试。
  - 回退阶段: S1
  - 需重跑 Gate: G2/G3/G4/G5/G6
  - 用户确认: ☑

## S0 · 用户需求（逐字）

> 分析问题 并解决掉
>
> 记录信息无法使用，经常出现这类问题
>
> 好

- 谁用 / 解决什么 / 现在怎么绕过: Mobile 小巴用户记录健康数据；当前只能先查记录再手工判断是否补录。
- 锚点用户相关性: 手工饮水、饮食、症状等记录是 Health OS 执行事件入口。

## S1 · Discovery（现状勘察）

- 已有可复用:
  - `backend/app/services/agent_write_outcome.py`: 单一写结果分类器。
  - `backend/app/services/agent_executor.py`: verified receipt 与 runtime operation ledger。
  - `backend/app/services/agent_turn_retry.py`: 已有 fail-closed retry-source action。
  - `mobile/utils/agentTurnState.ts`: Mobile 回合状态机。
- 缺什么:
  - SSE 未向 Mobile 传递写结果类型、dispatch 和安全重试事实。
  - Mobile 把写工具中间失败提前锁成 `failed/recoverable`，后续 `done` 无法覆盖。
  - water goal/handler 未可靠携带历史目标日期。
  - Mobile Retry 未消费后端已有 `recovery_action`，而是直接重发原文。
- 生产证据:
  - run `run_e5b5b27831144534` / turn `turn-55e95c453da14d1bb0e484a8b02cc17c`。
  - operation `health_record` ended `reconciliation_required / missing_receipt`。
  - water row `#705`, 1200 ml, committed to 2026-08-01 although request targeted yesterday。
  - available 30-day runtime aggregation: 46 verified health records, 11 pre-dispatch rejections, 4 reconciled no-effect, 1 missing receipt; Mobile collapses these states.
- 硬约束:
  - uncertain write must never blind-retry;
  - no raw health args in runtime/SSE telemetry;
  - user-scoped persistence and lookup;
  - no production data mutation without separate approval.

## G1 · 准入裁决

- first_class_objects: `ExecutionEvent`, `WriteIntent`, `HealthTwin`
- core_loop_step: Mobile execution → execution event → verification/Twin
- target_surface / safety_level / autonomy_tier: Backend + Mobile / privacy-sensitive write path / unchanged
- spec_required: yes — `docs/specs/record-write-outcome-reliability-spec.md`
- smallest_end_to_end_slice: historical water record + typed SSE outcome + safe Mobile terminal state
- stale_surface_to_remove: generic client-side write-failure inference
- **裁决**: PASS
- 用户确认: ☑

## S2 · PRD

- 链接: `docs/specs/record-write-outcome-reliability-spec.md`（bugfix 使用 focused feature spec，不新建重复 PRD）
- 边界: 不改临床建议、不扩自治、不做 DB migration、不自动修生产记录。
- 验收 Gate: exact incident phrase, typed SSE, no blind retry, backend/mobile regressions.
- 未决问题: 无。

## S3 · 规划

- 链接: `docs/plans/2026-07-31-record-write-outcome-reliability.md`
- 分阶段 + 反馈环路由: backend first → backend health → Mobile OTA → real path verification.
- 长杆: Mobile intermediate/terminal event ordering and backward compatibility.

## G2 · 可行性 + 安全压测

- 评审方式: ☑ Codex challenge based on production ledger and persisted row.
- 硬阻断:
  - Mobile may not infer retry safety from `success=false`.
  - An uncertain write may not expose generic one-tap resubmit.
  - Backend result fields must be additive for old clients.
  - Existing `retry_source_turn` must be used instead of inventing a second retry protocol.
- 待拍板分叉: none.
- **裁决**: PASS
- 用户确认: ☑

## S4 · 研发任务分解

- 跨端 API 契约: additive `tool_result` outcome facts; existing `done.turn_outcome/recovery_action` becomes Mobile authority.
- 任务表:
  - [ ] T1 deterministic water amount/date and persistence regression.
  - [ ] T2 backend typed write outcome event and terminal retry classification.
  - [ ] T3 Mobile parser and non-terminal tool result state.
  - [ ] T4 Mobile retry-source action and no-retry uncertain state.
  - [ ] T5 integrated verification, safety review, deployment, production validation.
- 并发检查: isolated worktree from `origin/main`; dirty local main untouched. ☑

## S5 · 实现

- 分支: `codex/fix-record-write-outcome`
- commit: pending

## G3 · 测试闸

- 集成闸: pending
- main CI 真实色: pending
- capstone review: pending
- **裁决**: pending

## G4 · 安全闸

- 触发: health write path and retry semantics.
- 评审: independent safety/code review required after commit.
- **裁决**: pending

## S6 · 部署

- 路由: backend-deploy then mobile-ota.
- 部署 SHA / 回滚点: pending

## G5 · 部署健康闸

- 健康分 / prod smoke: pending
- **裁决**: pending

## S7 · 上线验证

- 真实路径: exact historical water phrase plus local rejection and uncertain write presentation.
- 结果: pending

## G6 · 验证闸

- prod / true-device confirmation: pending
- **裁决**: pending

## S8 · 沉淀

- Agent contract / system map / release notes: pending after final diff.
- 状态: building
