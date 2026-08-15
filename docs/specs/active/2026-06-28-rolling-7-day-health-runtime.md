# 滚动 7 天健康运行时编排 Spec

> 状态: active slice v1
> 日期: 2026-06-28
> 关联 PRD: `docs/prd/2026-06-27-code-derived-product-prd-and-10m-goal.md`
> 关联计划: `docs/plans/2026-06-27-health-runtime-governance-plan.md`
> 关联 Dossier: `docs/dossiers/2026-06-28-rolling-health-runtime-next-slice.md`
> Scope handoff: 本文件只裁决已上线的 1-14 天只读 Agenda runtime projection、读取时 rerank、`runtime_context` 与 provenance。文中的 `replan/rebuild` 只表示下一次读取投影时根据既有事实改变排序/解释,不代表持久化计划 mutation、版本化 trigger execution 或通知。Health Day v2 的 composer、plan version、Chat-first surface、confirmed mutation 与主动 trigger 合同见 `docs/specs/active/2026-08-15-quiet-proactive-health-day.md`;不得从本文件扩出第二套写入或 daily shell 真源。

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
- DataConnection 连接中心已覆盖 Mobile/Mac/Web UI；继续扩展撤权后删除、token refresh、rate limit、更多 provider metadata 和 Review provenance 展示。

## 7. 已完成后续切片

### 2026-06-28 · Home Daily Artifact Runtime 化

- `GET /api/v1/daily-artifact/me` 已改为由 7 天 `agenda.runtime_range` 派生。
- Home Daily Artifact 仍只展示一个 primary next action。
- Mobile service 默认查询 7 天并保留 `top_action.runtime_context`。
- Home telemetry 已记录 runtime generator、source kind、horizon 和 replan reason。

### 2026-06-28 · Daily Artifact Control Input Surface

- Daily Artifact `top_action` 已稳定透传 `trajectory_context`、`target_state_variable`、`verification_signal` 和 `claim_boundary`。
- Mobile Home Daily Artifact 卡片已展示目标状态变量、轨迹周期和验证摘要，复用 Agenda 的 trajectory display 语义。
- 本切片不改行动排序、不新增写路径、不新增诊断/处方/剂量/因果承诺，只把已有 suggest-only runtime 字段产品化。
- 已发布：代码 commit `c6af470e5ebfff6eb5eb6fbf2c046eeb54c57772`；后端部署 HEAD `bb08085eb54ce36c9a143c7313952494f570c5f8`；Mobile OTA group `1ad7bd94-3ae9-4614-b713-05743488775b`，iOS update `019f0da5-f3cd-7136-94d8-aabc9bd34a22`。

### 2026-06-28 · Chat + Watch Runtime Surfaces

- Chat SSE inline cards 已新增 `runtime_agenda` 只读动态卡片。
- `runtime_agenda` 后端 builder 消费 7 天 `agenda_service.runtime_range_view`，并跳过记录/打卡类 query，避免把快速记录误判成规划查询。
- Mobile Chat card registry 已支持渲染“7天健康运行时”卡片，展示下一步行动、重排原因、验证指标和打开 Agenda 的 `route.open` 动作。
- Watch summary 已改为消费 1 天 `agenda_service.runtime_range_view`，并保留既有 `rank_agenda_actions`、安全预算和手动完成边界。
- Watch shared model 已支持解码 root `runtime` 和 top action `runtime_context`，为原生 Watch UI 使用同一行动合同打底。
- 已发布：backend SHA `a1535357f76339e11a83f1a20dbb13987c5b6ef5`；Mobile OTA group `d731f134-0d98-46c4-8cc9-3b916c6281be`；生产 smoke 覆盖 Watch root runtime 与 Chat runtime card。

### 2026-06-28 · Chat Operating Review Card

- Chat SSE inline cards 已新增 `operating_review` 只读动态卡片，用于“复盘 / 预测回测 / 效果怎么样 / 近期进展”类 query。
- 后端 builder 复用 `health_operating_review.build_health_operating_review()`，输出窗口、完成率、最多 4 个指标变化、prediction backtest 摘要、最多 2 条结果和 causal memory 摘要。
- Mobile Chat registry 已新增 `OperatingReviewCard`，展示完成率、预测回测状态、结果行和 observation/non-causal boundary，并提供 `route.open` 到 `/my-progress` 的只读跳转。
- 记录/打卡类 query 不触发该卡片，避免把快速记录误判成复盘。
- 本切片不新增 DB schema、不新增 prediction 写入、不新增诊断/处方/剂量/因果证明文案。
- 已发布：backend SHA `a84bd620b0271a0d52711ea3de411ffb4289d18c`；Mobile OTA group `78bf1ba3-3a75-4aa7-a30a-5bee29b4f3c9`；生产 smoke `build_cards(user_id=3)` 返回 `operating_review` 且 `status=not_ready`。

### 2026-06-28 · Prediction Review Timeline

- `GET /api/v1/daily-plan/review` 已新增只读 `prediction_timeline` 合同。
- timeline 从已持久化的 `InterventionEvent.action_snapshot.prediction` 与窗口指标变化派生，不新增 DB schema、不新增 prediction 写入。
- ready backtest 会展开为 `prediction_created`、`action_executed`、`outcome_observed`、`review_verdict` 四类节点，保留 metric、status、confidence 与 observation/non-causal boundary。
- Mobile `/my-progress` 的 Daily Plan 复盘卡已展示预测时间线摘要、前四个节点和非因果边界。
- 本切片不新增诊断/处方/剂量/因果证明文案，不改变行动排序或自动重排。
- 已发布：backend SHA `280b572577b963b28b64b638450b0a33851ffdaf`；Mobile OTA group `37f226c1-2de2-4d15-bbcc-3387590e3e56`；生产 smoke `build_health_operating_review(user_id=3)` 返回 `backtest_status=not_ready timeline_count=0`。

### 2026-06-28 · Prediction Record Attachment MVP

- `PersonalPrediction` context 已通过统一 helper 进入 Trajectory/Agenda/Daily Plan action。
- Daily Plan feedback/event 写入执行事件时，会把 carried context 标准化为 `prediction_record`，作为 Review backtest 的稳定输入。
- Review backtest result 已保留模型和证据 metadata：`source_model`、`prediction_type`、`domain`、`unit`、`uncertainty`、`evidence_tier`、`model_version`、`review_hint`、`requires_clinician`。
- 低置信预测仅作为复盘记录携带，继续暴露 uncertainty/evidence tier/boundary，不新增行动、不触发自动干预、不做因果证明。
- Mobile `healthOperatingReview` service 已同步 additive metadata 类型；本切片不新增可见 UI。
- 已发布：backend SHA `c47cd109749433ffad35c73af30c81802a9fe212`；Mobile OTA group `20d8c133-08f5-4873-9bda-c9d450fc3d5a`；后端部署健康分 `60/60`。

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

### 2026-06-28 · Mac Connector Health Surface

- Mac Core 已新增 `DataConnection`、`ConnectorPolicy`、`DataConnectionHealth`、旧后端 fallback 和 display mapping。
- Mac sidebar 与 command palette 已新增“数据连接与授权”入口。
- Mac `DataConnectionsView` 已只读展示连接状态、授权 scope、最近同步、token 状态摘要、缓存可用性和 degraded explanation。
- 本切片不显示 token、不新增重连 flow、不做撤权删除、不新增 provider 写路径。
- 已发布：Mac code commit `55964db040a0952063df1824488a93cc6687c155`；`swift test --package-path apps/mac --filter HealthAgentMacCoreTests` 通过 259 tests / 1 skipped / 0 failures；`apps/mac/scripts/package-app.sh --install --open` 已安装并打开 `/Applications/健康 Agent.app`。
