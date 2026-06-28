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

### `GET /api/v1/data-connections/me`

返回用户数据源连接状态。每个 connection 包含 `connection_health`，供 Mobile/Mac/Web 连接中心和运行时解释层共用:

- `status`: `healthy | degraded | revoked | unknown`。
- `severity`: `ok | warning | blocked`。
- `message_code`: 稳定机器码，前端负责 i18n 和文案映射。
- `can_attempt_sync`: 当前是否可以尝试同步。
- `can_use_cached_data`: 降级或 token 失效时，是否还允许只读使用已授权缓存数据。
- `needs_reconnect`: 是否需要用户重新授权。
- `user_action`: `none | retry_later | reconnect`。
- `connection_status` / `token_status` / `degraded_behavior` / `last_success_at` / `last_attempt_at` / `sync_error`: 原始状态摘要，便于调试和 UI 解释。

## 3. Runtime Context

每个 runtime item 必须包含:

- `surface`: 当前为 `agenda`。
- `current_state_summary`: 为什么此刻需要看到这条行动。
- `evidence`: source、rank score、trajectory context 和 confidence 摘要。
- `evidence.provenance`: 可选；关键事实来源摘要。当前策略为 `runtime_key_fact_provenance_v1`，返回 source kind/id、object type/id、观测/接收时间、转换器、置信度、隐私级别和受控 `metadata_summary`，不得返回 raw hash、原始报告内容或完整 metadata。
- `safety_boundary`: 不诊断、不处方、不调药；高风险症状转医生/急救。
- `freshness`: 投影生成日期、来源对象类型。
- `verification_window`: `window_days` + `metrics`。
- `replan_reason`: `today_smart_rank`、`daily_protocol_projection`、`scheduled_followup_projection`、`recent_skip_reason_projection`、`recent_completion_projection` 或 `active_snooze_projection`。
- `next_replan_triggers`: completion、skip、snooze、新可穿戴信号、新报告、安全警报。
- `feedback_adjustment`：可选；当最近 7 天内有完成、跳过或稍后反馈时，说明 `latest_status`、`strategy`、`priority_delta`、`skip_reason` 或 `snoozed_until`。

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

- runtime provenance 继续扩展到 HealthKit、wearable/device、体检报告 provider 的更多 key facts，并在 Review 中展示纠错链路。
- DataConnection 连接中心继续扩展到 Mobile/Mac/Web UI、撤权后删除、token refresh、rate limit 和更多 provider metadata。

## 7. 已完成后续切片

### 2026-06-28 · Home Daily Artifact Runtime 化

- `GET /api/v1/daily-artifact/me` 已改为由 7 天 `agenda.runtime_range` 派生。
- Home Daily Artifact 仍只展示一个 primary next action。
- Mobile service 默认查询 7 天并保留 `top_action.runtime_context`。
- Home telemetry 已记录 runtime generator、source kind、horizon 和 replan reason。

### 2026-06-28 · Chat + Watch Runtime Surfaces

- Chat SSE inline cards 已新增 `runtime_agenda` 只读动态卡片。
- `runtime_agenda` 后端 builder 消费 7 天 `agenda_service.runtime_range_view`，并跳过记录/打卡类 query，避免把快速记录误判成规划查询。
- Mobile Chat card registry 已支持渲染“7天健康运行时”卡片，展示下一步行动、重排原因、验证指标和打开 Agenda 的 `route.open` 动作。
- Watch summary 已改为消费 1 天 `agenda_service.runtime_range_view`，并保留既有 `rank_agenda_actions`、安全预算和手动完成边界。
- Watch shared model 已支持解码 root `runtime` 和 top action `runtime_context`，为原生 Watch UI 使用同一行动合同打底。
- 已发布：backend SHA `a1535357f76339e11a83f1a20dbb13987c5b6ef5`；Mobile OTA group `d731f134-0d98-46c4-8cc9-3b916c6281be`；生产 smoke 覆盖 Watch root runtime 与 Chat runtime card。

### 2026-06-28 · Feedback-driven Future Replan

- Future projection 已读取最近 7 天 `HealthProtocolEvent`，把 completion、skip、snooze 转为 future runtime 的重排因子。
- skip reason 进入排序和解释：`too_tired`、`too_hard`、`unwell` 采用 `reduce_pressure` 策略并降低未来优先级；其他跳过原因采用 `retry_in_better_window`。
- completion / auto observed 采用 `observe_metric_change`，保留行动但把解释转向验证窗口。
- active snooze 采用 `respect_snooze_window`，降低短期打扰强度，并暴露 `snoozed_until`。
- Runtime root context 新增 `feedback_policy=recent_protocol_event_feedback_v1` 和 `feedback_applied_count`。
- 测试覆盖：`backend/tests/test_agenda_range_complete.py` 新增 feedback future projection 合同测试。
- 已发布：代码 commit `16c093f5f288f863d4759601e6affaea3d87824c`；后端部署 HEAD `ab65154382a98d25a70cd4038dfe92b85cf5d6c8`；生产 user_id=3 smoke 覆盖 `feedback_policy`、`feedback_count` 和抽样 `feedback_adjustment`。

### 2026-06-28 · Runtime Key Fact Provenance

- Runtime item 已在 `runtime_context.evidence.provenance` 暴露关键事实来源摘要。
- 当前最小覆盖 FHIR/report 导入后的 `BiomarkerObservation`，由 `verify_by.metrics`、trajectory signals 和 canonical biomarker code 关联 `ProvenanceRecord`。
- 摘要只返回受控字段，不返回 `raw_hash`、原始报告内容或完整 source metadata。
- Runtime root context 新增 `provenance_policy=runtime_key_fact_provenance_v1`。

### 2026-06-28 · ConnectorPolicy Connection Health

- `serialize_data_connection()` 已新增只读 `connection_health` 合同。
- active 连接返回 `healthy/ok/none`，可尝试同步，也可使用缓存数据。
- 鉴权失败降级返回 `degraded/warning/reconnect`，不可继续尝试同步，但在 `read_only` 降级策略下仍可使用已授权缓存数据做只读判断。
- revoke 后返回 `revoked/blocked/reconnect`，不可尝试同步，也不可继续使用缓存数据。
- 已发布：backend SHA `d4003e1594fc89f76e4353b4dd29c0876e3857e6`；生产 smoke 使用 user_id=3 只读 HTTP + rollback 事务合同验证。

### 2026-06-28 · Mobile Connector Health Surface

- Mobile service 已支持 `ConnectionHealth` 类型、旧后端 fallback 和 `connectionHealthDisplay`。
- Mobile 设置页摘要优先使用 `connection_health`，不再只看原始 `connection_status`。
- Mobile `/data-connections` 卡片展示状态、解释文案、缓存可用性和需重连动作语义。
- 已发布：Mobile OTA production group `dae8abc9-8dcf-4fb8-8e18-3252faf29f7b`，iOS update `019f0d33-d178-7fe1-843c-de5430217f5e`。

### 2026-06-28 · Web Connector Health Surface

- Web 已新增 `/data-connections` 连接中心，用于查看外部数据源、授权范围、同步状态和 `connection_health` 降级解释。
- Web service 已支持 `ConnectionHealth` 类型、旧后端 fallback、状态摘要和 display mapping，与 Mobile 使用同一语义。
- 侧边导航“管理中心”和设置页“数据和智能”已接入连接中心入口。
- 本切片只读展示，不新增 token refresh、撤权删除、重连 flow 或 provider 写路径。
- 已发布：Web commit `f6ab4e3dc688e583a72f43583e3fd51c8d69926a`；生产 page smoke `GET /data-connections` 返回 200；user_id=3 authenticated API smoke 返回 `http_status=200 connections=0`。
