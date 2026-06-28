# Dossier: 执行反馈驱动 Runtime Future Replan

| 字段 | 值 |
|---|---|
| slug | `runtime-feedback-replanning` |
| 创建日期 | 2026-06-28 |
| 当前阶段 | S5 验证中 |
| 状态 | implemented |
| 负责 | Codex |
| 反馈环 | backend deploy |

## S0 · 用户需求

> 继续执行下两批。

上下文解释：按 PRD/Plan/Code 对比继续推进滚动 7 天健康运行时。上一批已经完成 Home / Chat / Watch runtime surface，本批选择剩余最高优先级缺口：让 completion、skip reason、snooze 真正进入 future projection 的重排因子。

## S1 · Discovery

已确认：

- `backend/app/models/data_connection.py`、`backend/app/services/data_connections.py`、`backend/app/api/data_connections.py` 已存在 DataConnection / ConsentGrant / ProvenanceRecord 最小底座。
- `backend/app/services/agenda_service.py` 的 runtime projection 已有 `next_replan_triggers`，但 future protocol template 仍固定 `daily_protocol_projection`。
- `backend/app/services/health_protocol_service.py` 已记录 `HealthProtocolEvent.status`、`skip_reason` 和 `snoozed_until`。

缺口：反馈被记录了，但未来 7 天 projection 还没有基于这些反馈改变排序、解释或 replan reason。

## G1 · 准入裁决

- first_class_objects：`HealthAgendaItem`、`ExecutionEvent`、`HealthProtocolEvent`
- core_loop_step：执行反馈 -> 重排 -> 验证
- target_surface：Backend runtime projection，供 Mobile / Chat / Watch 共用
- safety_level：medical_boundary
- autonomy_tier：manual_confirm
- 裁决：PASS。原因：本切片只改只读投影，不新增写路径，不改剂量、治疗或真实世界动作。

## S2 · PRD

- 链接：`docs/specs/active/2026-06-28-rolling-7-day-health-runtime.md`
- 需求：`skip reason`、`snooze`、`completion` 进入 future projection 的重排因子。
- 非目标：不生成新医疗结论，不自动改协议，不绕过 `/agenda/complete`。

## S3 · 规划

- 链接：`docs/plans/2026-06-27-health-runtime-governance-plan.md`
- 范围：backend 编排层最小切片；Mobile/Chat/Watch 通过既有 runtime card/watch summary 自动消费新增上下文字段。

## G2 · 可行性 + 安全压测

- 数据源：只读最近 7 天 `HealthProtocolEvent`。
- 重排策略：
  - `skipped + too_tired/too_hard/unwell` -> `reduce_pressure`，降低未来优先级。
  - 其他 `skipped` -> `retry_in_better_window`。
  - `completed/auto_observed` -> `observe_metric_change`。
  - active `snoozed` -> `respect_snooze_window`。
- 裁决：PASS。重排只影响展示排序和解释，不能写入协议字段。

## S4 · 研发任务分解

- [x] T1 增加失败测试，证明 feedback 尚未进入 future projection。
- [x] T2 增加 `_protocol_feedback_map` 和 feedback adjustment。
- [x] T3 将 feedback 穿透到 `rank_reason`、`runtime_feedback` 和 `runtime_context.feedback_adjustment`。
- [x] T4 更新 Spec / Plan 状态。
- [ ] T5 后端部署与生产 smoke。

## S5 · 实现

- `backend/app/services/agenda_service.py`
- `backend/tests/test_agenda_range_complete.py`
- `docs/specs/active/2026-06-28-rolling-7-day-health-runtime.md`
- `docs/plans/2026-06-27-health-runtime-governance-plan.md`

## G3 · 测试闸

- 新增测试 RED：当前代码返回 `daily_protocol_projection`，未带 `feedback_adjustment`。
- 新增测试 GREEN：`runtime_future_projection` 两个合同测试通过。
- 议程回归：`backend/tests/test_agenda_range_complete.py` `11 passed`。

## G4 · 安全闸

- 裁决：GO。
- 理由：只读 projection；不新增 confirmed write；不提升用药、补剂、复查自治等级；跳过/稍后/完成仍由原有写路径产生事实。

## S6 · 部署

- 待执行。

## G5 · 部署健康闸

- 待执行。

## S7 · 上线验证

- 待执行。

## S8 · 沉淀

- 待部署完成后回写 commit、deploy SHA 和 smoke 结果。
