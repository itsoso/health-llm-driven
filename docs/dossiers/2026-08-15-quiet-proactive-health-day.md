# Dossier: Quiet Proactive Health Day

| 字段 | 值 |
|---|---|
| slug | `quiet-proactive-health-day` |
| 创建日期 | 2026-08-15 |
| 当前阶段 | S3 规划 |
| 状态 | blocked_at_g2 |
| 负责 | Codex |
| 反馈环 | product definition / architecture review / later TDD + shadow rollout |

## S0 · 用户需求

用户希望系统真正管理一个人全方位的健康,覆盖饮食、睡眠、补剂打卡、日常日程、锻炼、用药和复查;期望交互方式是:

> 安静主动型,但可以查询并且可以修改和调整。

用户已逐节确认产品形态、Mobile 体验、后端对象脊柱、主动/失败策略和分期验证方向。

## S1 · Discovery

### 外部参考

审计 `/Users/liqiuhua/work/personal/deepseek-harness` 后,确认值得借鉴的是统一 tool pipeline、turn/step lifecycle、真实 assembled snapshot、可回放事件和有界并发;不移植 Cordis/plugin runtime、shell 自修改或另一套工具注册系统。

### 仓库现状

- `docs/system-map/mobile-nav-map.md` 与代码证明 Mobile 已是 Chat-first:tab bar 隐藏,`/(tabs)/index` 重定向 `/chat`,Today 是二级详情。
- `docs/system-map/product-map.md` 原先仍写多可见 tab,本定义切片已纠正该现状叙事;未改代码派生计数。
- `backend/app/services/daily_operating_plan.py` 已有跨域 DailyOperatingPlan,但 `build_daily_operating_plan` 混合计算与 upsert/commit。
- Chat/Today 当前都消费 `/timeline/today`;Phase 1a 必须把该 compatibility projection 纳入 backend/service assembled diff。
- `mobile/app/day-schedule.tsx` 仍写工作时间并记录药/补剂依从,不是可直接退役的 read adapter;`mobile/app/timeline.tsx` 是近 30 天历史事件流,不属于同一个迁移对象。
- `day_schedule_service` / `timing_solver` 已覆盖药、补剂、饮食、睡眠、锻炼、复查与 calendar constraints。
- Agenda/rolling runtime 已有可执行 item、反馈重排、provenance 和 1-14 天 projection。
- Daily Artifact / Today DynamicView 已有 one top action、runtime adapter 和 safety floor。
- `docs/specs/active/2026-07-17-xiaoba-agent-kernel.md` 已定义统一 intent/capability/ToolGateway/receipt,无需 Health Day 专用自然语言执行器。
- `docs/specs/active/2026-06-26-notification-interruption-budget.md` 和代码显示 P0/P1/P2、普通 quiet hours、09:00 morning sleep floor 与预算是不同裁决维度;prescribed reminder 与 P0 cap 的合同需要在主动放量前单独压测/裁决。

### 文档真源清理

- 产品方向:更新 `docs/prd/2026-06-19-proactive-planning-prd.md`。
- v2 唯一详细合同:新增 `docs/specs/active/2026-08-15-quiet-proactive-health-day.md`。
- 实施选择/迁移蓝图:新增 `docs/plans/2026-08-15-quiet-proactive-health-day-design.md`,不复制规范真源。
- 领域 timing/safety baseline:`docs/specs/active/2026-06-22-time-driven-health-management.md`,已加 scope handoff。
- shipped rolling runtime:`docs/specs/active/2026-06-28-rolling-7-day-health-runtime.md`,已收窄到只读 projection。
- `docs/specs/deprecated/2026-06-27-rolling-7-day-health-runtime.md` 已明确 superseded,不再作为实现合同。

## G1 · 准入裁决

- first_class_objects:`HealthProblem`, `HealthProgram`, `HealthProtocol`, `DailyOperatingPlan`, `HealthAgendaItem`, `ExecutionEvent`, `WriteIntent`, `InterventionCycle`。
- core_loop_step:observe -> decide next action -> execute/adjust -> verify -> review。
- target_surface:Mobile Chat-first shell + Today/Agenda detail;Watch execution;Mac planning/review;Backend source of truth。
- safety_level:L3 health data + medical boundary + write boundary。
- autonomy_tier:read/rank/remind 可自动;material mutation 默认 manual_confirm。
- smallest_end_to_end_slice:internal read-only composer -> canonical snapshot manifest/keyed digest -> assembled legacy diff;无 API/客户端/DB write/materialization/push。
- stale_surface:重复 planner glue 和经 ownership migration + 动态点击/依赖审计证明的重复 UI;保留 `/timeline/today` compatibility、Day Schedule 写职责和历史事件 Timeline,直到各自条件满足。
- spec_required:yes,涉及跨端可见行为、主动触发、写路径与通知。
- **裁决: PASS**。

## S2 · PRD

- 权威产品方向:`docs/prd/2026-06-19-proactive-planning-prd.md` §0.1/§6。
- v2 选择 Chat-first 小巴单入口,Health Day 摘要嵌入主壳;Today/Agenda 展开详情,不恢复多 tab。
- 固定承诺、自适应行动、机会行动三层和五阶段 roadmap 已确认。

## S3 · 规划

- Feature Spec:`docs/specs/active/2026-08-15-quiet-proactive-health-day.md`。
- 设计/迁移蓝图:`docs/plans/2026-08-15-quiet-proactive-health-day-design.md`。
- Phase 1a 只做 internal read-only shadow;不改 API/客户端,不写 DB、不物化计划、不 mutation、不推送。
- Phase 2 收敛 Chat shell + Today detail;Phase 3 统一 mutation;Phase 4 才放 quiet proactive triggers;Phase 5 review/retirement。

## G2 · 可行性 + 安全压测

**裁决: BLOCK。** 双轮只读架构/安全压测已完成,发现 authorizing snapshot、健康 mutation 和主动通知合同均未达到可交付条件。不得让 Phase 2-4 进入交付环。

Gate 语义:本 umbrella G2 的退出证据是批准后的架构/安全合同以及 migration/test/rollback 设计,不要求先实现 schema 或取得 G3/G4 测试结果。umbrella G2 PASS 后,Phase 2/3/4 各自建立子 Dossier 和 phase-specific G2,再进入 S4/S5 实现与 G3/G4,避免“禁止实现但又要求实现后才能过 G2”的循环。

已完成第一轮只读架构审查,并据此修正:

- 阻止 PRD、6/22 spec 和 design plan 三重真源;
- 保留 Chat-first 现状,避免无意反转 IA;
- 把可继续工作的最小切片收窄为 Phase 1a pure composer + internal shadow diff;
- 区分 Health Day plan version 与 DynamicView context hash;
- 区分 read-only rerank、mutation preview 和 confirmed write;
- 把 notification budget/quiet-hours 裁决交回现有权威合同;
- 证实现有 content hash 不能防 A→B→A、WriteIntent 不具备通用 version/CAS/expiry/receipt 合同;
- 证实 occurrence identity、pre-write SafetyGuardian、atomic notification outbox 和 emergency delivery policy 是安全前置。

G2 blocker:

1. canonical snapshot owner + PostgreSQL read-only repeatable-read/exported snapshot + server-owned monotonic generation;不得以内容 hash 或 wall-clock cutoff 充当一致性/授权版本;
2. stable internal occurrence identity + rotatable short-lived authorization token、多剂次与 fixed commitment 在 SafetyGuardian veto 下的 `actionable=false` 语义;
3. WriteIntent additive migration:version/generation/preview digest/expiry/atomic CAS/owner-scoped idempotency/operation/receipt states;
4. 所有健康 mutation 在副作用前过 deterministic SafetyGuardian;rollback 不得关闭 owner/version/safety/idempotency gates;
5. `emergency_safety` 与 `scheduled_required` 拆 tier,并指定只有 allowlisted deterministic SafetyGuardian rule/severity 可升级 emergency,防止 producer/LLM 自报或 morning floor/普通预算延迟真正急症;
6. owner-scoped atomic notification reservation/outbox schema/唯一约束、同事务预算 reservation、每次 egress 前 generation/source/occurrence/safety/deadline revalidation、generation-only same-key reauthorization、material-change supersession、flush CAS、same-key retry 与 receipt taxonomy;
7. calendar freshness/tombstone/timezone/unknown policy;stale/unavailable 不得被当 free window;
8. mutation `verifying` 与 notification `verifying_unknown` 两张 canonical state/receipt transition 表成为 adapter 唯一词汇,统一 `completed`,并拆开 device delivered/surface visible/notification interacted/health action committed,为每类 operation 声明 required receipt level;
9. Day Schedule 的 work-hours/medication adherence ownership 与 occurrence command migration,避免把有写职责的 surface 当 adapter;
10. domain-separated HMAC 的 L4 key/key_id、length-prefixed canonical bytes、rotation/expiry/fail-closed migration/test 设计与隐私审计;
11. `contract_complete=false`/degraded evaluation 到新 Health Day producer 的直接 fail-closed adapter 接线;
12. PostgreSQL 下的 A→B→A、双端确认、timeout、跨用户、双 worker 和 provider `verifying_unknown` 压测。

允许的下一步只有另立 **Phase 1a read-only shadow 子 Gate/Dossier**:无客户端可见变化、无计划物化副作用、无 mutation、无 proactive push。它通过不代表本 Dossier 的 G2 通过。

## S4 · 需求分解

整体交付环被 G2 阻断。可单独为 Phase 1a read-only shadow 建 implementation plan 和原子任务;Phase 2-5 必须等待本 Dossier G2 对合同与 migration/test/rollback 设计重新评审并 PASS,随后各自建子 Dossier/G2,不得捆绑推进。

## G3 · 测试闸

待实现。Phase 1a 要求 pure/no-write proof、deterministic manifest/digest、real assembled legacy diff、user-local/DST/calendar unknown 和 L3 telemetry 最小化。未来 G3 还必须覆盖同药多剂次、fixed+safety conflict、A→B→A、双端 confirm、跨用户相同 key、双 notification worker、provider timeout→`verifying_unknown`、reserve 后 supersede/cancel、offline expiry 与 receipt claim levels;helper-only mock 不足以通过。

## G4 · 安全闸

待实现后独立 review。重点:false write、fixed commitment 丢失、SafetyGuardian bypass、L3 日志泄露、无 receipt 成功声明、推送隐私与 medication reminder policy。

## S6/G5 · 部署健康

待实现。Phase 1a shadow 不改变用户可见行为且无 DB/notification 副作用;后续各 flag 可独立关闭。任何 Gate 失败回到上游,不带红发布。

## S7/G6 · 上线验证

待实现。核心口径:下一步可识别率、完成/跳过、mutation verified success、版本冲突、通知关闭/投诉、每周带 verification plan 的完成行动和重复页面流量下降。

## S8 · 沉淀

定义阶段已完成文档真源去重和现状 system-map 叙事纠偏。代码/导航/架构结构实际变更后必须重新生成 system map,并在本 Dossier 记录每道 Gate 的真实裁决与证据。
