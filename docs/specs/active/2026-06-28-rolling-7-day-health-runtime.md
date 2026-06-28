# 滚动 7 天健康运行时编排 Spec

> 状态: active slice v1
> 日期: 2026-06-28
> 关联 PRD: `docs/prd/2026-06-27-code-derived-product-prd-and-10m-goal.md`
> 关联计划: `docs/plans/2026-06-27-health-runtime-governance-plan.md`
> 关联 Dossier: `docs/dossiers/2026-06-28-rolling-health-runtime-next-slice.md`

## 1. 产品定义

“滚动 7 天健康运行时编排”是 Reva 的一级产品能力。它把用户的当前健康状态、每日协议、复查日历、轨迹风险、执行反馈和安全边界投影成未来 7 天可执行、可解释、可验证、可重排的健康行动路线。

首个切片不新增表、不生成新医疗结论、不自动执行真实世界动作。它复用 `Agenda` 作为行动脊柱，输出一个虚拟 runtime projection，供 Mobile Today/Agenda、Chat 动态卡片和 Watch top action 复用。

## 2. API 合同

### `GET /api/v1/agenda/range?days=7&mode=runtime`

返回 1-14 天 horizon 的运行时投影。默认产品使用 7 天。

核心字段:

- `mode`: 固定为 `runtime`。
- `generated_by`: 当前为 `rolling_health_runtime_v1`。
- `horizon_days`: 实际投影天数。
- `next_action`: horizon 内第一个可执行行动。
- `days[]`: 每天的行动分桶。
- `days[].next_action`: 当天主要行动。
- `days[].time_windows[]`: 按 morning/noon/afternoon/evening/bedtime/anytime 分桶。
- `item.runtime_context`: 运行时解释与治理字段。

### `GET /api/v1/agenda/today?mode=runtime`

返回同一合同的一天投影，用于 Watch、首页或 Chat 只需要今日行动的场景。

## 3. Runtime Context

每个 runtime item 必须包含:

- `surface`: 当前为 `agenda`。
- `current_state_summary`: 为什么此刻需要看到这条行动。
- `evidence`: source、rank score、trajectory context 和 confidence 摘要。
- `safety_boundary`: 不诊断、不处方、不调药；高风险症状转医生/急救。
- `freshness`: 投影生成日期、来源对象类型。
- `verification_window`: `window_days` + `metrics`。
- `replan_reason`: `today_smart_rank`、`daily_protocol_projection` 或 `scheduled_followup_projection`。
- `next_replan_triggers`: completion、skip、snooze、新可穿戴信号、新报告、安全警报。

## 4. 安全边界

- 本能力只读投影，不写真实记录。
- 完成、跳过、手工记录仍必须走 `/agenda/complete` 或对应 confirmed write path。
- 用药、补剂、复查、检查、疾病相关行动不得因出现在 runtime projection 中提升自治等级。
- 未来接入 Chat/Watch 时，写动作仍然遵守 `manual_confirm` 和 SafetyGuardian。
- 弱证据只能表达为 observation 或 hypothesis，不表达 validated effect。

## 5. 首个切片验收

- 后端支持 `mode=runtime`，默认 `regular` 响应不变。
- `/agenda/range?days=7&mode=runtime` 返回 7 天 day list、root `next_action` 和 item `runtime_context`。
- `/agenda/today?mode=runtime` 返回 1 天同构 projection。
- Mobile service/hook 暴露 `getRuntimeAgendaRange` / `useRuntimeAgendaRange`。
- Mobile Agenda 页面展示“7天运行时”面板，包含下一步行动和未来几天主要行动。
- 测试覆盖后端合同、非法 mode、Mobile service 参数合同。

## 6. 后续切片

- Home Daily Artifact 使用同一 runtime projection，只展示一个 primary next action。
- Chat 动态卡片渲染 `RuntimeAgendaRange` 或单日 runtime card。
- Watch summary 使用 `today?mode=runtime`，只显示一句话行动和安全边界。
- skip reason、snooze、completion 进入 future projection 的重排因子。
- DataConnection/Consent/Provenance 补齐后，runtime context 增加关键事实 provenance。
