# Feature Spec: Quiet Proactive Health Day

> Status: draft · G1 passed · G2 blocked
> Owner: Reva / Personal Health OS
> Updated: 2026-08-15
> Related PRD/PDD: `docs/prd/2026-06-19-proactive-planning-prd.md` · `docs/plans/2026-08-15-quiet-proactive-health-day-design.md`
> Related specs: `docs/specs/active/2026-06-22-time-driven-health-management.md` · `docs/specs/active/2026-06-28-rolling-7-day-health-runtime.md` · `docs/specs/active/2026-07-17-xiaoba-agent-kernel.md` · `docs/specs/active/2026-06-26-notification-interruption-budget.md` · `docs/specs/active/2026-06-26-surface-ownership-inventory.md`
> Related code: `backend/app/services/{daily_operating_plan,day_schedule_service,agenda_service,daily_artifact_service,today_dynamic_view_service}.py` · `backend/app/services/agent_kernel/` · `mobile/app/(tabs)/{chat,today}.tsx`

## 1. Decision

把现有 Daily Plan、Schedule、Agenda、rolling runtime、Daily Artifact 和 Today DynamicView 收敛成一份带版本的每日健康投影。Mobile 保持现有 **Chat-first 小巴主壳**:打开 App 先看到 Health Day 摘要和下一步,需要管理完整日程时进入 Today/Agenda 详情;查询和修改在同一对话上下文内完成。

本 spec 是 Health Day v2 的 composer、跨端投影、查询/修改和主动重排权威合同。领域时点与安全规则仍归 `2026-06-22-time-driven-health-management.md`;滚动 7 天只读 projection 的已上线合同仍归 `2026-06-28-rolling-7-day-health-runtime.md`;自然语言执行边界仍归 XiaoBa Agent Kernel。

## 2. Problem

用户想让系统真正管理饮食、睡眠、补剂打卡、日常安排、锻炼、用药和复查,而不是分别打开多个页面自己拼计划。

当前能力已经很丰富,但日常体验仍有结构性裂缝:

- `DailyOperatingPlan`、Schedule、Agenda/runtime 和 Daily Artifact 可从不同入口组装/排序;
- Today、Agenda、`/timeline/today` 和 Day Schedule 表达相近内容,用户仍需理解产品结构;但它们并非都可直接退役:`/timeline/today` 是当前 Chat/Today read seam,Day Schedule 仍拥有工作时间和依从写入,而 `mobile/app/timeline.tsx` 是独立的历史事件流;
- 当前 plan 没有跨端版本 token,调整可能基于旧快照;
- query、completion、snooze 和 plan mutation 虽有底层能力,还没有统一到一个 Health Day 语义合同;
- 主动重排的 materiality、通知预算和失败降级没有被一个跨端 spec 共同钉死。

此外,Mobile 自 2026-07-03 起已经是 Chat-first 单入口,`/(tabs)/index` 重定向到 `/chat`,Today 是二级详情。如果重新把 Today 改成独立一级入口,会逆转现有 agent-native IA 并重新制造入口竞争。因此 v2 将 Health Day 嵌入小巴主壳,而不是恢复多 tab 或建立第二个首页。

## 3. Requirement Admission

```yaml
RequirementAdmission:
  request: "让系统安静主动地管理饮食、睡眠、补剂打卡、日程、锻炼等,并允许查询、修改和调整"
  classification: new_product_behavior
  first_user_fit: yes — 高带宽工作用户需要系统承担日程心算但保留最终控制权
  core_loop_step: observe -> decide next action -> execute/adjust -> verify -> review
  first_class_objects:
    - HealthProblem
    - HealthProgram
    - HealthProtocol
    - DailyOperatingPlan
    - HealthAgendaItem
    - ExecutionEvent
    - WriteIntent
    - InterventionCycle
  target_surface: Mobile Chat-first shell -> Today/Agenda detail; Watch execution; Mac planning/review
  source_of_truth: backend Health Day composer over existing DailyOperatingPlan + Agenda contracts
  safety_level: medical_boundary
  prescription_or_causal_verdict: none
  autonomy_tier: manual_confirm
  evidence_provenance: immutable source snapshot + freshness + safety decision + verified receipts
  claim_hedging: hedged
  verification_window: same-day execution + 7-day adherence + protocol-specific 4/8/12-week review
  success_metric: user knows the next action and can safely complete/adjust it from one daily shell
  added_user_burden: low
  burden_justification: one-tap confirmation only for material changes, replacing manual cross-page planning
  non_goals:
    - new HealthDayPlan table
    - automatic prescription/dose/course changes
    - automatic purchasing/payment
    - restoring a multi-tab daily navigation
  smallest_end_to_end_slice: internal read-only Phase 1a shadow artifact -> deterministic snapshot manifest/digest -> assembled diff against legacy outputs; no client, mutation, persistence side effect or push
  stale_surface_to_remove_or_archive: independent planner glue and only UI proven duplicate after command-ownership migration plus click/dependency audit; exclude historical event Timeline
  spec_required: yes
```

**G1 decision: PASS.** 需求直接强化现有核心环和一等对象,但因跨端、主动通知和写边界必须走独立 Feature Spec 与 safety review。

## 4. Non-Goals

- 不新增 `HealthDayPlan`、第二个 Agenda 或 Health Day 专用 ToolGateway。
- 不在第一阶段改变任何用药/补剂/复查事实或默认开启新协议。
- 不让 LLM 决定 safety、rank hard constraints、写权限或执行是否成功。
- 不把完整 7 天日历塞进小巴首屏;首屏仍只突出当前/下一项和一个 top action。
- 不恢复底部 tab bar;Today/Agenda 是从小巴上下文进入的详情/管理面。
- 不把外卖、挂号、购物、支付或硬件 adapter 设为核心日常闭环的前置依赖。
- 不在动态点击审计和跨端依赖清零前删除旧 route。
- 不把 `/timeline/today`、带写职责的 Day Schedule 和历史事件 Timeline 混成一个“重复时间线”迁移对象。

## 5. Product Object Mapping

| Object | Change |
|---|---|
| `HealthProblem` | 提供当前问题、风险、复查与长期优先级。 |
| `HealthProgram` | 作为计划中的 composer 输入 seam;当前 DOP/Agenda 尚未完整消费,Phase 1a 必须显式读取或标记 unsupported,不得写成已具备。 |
| `HealthProtocol` | 提供可重复行动、cadence、时间窗口和安全约束。 |
| `DailyOperatingPlan` | 未来成为当日跨域策略快照;authorizing generation/version/freshness metadata 受 G2 阻断,Phase 1a 不改模型。 |
| `HealthAgendaItem` | 未来成为唯一跨端 occurrence projection;occurrence/commitment/mutability/version 关联受 G2 阻断,Phase 1a 只产生内部 normalized item。 |
| `SafetyGuardian` | 在固定承诺解析、候选排序和 mutation 副作用前拥有确定性否决权;receipt 后只核验结果并标注新风险。 |
| `HealthTwin` | 提供 snapshot、置信度和来源新鲜度;不直接写计划。 |
| `HealthEvent` / `InterventionEvent` | 记录完成、跳过、延后、自动观察和 plan recompose audit。 |
| `WriteIntent` | 承载新增/删除/启停/实质时点或 cadence 调整的 before/after、确认和 receipt。 |
| `InterventionCycle` / `OutcomeReview` | 消费周复盘和 verification signals,只产调整建议。 |

`Health Day` 只是上述对象的产品投影名,不是一等持久化对象。

## 6. User Flow

### 6.1 Daily open

```text
App opens /chat
  -> backend returns versioned Health Day summary
  -> XiaoBa shell shows:
       now/next due item
       one Daily Artifact top action
       freshness or safety exception when needed
  -> user completes/defers/skips inline
     or opens Today/Agenda for the full day
  -> verified execution event
  -> future adaptive items recompose
```

### 6.2 Query or adjust

```text
"为什么今晚不适合跑步?" / "把锻炼改到 7 点"
  -> AgentEnvelope + TurnSnapshot(occurrence_id, plan_version, source_ref)
  -> IntentFrame(read | execute | mutate)
  -> CapabilityPolicy + SafetyGuardian
  -> read answer OR before/after preview
  -> explicit confirmation when mutate
  -> idempotent ToolGateway execution
  -> verified receipt
  -> new plan version and affected-future-items summary
```

### 6.3 Evening/weekly review

```text
evening prompt in shell or Today detail
  -> confirm omissions + capture skip reasons (< 1 minute)
  -> weekly aggregation of execution and metric changes
  -> InterventionCycle / protocol adjustment suggestion
  -> user confirmation for any material protocol change
```

## 7. Composition Contract

```text
calendar / wearable / labs / meds / supplements / symptoms / preferences / execution feedback
  -> immutable HealthTwin/source snapshot
  -> SafetyArbiter
  -> FixedCommitmentResolver
  -> ScheduleResolver
  -> ActionRanker
  -> PlanProjector
  -> DailyOperatingPlan + HealthAgendaItem-compatible projection
  -> Chat summary / Today / Agenda / Watch / Mac adapters
```

### 7.1 Commitment classes

| Class | Meaning | Replan rule |
|---|---|---|
| `fixed` | 处方/医嘱事实、到期复查、已确认 calendar commitment,以及用户明确启用且来源可追溯的补剂 protocol | 不得因 rank 消失;承诺/指令不可静默改变。`fixed` 不等于相同医疗风险、通知 tier 或 push 豁免。 |
| `adaptive` | nutrition focus、训练强度、恢复、winddown | 可只调整未来未执行项。 |
| `opportunity` | 空窗微运动、用眼/姿态和低压力建议 | 置信度不足、冲突或预算不足时可不出现。 |

每个可执行项是一个 occurrence,不是 source object 本身。Future authorizing snapshots use a server-issued stable `occurrence_id` (opaque UUID/internal identity) mapped under an owner-scoped unique key of canonical source + user-local date + scheduled slot/dose ordinal;同药一日多剂、同协议多次执行不得碰撞。Generic source revision is deliberately not part of durable identity:the short-lived signed `occurrence_token` binds source revision + current generation,so stale facts fail authorization without making an already completed dose reappear after an unrelated metadata update or key rotation. complete/skip/snooze 只作用该 occurrence。

固定承诺仍必须经过安全间隔和 calendar constraint。无法安全执行时保留医嘱/承诺的可见性,但 occurrence 转为 `blocked | conflict | deferred`、`actionable=false`,显示安全原因/升级路径;不得一边保留 fixed 一边提示“现在执行”,也不得为了解冲突静默改处方或 clinician floor。

### 7.2 Purity and determinism

- composition 输入必须是一份 snapshot manifest,至少含 owner、user-local date/timezone、`as_of`、schema version,以及每源 revision/acquired_at/freshness/error/tombstone;
- composer 本身不得 commit DB、发送通知或执行外部动作;
- 当前 `build_daily_operating_plan` 的计算与物化应拆开;只读 surface 不隐式更新计划行;
- Phase 1a 同一完整 manifest 必须得到同一规范化输出和非授权 `shadow_manifest_digest`;
- 来源可有界并行读取,但 merge 顺序、超时和 degraded reason 必须确定;
- PostgreSQL-owned sources 必须在同一 read-only `REPEATABLE READ` transaction snapshot(或同一 exported snapshot)读取;仅共享 wall-clock cutoff 不能替代 MVCC 一致性。无法加入该 snapshot 的异步/外部来源必须标成 external,携带 revision/acquired_at/cutoff 并进入 freshness/degraded 裁决;
- calendar manifest 必须包含 timezone、all-day/cross-midnight 语义和 deletion/tombstone;stale/unavailable 是 unknown,不能解释为 free window,不能触发 opportunity push 或自动移动;
- 来源失败必须可见,不得空 catch 后当作“没有健康问题/没有日历冲突”;
- `date.today()`、China-day 与 user-local-day seam 必须进入 Phase 1a inventory;manifest 未完整前不得计算可授权版本。

## 8. Data Contract

### 8.1 Phase 1a read-only shadow (only current implementation candidate)

Phase 1a has no client/API contract change, no plan materialization, no mutation and no push. It produces one internal canonical shadow artifact and compares it at backend/service-fixture level with assembled legacy outputs from Daily Plan, Agenda/runtime, Schedule, Daily Artifact/DynamicView and the current `/timeline/today` compatibility projection. It must not mount Today as a purity oracle because the current Today mount schedules local medication/behavior reminders.

```yaml
shadow_artifact:
  shadow_run_id: non-authorizing internal id
  shadow_manifest_digest: keyed digest of the complete snapshot manifest
  schema_version: health_day_shadow.v1
  plan_date: user-local date
  as_of: cutoff timestamp
  status: current | stale | degraded
  sources:
    - source_kind
      revision
      acquired_at
      freshness
      error_code
      tombstone
  items: normalized occurrence projections
  legacy_diff: missing | extra | rank_changed | timing_changed | safety_changed
apis: []
db_writes: []
notifications: []
client_changes: []
```

`shadow_manifest_digest` is an HMAC/keyed digest over owner + schema + canonical manifest. It is internal observability metadata, not a future confirmation token and never contains or exposes a raw low-entropy medication/safety fact hash.

All Health Day keyed digests and authorization tokens use HMAC-SHA-256 with independent HKDF-derived keys from an L4 server-side key service/environment secret. The signed bytes are a length-prefixed tuple of the explicit domain label (`health-day-shadow-v1`, `health-day-plan-v1`, `health-day-occurrence-token-v1`, `health-day-preview-v1`) and deterministic UTF-8 RFC 8785/JCS canonical JSON;ad-hoc string concatenation is forbidden. The opaque token carries a non-secret `key_id`; key material never enters logs, clients or DB payloads. Unknown `key_id`, canonicalization error or signature failure is fail-closed. Rotation accepts a bounded previous key only until the associated snapshot/preview expiry, then rematerializes a higher generation and re-signs the same stable `occurrence_id`;terminal execution facts reference that stable internal identity and are never rewritten. Raw SHA hashes and one shared undifferentiated HMAC domain are forbidden.

### 8.2 Future authorizing snapshot (blocked by G2)

Before any client display or mutation relies on a version, the server must own a monotonic generation per owner + user-local day. Content hash alone is forbidden because an A→B→A sequence can replay an old authorization.

```yaml
authorizing_snapshot:
  plan_id: existing DailyOperatingPlan id
  snapshot_id: opaque server id
  snapshot_generation: monotonic integer per user + local day
  schema_version: health_day.v1
  plan_version: HMAC(owner, local_day, schema_version, generation, manifest_digest)
  generated_at: iso datetime
  composition_reason: morning | health_signal | calendar_change | execution_feedback | user_adjustment
  status: current | stale | degraded
  manifest: bounded source revisions/freshness/errors
item:
  occurrence_id: stable server-issued opaque UUID mapped to owner + canonical source occurrence
  occurrence_token: HMAC(owner, occurrence_id, source_revision, snapshot_generation, expiry)
  commitment_class: fixed | adaptive | opportunity
  delivery_class: emergency_safety | scheduled_required | actionable | informational
  mutability: immutable_instruction | confirm_to_change | feedback_only
  lifecycle: pending | blocked | conflict | deferred | completed | skipped | expired | cancelled
  actionable: boolean
  source_ref: canonical owner reference
  complete_ref: occurrence-specific completion reference
  why_now: bounded reason codes plus display inputs
  safety: deterministic decision summary
```

`delivery_class` is independent from `commitment_class`:a fixed medication occurrence is not automatically an emergency, and an emergency safety event does not consume the ordinary wellness budget contract.

The current snapshot may remain in `daily_operating_plans`; no `HealthDayPlan` table is added. Whether explicit materialization is synchronous or background is a G2 implementation decision, but all adapters must load one server-owned snapshot/generation rather than independently minting authorizing versions.

### 8.3 Phase 3 mutation schema (blocked; additive migration required)

Existing `WriteIntent` is only a manual-confirm foundation. It does not yet provide the generic version binding, expiry, CAS lifecycle or durable receipt guarantees required here.

```yaml
write_intent_additions:
  snapshot_generation: required
  expected_plan_version: required
  occurrence_id: required when item-scoped
  occurrence_token: required when item-scoped; short-lived authorization,not durable identity
  preview_digest: immutable HMAC of normalized before/after
  expires_at: required
  idempotency_key: owner-scoped unique
  operation_id: stable across timeout verification
  status: pending | executing | verifying | executed | failed_retryable | failed_terminal | dismissed | expired
confirm:
  atomic_transition: pending -> executing
  checks: owner + generation + stable occurrence_id + occurrence_token + preview_digest + expiry + pre-write safety
  stale_result: 409 with a newly minted preview; never inherits old authorization
receipt_levels:
  - db_resource_committed
  - provider_accepted
  - device_delivered
  - surface_visible
  - notification_interacted
  - health_action_committed
```

Each receipt level allows a different claim. Provider acceptance is not device delivery;device delivery is not surface visibility;notification interaction is not health-task completion. A mutation timeout persists `verifying`;a notification timeout persists `verifying_unknown`. Both query the same operation id/key before any retry.

Canonical required receipt level by operation:

| Operation | Minimum evidence before claim |
|---|---|
| Internal plan/config mutation | `db_resource_committed`;may say saved/updated,not externally delivered. |
| Reminder creation | `db_resource_committed`;may say reminder created,not pushed or visible. |
| External provider request | `provider_accepted`;may say provider accepted only,unless a stronger domain receipt is configured. |
| Push send | `provider_accepted`;`device_delivered` and `surface_visible` require their own markers. |
| Notification tap/action | `notification_interacted`;does not prove the health action occurred. |
| Agenda complete/skip | `health_action_committed` for the exact occurrence;this includes the durable owner-scoped health event/resource write. |

The operation contract declares its required receipt level before execution. An adapter cannot upgrade the claim based on generic `executed` state alone.

### 8.4 Events, compatibility and privacy

```yaml
events:
  - health_day.shadow_composed
  - health_day.shadow_diffed
  - health_day.snapshot_materialized
  - health_day.mutation_previewed
  - health_day.mutation_confirmed
  - health_day.mutation_receipt_verified
backward_compatibility:
  - Phase 1a changes no endpoint or client
  - later additive fields preserve default legacy responses behind flags
migration:
  - no new Health Day table
  - authorizing snapshot/generation fields add to DailyOperatingPlan or an approved existing snapshot owner
  - stable occurrence_id mapping and owner-scoped unique canonical-occurrence key add to that approved existing owner;source revision stays in the authorization token
  - mutation fields and owner-scoped unique constraints add to WriteIntent before Phase 3
audit:
  - reason/source enums, opaque ids, generation and minimal redacted summary only
  - no raw health text, raw fact hash, medication name, diagnosis name or unrestricted before/after payload
```

`plan_version` and Today DynamicView `context_hash` are unrelated. `context_hash` is a short-TTL presentation-cache/safety fingerprint; it cannot authorize a mutation.

## 9. Mutation And Receipt Contract

- Read/explain is strictly side-effect free.
- Complete/skip on an explicit occurrence may reuse existing execution-event paths only after multi-dose occurrence identity, owner isolation and idempotency tests pass; the explicit click/command is the user action.
- Registered card/button actions call the deterministic command/capability path directly; they do not round-trip through an LLM. Natural language is compiled by Agent Kernel into the same command.
- Move, snooze with material time impact, cadence change, enable/disable, add and delete create a `WriteIntent` preview with before/after.
- A clearly labelled quick action may combine visible outcome and explicit click confirmation; free-form text always returns preview before mutation.
- Prescription start/stop/dose/course, clinician recheck floor, supplement purchase, payment and external actions always require item-level strong confirmation; ambiguous batch authorization is invalid.
- Every medical/supplement/recheck/workout-safety preview and confirm runs deterministic SafetyGuardian/hard rules **before any side effect**. Post-receipt evaluation only verifies the result and annotates newly discovered risk; it cannot be the first safety gate.
- Every write uses an owner-scoped stable idempotency key, atomic state transition and typed receipt. Timeout becomes `verifying`/“核对中”; the assistant must not claim success before the required receipt level and must query the same operation id before retry.
- Offline queues expire. On reconnect they load the current snapshot generation; an old preview can never auto-confirm in the background.
- Reversal can change user-owned plan configuration, but cannot delete already observed/executed health facts.
- Rollback may restore the old read UI, but may not disable owner/version/safety/idempotency gates after mutation rollout; rollback must never reopen stale or unsafe legacy writes.

Canonical mutation state semantics:

| State | Retry/terminal | Allowed user claim |
|---|---|---|
| `pending` | non-terminal | 已准备,等待确认。 |
| `executing` | non-terminal; no duplicate executor | 正在执行,不能宣称成功。 |
| `verifying` | non-terminal; query same mutation operation | 核对中,不能换 key 重做。通知使用独立的 `verifying_unknown`,不得混用。 |
| `executed` | terminal after required receipt | 只陈述 receipt 已证明的层级。 |
| `failed_retryable` | non-terminal with same operation/idempotency policy | 执行未确认,可按策略重试/核对。 |
| `failed_terminal` / `expired` / `dismissed` | terminal | 未执行;新请求必须生成新 preview。 |

## 10. Quiet Proactive Policy

Full recompose is allowed only for:

1. morning composition in the user's timezone;
2. a meaningful health signal that changes safety, recovery or rank;
3. a calendar change that creates a conflict or meaningful window;
4. completion, skip, snooze or other execution feedback;
5. an explicit user adjustment.

Page open, duplicated sync, small metric fluctuations and low-confidence observations do not full-recompose. A valid recompose:

- changes only future unexecuted `adaptive/opportunity` items;
- preserves `fixed` items and terminal facts;
- exposes `replan_reason` and affected items;
- lets new SafetyGuardian findings suppress unsafe future actions without inventing a prescription change.

Notification policy delegates delivery to the existing interruption contract and code; Health Day must not invent a second exemption table:

- morning-plan summary is P1, at most one candidate per day, and remains subject to P1 quiet-hours/budget/fallback decisions;
- low-confidence observations are P2/log-only and stay inside the shell/Today detail;
- medication/event reminder tier comes from `event_reminders`; composition must keep the fixed item, but it cannot claim delivery or bypass the interruption decision;
- budget exemption and quiet-hours exemption are separate concepts. Health Day cannot grant either through `fixed` classification alone;
- current P0 conflates true emergency safety and scheduled-required reminders, while both remain capped and blocked by the morning sleep floor. G2 must split `emergency_safety` from `scheduled_required`:emergency uses a separately reviewed escalation/flood-control policy rather than ordinary wellness budget; scheduled medication/recheck retains its occurrence, unreceived/overdue state and recovery path under explicit timing policy. Until that review passes, Health Day emits no new emergency exception and Phase 4 stays disabled;
- only an allowlisted, versioned deterministic SafetyGuardian rule/severity may assign `emergency_safety`,and the candidate/outbox stores `classification_rule_id`,rule version,episode id and bounded evidence refs. LLM output,free-form producer input,`fixed` classification and client payloads cannot assign or upgrade this class;
- existing proactive helper/check failures can fail open. New Health Day P1/morning paths must not inherit that behavior: an unavailable quiet-hours/budget evaluation degrades to no push + in-app fallback, with an observable reason. Phase 4 stays disabled until the decision contract exposes evaluation degradation deterministically;
- every new Health Day producer/adapter must branch directly on `decision.evaluation_status` and `decision.contract_complete`. `evaluation_status != ok` or `contract_complete=false`/non-empty `missing_contract_fields` forbids calling PushService for non-emergency P0/P1 and routes to the declared in-app fallback. A true `emergency_safety` event uses a deterministic generic template and stable rule/occurrence id, never free-form degraded copy;
- notification admission and dedupe require an owner-scoped atomic reservation/outbox with a stable episode/occurrence key. Concurrent workers cannot both consume budget; delayed flush uses conditional claim; `failed_retryable` may retry the same key and `verifying_unknown` verifies before retry rather than being treated as delivered/deduped;
- every send/retry revalidates current snapshot generation,source revision,occurrence existence/actionability,valid-until/clinical deadline and deterministic SafetyGuardian decision immediately before provider egress. A changed/stopped/cancelled/blocked occurrence becomes `superseded | cancelled | expired`,releases any unconsumed reservation exactly once and is never sent;
- an unrelated snapshot-generation change does not by itself supersede a still-identical occurrence. If stable `occurrence_id`,source revision,scheduled delivery slot,class,deadline and safety decision remain valid,the outbox conditionally reauthorizes/rebinds to the newer generation under the same candidate key;material occurrence/timing/safety changes supersede the old row and mint a new candidate key where appropriate;
- receipt taxonomy is explicit:provider accepted,device delivered,surface visible,notification interacted and health action committed are separate evidence markers and allow different wording;
- every producer, not only LLM, separates generic lockscreen text from in-app/data-only detail and passes the shared privacy boundary. Audit fields use controlled reason codes/surface enums, never copied medication/diagnosis text;
- every decision retains reason code, action capability, fallback surface, dedupe key and typed receipt semantics.

Health Day uses the exact notification execution vocabulary owned by `2026-06-26-notification-interruption-budget.md` §8.3:

| State | Health Day adapter behavior |
|---|---|
| `reserved` / `sending` | Pending only;never claim provider acceptance or delivery. |
| `provider_accepted` | May claim provider accepted;wait for independent device/user receipts for stronger wording. |
| `verifying_unknown` | Show 核对中;query the same operation/key and never blind-send. |
| `failed_retryable` | Retry only under the same operation/dedupe policy. |
| `failed_terminal` / `expired` / `suppressed` / `superseded` / `cancelled` | Terminal no-send state;retain scheduled-required in-app recovery where applicable. |

Bare notification `unknown`, generic `sent` and generic `delivered` are not canonical Health Day states.

## 11. Surface Contract

| Surface | Responsibility | Contract |
|---|---|---|
| Mobile XiaoBa shell (`/chat`) | Sole daily entry and query/control surface. | On open, show now/next + one top action + exception/freshness when material; execute inline or open detail. |
| Mobile Today detail | Full current-day drill-down. | Four semantic slots: 现在、今日重点、今日日程、快速记录; consumes the same plan/item version. |
| Mobile Agenda | Day/7-day management detail. | Same `HealthAgendaItem` IDs/status/source refs; no second ranking truth. |
| Backend `/timeline/today` | Current Chat/Today compatibility read seam. | Included in Phase 1a assembled diff;future implementation projects it from the one canonical snapshot until clients migrate. |
| Mobile Day Schedule | Current timing detail plus work-hours and medication/supplement adherence writes. | Keep until work-hours ownership and occurrence-scoped adherence commands migrate with typed receipts;not a read-only adapter today. |
| Mobile historical Timeline (`mobile/app/timeline.tsx`) | 30-day multi-source health event history. | Outside Health Day retirement scope;do not confuse it with `/timeline/today`. |
| Watch | Low-friction execution. | Next due item, complete/later/skip and receipt; no free-form planner. |
| Mac | Complex planning and review. | Consume same version; expose conflicts, sources and longer review. |
| Backend | Sole composition/safety/write authority. | Pure compose, explicit persistence, version check, audit and receipts. |
| External agents | Controlled adapters. | Query or propose through Agent Kernel/WriteIntent; never bypass safety or confirmation. |

Mobile Today detail exposes four semantic slots, not a hard-coded dashboard/card list. DynamicView/AtomicCapability may choose allowlisted components inside each slot, but cannot change item ownership, safety or rank:

1. **现在** — due/next item with complete/later/skip/adjust;
2. **今日重点** — exactly one Daily Artifact top action;
3. **今日日程** — medication/supplement/meal/workout/recheck/winddown plus calendar context;
4. **快速记录** — diet/symptom/measurement/medication/supplement capture.

`/timeline/today` remains a compatibility projection until Chat/Today consume the canonical snapshot directly. Day Schedule remains a functional surface until its work-hours and adherence writes have an explicit new owner and verified migration. The historical event Timeline remains a separate product surface. Only a dynamically verified, genuinely duplicate UI may be retired.

## 12. Safety, Privacy, And Medical Boundary

- All composition and mutation is owner-scoped by authenticated `user_id`; no client-provided owner identity.
- Medication/supplement conflicts, readiness/acute symptoms, red flags and clinician recheck floors remain deterministic SafetyGuardian/hard-rule decisions.
- The feature never diagnoses, changes dose/course, proves causal effect or implies emergency clearance.
- Raw L3 inputs are not copied into plan-version logs; audits store opaque source references, keyed digests/HMACs, controlled reason codes and minimal redacted summaries.
- Calendar failure means “not checked”, not an empty busy schedule.
- Cached plans show freshness and stale/degraded status; stale data cannot silently upgrade autonomy.
- Material changes, confirmations, version conflicts and execution receipts are auditable.

## 13. AI Behavior

LLMs may:

- parse a query or requested adjustment into a typed IntentFrame;
- explain why an item appears now using bounded evidence/freshness;
- generate user-facing preview/explanation copy after deterministic calculation;
- summarize evening/weekly review.

LLMs must not:

- create arbitrary plan items, routes, tool names or write schemas;
- override SafetyGuardian, fixed commitments, notification budget or version conflict;
- treat their own tool narration as a receipt;
- infer that missing calendar/device data is healthy/available;
- expose sensitive medication/supplement/diagnosis names in default lockscreen copy.

Failures degrade to deterministic plan text, read-only explanation, explicit stale state or manual confirmation.

## 14. Acceptance Criteria

```gherkin
Given the app cold-starts into the existing Chat-first shell
When the Health Day projection is current
Then the shell shows the next due item and exactly one top action without restoring a bottom tab bar.

Given Daily Plan, Agenda, Today detail and Watch render the same day
When an item appears on more than one surface
Then every surface uses the same item id, plan version, status and source reference.

Given a prescribed medication item ranks below an adaptive action
When the projection is built
Then the medication commitment remains in the projection and any delivery decision is explicit, tiered and explainable rather than silently dropped or claimed as delivered.

Given a user asks "把今晚锻炼改到 7 点"
When the current version is still valid
Then the system shows before/after and affected future items, requires confirmation, executes idempotently and answers from a verified receipt.

Given the plan changes after a preview
When the user confirms the old preview
Then execution is blocked with 409 plan_version_conflict and a new preview is required.

Given a wearable value changes insignificantly
When the signal arrives
Then no full recompose or push occurs.

Given a calendar connector is unavailable
When the day is composed
Then the plan is marked degraded and never claims that meeting conflicts were checked.

Given write execution times out
When no receipt has been verified
Then the UI says "核对中" and does not retry a real write with a different idempotency key.

Given an LLM-generated push contains a specific medication or supplement name
When it reaches the push boundary
Then visible lockscreen copy is generalized and the original detail remains in an in-app/data-only path.

Given quiet-hours or budget evaluation is unavailable for a Health Day P1 notification
When the notification candidate is processed
Then no push is sent, the item remains available in the XiaoBa/Today fallback surface and the degraded decision is observable.

Given the same medication has multiple scheduled doses on one local day
When one dose is completed, skipped or deferred
Then only that owner-scoped occurrence changes and the other doses retain distinct identities and state.

Given a fixed commitment conflicts with a deterministic safety rule
When the projection is composed
Then the commitment remains visible as blocked/conflict/deferred with actionable=false and never instructs the unsafe action.

Given a plan goes from A to B and later returns to content equivalent to A
When the user confirms a preview minted for the first A generation
Then the atomic confirm rejects it as stale and returns only a newly authorized preview.

Given Mobile and Mac confirm the same pending WriteIntent concurrently
When the server performs the pending-to-executing CAS
Then exactly one executor wins and both surfaces resolve against the same operation receipt.

Given two users present the same client idempotency key or query the same opaque operation id
When ownership is evaluated
Then the other owner's resource is denied as not found without returning a current snapshot or preview.

Given a calendar event is deleted, crosses midnight or changes timezone
When its source revision/tombstone is composed
Then the result is deterministic and stale/unavailable state never becomes a claimed free window or automatic move.

Given two notification workers claim the same owner/occurrence candidate
When budget admission and dedupe run
Then one atomic reservation wins, provider timeout becomes verifying_unknown under the same key and no worker blind-sends with a new key.

Given a provider accepts a notification but no device visibility or user-action receipt exists
When XiaoBa explains the result
Then it says only provider accepted and never claims delivered, visible or completed.

Given a scheduled-required occurrence is reserved and is then stopped,retimed,cancelled or SafetyGuardian-blocked
When delayed flush or retry reaches pre-send revalidation
Then the operation becomes superseded/cancelled/expired without provider egress and any unconsumed budget reservation is released once.

Given an LLM or ordinary producer labels its own candidate emergency_safety
When classification provenance is checked
Then delivery is rejected or downgraded;only an allowlisted deterministic SafetyGuardian rule may create that class.

Given the HMAC signing key rotates after an occurrence has been completed
When a later snapshot is materialized
Then a new occurrence_token may be signed but the stable occurrence_id and terminal completion remain unchanged and the dose cannot reappear.

Given an unrelated source causes a new snapshot generation while a reserved occurrence remains identical
When pre-send revalidation runs
Then the same candidate is reauthorized to the new generation rather than terminally superseded or duplicated.
```

## 15. Verification Plan

Planned implementation gates:

```bash
# TEST_DATABASE_URL points to an isolated PostgreSQL database.
# Backend focused composer, version and mutation contracts
DATABASE_URL="$TEST_DATABASE_URL" TZ=Asia/Shanghai backend/venv/bin/python -m pytest \
  backend/tests/test_health_day_composer.py \
  backend/tests/test_health_day_projection_contract.py \
  backend/tests/test_health_day_mutations.py \
  backend/tests/test_health_day_replan_triggers.py \
  backend/tests/test_agent_kernel_tool_gateway.py \
  -q --no-cov

# Existing integration seams
DATABASE_URL="$TEST_DATABASE_URL" TZ=Asia/Shanghai backend/venv/bin/python -m pytest \
  backend/tests/test_daily_operating_plan_arbitration.py \
  backend/tests/test_daily_plan_feedback.py \
  backend/tests/test_waist_and_daily_plan.py \
  backend/tests/test_agenda_range_complete.py \
  backend/tests/test_today_dynamic_view.py \
  backend/tests/test_event_reminders.py \
  -q --no-cov

# Mobile Chat-first shell + Today detail
pnpm --dir mobile exec jest --runInBand \
  'app/(tabs)/__tests__/chat.test.tsx' \
  'app/(tabs)/__tests__/home.test.tsx' \
  components/home/__tests__/DailyArtifactCard.test.tsx
pnpm --dir mobile exec tsc --noEmit

# Repo/system-map hygiene
python3.12 backend/scripts/check_dossier_consistency.py
./scripts/system-map-check.sh
git diff --check
```

Test design must include real assembled snapshots from source fixtures through composer/API and `/agent/stream` event order, plus user-timezone/DST, multi-dose occurrences, fixed+safety conflict, calendar deletion/tombstone/cross-midnight/timezone, A→B→A, two-client CAS, cross-user same-key isolation, two notification workers, provider `verifying_unknown` retry, reserve-then-stop/retime/safety-veto, invalid emergency classification,offline expiry and receipt-claim journeys. Helper-only mocks are insufficient for G3.

## 16. Rollout And Rollback

1. **Phase 1a internal read-only shadow**:build an in-memory canonical manifest/artifact and compare at backend/service-fixture level with assembled Daily Plan/Agenda/Schedule/Daily Artifact/DynamicView/`timeline/today`; no API/client/DB/materialization/mutation/push change and no Today mount side effect.
2. **Authorizing snapshot + Chat/Today**:after umbrella + phase-specific G2 design PASS,implement one server-owned generation;only after G3/G4 may summary/detail enable behind a user allowlist. Legacy Today/Agenda reads remain.
3. **Unified mutation**:after its phase-specific G2 design PASS,implement schema/CAS/safety,then require G3/G4 evidence before enabling preview-confirm-receipt for low-risk schedule changes. Rollback may restore legacy read UI but never re-enables writes that bypass owner/version/safety/idempotency gates.
4. **Quiet proactive triggers**:after umbrella + phase-specific emergency/reminder/outbox/calendar G2 design PASS,implement in shadow;only after G3/G4 and notification review may one trigger class enable at a time.
5. **Review + cleanup**:add evening/weekly loop, then hide duplicate navigation only after dynamic click/dependency audit.

Rollback disables the new composer/summary/mutation/trigger flags independently and returns to current Chat cards plus existing runtime Agenda. No rollback deletes execution facts or replays old plan snapshots over newer records.

Immediate rollback conditions:

- false write or claim without receipt;
- fixed medication/recheck commitment disappears;
- Health Day silently drops a prescribed reminder candidate or bypasses the existing interruption decision;
- cross-user data or raw L3 data enters audit/logs;
- SafetyGuardian output is bypassed;
- Chat-first navigation or deep-link return path breaks.

## 17. Success Metrics

- Chat shell open -> next action visible/understood rate;
- due/top action completion rate;
- skip reason coverage;
- adjustment preview -> confirm -> verified success rate;
- version conflict rate and reconfirm completion rate;
- notification disable rate, quiet-hours complaints and morning-budget compliance;
- weekly completed actions with a verification plan;
- duplicate page traffic reduction without failed-task/dead-end increase.

Each metric requires an event definition, denominator, baseline and observation window before rollout.

## 18. Open Questions And G2 Exit Conditions

Gate semantics:the umbrella Health Day G2 exits on an approved architecture/safety contract plus migration,test and rollback design. It does **not** require feature implementation or passing G3/G4 evidence. After umbrella G2 PASS,each Phase 2/3/4 gets its own Dossier and phase-specific G2 before S4/S5 implementation;implementation evidence is judged at G3/G4. This avoids a Gate that requires implementation while simultaneously forbidding delivery work.

Phase 1a implementation planning must decide only:

- Exact internal manifest/artifact shape and deterministic assembled-diff semantics;it is not an additive client API envelope.
- How the shadow path calls pure composition without invoking current read-upsert/commit behavior, and how telemetry proves zero DB/push side effects.

Must be decided and specified in migration/test/rollback design before umbrella G2 can PASS for Phase 2/3:

- One server-owned snapshot owner/materializer and monotonic generation model shared by `/daily-plan/me`, DynamicView and Agenda without independently minting versions.
- Stable internal occurrence identity + rotatable short-lived occurrence token,and fixed-vs-safety state semantics for multi-dose and conflicting commitments.
- Additive WriteIntent schema, owner-scoped unique constraints, atomic confirm CAS, expiry, timeout verification and canonical receipt states.
- Pre-side-effect deterministic SafetyGuardian for every health mutation, including rollback invariants.

Must be decided and specified in migration/test/rollback design before umbrella G2 can PASS for Phase 4:

- Reconcile true emergency safety with scheduled medication/recheck correctness under current P0 caps and 09:00 morning sleep floor;candidate retention, budget, quiet-hours, escalation and verified delivery remain separate axes.
- Owner-scoped atomic notification reservation/outbox, delayed-work claim, pre-send revalidation, retry/`verifying_unknown` behavior and split receipt taxonomy.
- Explicit interruption-policy evaluation status so failed checks fall back in-app for new non-emergency callers, plus deterministic emergency template behavior.
- Calendar revision/freshness/timezone/tombstone contract so unknown never becomes free or an automatic material move.

Can defer:

- Exact UI convergence order after `/timeline/today` compatibility and Day Schedule work-hours/adherence ownership migration;the historical event Timeline is not a retirement candidate for this feature.
- First real posture/screen-focus hardware adapter.
- External food ordering/doctor booking provider; payment remains outside Reva execution.

## 19. Changelog

| Date | Change | Reason |
|---|---|---|
| 2026-08-15 | Initial accepted definition | User confirmed a quiet proactive system that can be queried and safely modified; reconcile it with the existing Chat-first shell and shipped planning/runtime capabilities. |
