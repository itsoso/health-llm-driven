# 安静主动型 Health Day 收敛设计

> 状态: accepted product direction · engineering G2 BLOCKED
> 日期: 2026-08-15
> 规范真源: `docs/specs/active/2026-08-15-quiet-proactive-health-day.md`
> 产品真源: `docs/prd/2026-06-19-proactive-planning-prd.md` §0.1/§6
> Dossier: `docs/dossiers/2026-08-15-quiet-proactive-health-day.md`

本文件记录实现选择、迁移顺序和验证方法。对象/API/安全/surface 的规范合同只在关联 Feature Spec 维护,不在这里复制第二份真源。

## 1. 经确认的体验方向

- 系统以安静主动方式组织饮食、睡眠、用药/补剂、复查、日历和锻炼。
- 自动观察、分析、排序和到点提醒;实质修改先预览,确认后才执行。
- 用户随时可以问“今天还有什么/为什么这样排”,也可以说“把锻炼改到 7 点”。
- 一天包含固定承诺、自适应行动和机会行动;只调整尚未执行的未来自适应/机会项。
- Mobile 保持现有 Chat-first 小巴主壳。打开 App 就在小巴里看到 now/next 和一个 top action;Today/Agenda 是完整日程详情,不是新的并列首页。
- Watch 低摩擦执行,Mac 负责复杂计划和复盘。

## 2. 代码现状与迁移 seam

### 2.1 可直接复用

| Existing seam | Reuse |
|---|---|
| `daily_operating_plan.build_daily_operating_plan` | 当前跨域当天策略与验证窗口。 |
| `day_schedule_service` + `timing_solver` | medication/supplement/diet/sleep/movement/checkup 时点和冲突。 |
| `agenda_service.runtime_range_view` | 1-14 天可执行 projection、feedback-driven replan 和 provenance。 |
| `/timeline/today` + `today_timeline_service` | 当前 Chat/Today 实际消费的 now/item compatibility projection;Phase 1a 必须纳入 assembled diff。 |
| `daily_artifact_service` | 从 runtime 选一个 top action。 |
| `today_dynamic_view_service` | 组合 Daily Artifact、runtime 和安全卡的受控 DynamicView。 |
| `agent_kernel` | `IntentFrame -> CapabilityPolicy -> ToolGateway -> receipt`。 |
| `WriteIntent` + completion/event APIs | 只作为 manual-confirm / execution-event 基础。现有模型尚无通用 snapshot generation 绑定、一次性 CAS、过期、owner-scoped 幂等唯一键和分层 receipt;Phase 3 前必须 additive migration。 |
| Mobile `/chat`, `/today`, `/agenda` | Chat-first shell、今日详情和管理详情。 |

### 2.2 必须先消除的结构债

1. `build_daily_operating_plan` 当前把计算和 DB 物化放在同一函数,读取会更新快照。
2. Schedule、Daily Plan、Agenda/runtime 与 Daily Artifact 仍可能分别组装/排序。
3. plan/item 没有统一 occurrence identity 和 server-owned monotonic generation,跨端 mutation 可能基于过期视图,内容 hash 还存在 A→B→A 重放。
4. DynamicView 可以组合多个读模型,但还没有强制每张卡引用同一 item id/version。
5. `/timeline/today` 是当前 Chat/Today 读 seam;`mobile/app/day-schedule.tsx` 仍拥有工作时间设置和 medication/supplement adherence 写入;`mobile/app/timeline.tsx` 则是近 30 天历史事件流。三者不能统称“重复时间线”或直接降成 adapter。
6. notification P0 同时承载真正急症和 scheduled-required reminder,现有 morning floor/预算/去重又不是原子合同;Health Day 主动推送不得直接继承。
7. system-map 的 `product-map.md` 曾写可见多 tab,与实际 Chat-first 代码/`mobile-nav-map.md` 漂移,本定义切片同步纠正叙事真源。

## 3. 实现结构

### 3.1 提取纯 composer

把 Health Day composer 做成内部 facade,不创建新 DB model:

```text
load immutable source snapshot (user timezone + revisions + freshness)
  -> SafetyArbiter
  -> FixedCommitmentResolver
  -> ScheduleResolver
  -> ActionRanker
  -> PlanProjector
  -> Phase 1a internal shadow diff
  -> future explicit snapshot persistence / adapters / notifications (G2-gated)
```

建议分离的函数边界:

- `load_health_day_context(...)`:只读并返回每个 provider 的 result/error/freshness;
- `compose_daily_operating_plan(context)`:纯计算,无 DB commit、推送和外部动作;
- `project_health_agenda_items(plan)`:把 plan actions 投影成 canonical item;
- `materialize_daily_operating_plan(...)`:未来显式写 current snapshot;不属于 Phase 1a;
- `build_health_day_summary(...)`:给 Chat shell/Today/Watch 的 presenter adapter。

来源读取可有限并行,但要有 per-source timeout、确定性 merge 顺序和 degraded reason。任何失败都显式进入 projection,不能静默当成空数据。

### 3.2 Shadow digest 与未来授权版本

Phase 1a 只有内部 `shadow_manifest_digest`:对 owner、schema 和完整 source manifest 做 domain-separated keyed HMAC,使用规范化 JSON 与 L4 server key/key_id,用于同输入确定性与 legacy assembled diff。它不是客户端 token,不写计划、不授权 mutation,也不暴露可枚举的原始健康事实 hash。key rotation/previous-key expiry 以 Feature Spec 合同为准。

任何客户端版本或写授权必须等 G2 通过后再引入:

```text
snapshot_generation = server-owned monotonic counter per owner + user-local day
plan_version = HMAC(owner, local_day, schema, snapshot_generation, manifest_digest)
occurrence_id = stable server-issued opaque UUID mapped to owner + source + local day + slot/dose ordinal
occurrence_token = HMAC(owner, occurrence_id, source_revision, snapshot_generation, expiry)
```

- `snapshot_generation` 防止 A→B→A 时旧 preview 再次匹配;内容相同也不能复用旧授权。
- stable `occurrence_id` 是 terminal fact 的 durable identity;轮换 key 只重签短期 `occurrence_token`,不能让完成剂次复活。
- 当前快照优先继续复用 `daily_operating_plans`,但所有 adapter 只能读取同一 server-owned snapshot/generation。
- mutation 绑定 owner、generation、occurrence、immutable preview digest 与 expiry;不匹配返回 409 + 新 preview,绝不继承旧授权。
- 审计只存受控 reason/source enum、opaque id、generation 和最小脱敏摘要;不存 raw fact hash 或完整 before/after L3 文本。
- 若后续需要完整 plan replay,先以真实审计需求证明再考虑 revision persistence,不预建第二套 Health Day 表。

### 3.3 Adapter 规则

- Daily Artifact 从 canonical items 选一个 top action,不再次 rank。
- Chat shell 摘要只显示 now/next、一个 top action 和必要的安全/新鲜度异常。
- Today detail 按“现在 / 今日重点 / 今日日程 / 快速记录”展示同一版本。
- Agenda 提供 1/7 日管理详情;`/timeline/today` 暂作当前 Chat/Today compatibility projection,未来只从 canonical snapshot 投影。
- Day Schedule 保持现有工作时间设置和服药/补剂打卡职责,直到这些写操作迁移到 typed occurrence commands 并通过 receipt 测试;在此前它不是 read-only adapter。
- `mobile/app/timeline.tsx` 是历史健康事件流,不属于 Health Day 重复页退役范围。
- Watch/Mac 必须保留相同 item id、status、source ref 和 plan version。

### 3.4 Mutation 接线

不新增 Health Day NLP 路由。给现有 Agent Kernel 增加 typed operations 和 item binding:

```text
TurnSnapshot(occurrence_id, plan_version, source_ref)
  -> read | execute | mutate
  -> CapabilityPolicy + pre-side-effect SafetyGuardian
  -> preview if mutate
  -> confirm
  -> atomic WriteIntent CAS(pending -> executing)
  -> idempotent ToolGateway execution / verifying on timeout
  -> typed receipt verification
  -> future-only recompose
```

完成/跳过只作用 stable occurrence-level item,并在多剂次、owner isolation、token rotation 和幂等测试通过后复用 execution event。新增/删除/启停/实质移动或 cadence 调整复用 additive-migrated `WriteIntent`;它必须带 generation、expected version、stable occurrence id + short-lived token、preview HMAC、expiry、owner-scoped idempotency key、operation id 和 canonical states。处方、剂量、疗程、复查下限、购买和付费保持逐项强确认。所有健康写入在副作用前执行确定性 SafetyGuardian;receipt 后只核验结果/新风险。

## 4. 从 deepseek-harness 借鉴什么

只借结构纪律,不移植其 runtime:

- 统一 pipeline:对应现有 Agent Kernel,Health Day 只补 capability mappings。
- turn/step lifecycle:composition、preview、confirm、tool result、receipt、recompose 都有明确事件。
- assembled snapshot:测试真实 API/DB/事件序列,不只测 helper mock。
- replayable audit:owner-scoped idempotency key、monotonic generation、keyed preview digest、最小脱敏变更摘要和 typed receipt。
- bounded concurrency:provider 并行读取有上限、超时和可归属错误。

不借 Cordis/plugin 容器、shell 自修改或另一套工具注册系统;这些会扩大健康安全边界且与现有 kernel 重复。

## 5. 分期迁移

### Phase 1a · Internal read-only shadow

- 提取无副作用的 context loader / pure composer;现有物化逻辑保持不动,不从新路径调用。
- 定义内部 snapshot manifest、occurrence projection、非授权 `shadow_manifest_digest` 和 deterministic diff。
- shadow 生成 Health Day artifact,在 backend/service fixture 层与 Daily Plan、Agenda/runtime、Schedule、Daily Artifact/DynamicView 和 `/timeline/today` 真实 assembled 输出做 diff;不得通过 mount Today 来证明纯度,因为当前 Today mount 启动本地提醒副作用。
- 不新增/修改 API、客户端、DB 行、通知或 materialization;默认用户行为完全不变。

Phase 1a 可以单独做 implementation plan 和独立 Gate;它不能被描述为已经解决未来 authorizing snapshot 或 mutation 合同。

### Phase 2 · Chat shell + Today detail

- 前置:umbrella + phase-specific G2 已批准 authorizing snapshot/generation、migration/test/rollback 设计。migration 属于本阶段 S4/S5;PostgreSQL 证据在 G3/G4 裁决,不作为实现前 G2 的循环前置。
- 小巴主壳首屏嵌入 now/next + one top action。
- Today detail 落四段,所有动作携带 occurrence/version context。
- Agenda 和 `/timeline/today` compatibility path 保留;Day Schedule 的工作时间/依从写入口在迁移完成前保留;不恢复 tab bar。

### Phase 3 · Unified mutation

- 前置:umbrella + phase-specific G2 已批准 occurrence identity、WriteIntent schema/CAS/expiry/idempotency/receipt、pre-write SafetyGuardian 和 owner-isolation 设计;实现后再过 G3/G4 才放量。
- 补 Health Day intent/capability/tool mappings。
- 实现 preview、一次性 confirm、version conflict、timeout verification 和 typed receipt。
- 先开低风险 move/snooze/enable/disable;医疗与付费自治不升级。

### Phase 4 · Quiet proactive triggers

- 前置:umbrella + phase-specific G2 已批准 emergency/scheduled-required 分类权威、atomic notification outbox/pre-send revalidation、calendar unknown policy 和 receipt taxonomy 设计;实现后再过 G3/G4 才放量。
- 为 morning、material health signal、material calendar change、execution feedback、user adjustment 建 shadow trigger。
- 加 materiality filter,只改 future adaptive/opportunity items。
- 逐类放量,接 notification budget、prescribed-reminder invariant 和 push privacy backstop。

### Phase 5 · Review and retirement

- 晚间一分钟复盘、周复盘和 InterventionCycle suggestion。
- 只有在 Day Schedule 的工作时间/服药依从 ownership 完整迁移、动态点击/依赖审计确认替代路径后,才考虑收敛它的 UI。
- 历史健康事件流 `mobile/app/timeline.tsx` 不因 Health Day 收敛而退役。
- 删除旧 planner glue 后重生成 system map。

## 6. 验证设计

### Deterministic planner

- 同完整 manifest 同 canonical shadow output/digest;
- user-local date、DST、跨日;
- 同药同日多剂次 occurrence 不碰撞;
- fixed item 不因 rank/普通预算消失;安全冲突时仍可见但 `actionable=false`;
- 小波动不 full recompose;
- 只改未来未执行 adaptive/opportunity;
- stale/degraded provider 可见;calendar tombstone/跨时区/跨午夜不会被当空闲。

### Write and safety invariants

- stale preview 必须 409;
- A→B→A 旧 preview 永远不能重放;
- 两端同时确认、double-click/timeout 只产生一个真实写;
- cross-user 相同 idempotency key/receipt lookup 必须 404/deny且不泄露新 preview;
- 无 receipt 不宣称成功;
- SafetyGuardian rejection 不被 LLM/adapter/replan 覆盖;
- prescription/dose/course/recheck floor 无模糊批量 mutation;
- prescribed reminder 和 push privacy 正反例;
- 两 worker 同时处理同 dedupe key 只能一个 reservation;provider timeout 用同 key 核验/重试,不能盲发;
- reserve 后停药/改时点/取消/新 safety veto 在每次 provider egress 前转 `superseded/cancelled/expired`,零发送;
- unrelated generation change 对仍相同 occurrence 做同 key reauthorization;只有 material occurrence/timing/safety 变化才 supersede 并换 candidate key;
- 只有 allowlisted deterministic SafetyGuardian rule 可赋 `emergency_safety`。

### Real assembled snapshots

- one read-only PostgreSQL repeatable-read snapshot + external revision fixtures -> composer -> Daily Plan/Agenda/Schedule/DynamicView/`timeline/today` JSON;
- `/agent/stream`:intent -> policy -> preview -> tool result -> receipt -> turn end;
- recompose 前后只有预期 item 改变;
- stale calendar、delete/tombstone、跨时区、composer exception、write timeout、offline replay、version conflict。

### Cross-surface journey

- cold start `/chat` -> 看见下一项 -> inline 完成 -> shell 刷新;
- Chat 调整 -> preview/confirm/receipt -> Today/Watch 同版本;
- Watch 完成 -> Chat/Today 同 item 熄灯;
- Mac 调整 -> Mobile 新版本;
- offline queued write -> expiry/reconnect conflict -> fresh preview + reconfirm,绝不后台 auto-confirm。

## 7. 关键取舍

- 不新增 `HealthDayPlan`:避免和 DailyOperatingPlan/Agenda 双真源。
- 不把 UI 合并当成后端收敛:否则一致性和 stale mutation 仍存在。
- 不改回 Today-first tab:保留已经落地的 Chat-first agent-native shell,把 Health Day 作为其每日状态。
- 不让 LLM 直接规划/写库:LLM 只解析和解释。
- 不先删旧 route:先区分 today compatibility API、带写职责的 Day Schedule 和历史事件 Timeline;完成 ownership migration + traffic/dependency audit 后只收敛真正重复的 UI。
- 不把购买/硬件 provider 设为主路径依赖。

## 8. Gate 状态与 implementation planning 边界

产品方向已经确认,但整体工程 **G2 BLOCKED**。只有 Phase 1a 可另立严格只读的 implementation plan;该计划不得包含 API/客户端/物化/mutation/push。

本 umbrella G2 的退出证据是确定的架构/安全合同 + migration/test/rollback 设计,不是已经实现的 schema 或通过 G3/G4。umbrella PASS 后,Phase 2/3/4 各立子 Dossier 和 phase-specific G2,再进入实现与测试,避免 Gate 循环。

Phase 1a 仍需在计划中明确:

1. canonical manifest 的 owner/user-local/cutoff/source revision/freshness/error/tombstone 结构;
2. 如何调用纯 composer 而不触发 `DailyOperatingPlan` 现有 read-upsert/commit;
3. assembled legacy diff 的确定性口径、脱敏 telemetry 与 no-write 证明。

Phase 2/3 的 G2 blocker:

- server-owned monotonic snapshot generation 与唯一 snapshot owner/materialization 模式;
- stable occurrence identity + rotatable authorization token、多剂次和 fixed-vs-safety 可执行语义;
- WriteIntent migration、原子 CAS、expiry、owner-scoped idempotency、timeout verification 与 receipt state machine;
- 所有健康 mutation 的 pre-side-effect SafetyGuardian 和不可回退 invariant gates。

Phase 4 的 G2 blocker:

- `emergency_safety` 与 `scheduled_required` 的 delivery policy 拆分;
- owner-scoped atomic notification reservation/outbox、预算/去重/重试与 receipt taxonomy;
- `contract_complete=false`/degraded evaluation 到 Health Day adapter 的直接 fail-closed 接线,以及统一 `verifying_unknown` vocabulary;
- calendar stale/unavailable 的 negative-knowledge policy 和新 producer 的 fail-closed fallback。

provider、硬件和经 ownership/traffic 审计后确认可收敛的重复 UI 顺序仍可后置;它们不阻塞 Phase 1a。历史事件 Timeline 不属于该清理队列。
