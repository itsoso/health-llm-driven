# Dossier: Health Day Phase 1a Read-only Shadow

| 字段 | 值 |
|---|---|
| slug | `health-day-read-only-shadow` |
| 创建日期 | 2026-08-15 |
| 当前阶段 | S4 需求分解 / S5 实现（Task 0） |
| 状态 | building |
| 负责 | Codex |
| 父 Dossier | `docs/dossiers/2026-08-15-quiet-proactive-health-day.md` |
| 反馈环 | PostgreSQL service-fixture shadow / no runtime rollout |

## Correct Course

- [x] 2026-08-15 scope correction
  - 触发:只读审计发现多个现有 read wrapper 会隐式 commit、物化或跨连接读取。
  - 旧基线:直接在 shadow 中调用 Daily Plan、Agenda/runtime、DynamicView 和 `/timeline/today` 组装器。
  - 新基线:legacy wrapper 只在测试 seed/oracle 阶段运行;被测 shadow 只接受同一 PostgreSQL read-only snapshot 的 plain-data manifest,并调用 pure composer/projector。
  - 回退阶段:S3。
  - 需重跑 Gate:G2、G3、G4。
  - 用户确认:☑ 用户已确认继续严格只读的 Phase 1a。
- [x] 2026-08-15 adversarial design correction
  - 触发:fresh composer/projection/Gate review 发现 writeful oracle 污染 candidate、global items 无法定义 per-surface diff、`schedule_from_medications` 隐含 registry/China clock,以及 manifest 未绑定 DTO payload。
  - 旧基线:同一 DB 顺序抓 legacy outputs、global canonical list 直接比较、复用名义 pure scheduler、三段以上未固定 HMAC frame。
  - 新基线:同一 committed semantic seed 的 per-surface oracle schemas + untouched candidate schema、symmetric versioned surface projectors、bounded pre-AdviceGuard Daily Plan subset/slot projector、payload-bound two-segment signing protocol和 mechanical no-skip PostgreSQL Gate。
  - 回退阶段:S3。
  - 需重跑 Gate:G2(本轮文档复审)、G3、G4。
- [x] 2026-08-15 implementation-reachability correction
  - 触发:Task 3 fresh preflight 发现 SQL cursor guard 按字面会拦截 measured transaction 自己必需的三条 session-local setup,且 private Core schema 不含 `users` 表却要求 seed User。
  - 旧基线:approval 后无条件拒绝全部 GUC change;Task 3 seed 叙述暗示需要未列入 source inventory 的 User/FK。
  - 新基线:只允许三条逐字节、参数 shape 已批准且 one-shot 消费的 measured setup (`statement_timeout`,`idle_in_transaction_session_timeout`,`app.user_id`);其他 GUC/transaction change 仍 fail closed。Task 3 使用 explicit owner scalar;有 owner column 的表直接过滤,owner-less child (`outcome_metrics`)只能通过已 owner-scoped parent cycle IDs 读取,不新增 `users` mapping/FK/伪造 owner column。
  - 回退阶段:S3 计划机械澄清;不扩大 source、runtime 或安全范围。
  - 需重跑 Gate:Task 3 focused RED/GREEN、G3、G4。
- [x] 2026-08-15 digest-construction reachability correction
  - 触发:Task 2 preflight 发现原计划仍允许 caller 以分离的 payload/metadata 形状触达 digest,且“verified bundle”未机械限定 verifier、key provider 与原 bundle object。
  - 旧基线:`build_digest_bound_shadow_bundle(payloads,manifest_metadata,key_provider)` + caller-supplied digest mismatch 检查;Task 4/7 只写“verified bundle”,未固定验证入口。
  - 新基线:signing-local exact frozen/slots `SourceSigningInput`/`ManifestSigningInput`,前者无 `payload_digest`;builder 只收 manifest input + provider、一次读取 key、内部逐源计算 digest 后签 manifest。`verify_digest_bound_shadow_bundle` 以 `compare_digest` 重算逐源与 manifest;Task 4 的 context factory 首步调用 verifier 并继续使用同一 snapshot 的原 bundle object,不引入 wrapper,oracle 永不参与。item key 只经窄 `bind_signed_shadow_item_key` factory 绑定 Task 2 生成的非授权 token。
  - 回退阶段:S3 计划机械澄清;不扩大 source、runtime、写路径或生产 key 范围。
  - 需重跑 Gate:Task 2/4 focused RED/GREEN、G3、G4。

## S0 · 用户需求(逐字)

> 继续

本句承接已确认的目标:“安静主动型,但可以查询并且可以修改和调整”,以及上一阶段明确的安全下一步:只为 Phase 1a 建独立 Dossier 和可执行实施计划,不碰客户端、写路径或主动推送。

- 谁用 / 解决什么:为 Health Day 后续收敛先证明一份跨域日投影可以确定性组合、比较和降级,且不会制造健康事实或用户可见副作用。
- 当前绕法:Daily Plan、Agenda/runtime、Schedule、Daily Artifact/DynamicView 和 `/timeline/today` 分别组装;部分 GET/read service 会写 AdviceLedger、DailyOperatingPlan、HealthProtocol 或 HealthEvent。
- 锚点用户相关性:高。它降低后续把饮食、睡眠、用药/补剂、复查、日历和锻炼收敛成单日入口时的错误承诺、重复行动和陈旧写风险。

## S1 · Discovery(现状勘察)

### 可复用的纯计算岛

- `backend/app/services/timing_solver.py` 中只依赖显式值的 slot/parser helper、Daily Plan 中不读 DB/clock/registry 的规则 helper 可作为实现参考,但必须逐个通过 import/clock/registry 测试后才能复用。
- `schedule_from_medications` **不是** Phase 1a pure seam:它调用全局 SafetyGuardian registry,其中 DSI 使用隐藏的 China-day clock,并额外合成 meal/sleep/workout。shadow 禁止调用,改用 frozen medication DTO 的最小确定性 occurrence projector;安全快照缺失时明确 degraded。
- `daily_artifact_service`、`today_dynamic_view_service` 和 `today_timeline_service` 已包含大量纯投影 helper,但当前 public builder 的 loader/materializer 边界没有分开。
- Agenda/runtime、Daily Artifact、DynamicView 和 Today Spine 现有测试提供 single-top-action、BID slot、status、safety floor、timezone 和 response-shape fixture。

### 不能直接复用的 wrapper

| Seam | 隐式副作用 / 不一致性 |
|---|---|
| `daily_operating_plan.build_daily_operating_plan` | 过滤过期 ActionCard 时修改 ORM;`guard_and_record_advice` 插入并 commit AdviceLedger;最后 upsert/commit DailyOperatingPlan。 |
| `twin.builder.build_twin(use_cache=False)` | 仍为多个 partition 自开 `SessionLocal`;不能共享一个 PostgreSQL MVCC snapshot。部分 partition 还访问 Redis/环境 provider。 |
| `agenda_service.today` | workout chain 开启时会物化 HealthProtocol;smart/runtime 又传递 Daily Plan 写入。 |
| `today_timeline_service.build_today_spine` | `_attach_event_ids` 物化并 commit HealthEvent;因此 `/timeline/today` 不是纯度入口。 |
| `daily_artifact_service.build_daily_artifact` / `today_dynamic_view_service.build_today_dynamic_view` | 自身主要是投影,但经 runtime/smart/Daily Plan 传递上述写入。 |
| `day_schedule_service.build_day_schedule` | 无直接 DB commit,但经 Twin/cache/外部 provider 使用独立时点;calendar 失败会被吞成无 busy。 |
| `day_schedule_service.schedule_from_medications` | 无 DB handle 但调用全局 SafetyGuardian/隐藏 China-day seam,并合成非 medication 默认项;不满足 manifest-pure。 |

### 并发现状

- `main` 与 `origin/main` 在勘察时 0/0 对齐。
- 开放 PR #225 只改 Mobile Today DynamicView 消费/刷新面;Phase 1a 不改 mobile 或 API,无直接文件冲突。
- 开放 PR #252 直接修改 `.github/workflows/ci.yml`、release contract 相关 harness 和 generated system map,与本计划 Task 9 存在合并冲突风险。实现前必须 fresh fetch/重读其状态;若已合并,以新 main 重写 CI contract,若仍开放,不得在旧 CI 基线上盲改 Task 9。
- 工作区已有与本 feature 无关的修改/未跟踪文件;本 feature 只精确 stage 自己的文件。

## G1 · 准入裁决(governance §8 RequirementAdmission)

```yaml
RequirementAdmission:
  request: "继续推进 Health Day 的安全下一步"
  classification: experiment
  first_user_fit: yes
  core_loop_step: observe -> decide next action, 仅验证内部组合 seam
  first_class_objects:
    - DailyOperatingPlan
    - HealthAgendaItem
    - HealthProtocol
    - HealthProblem
    - HealthProgram
  target_surface: backend internal service-fixture only
  source_of_truth: parent Health Day Feature Spec + PostgreSQL source rows
  safety_level: privacy_sensitive + medical_boundary
  prescription_or_causal_verdict: none
  autonomy_tier: none
  evidence_provenance: one read-only repeatable-read snapshot + explicit external fixture revisions
  claim_hedging: n/a
  verification_window: same implementation Gate
  success_metric: deterministic assembled diff with mechanically proven zero shadow side effects
  added_user_burden: none
  burden_justification: no user-visible behavior
  non_goals:
    - API or client response
    - DB materialization or migration
    - mutation, reminder, notification or background job
    - authorizing plan_version or occurrence_id
    - production shadow scheduling
  smallest_end_to_end_slice: seeded legacy oracle -> isolated PostgreSQL READ ONLY snapshot -> manifest -> pure composer/projectors -> redacted in-memory diff
  stale_surface_to_remove_or_archive: none
  spec_required: no — parent Feature Spec already owns the product and safety contract
```

- **裁决: PASS。** 这是父 feature 明确允许的内部实验切片,不新增用户行为或写能力。
- 用户确认:☑ 用户已确认继续 Phase 1a。

## S2 · PRD / Spec authority

- 产品方向:`docs/prd/2026-06-19-proactive-planning-prd.md` §0.1/§6。
- 规范真源:`docs/specs/active/2026-08-15-quiet-proactive-health-day.md` §7、§8.1、§14–§18。
- 父设计:`docs/plans/2026-08-15-quiet-proactive-health-day-design.md` §3.1、§5 Phase 1a、§8。
- 本 child 不新增 PRD/Feature Spec,不把测试诊断合同升级成客户端合同。

## S3 · 规划

- 实施计划:`docs/plans/2026-08-15-health-day-read-only-shadow-implementation.md`。
- 分期路由:只进入 backend TDD 和隔离 PostgreSQL test;没有 OTA、EAS、backend deploy 或 prod flag。

### 1. 运行边界

Phase 1a 交付物是**休眠的内部诊断库和测试 harness**,不是线上 sidecar:

- 无 router、API schema、client type、Celery task、scheduler、startup hook、feature flag 或生产调用点;
- shadow entry 不接受 `Session` 以外的隐式数据库工厂,不导入 `SessionLocal`、`build_twin`、`build_daily_operating_plan`、PushService 或 notification producer;
- 当前 legacy wrapper 仅可在隔离 PostgreSQL 测试的 seed/oracle 阶段运行。oracle 完成并关闭其写事务后,才开始被测 read-only transaction;
- shadow 失败只返回受控 degraded/error code,不 fallback 到 legacy live builder,否则会重新打开隐式写。
- Phase 1a 连手工 CLI 都不接;未来若要让任何 runtime/manual runner 调用该库,必须另开 child Dossier/G2,重新裁决 owner allowlist、限流、telemetry 和退出开关。

### 2. Manifest / input contract

```yaml
manifest:
  schema_version: health_day_shadow.v1
  owner_id: internal-only authenticated owner
  local_day: derived from as_of + effective timezone
  timezone: effective IANA zone derived inside snapshot
  as_of: explicit aware timestamp
  transaction:
    dialect: postgresql
    isolation: repeatable_read
    read_only: true
  sources:
    - source_kind: controlled enum
      source_role: candidate | projection | diagnostic
      revision: opaque/keyed or external revision token
      payload_digest: keyed digest of the exact frozen source DTO bytes
      acquired_at: explicit timestamp or null
      freshness: current | stale | unknown
      availability: available | unavailable | unsupported
      error_code: controlled enum or null
      tombstone_state: present | absent | unsupported | unknown
```

Loader 入参只有 injected Session、authenticated owner、aware `as_of`、required valid IANA `fallback_timezone` 与外部 revision fixture;caller 不能自报 authoritative manifest timezone/local-day。loader 在同一 snapshot 冻结 ProfileScheduleDTO,逐个以 `ZoneInfo` 验证非空候选和 fallback,按 `manual -> detected -> legacy -> fallback` 选 effective timezone,再由 `as_of` 推 local day并构造/签名 manifest。高优先候选无效不静默 fall through;bundle verifier 重算 precedence,timezone/local-day mismatch 或伪造 manifest fail closed;绝不读取 OS/China ambient default。

输入 payload 与 manifest 作为一个不可拆分的 `HealthDayShadowBundle` 留在内存,均先转 frozen/plain-data DTO;不把 ORM object、lazy relationship、wall clock 或 provider client交给 composer。Task 2 在 signing module 内定义 exact frozen/slots `SourceSigningInput(source_kind,source_role,revision,acquired_at,cutoff,freshness,availability,error_code,tombstone_state,value)` 与 `ManifestSigningInput(schema_version,owner_id,local_day,timezone,as_of,transaction,sources)`;source input 明确没有 `payload_digest`,raw `value` 使用 `repr=False` 或等价 safe descriptor。safe-repr 约束只裁决 signing input/验证异常不得回显原值或 token,不要求改变 `repr(bundle)`;bundle 仍禁止进入日志。`build_digest_bound_shadow_bundle(manifest_input,key_provider)` 只读 provider 一次,逐源从 exact input 重算 HMAC、创建带 digest 的 SourceResult、构造 bundle-owned graph 后签 manifest;外部调用者不能自报 digest。`verify_digest_bound_shadow_bundle(bundle,key_provider)` 用 `compare_digest` 重算每源和 manifest,任何 changed payload/field 搭配旧 revision/digest 都 fail closed且错误不回显原文/token。所有查询显式 `ORDER BY ... id`,相同完整 bundle 的 canonical artifact 必须逐字节一致。

Phase 1a source support:

- supported read-only:implementation plan source matrix 明确列出的 Daily Plan subset facts + 已存在 DailyOperatingPlan row(只作 legacy/projection diagnostic)、active HealthProtocol + cadence window 内全部 terminal/snooze/event-trigger facts、HealthProblem follow-up、active Medication/Supplement、UserProfile、HealthProgram inventory、CalendarSource/Event 同步缓存和必要 execution facts;
- pure calculation:frozen Daily Plan subset facts -> pre-AdviceGuard/non-authorizing diagnostic candidates;medication/profile/calendar DTO -> minimal medication/supplement occurrence projection;protocol cadence-window events/follow-up DTO -> canonical fixed items。不得调用现有 DOP/Day Schedule builder;
- explicit unsupported/degraded:Daily Plan lab flags/composite training gate/AdviceGuard+top-5/prediction/registry labels、fresh full Twin rebuild、AdviceLedger record、workout-chain materialization、external connector refresh、Program-to-action composition、authoritative SafetyGuardian recompute、calendar tombstone(当前模型无 tombstone)。unsupported 不能静默变成空/健康/空闲/允许。

Calendar knowledge is `trusted_current | provenance_unknown | stale_unknown | failed_unknown | tombstone_unsupported`. Only a future provenance-aware source may reach `trusted_current` and prove a free window or place/move flexible actions. Current CalendarEvent ingestion/schema loses aware-vs-floating provenance and hard-attaches all-day/floating values to Beijing,so the measured loader always emits `provenance_unknown` (all-day and timed use separate controlled reasons) even when sync is fresh. Unknown states may retain degraded diagnostic conflict candidates but empty busy never means free. Fixed source times stay visible with conflict unknown;flexible/calendar-influenced Schedule timing is unsupported precision and never yields timing drift.

Weekly/monthly/quarterly/annual protocol status must load from an exact inclusive `[period_start,local_day]` window,not only today's event rows:weekly starts on the local Monday;monthly on local month day 1;quarterly on day 1 of month `1 + 3 * ((month - 1) // 3)`;annual on local January 1. `snoozed_until` and event-trigger facts are evaluated against explicit `as_of`;a protocol completed earlier in the same period must not resurface. Tests cover all four cadences plus week/month/quarter/year boundaries.
Current protocol storage has one event per protocol/day,so `per_meal_slot` cannot prove occurrence-complete history;mark it `protocol_per_meal_occurrence_unsupported/lossy_identity` rather than inventing meal-level completion.

### 3. Canonical shadow item

```yaml
item:
  shadow_item_key: internal non-authorizing HMAC
  identity:
    storage_namespace: medication_row | supplement_definition | health_protocol | health_problem | daily_plan_action
    source_kind: controlled enum
    source_id: in-memory only
    slot_local_minute: normalized integer 0..1439 or null
    dose_ordinal: stable integer;required for every repeated occurrence
    local_day: manifest local day
    projection_role: action | checkup | schedule | safety | presentation
  domain: controlled enum
  status_canonical: pending | due | overdue | snoozed | adjusted | auto_observed | blocked | conflict | deferred | completed | skipped | expired | cancelled | info | unknown
  actionable: boolean
  commitment_class: fixed | adaptive | opportunity | unknown
  timing:
    precision: exact | window | date | unknown
    value: normalized local value
  safety:
    disposition: allowed | blocked | degraded | unknown
    reason_code: controlled enum or null
  ordering_facts:
    source_ordinal: integer or null
    priority_class: controlled enum
    scheduled_local_minute: integer or null
```

`shadow_item_key` 不是未来 `occurrence_id` 或 authorization token。canonical 与 legacy 两侧先把 `8:00`/`08:00` 统一成 user-local minute;BID/TID 再以 dose ordinal 区分。identity 还必须含 storage namespace:`medication_row` 与 `supplement_definition` 即使 numeric id/domain 相同也不能碰撞;legacy Schedule/Timeline 的 supplement ref 只绑定 Medication-table row。重复规范化 slot 或非法时点标 `slot_identity_ambiguous`/degraded,不得静默折叠或生成可执行 occurrence。title 永不作为 identity。Canonical rejected/deferred 都保持可见且不可执行;当前 legacy medication/supplement Schedule 的闭集只有 scheduled/rejected,伪造或未来的 deferred tuple 必须先走 unknown policy bump。

普通 `HealthDayShadowItem(shadow_item_key=non_empty)` 构造继续 fail closed。contracts leaf 不暴露 public raw-token factory;只预留 private `_SIGNED_SHADOW_ITEM_KEY_BINDER`,并把输入收紧为 exact unsigned item + `[A-Za-z0-9_-]{1,32}\.[0-9a-f]{64}`。Task 2 是该 private seam 的唯一允许 importer,由 public `health_day_shadow.bind_signed_shadow_item_key(...)` 先调用 `sign_shadow_item_identity` 计算当次非授权 token 再绑定;caller 不能传任意 token 字符串。绑定逐字段保留 unsigned item 除 `shadow_item_key` 外的全部内容;Task 8 以 import graph 锁住这条边,不得为方便放宽 Task 1 constructor invariant。

Medication execution 只按**唯一 exact normalized slot**绑定 occurrence,绝不 nearest-match。source slot 先按 minute 排序并赋 dose ordinal;duplicate-normalized slot 或 `times_per_day` 与多 slot 数不一致使整组 degraded。单一 occurrence 可接 `taken_time=NULL` 的 daily marker,但 timing precision unsupported;BID/TID 的 NULL、off-slot log、或 `8:00` + `08:00` 两条 raw log 归一碰撞都标 lossy/ambiguous 且不得终结任何剂次。status 映射固定:`taken -> completed terminal`,`skipped -> skipped terminal`,`delayed -> adjusted nonterminal`;unknown 不猜。SupplementRecord 保持 once-per-day 事实,`taken=true` 才完成,optional time 不制造第二 occurrence。

Schedule 与 Timeline 的 assembled payload 已丢部分 source-slot/fixed/count 证据,所以两者必须同时接收由 untouched HMAC-bound bundle 派生的 immutable `LegacyOccurrenceContext`。它按 `(storage_namespace,source_id)` 保存 versioned domain、slot/ordinal、count consistency、fixed/flexible 与 conservative calendar-busy eligibility;不含 oracle delta、title 或授权。fixed 与 flexible 即使都显示 `anchor=anytime` 也只按 context 分类;calendar 只能声明“有 eligible busy input”,不能伪称实际参与。single occurrence 被 solver 移动时保留 source identity但 precision unsupported;multi-dose/invalid 无法唯一回绑时 canonical+legacy 同组都降为 ambiguous,不得制造 missing/extra。

DST 采用一条明确的 Phase 1a 政策:纯 `HH:MM` 事实只定义一个 `local_day + local_minute + dose_ordinal` wall-clock occurrence,不擅自换算 UTC instant。对 `America/New_York` 类 spring-forward nonexistent minute,保留一条诊断项但标 `nonexistent_local_time` + `unsupported_precision` + `actionable=false`;对 fall-back ambiguous minute,若来源没有 offset/fold 证据,保留单一 wall-clock occurrence,标 `ambiguous_local_time_without_fold` + `unsupported_precision` + `actionable=false`,既不自动选 fold 也不复制两次。

CalendarEvent 的 PostgreSQL `timestamptz` 保存数据库 instant,但现有 ingestion 会给 floating datetime 和 all-day DATE 强贴北京时区,模型又没保存原始 TZ/DATE/floating provenance。因此 current-schema row 不能证明外部 producer 的真实 instant/date。loader 对合法 interval 先归一 UTC,再用 `astimezone(ZoneInfo(effective_timezone))` 只推导**降级诊断**的本地 wall time/offset/fold/cross-midnight;all-day 与 timed cache 分别标 provenance unsupported/unknown,绝不授权 free/busy 或 retime。纯转换测试的 fall-back 两个 UTC instant 必须分别推导 fold 0/1,不得直接信 psycopg datetime 的 `.fold`;legacy 北京日+HH:MM payload 已丢精度,不得宣称与 canonical 同规则归一。日边界由有效时区的两个本地午夜分别转 UTC,半开 overlap 为 `start < day_end && end > day_start`;null/zero/reversed interval fail visible,并覆盖 23h/25h 日。

`unknown` lifecycle 必须带受控 `unsupported_lifecycle_state` 并退出 comparable scope,不得猜映射。`snoozed`、`adjusted`、`auto_observed` 必须无损穿过 adapter;需要时另带 controlled completion provenance,不能都压成 `completed`。

### 4. Digest and privacy

- `shadow_manifest_digest`、每源 `payload_digest` 与 `shadow_item_key` 共用父 Spec 规定的外层 domain `health-day-shadow-v1`,但分别使用 `manifest-digest` / `source-payload` / `item-key` HKDF purpose。item-key payload 只含 schema/owner/local-day/**storage_namespace**/source kind+id/normalized slot+dose ordinal/projection role,不含 title 或健康原文;namespace 是必填 controlled enum,不能从 domain 猜。相同 numeric id 的 `medication_row` 与 `supplement_definition` 必须得到不同 MAC;token 随 test key 变化且不作为 durable identity/authorization。
- 签名 frame 严格只有父 Spec 的两个 segment:`u32be(len(domain)) || domain || u32be(len(canonical_envelope)) || canonical_envelope`。`domain` 是 ASCII bytes `health-day-shadow-v1`;`canonical_envelope` 的字段固定为 `key_id,payload,purpose,schema_version`,无其他/缺失字段,optional payload field 一律显式 `null`。`key_id` 只允许 `[A-Za-z0-9_-]{1,32}`,因此输出 grammar 无转义歧义。
- HKDF 固定 SHA-256、32-byte output、salt `b"health-day-shadow-v1\x00hkdf-salt-v1"`、info `b"health-day-shadow-v1\x00" + purpose_ascii`;root key 至少 32 bytes。最终 MAC 为 HMAC-SHA-256 lowercase 64-char hex,token 为 `key_id + "." + mac_hex`。purpose、key_id 都在 canonical envelope 内,同时 purpose 决定 HKDF info;未知 purpose/key_id、短 key 或字段漂移 fail closed。
- manifest payload 显式序列化 `schema_version,owner_id(decimal ASCII),local_day,timezone,as_of,transaction,sources`;source payload 固定为该 source 的完整 frozen DTO primitive。timestamp 全部先归一成 UTC `YYYY-MM-DDTHH:MM:SS.ffffffZ`;同一 schema 不允许 absent/null 混用。manifest 必须包含重新计算的每源 keyed `payload_digest`,所以相同 revision 搭配不同 DTO bytes 也会改变 manifest digest。
- canonical 子集只接受 ASCII dict key、有效 Unicode string、`null/bool`、I-JSON 安全整数和 built-in list/tuple/dict,且 validator 用 `type(x) is ...` 拒绝子类/自定义容器。float、超出 `[-(2^53-1), 2^53-1]` 的整数、lone surrogate、bytes、datetime、自定义 Mapping、非 ASCII key 和任意 object 均 fail closed。
- serializer 固定为 stdlib `json.dumps(..., sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)` 后严格 UTF-8 编码。ASCII-only key 消除了 JCS UTF-16 property-order 差异;无 float 消除了 ECMAScript number-format 差异;整数范围、Unicode/escape 与结构限制由 RFC 官方向量和独立 fresh-process golden tests 锁定。字符串不得 NFC/NFD normalize,JCS 要求原样保留。
- 一条完整 golden vector 必须锁定 fixed root/key_id、覆盖全部 manifest/source fields 的 nested primitive、canonical envelope bytes、two-segment frame hex、三个 derived purpose keys 和最终 MAC;另测整数上下界、控制字符、Unicode 不归一化、unknown/absent/null 和 fresh process。
- 不新增 `rfc8785` 第三方包:现有 stdlib 可在上述子集内满足合同,而候选包的最新 release 已超过仓库“新增依赖最近 6 个月更新”的门槛。实现和文档不得把该 helper 宣称为通用 JCS serializer。
- owner、原始 payload、药名/补剂名、诊断/化验、source id、title/subtitle、日历 PII 和自由文本永不进入日志/telemetry。
- Phase 1a 不接生产 key store,也不持久化 digest。测试用固定短生命周期 key;未来 runtime/key rotation 仍归父 G2。

### 5. Per-surface assembled diff

不做错误的“所有 surface 全局集合相等”,也不把 canonical 全量 items 直接喂给 diff。`project_canonical_surface(artifact, policy, occurrence_context=None)` 与 legacy adapter 对称地产生 `CanonicalSurfaceProjection` / `LegacySurfaceProjection`;Schedule/Timeline 两侧必须调用 `derive_legacy_occurrence_context_from_bundle(bundle,key_provider)`,其首步对 measured candidate 同一原始 bundle object 调用 `verify_digest_bound_shadow_bundle`。校验 manifest/schema/payload digests 完全一致后才派生 context;不引入 `VerifiedBundle` wrapper,不能从 oracle payload/delta 或第二个 snapshot 重建。**两侧每一行**都必须分类 `comparable | intentionally_unscoped | lossy_identity | ambiguous_identity | unsupported_precision`,否则 fail closed。

每个 versioned surface policy 显式声明:local-day/horizon、包含的 domain/role、cardinality/top-N、dedupe group、surface-specific ordering、top/now 规则和 safety comparability。global item 只持 neutral ordering facts;`ordinal/is_top/is_now` 只存在 surface projection,同一 item 可在 DOP/Agenda/Timeline 拥有不同 rank。

| Surface | Comparable scope | Explicit exclusion |
|---|---|---|
| Daily Plan | source availability/degraded classification only | all pre-AdviceGuard candidates and post-guard/top-5 legacy actions are intentionally_unscoped for missing/extra/rank/safety;lab flags、full Twin/training gate、registry labels、DB metadata/自由文案 |
| Agenda | exact regular `agenda_service.today(...,followup_within_days=14)` 的 protocol/checkup/advisory;non-DOP supported facts | regular builder 没有 Daily Plan branch,不得人为加 DOP exclusion;source_count 等派生计数 |
| runtime | current-day non-DOP fixed/checkup/schedule items;future horizon 只做 diagnostic | Daily Plan-derived actions and future anchors intentionally_unscoped |
| Schedule | Medication-table medication/supplement identity + exact source reminder minute only when legacy preserves that minute;standalone `supplement_definition` once-daily identity/lifecycle is comparable and its legacy absence is expected missing | flexible/meal/anytime/calendar-influenced timing is unsupported precision;standalone definition timing不推断 clock minute;generated meal/sleep/workout defaults intentionally_unscoped;disclaimer、自由处方文案 |
| Daily Artifact | exactly one top-action identity/state when `source.object_type` is a supported non-DOP protocol/problem/checkup source | only `daily_plan_action` top inherits `daily_plan_post_guard_selection_uncomparable`;unknown top source is `daily_artifact_top_source_unsupported`;evidence prose、route/endpoint copy |
| DynamicView | non-DOP runtime semantic identity、top/cardinality 与 intentional dedupe | DOP-derived hero/action plus safety row 在无 pure AdviceGuard/SafetySnapshotDTO 时 intentionally_unscoped,只比较 source availability/degraded;view/cache/render copy |
| `/timeline/today` | exact `build_today_spine` 的 current checkup/schedule identity,now,status;standalone `supplement_definition` identity/lifecycle comparable且当前缺失记 expected missing | 当前 builder 消费 regular Agenda,没有 DOP branch;standalone definition绝不与 Medication-table supplement ref合并;event_id、past events、rhythm/outcome/work 按 intentionally_unscoped 记录 |

Standalone `supplement_definition` 只在 Schedule 与 Timeline policies 进入 comparable scope;在 Daily Plan/Agenda/runtime/Artifact/Dynamic 上必须显式 `intentionally_unscoped + standalone_supplement_non_schedule_surface_unscoped`,不能被 silent drop 或额外制造 missing。

Legacy 分类不是开放式 heuristic。`LEGACY_SOURCE_ROLE_MATRIX_V1` 只读先规范化的结构化 tuple `(surface,source_object_type,complete_ref_object_type,type/action_kind/kind/domain,status/list_disposition,driver,horizon_role,section_role,structured_id_family)`,并闭集覆盖现有 producer。Schedule medication/supplement family 只接受 exact `med:<base10 integer>` + matching `domain`;其他 `structured_id_family` 只可由 versioned parser 接受 `meal:{breakfast|lunch|dinner}`、`sleep:{winddown|caffeine_cutoff}`、`workout:today`,不得解析任意前缀或人话。协议 comparable type 也冻结为 reviewed `PROTOCOL_DOMAIN_TYPES_V1 = hydration,diet,sleep,training,medication,supplement,measurement,mood,activity,exercise,checkup,respiratory`,它进入 surface policy version/coverage golden;null、bogus 或模型新增但尚未 bump policy 的 domain 都走 unknown catch-all:

| Family / role | Phase 1a disposition | Controlled exclusion |
|---|---|---|
| today `health_protocol` 非 correction + supported lifecycle | comparable | — |
| today `health_problem/checkup` due/overdue | comparable | — |
| `daily_plan_action` | intentionally_unscoped | `daily_plan_post_guard_selection_uncomparable` |
| `review_schedule/checkup` | intentionally_unscoped | `legacy_review_schedule_unsupported` |
| `training_decision/training/info` | intentionally_unscoped | `legacy_training_decision_unsupported` |
| `day_schedule_workout/movement/(pending|info)` | intentionally_unscoped | `legacy_day_schedule_workout_unsupported` |
| `data_quality/data_quality/info` | intentionally_unscoped | `legacy_data_quality_unsupported` |
| `wearable_router/data_quality/info` | intentionally_unscoped | `legacy_wearable_router_unsupported` |
| `health_protocol/correction/info` | intentionally_unscoped | `legacy_protocol_correction_unsupported` |
| `outcome_correction/correction/info` | intentionally_unscoped | `legacy_outcome_correction_unsupported` |
| `baseline_deviation/baseline_deviation/info` | intentionally_unscoped | `legacy_baseline_deviation_unsupported` |
| runtime future protocol/checkup or `runtime_guidance` | intentionally_unscoped diagnostic | `runtime_future_projection_unscoped` / `legacy_runtime_guidance_unsupported` |
| Schedule generated `meal/diet`、`sleep`、`workout/movement` defaults | intentionally_unscoped | `legacy_schedule_meal_default_unsupported` / `legacy_schedule_sleep_default_unsupported` / `legacy_schedule_workout_default_unsupported` |
| Timeline medication/supplement action with `kind=action`,`driver=plan_driven`,`action_kind == complete_ref_object_type`,`status in {pending,completed,skipped,overdue}` | comparable | — |
| Timeline past/observation、outcome、work、day-rhythm | intentionally_unscoped | role-specific controlled reason |
| DynamicView safety section | intentionally_unscoped + degraded | `safety_snapshot_unavailable` |

同一个 `source.object_type=health_protocol` 的 `type=correction` 不得冒充 due protocol,未知协议 domain 也不能靠 `type != correction` 自动放行;legacy Schedule 自动生成的 meal/sleep/workout 也不得冒充 supported medication occurrence;Timeline 药/补剂的 status、driver、action_kind、complete_ref 任一未知/不匹配也不得 comparable。任何未列 tuple、已知 family 的未知 type/status/disposition/driver/role/id family 或缺必需 discriminator 一律 `intentionally_unscoped + legacy_surface_source_role_unknown`,绝不自动 comparable,也绝不回退 title。这个 catch-all 本身进入 policy coverage obligation,因此新 producer 若未 bump policy/version 和 golden,Gate 必红。

匹配优先级:`complete_ref + slot` -> `source + slot` -> versioned Schedule id -> Daily Plan action_key。无可靠 source 的项必须标 `lossy_identity`,不能退回 title。

diff 方向以 canonical shadow 为基准:

- `missing`:canonical comparable item 在该 legacy surface 缺失;
- `extra`:legacy comparable item 不在 canonical shadow;
- `rank_changed`:同 surface matched items 的相对顺序/top/now 不同;
- `timing_changed`:双方 precision 可比且值不同;
- `safety_changed`:actionable、lifecycle、blocked/degraded 或 safety reason 语义不同。

exact 对 window 不制造假 timing drift,而记 `unsupported_precision`;DynamicView 的已知 intentional dedupe 不算 missing。lossy row 不得伪造 item identity:`opaque_item_key=null`,只带非敏感的 surface-local diagnostic ordinal。diff 最终按 `surface + diff_kind + (opaque_item_key or "") + diagnostic_ordinal + reason_code` 排序。

Surface projector 不接触 key:它们只产生带 typed `ShadowItemIdentity` 的 unsealed comparable row。外层 signing module 用 trusted manifest owner/local-day + normalized identity 统一调用 `item-key` HMAC,封装后移除 raw identity,再交给 diff。legacy-only extra 也必须由这个 sealer 生成 opaque key,不得传 raw/unkeyed source id、复制签名算法或信任 legacy payload 自报 owner/date。Diff 只接受两侧同 policy/version 的 sealed projection;任何 comparable row 缺 key、任何 non-comparable row 夹带 raw identity 或 partial seal 都 fail closed。

每个 policy 先执行**唯一且显式**的 intentional-dedupe rule,然后 canonical/legacy 两侧的 comparable key 必须各自一一唯一。任何剩余重复整组降为 `ambiguous_identity` + controlled reason,禁止 dict last-wins、任选一条或跨组配对;diff 遇未处理 duplicate 直接失败。

Phase 1a 必须含 active HIGH/CRITICAL legacy safety fixture,证明它被明确分类 `intentionally_unscoped` 且 artifact 标 `safety_snapshot_unavailable`,而不是被误报 extra、静默丢弃或参与 `safety_changed`。只有未来独立采集带 revision/acquired_at 的 immutable SafetySnapshotDTO 并经新 Gate 后,才能扩大 safety comparable scope。

Daily Plan subset 也使用同样的证据谦抑:canonical pre-AdviceGuard candidate 与 legacy post-AdviceGuard/top-5 action 两侧都标 `intentionally_unscoped + daily_plan_post_guard_selection_uncomparable`;只有确实消费 smart agenda 的 runtime/Artifact/DynamicView 传播该分类。Regular Agenda oracle 固定为 `agenda_service.today`,Timeline 固定为消费 regular Agenda 的 `build_today_spine`,两者当前都没有 DOP branch,不得制造虚假的 exclusion row。真实 DOP rows 进入 exact coverage matrix,但不产生 `missing | extra | rank_changed | safety_changed`;否则 guard 拦截或 top-5 截断会被误报成 composer drift。每个 candidate 自身仍带 `daily_plan_advice_guard_unsupported` 表示尚未经安全/证据准入。

Legacy oracle 与 shadow candidate 不能共享被 oracle 改过的 DB。测试从同一 deterministic committed baseline 建立独立 PostgreSQL schema copy:每个 legacy surface 各用一个 fresh oracle schema,shadow 再用一个从未调用 legacy builder 的 candidate schema。任何 schema DDL 都要求 exact feature opt-in + test-name heuristic + fresh connection 校验 `current_database()==URL database` + 预先由 ephemeral CI/人工建立的 `health_day_shadow_test_control.safety_marker` 精确值;fixture 不得自建/修复 marker,每次 create/drop/finalizer 都复验,且只接受严格 generated-name regex。Task 3 也用同一 test-only guard/private schema,禁止共享 `db` fixture 或 `Base.metadata` 触碰 public。每 schema 使用独立 `NullPool` engine、`schema_translate_map` + exclusive `search_path`(无 public fallback),每次 checkout 断言 `current_schema/current_schemas`;global engine checkout 与独立 generated poison schema 负例防逃逸,绝不写 public。所有 nested `SessionLocal` alias 必须进入 schema checkout inventory。每 surface/permutation 使用全新 schema-namespaced empty fake cache并销毁/reset module cache。所有 copy 在任何 builder 前的 ordered semantic baseline digest 必须相等;oracle delta 只记录、不复制回 candidate。加 surface 调用顺序置换测试,证明 capture 不依赖先后顺序。

Assembled Gate 使用三份人工复核、不可由被测代码自动更新的合同:`LEGACY_PRODUCER_SITE_INVENTORY_V1` 逐 file+symbol+emitter family+propagated surfaces+required variants 盘点 Daily Plan/Agenda/Schedule/runtime/Artifact/Dynamic/Timeline producer/propagation site,静态 AST extracted site set 必须完全相等,inventory required variant IDs 又必须与 real-builder 实际执行 set 完全相等;multi-value discriminator 每个 member 另有 set-equal 参数 case。`POLICY_COVERAGE_OBLIGATIONS_V1` 与 `LEGACY_SOURCE_ROLE_MATRIX_V1` branch id 集合完全相等并覆盖每个 branch/reason;`EXPECTED_ASSEMBLED_MATRIX_V1` 逐 variant/surface 固定 comparable identities/counts、exclusion counts 与 diff rows。Daily Artifact 至少有 DOP-top 与 supported non-DOP top 独立 variant,calendar/DST flexible timing 也有 real-builder variant。新增/dormant producer/member/branch/exclusion、coverage 缩水或 diff 漂移必须失败;合法改动需 inventory/policy version bump + reviewed obligation/golden update,不能靠 catch-all 或更多 unscoped 变绿。

### 6. No-write proof

被测 loader/composer/projector 必须同时满足:

1. 独立 PostgreSQL connection 以 `isolation_level="REPEATABLE READ", postgresql_readonly=True` 建立事务,并实查 `SHOW transaction_isolation` / `SHOW transaction_read_only`;一个 shadow run 只绑定这一条 connection/Session,`join_transaction_mode="rollback_only"`;
2. 事务内设置 bounded `statement_timeout`、`idle_in_transaction_session_timeout` 和 owner-local `app.user_id`,记录 `pg_current_snapshot()` 仅作测试断言,不进入 telemetry;
3. SQLAlchemy `before_flush` 断言 `new/dirty/deleted` 为空,`before_commit` fail-loud;
4. SQLAlchemy `before_execute` 对 ClauseElement 采用 default-deny 结构 walker:数据查询只允许单个 allowlisted model table 的 `Select`,child node 仅限 allowlisted columns、primitive bind parameter、精确 `Null/True_/False_` 常量、受控 AND/OR、比较/IN/IS 谓词、只包住已批准 boolean tree 的 inert `Grouping`,以及 allowlisted column 的 ASC/DESC 可选**恰一层** NULLS FIRST/LAST(供声明的 `taken_time ASC NULLS FIRST,id ASC`)。这些是 owner/active/null/date-overlap filter 的闭集;Grouping 包值/算术/text/function、未知常量、未知/嵌套 unary modifier 或对表达式排序均拒绝。任意 join/subquery/union、算术/字符串表达式、`FunctionElement`、locking/prefix/suffix、textual/literal SQL fragment、非 allowlist FROM、data-changing CTE、Update/Insert/Delete 和未识别 node 均拒绝。`set_config(app.user_id)`、`SHOW ...`、`pg_current_snapshot()` 等 setup/proof SQL 只能以计划列出的逐字节 TextClause + 精确参数 shape 执行,任意其他 TextClause 均拒绝。每次通过后只发一个 connection-local one-shot approval;`before_cursor_execute` 必须原子消费立即前一条匹配的 clause/compiled/parameter-shape approval,`context.compiled is None`、缺失/错配/重放 approval 或 `exec_driver_sql` 直接拒绝,再拦 DML/DDL/DO/TRUNCATE/CALL/COPY/LISTEN/NOTIFY/LOCK、四种 locking select、sequence/advisory lock、transaction-mode/GUC 改写和 text 变体。所有 shadow module 的 AST 另禁 `exec_driver_sql/raw_connection/driver_connection/DBAPI connection/cursor` escape,loader 只可对 injected Session 使用批准的 Core `execute`。正例必须跑 declared grouped boolean/null/true/false filters 和 NULLS FIRST order;负例必须含 unknown constant、Grouped non-boolean、unknown/nested unary、`select(func.set_config(...))`、`pg_notify`、fixture volatile UDF、driver SQL 和 approval 重放,并在事务外比较 GUC、notification listener、lock、sequence/temp/table state。数据库 `READ ONLY` 是普通持久表的最终硬门,但 PostgreSQL 允许部分 temp/session/external-effect 操作,不能只信 DB、`Select` 类型或字符串 denylist;
5. shadow module 使用无环逐文件 import allowlist:`health_day_shadow_contracts` 是 stdlib-only behavior-free leaf;source table mapping 使用 private metadata 且只依赖 SQLAlchemy,为全部 measured source 定义闭集最小列。loader 不得 import 任何 `app.models.*`/`app.database`/`app.config`,因为现有 ORM model 都经 Base 触发 global config/engine,calendar model 还会 import-time 构造 Fernet;signing/summary 只依赖 contracts + `cryptography`;composer 只依赖 contracts + signing;projector/diff 只依赖 contracts;loader 额外只允许 SQLAlchemy + source mapping + contracts/signing。动态 import/eval 禁止。fresh-process import 以 fail-loud hook 禁 `app.config`/`app.database`/`app.models`/Fernet,避免 conftest cache 假绿;`SessionLocal`、任何 legacy builder/service、Redis、环境 provider、PushService/outbox/notification producer 全部静态禁入并在集成测试 patch 为 fail-loud;
6. composer/projector 完成后 Session identity map 仍无 dirty object,相关表 before/after 状态一致;
7. shadow 调用阶段不挂 TestClient/现有 public endpoint,防止进入 legacy materializer;所有退出路径都 rollback + close;
8. PostgreSQL MVCC barrier 固定为:shadow scalar SQL 读 A -> writer 独立 commit B -> fresh reader 确认 B -> shadow 再发 scalar SQL 仍读 A;前后 `pg_current_snapshot()`、isolation/read-only 均不变,不得用 ORM identity map 当证据。
9. 每条恶意 SQL 使用全新 read-only transaction。DB-authority cases 关闭自定义 guard并只接受 SQLSTATE `25006`,不得接受任意异常/`25P02`;guard cases 单独断言受控 guard error。事务外比较 sequence `last_value`、相关表和 temp schema/object before/after。owner isolation 以显式跨用户 fixture 验证;测试 role 可能是 superuser,不得把结果夸大成 RLS 证明。

### 7. Telemetry allowlist

Phase 1a 不写 telemetry。只提供可在测试中检查的 redacted in-memory summary:

```yaml
allowed:
  schema_version
  overall_status
  source_status_counts
  diff_counts_by_surface_and_kind
  degraded_reason_codes
  duration_bucket
forbidden:
  owner/date/timezone/digest/key_id
  source ids/item keys/titles/free text
  medications/supplements/diagnoses/labs/readings
  raw manifest/payload/diff rows/exceptions
```

## G2 · 可行性 + 安全压测

- 评审方式:☑ 三条独立只读审计(composer/write boundary、projection/diff、PostgreSQL/Gate) + 主 agent 代码复核。
- 已焊进规划的硬边界:
  - shadow module 逐文件 import allowlist;public/transitive legacy wrapper、SafetyGuardian registry、wall clock/logging 禁入;
  - 全部 measured source 通过 SQLAlchemy-only 闭集最小 table mapping 读取;fresh-process 证明 shadow import 不触发 app model/Base/global engine/config/secret/Fernet 或解密;
  - 单 PostgreSQL read-only repeatable-read snapshot;
  - unsupported/unknown fail visible,calendar failure 不得等于 free;
  - bounded in-memory Daily Plan shadow subset + per-slot medication projector;existing DOP/Day Schedule row/wrapper 不充当 canonical truth,也不把 subset 宣称为已提取的完整 DOP calculation half;
  - Daily Plan 逐字段 source matrix 锁定可支持 weight/single-source recovery/structured acute+intervention/terminal/cycle 事实;lab flags、composite training gate、AdviceGuard/top-5、prediction 和 registry label 明确 degraded/unscoped,缺失不得当 green/allowed;
  - symmetric canonical/legacy surface policy + normalized-minute/dose-ordinal identity + complete lifecycle + title-free matching;
  - item identity/HMAC 必含 closed storage namespace,Medication-table supplement 与 standalone definition 同 numeric id 不碰撞;Schedule/Timeline 以 `derive_legacy_occurrence_context_from_bundle(bundle,key_provider)` 先验签并从 same snapshot/same original bundle object 派生 `LegacyOccurrenceContext`,不引入 wrapper、不接受 oracle 输入;
  - 每个 legacy surface 与 untouched candidate 从相同 committed semantic baseline 建独立 PostgreSQL schema;oracle delta 永不喂回 shadow;
  - schema DDL 需 feature opt-in + fresh current_database/marker 复验 + strict generated-name regex;Task 3/7 禁 shared `db` fixture、public DDL 和自建 marker;
  - 五个 Phase 1a tests + local conftest/helper 位于独立 `backend/health_day_shadow_tests/` sibling tree,不加载 `backend/tests/conftest.py`;真实 Redis/provider/global engine 默认 fail-loud,legacy oracle 只用 per-schema/per-variant 空 fake cache;
  - assembled 证据按闭集 `variant_id × surface_id` case manifest 在 collection time 参数化,每个 JUnit node 只创建一组 candidate/oracle/minimal-poison;禁止在单 test body 内遍历全 matrix;
  - 独立 blocking `health-day-shadow-postgres` job 使用自己的 ephemeral PostgreSQL 16 database、30 分钟 job budget + 120 秒 per-test budget,并作为 `backend-tests` aggregate 的必过依赖;不挤占现有 Runtime job 的 20 分钟预算;
  - 无 runtime wiring、持久化、mutation、notification 或 client/API;
  - aggregate-only in-memory telemetry summary;
  - exact two-segment frame/HKDF/output grammar、payload-bound source HMAC、受限 RFC 8785/JCS 完整 golden vector 和 fail-closed input domain,不引入陈旧的新依赖;
  - PostgreSQL raw-scalar MVCC barrier、per-transaction SQLSTATE/structural allowlist 负例、跨 owner、row/sequence/temp/GUC/notify/lock before-after 和 mechanical no-skip CI 证据合同;
  - DST nonexistent/ambiguous wall-clock 时点在无 offset/fold 证据时 fail visible/non-actionable;effective timezone 在同一 snapshot 内按 profile precedence 推导并签入 manifest;Calendar UTC instant 只产降级本地 offset/fold/cross-midnight 诊断,all-day/floating provenance 不足且不授权 free/retime;
  - authoritative safety snapshot 缺失时 active safety row 明确 unscoped + artifact degraded,不制造 safety parity。
- 待拍板分叉:无。上线 runtime、authorizing snapshot、SafetyGuardian recompute 和生产 key wiring 均明确不属于本 child,不得在实现中顺手加入。
- 当前环境未设置 `TEST_DATABASE_URL`;这是 G3 执行前置,不是实现前 G2 循环条件。
- **裁决: PASS。** 仅允许按本计划进入 S4/S5;父 `quiet-proactive-health-day` 仍为 G2 BLOCK,Phase 2–4 仍不得实施。

## S4 · 研发任务分解

- 用户已于 2026-08-15 明确要求“按照计划行动”;当前按实施计划从 Task 0 开始分批执行。
- Workflow trace:`docs/_generated/harness-runs/ae8348a1d08b.jsonl`（本地生成物,不提交）。
- 原子任务、精确文件和 red/green 命令见实施计划。
- 实现前重新 `git fetch` + `gh pr list`;不依赖 PR #225,并在 Task 9 前明确处置与 PR #252 的 CI/system-map 重叠。

## G3 · 测试闸

待实现后执行,只接受显式隔离 PostgreSQL。运行下列命令前必须先按 Task 0 在这个 disposable database 预装 authority marker;fixture 不会替你创建:

```bash
set -euo pipefail
PHASE1A_TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/health-day-phase1a.XXXXXX")"
PHASE1A_JUNIT="$PHASE1A_TMP_DIR/report.xml"
trap 'rm -f "$PHASE1A_JUNIT"; rmdir "$PHASE1A_TMP_DIR"' EXIT
env -u TEST_DATABASE_URL -u HEALTH_DAY_SHADOW_TEST_DDL_OPT_IN \
  DATABASE_URL="sqlite:///:memory:" \
  POSTGRES_HOST="" POSTGRES_PASSWORD="" \
  REDIS_URL="unix:///nonexistent/health-day-shadow-phase1a.sock" \
  TZ=Asia/Shanghai backend/venv/bin/python -m pytest \
  backend/health_day_shadow_tests/test_health_day_shadow_architecture.py -q --no-cov
export HEALTH_DAY_SHADOW_TEST_DDL_OPT_IN=drop-generated-health-day-shadow-schemas-v1
DATABASE_URL="$TEST_DATABASE_URL" TEST_DATABASE_URL="$TEST_DATABASE_URL" \
  POSTGRES_HOST="" POSTGRES_PASSWORD="" \
  REDIS_URL="unix:///nonexistent/health-day-shadow-phase1a.sock" \
  SECRET_KEY="test-secret-key-32-chars-minimum!!" \
  GARMIN_ENCRYPTION_KEY="mI4nYXirjGlbHD7sFogYlqPQJzirU04mUsS5LyDS0SU=" \
  TZ=Asia/Shanghai backend/venv/bin/python -m pytest \
  backend/health_day_shadow_tests/test_health_day_composer.py \
  backend/health_day_shadow_tests/test_health_day_projection_contract.py \
  backend/health_day_shadow_tests/test_health_day_shadow_postgres.py \
  backend/health_day_shadow_tests/test_health_day_shadow_assembled_postgres.py \
  backend/health_day_shadow_tests/test_health_day_shadow_architecture.py \
  -q --no-cov --timeout=120 --timeout-method=signal \
  --junitxml="$PHASE1A_JUNIT"
backend/venv/bin/python backend/scripts/assert_pytest_no_skips.py \
  "$PHASE1A_JUNIT" \
  --require-module test_health_day_composer \
  --require-module test_health_day_projection_contract \
  --require-module test_health_day_shadow_postgres \
  --require-module test_health_day_shadow_assembled_postgres \
  --require-module test_health_day_shadow_architecture \
  --max-case-seconds 90 \
  --max-suite-seconds 1500
```

还需运行 legacy projection 回归、CI contract、Dossier consistency、system-map 和 doc-drift。五个 Phase 1a module 与其 fixture 必须全部放在 `backend/health_day_shadow_tests/`,位于 `backend/pytest.ini` 的 `testpaths=tests` 之外,不继承 `backend/tests/conftest.py`、不被默认 SQLite shard/广义 `pytest tests/` runner 发现。它们由独立 blocking `health-day-shadow-postgres` job 以精确路径、无 skip 执行,该 job 有独立 PostgreSQL service、30 分钟总预算、120 秒 hard per-test 预算,并接入 `backend-tests` aggregate。JUnit gate 逐一要求五个 module 至少执行一个 testcase、拒绝任何 skip,并要求每 case `<90s`、整套 `<1500s`留出安全余量。不得以 SQLite skip、未收集 module、helper-only mock 或单节点遍历全 matrix 通过。

## G4 · 安全闸

待实现后独立复审。重点:oracle baseline 污染、surface scope 假 diff、no-write/registry/clock/SessionLocal/Redis/provider 逃逸、slot/lifecycle 折叠、calendar unknown 变 free、fixed/rejected item 丢失、safety unsupported 被伪装 comparable、L3 telemetry 泄露和把 shadow key 当授权 token。

## S6/G5 · 部署健康

本 child 无部署/production rollout。代码合入后仍保持无调用点;若发现任何 runtime wiring,Gate 失败回 S5 删除。

## S7/G6 · 上线验证

不适用生产验证。Phase 1a 的闭环是隔离 PostgreSQL assembled/no-write evidence;它不证明用户可见 Health Day 已上线。

## S8 · 沉淀

实现后把 hidden-write inventory、pure seam 和 diff evidence 回填本 Dossier。只有代码/路由/架构结构实际变化时才重新生成 system map;纯文档阶段不手改代码派生计数。
