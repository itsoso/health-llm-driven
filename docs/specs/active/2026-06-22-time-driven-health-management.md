# Feature Spec: Time-Driven Health Management

> Status: draft
> Owner: Reva / Personal Health OS
> Updated: 2026-06-22
> Related PRD/PDD: docs/prd/reva-personal-health-os-prd.md · docs/prd/2026-06-19-proactive-planning-prd.md · docs/specs/active/2026-06-17-day-timing-schedule.md · docs/specs/active/2026-06-19-p1-pre-event-reminders.md · docs/specs/archive/2026-06-18-calendar-v2.md
> Related code: backend/app/api/schedule.py · backend/app/services/{day_schedule_service,timing_solver,timing_adapter,schedule_diet_sleep,agenda_service}.py · backend/app/tasks/event_reminders.py · backend/app/api/{agenda,rokid,write_intents,reorder_intents}.py · backend/skills
>
> **Current release override (2026-08-12):** historical shipped/OTA evidence below remains a dated
> fact, not a current command. All repo-contained automatic remote/vendor release entrypoints, local
> signing/install/automatic-provisioning entrypoints and OTA/rollback channels are frozen. Only
> production network observation and release plan/validate are also frozen. Only local Metro/iOS
> Simulator/tests, offline evidence and public unauthenticated HTTPS are allowed, and none forms
> G5/G6; physical iOS/Rokid/Watch
> acceptance is a future external-manual evidence gap and remains BLOCKED.

## 1. Decision

把 Reva 的日程能力从“药/补剂/锻炼的时间轴”升级为统一的
**时间驱动健康管理层**:所有可执行健康行为都先变成 `HealthProtocol`,再由后端根据
作息、日历、身体状态、安全规则、设备观察和外部技能能力投影成 `HealthAgendaItem`,
并通过提醒、硬件、技能或人工确认产生 `ExecutionEvent` 和复盘。

## 1.5 Reconciliation & Build Status（Claude A · 2026-06-22）

> 本节把已落地的「执行层闭环基础」与本 spec 对齐,并回答 §18 的 must-decide 开放问题。
> **本 spec 仍是时间驱动健康管理的权威路线图**;以下只补「已建什么 + 三个开放问题的裁决 + 脊柱 seam 对齐」,
> 不改写下游章节。结论:Codex 的本 spec 与已建的 Increment 1 **互补、非冲突** —— 本 spec 描述
> 「协议→投影→设备观察→外部意图」的**输入/编排侧**,Increment 1 已建其中的**执行/闭环侧**(= 本 spec §7 的
> `-> ExecutionEvent -> Review` 段)。

### 1.5.1 已构建:执行层闭环（= 本 spec 的 ExecutionEvent + 闭环段）

Increment 1 已合并 main(`f1ca1802`,未部署),实现了 §7 流水线
「`HealthAgendaItem timeline -> ... -> ExecutionEvent -> Review`」的执行/闭环段:

- **first-class HealthEvent agenda 生命周期** —— 扩展 `health_events`:`agenda_status`(pending→done/skipped/expired)
  + `scheduled_for` + `action_kind` + `complete_ref`,与既有 fact-stream `status` 枚举正交。即 §9.2 的
  「reuse ExecutionEvent if schema sufficient」:**执行事实统一落在 HealthEvent,不另起 ExecutionEvent 表**。
- **闭环完成端点** `POST /api/v1/timeline/events/{id}/complete` `{status, skip_reason?}` —— 翻转生命周期
  + 委托既有双轨 `agenda_service.complete_item` dispatcher 写真实源 + 幂等 + JWT 用户隔离 + 写失败返 422
  (不假装成功)。这是 §13 user flow 的 confirm/skip 落点。`skip_reason ∈ {no_time, forgot, no_supply,
  too_tired, wrong_place, too_hard, unwell, social}` —— 直接喂 §14 P6 learning loop。
- **past 投影**(`timeline_past_service`)—— 简报/异常进 timeline past,**复用 critical/medical_grade 排除**
  + `association_only`(相关非因果),即 §11 医疗边界 + non-goals 排除卡。
- **到点推送 data** 带 `category:AGENDA_ACTION` + `complete_ref` + `complete_endpoint` —— §9.1 的
  `execution.confirmation_required` 在通知侧的承载,使「推送→一键完成→首页熄灯」闭环可达。
- 测试 12/12 + 全套 3912 绿;doc-drift 绿。

### 1.5.2 §18 开放问题裁决(must-decide before P1)

1. **协议模板存哪(DB/code/hybrid)** → **hybrid**:9 个协议模板做成**代码常量**(同 SafetyGuardian 规则的工程惯例
   —— 可 version、可测、随部署走),seed 成**用户级 `HealthProtocol` DB 实例**(可个性化覆盖 timing/cadence)。
   Appendix A 临床默认值作为 seed 源。理由:模板是确定性逻辑(归 Agent 层),实例是可变业务(归 DB)。
2. **DeviceObservation 新模型 vs 折进 ExecutionEvent** → **统一折进 HealthEvent 流**:设备原始信号
   (`posture_bad`/`screen_focus_started`…)= HealthEvent(observation 类,带 `provider`/`event_type`/`confidence`/payload);
   完成信号(`eye_break_completed`…)→ 翻转对应 agenda HealthEvent 的生命周期。`POST /device-observations` 作为
   **薄 ingest**,内部落 HealthEvent。**一个事件模型、一条脊柱**,避免 ExecutionEvent / DeviceObservation /
   HealthEvent 三套并存。(Increment 1 已把执行事实落在 HealthEvent,此裁决与之一致。)
3. **首个 eye/screen-focus 信号由谁产** → **P1 先 Mobile 计时器 + 人工确认**(零硬件依赖,先把先验闭环跑通);
   **P2/P3** 接 Mac screen-focus adapter / Rokid 作为真实信号源。不阻塞 P1。

### 1.5.3 脊柱 seam 对齐(`/schedule/today` vs `/timeline/today`)

保持**两层、不重复**:
- `/schedule/today`(`day_schedule_service` + `timing_solver` 输出)= **上游**;§9.1 的富字段
  (`trigger`/`surface`/`chain`/`execution`/`safety`)在此 item 上产出。
- `/timeline/today`(`today_timeline_service`:agenda 未来 + past + outcome + 已加的 HealthEvent 生命周期)
  = **首页脊柱**,home 渲染只读它。§9.1 富字段经 agenda 投影流入 timeline 项。

**首页只有一个脊柱面**(`/timeline/today`);`/schedule/today` 是其上游 solver,不直接喂 home。

### 1.5.4 合并后路线图(本 spec §14 P0-P6 ⇄ Increment 编号)

| 状态 | 阶段 | 内容 |
|---|---|---|
| ✅ 已建 | (= §7 ExecutionEvent + loop) | HealthEvent agenda 生命周期 + 完成端点 + past 投影(Increment 1, `f1ca1802`) |
| ✅ 已建 | 横切·闭环 | **完成回路打通**:`complete_item` 加 medication/supplement 分支(与药同表,复用幂等 `log_medication`)+ `complete_by_ref` 核(懒物化 + 经 `complete_agenda_event` 单事务 + DB 原子认领防虚高依从)+ `can_complete` 扩到药/补剂 + 修推送 `complete_endpoint` 占位符 → `/agenda/complete`(后端 `f845ff9f`);**移动端 AGENDA_ACTION 推送类目 + 完成/跳过 handler**(`mobile/hooks/useNotifications.ts`,JS-only 可 OTA,前端 `4d940a79`)。安全 re-review **GO**;6 不变量复核;对抗测试真红保护幂等。 |
| ✅ 已建·已上线 | §14 P1a | 协议模板地基 + nasal_wash×2 + sleep_winddown(`c93077e8`):`protocol_templates.py` 代码常量注册表 + 幂等 `seed_behavior_protocols` + `POST /protocols/seed/behavior`(按需启用,非全员 auto-seed)+ 提醒桥(`time_window→HH:MM`、protocol 进 `_collect_timed_items`、**P1 绝不 P0**、`AGENDA_ACTION` 接完成/跳过)+ nasal 红旗 fail-safe 抑制 + R4 措辞。`respiratory` 入 `PROTOCOL_DOMAINS`。安全 self-review **GO**。 |
| ✅ 已建·已上线 | §14 P1b | `eye_20_20_20` 移动端 20-20-20 本地通知计时器(`a8f339a9`,JS-only/OTA,64-cap 滚动调度,明标时间近似非 screen-focus)+ `work_microbreak` §8.3 确定性安全门(`edf075e3`:readiness 红→mobility/rest、餐后<60min→免俯卧撑、急症→拒;含 GI-bleed 红旗)+ 移动端 skip+原因 UI(`02ca8b88`,8 原因喂 P6)。安全 GO(修 tz fail-open BLOCKING + archive HIGH)。 |
| ✅ 已建·已上线 | §14 P2 | 通用 DeviceObservation API 折进 HealthEvent(`04032c97`,无新表):signal verb=纯事实(不推不翻)、completion verb=复用 `complete_by_ref` 闭环(恰一条领域写)、拒原始帧/媒体、用户隔离;镜像 Rokid 俯卧撑。安全 GO。**仅后端契约——on-device adapter 见 P3** |
| ⬜ 外部边界 | §14 P3 | 坐姿/用眼硬件 adapter(Rokid posture / camera 本地姿态 / Mac screen-focus)—— **需真机 + Codex 活跃的 Rokid SDK,非纯软件可自主完成**;后端 DeviceObservation 契约(P2)已就位,缺的是 on-device 采集 + 真机验证 |
| ✅ 已建·已上线 | §14 P4 | workout chain(`07f8403a`):7 条 linked HealthProtocol(pre_check→workout→stretch→shower→massage→meal→review),链指针进 `implied_quantity` + `chain_key` partial-uniq DB backstop,reuse readiness/acute 降级(RED/rest→只拉伸),opt-in,meal 链既有恢复餐。安全 GO(修 fail-loud B1:`db.rollback()` 防链失败拖垮整议程,对抗测试真红)。 |
| ✅ 已建·已上线 | §14 P5 | external intents(`105e7749`):WriteIntent 账本加 `alarm_set`/`doctor_booking`(mint SmartReminder,doctor 源 ReviewSchedule)/`food_order`(**DRAFT-only**,confirm 返 acknowledged,inert 501 gateway)。manual_confirm 恒定;**永不自动支付、不存 L4 支付凭证**(嵌套 payment-key 递归拒,`578ee9a1`)。R4 食饮摘要过 guidance_validator。安全 GO。真外卖/挂号 provider = 外部边界(inert seam,需账号绑定+财务评审) |
| ✅ 已建·已上线 | §14 P6 | learning loop(`caed55f8`):extend self-correction seam → **suggest-only** field_delta(time_window/cadence/cooldown/surface)+ per-protocol nudge throttle(**只减不增、绝不 P1→P0、绝不动全局预算**)+ `/protocols/{id}/apply-adjustment`(**R4 硬门:绝不改药/补剂剂量**,3层守门红绿)+ 周 Celery audit-only。per-user 不跨用户。安全 GO。 |
| ✅ 已建·已上线 | 横切·稳健 | **CI UTC-runner vs Asia/Shanghai 午夜 date-base flake 根治**(`fd37225a`:CI 加 `TZ=Asia/Shanghai` 与生产同基准 + `_auto_observe` 对齐 date 收敛设备闭环恰一条事件——修了真生产 bug:上海午夜双写虚高依从)+ **Codex 跨家 capstone 评审修**(`578ee9a1`:嵌套 L4 支付 key 递归拒、device-obs/chain China-day 归一、文案软化)。CI 绿;4015 测试。 |

> 安全前置:Increment 1 基础在跑 P1 catalog 前需过一轮 safety-privacy review(R4 不诊断/不开方、R15 通知预算、用户隔离、§11 边界)。**已完成**(2026-06-22):基础 + 完成回路 APPROVE_WITH_FIXES → 修幂等 HIGH(`uq_medlog_med_date_time` + DB 原子认领 + 确定性 taken_time)→ re-review **GO**。
>
> **上线状态(2026-06-23,已全部上线)**:后端全量增量已部署生产(`f7b47b65`→`fd37225a`→`578ee9a1`,health 60/60,两次迁移 `workout_chain_enabled`/`chain_key` 已应用,celery-beat 重启接 `protocol_learning_watch`,prod `.env` 零漂移)+ `api.generated.ts` 已 `generate-types` 同步(`33f7e65a`)+ 移动端 OTA 已发(production channel,update `c2757163`,runtime 1.3.0,接 TestFlight build 184)+ TestFlight build 184 已 submit。CI 绿。
>
> **仍需外部输入（当前不得执行）**:① 解冻后由仓库外获权人工流程验证真机全链路(推送→完成/跳过→首页熄灯、用眼计时器、洗鼻/睡前提醒);② P3 坐姿/摄像头硬件 on-device adapter(需真机 + Rokid SDK);③ 真外卖/挂号 provider 接入(需账号 + 财务/安全评审,**支付永远用户自己执行**);④ 行为协议的「建议启用」UI(auto-seed 因 不劫持 故意不做,现经 `/protocols/seed/behavior` 手动启用)。前两项当前保持 BLOCK，Simulator 不得替代。

## 2. Problem

当前用户想要的不只是“今天几点吃药”。

第一用户是高强度工作的中年用户:长期坐在电脑前,有补剂/药物/体检/慢病复查/锻炼/睡眠/
饮食这些互相影响的事务,但每天没有足够带宽自己做排程、记忆、执行和复盘。

现有实现已经有重要基础:

- `timing_solver` 能把药、补剂、饮食、睡眠、锻炼按时点、餐锚、间隔、静默窗、恢复状态排入当日时间轴。
- `/api/v1/schedule/today` 能输出 `scheduled/rejected/deferred`。
- `agenda_service` 能把协议、随访、训练决策、数据质量和自我修正投影成 agenda。
- `event_reminders` 已定义事件前提醒,复用推送、通知预算和去重。
- Calendar v2 已把 CalDAV/.ics 的忙碌块输入到 day schedule,且对 LLM 只暴露脱敏 busy block。
- Rokid 已有俯卧撑 session/event/review 链路,但仍是俯卧撑专用。
- backend Agent skills 已覆盖营养、补剂、训练、提醒等入口,但技能不是核心安全裁判。
- `WriteIntent` / `ReorderIntent` 已经表达“建议写回/建议下单”的手动确认边界。

不足也很明确:

- 科学坐姿、科学用眼、工作间隙动作、洗鼻等还不是一等 `HealthProtocol`。
- Rokid/摄像头/桌面活动等设备信号没有统一的 observation contract。
- “锻炼前提醒 -> 锻炼 -> 拉伸 -> 洗澡 -> 按摩 -> 餐后营养 -> 复盘”还没有作为一个有前后置步骤的 protocol chain。
- 医生预约、外卖下单、闹钟设置等外部动作还缺统一的 `ExternalActionIntent` 手动确认契约。
- 饮食、补剂、睡眠建议虽然已有局部能力,但还没有完整说明如何受基因、最近检查、疾病治疗、药物、身体状态共同约束。

如果不统一,系统会继续堆功能:每个场景都有自己的提醒、按钮、设备接入和技能调用,最后变成多个健康小工具,
而不是 Personal Health OS。

## 3. Requirement Admission

```yaml
RequirementAdmission:
  request: 以时间线和时间驱动方式实现坐姿、用眼、工作间隙动作、洗鼻、补剂、医生预约、锻炼、饮食、睡眠管理
  classification: new_product_behavior
  first_user_fit: yes — 高强度工作者需要把健康行为压到合适时间点并减少执行带宽
  core_loop_step: Agenda top action / execution / verification / review
  first_class_objects:
    - HealthProtocol
    - HealthAgendaItem
    - LeverageAction
    - SafetyGuardian
    - HealthTwin
    - ExecutionEvent
    - WriteIntent
  target_surface: Backend source of truth -> Mobile daily timeline -> Watch/Mac/Rokid/skills execution
  source_of_truth: backend timing + agenda + safety + write-intent services
  safety_level: medical_boundary
  prescription_or_causal_verdict: no
  autonomy_tier: manual_confirm by default; passive observation allowed only after consent
  evidence_provenance: user data + clinician orders + deterministic safety rules + source protocol metadata
  claim_hedging: advisory; never diagnosis, dose change, or emergency clearance
  verification_window: same-day execution + 7-day adherence + protocol-specific 4/8/12-week review
  success_metric: completed high-leverage timed actions with safety gate and verification plan
  added_user_burden: low-to-medium
  burden_justification: 增加少量确认,换取少做日程心算、少漏执行、少错误时点
  non_goals: 见 §4
  smallest_end_to_end_slice: protocol template -> day_schedule projection -> reminder -> execution event
  stale_surface_to_remove_or_archive: 不新增平行提醒页;后续把旧分散提醒收口到 schedule/agenda
  spec_required: yes
```

## 4. Non-Goals

- 不诊断疾病,不替代医生,不提供急救分诊结论。
- 不自动更改处方药、补剂剂量、慢病治疗方案或复查周期下限。
- 不把摄像头原始图像默认上传到后端或 LLM。
- 不自动点外卖、付款、预约医生、设置闹钟;这些都是 `manual_confirm` 外部意图。
- 不把 Agent skills 作为核心医疗/安全推理层;skills 是受控入口和执行通道。
- 不在第一版做完整 habit/game/streak 社交化激励。
- 不为每个场景造新表和新 API;优先复用 `HealthProtocol`、`HealthAgendaItem`、`ExecutionEvent`、`WriteIntent`。

## 5. Product Object Mapping

| Object | Change |
|---|---|
| `HealthProtocol` | 新增时间驱动协议模板:posture, eye_break, microbreak, nasal_wash, supplement_timing, doctor_followup, workout_chain, nutrition_ordering, sleep_winddown。 |
| `HealthAgendaItem` | 所有协议实例投影成当日/本周可执行项,含触发条件、提前量、执行面、后续项、验证方式。 |
| `LeverageAction` | 把“现在做 20 秒远眺 / 10 个俯卧撑 / 预约复查 / 睡前关闭进食”表达为可执行动作。 |
| `SafetyGuardian` | 决定药物/补剂相互作用、训练 readiness、红旗症状、睡眠/饮食/慢病边界;LLM 不绕过。 |
| `HealthTwin` | 提供身体当前状态:睡眠债、训练恢复、症状、基因倾向、最近检查、用药/补剂、慢病标签。 |
| `ExecutionEvent` | 记录完成、跳过、延后、自动观察、硬件触发、技能执行结果和失败原因。 |
| `WriteIntent` | 提醒、记录、闹钟、预约、外部下单、饮食记录等写回都经手动确认或明确 allowlist。 |
| `InterventionCycle` | 对慢病、睡眠、训练、营养等中期干预定义 4/8/12 周验证窗口。 |

## 6. Current Capability Inventory

### 6.1 已具备的后端时间轴

- `backend/app/services/timing_solver.py`
  - 支持 `medication/supplement/diet/movement/sleep/checkup` domain。
  - 支持空腹、餐前、随餐、餐后、睡前、训练前后等 anchor。
  - 支持 quiet hours、busy blocks、work window、meal window、workout preference。
  - 支持钙/铁、左甲状腺素/钙铁、抗生素/益生菌等间隔约束。
- `backend/app/services/day_schedule_service.py`
  - 从药/补剂、用户作息、Calendar busy block、Garmin readiness、运动处方、营养/睡眠处方构建每日计划。
  - 现在已经能把 workout block、meal items、sleep winddown/caffeine cutoff 排进 schedule。
- `backend/app/api/schedule.py`
  - `GET /api/v1/schedule/today` 已能暴露当日 `scheduled/rejected/deferred`。

### 6.2 已具备的 agenda / reminder / write 基础

- `backend/app/services/agenda_service.py`
  - 已投影 protocol、problem follow-up、training decision、timing-solver workout、data quality 等。
- `backend/app/tasks/event_reminders.py`
  - 已定义事件前提醒的 lead time、去重、通知预算、推送路径。
- `backend/app/services/write_intent_service.py`
  - 已有 pending/confirm/cancel 的手动确认写回结构。
- `backend/app/services/reorder_intent_service.py`
  - 已有补剂低库存/下单意图雏形,且现阶段不自动下单、不处理支付凭证。

### 6.3 已具备的硬件/skills 基础

- Rokid 俯卧撑:
  - `backend/app/api/rokid.py`
  - `backend/app/services/rokid_pushup.py`
  - `backend/app/services/rokid_pushup_review.py`
  - 已支持 session、event ingest、finish、review,但不是通用 hardware observation。
- Agent skills:
  - `nutrition-advisor`: 饮食建议和记录入口。
  - `supplement-advisor`: 补剂建议入口,需检查用药/慢病。
  - `workout-coach`: 训练前准备、训练后同步/分析入口。
  - `reminder-setter`: 提醒入口,但要和当前后端提醒 API 重新对齐后才能作为正式契约。

## 7. Target Architecture

```text
Signals
  calendar / wearable / labs / meds / symptoms / genotype / device observations / user preference
    -> HealthTwin + SafetyGuardian
    -> Protocol Registry
    -> Time Orchestrator(day_schedule + agenda projection)
    -> HealthAgendaItem timeline
    -> Reminder Dispatcher / Device Prompt / External Skill Intent / Manual Action
    -> ExecutionEvent
    -> Review + protocol adjustment
```

### 7.1 Protocol Registry

所有场景先定义成协议模板,不直接写提醒逻辑。

```yaml
HealthProtocolTemplate:
  key: eye_20_20_20
  domain: eye_health
  cadence:
    type: accumulated_duration
    source: screen_focus
    threshold_minutes: 20
  action:
    title: 20 秒远眺
    duration_seconds: 20
    surface: mac_or_watch
  safety:
    red_flags: [eye_pain, sudden_vision_loss]
  reminder:
    lead_minutes: 0
    cooldown_minutes: 20
    notification_tier: P1
  verification:
    event_type: eye_break_completed
    review_window_days: 7
```

第一版协议模板至少覆盖:

| Protocol | Domain | Trigger | Default surface |
|---|---|---|---|
| `posture_monitoring` | ergonomics | 工作块内坐姿异常持续 N 秒 | Rokid/camera/Mac |
| `eye_20_20_20` | eye_health | 有效屏幕专注 20 分钟 | Mac/Watch/Rokid |
| `work_microbreak` | movement/hygiene | 工作 60-90 分钟或会议间隙 | Watch/Rokid/Mobile |
| `nasal_wash` | respiratory | 早晚/过敏环境/症状/医嘱 | Mobile/Watch |
| `supplement_timing` | supplement | 身体状态 + 用药/餐/训练约束 | Mobile/Watch |
| `doctor_followup` | checkup | 医嘱/慢病复查/体检周期 | Mobile/Mac/skills |
| `workout_chain` | movement | 周计划 + 当日 readiness + 日历空窗 | Mobile/Watch/Rokid |
| `nutrition_planning` | diet | 餐前/训练前后/治疗与检查状态 | Mobile/skills |
| `sleep_winddown` | sleep | 目标睡眠时间倒推 | Mobile/Watch/alarm skill |

### 7.2 Time Orchestrator

`day_schedule_service` 应继续做 source of truth,但从“药/补剂/餐/睡/锻炼”扩展成
“protocol items + constraints”。

新增或扩展内部接口:

```python
def protocol_templates_to_items(
    *,
    protocols: list[HealthProtocol],
    context: DayContext,
    twin: HealthTwinSnapshot,
    safety: SafetyDecisionSet,
    observations: list[DeviceObservation],
) -> list[Item]:
    ...
```

输出仍然进入 `solve_day_schedule`,避免每个协议自己算时间。

### 7.3 Device Observation Layer

Rokid、摄像头、桌面活动、NFC、手动按钮都进入统一 observation contract。

```yaml
DeviceObservation:
  id: server_generated
  user_id: authenticated_user
  provider: rokid | camera_local | mac_activity | watch | mobile | nfc | skill
  device_type: glasses | camera | desktop_agent | watch | phone | external_agent
  event_type:
    - posture_bad
    - posture_ok
    - screen_focus_started
    - screen_focus_ended
    - eye_break_completed
    - pushup_rep
    - pushup_set_completed
    - hand_sanitize_completed
    - nasal_wash_completed
    - food_order_confirmed
    - food_logged
    - alarm_set_confirmed
  occurred_at: iso_datetime
  confidence: 0.0-1.0
  source_session_id: optional
  payload: minimal_structured_metrics
  privacy_class: L2 | L3 | L4
```

API draft:

```http
POST /api/v1/device-observations
Authorization: Bearer <device_or_user_token>
Content-Type: application/json

{
  "provider": "rokid",
  "device_type": "glasses",
  "event_type": "posture_bad",
  "occurred_at": "2026-06-22T10:31:00-04:00",
  "confidence": 0.86,
  "source_session_id": "work-block-2026-06-22-am",
  "payload": {
    "neck_flexion_degrees": 34,
    "duration_seconds": 75
  }
}
```

Privacy rule:摄像头默认只上传结构化姿态/行为指标,不上传原始图像、音频、会议标题、位置或联系人。

### 7.4 External Action Intent

外部技能只处理“受控动作”,不是核心健康判断。

```yaml
ExternalActionIntent:
  intent_type: food_order | doctor_booking | supplement_reorder | alarm_set | calendar_hold | reminder_set
  source_agenda_item_id: optional
  autonomy_tier: manual_confirm
  proposed_payload: minimal_required
  safety_summary: deterministic_checks
  user_visible_summary: required
  status: proposed | user_confirmed | executed | failed | cancelled
  audit_required: true
```

第一版可以先复用 `WriteIntent` + `ReorderIntent`;等外部动作变多后再抽独立模型。

Hard rules:

- 点外卖和付款:不自动付款,不保存支付凭证,每单必须用户确认。
- 医生预约:可以准备候选科室/时间/材料,最终预约必须用户确认。
- 闹钟:可以建议并调用设备技能,但必须确认,并记录失败降级。
- 外部 agent/skill 只能拿最小必要上下文,不能绕过 user_id、SafetyGuardian、audit。

## 8. Domain Requirements

### 8.1 科学坐姿

目标:把“久坐姿态风险”变成工作块内的低打扰、可观察、可复盘行为。

Current:

- Rokid 已有 push-up event 链路,可以证明眼镜到后端的 session/event 结构可行。
- 还没有通用 posture observation。

Target:

```yaml
Protocol:
  key: posture_monitoring
  trigger:
    during: work_blocks
    source: rokid_or_camera
    condition: posture_bad_duration_seconds >= 60
  action:
    primary: 调整屏幕/头颈/背部姿态
    fallback: 站起 30 秒或做肩颈活动
  cooldown_minutes: 15
  execution_event:
    - posture_prompt_sent
    - posture_corrected
    - posture_prompt_skipped
```

接口扩展:

- `POST /api/v1/device-observations` 接收 `posture_bad/posture_ok`。
- provider:
  - `rokid`:眼镜端本地姿态识别,上传角度/置信度/持续时间。
  - `camera_local`:本地摄像头模型,上传结构化指标。
  - `mac_activity`:只能提供“工作块/屏幕活动”,不能判断姿态。
- 后端只在异常持续超过阈值且 cooldown 通过时生成 agenda/reminder。

安全/隐私:

- 默认不存 raw frame。
- 姿态提醒不能写成诊断,只能写成 ergonomic nudge。
- 若出现疼痛、麻木、头晕等 red flag,转入就医/评估建议,不是继续加动作。

### 8.2 科学用眼

目标:把 20-20-20 规则从口号变成基于有效屏幕时长的提醒。

Target:

```yaml
Protocol:
  key: eye_20_20_20
  trigger:
    accumulated_screen_focus_minutes: 20
  action:
    title: 远眺 20 秒
    duration_seconds: 20
  reset:
    on: eye_break_completed | screen_idle >= 5 minutes
```

Implementation notes:

- Mac/桌面 agent 提供 `screen_focus_started/screen_focus_ended`。
- 会议/视频/阅读都算屏幕暴露,但如果用户离开屏幕超过 5 分钟则重置计数。
- Rokid 可作为完成检测或提示 surface,不是唯一依赖。
- Watch/Mobile 可做 fallback 提醒。

Acceptance:

- 连续有效屏幕 20 分钟后出现一次提醒。
- 用户完成 20 秒远眺后写 `ExecutionEvent(eye_break_completed)`。
- 在 quiet hours 或高优先级会议中可延后,但不能无限累积导致提醒风暴。

### 8.3 工作间隙动作:俯卧撑、消毒擦手等

目标:把工作间隙变成身体状态允许时的“短动作窗口”,而不是固定打卡。

Target:

```yaml
Protocol:
  key: work_microbreak
  trigger:
    work_duration_minutes: 60-90
    calendar_gap_minutes: >= 5
  action_candidates:
    - pushup_set
    - shoulder_mobility
    - walk_2_min
    - hand_sanitize
  safety:
    readiness_red: choose_mobility_or_rest
    after_meal_less_than_60_min: avoid_pushup
    acute_symptom: reject
```

Implementation notes:

- 俯卧撑优先复用现有 Rokid push-up session/event/review。
- 本地/手机 fallback 继续保留,避免 Rokid 不可用时动作链断掉。
- 消毒擦手可以先用 Watch/Mobile 一键完成;未来可接 NFC、智能消毒器或摄像头观察。
- 动作选择由 `HealthTwin` 和 `SafetyGuardian` 约束,不要只按“该动了”触发。

### 8.4 洗鼻

目标:把洗鼻放到适合的日内时点,并受症状、环境、医嘱和安全边界约束。

Target:

```yaml
Protocol:
  key: nasal_wash
  trigger:
    default_windows: [morning_after_wake, evening_before_sleep]
    conditional:
      - allergy_symptom_high
      - pollen_or_aqi_high
      - clinician_order
  action:
    title: 洗鼻
    constraints:
      - avoid_immediately_before_leaving_if_uncomfortable
      - avoid_when_nosebleed_or_acute_pain
```

Implementation notes:

- 第一版只做 reminder + completion event。
- 若用户有鼻出血、明显疼痛、发热、术后状态等,转为医嘱/就医确认,不继续推荐。
- 若接入天气/花粉/AQI,先作为 evidence,不能夸大为诊断。

### 8.5 补剂:合适时间 + 基于当前状态推荐

目标:补剂必须同时满足“是否该吃”和“什么时候吃”两个问题。

Current:

- `timing_adapter`/`timing_solver` 已能处理补剂时点、餐锚和常见间隔。
- `schedule_safety_seam` 已把 DDI/DSI 风险接到排程拒绝/警告。
- `supplement-advisor` skill 可做外部入口,但不能绕过后端安全。
- `reorder_intent` 已支持低库存意图,当前不自动下单。

Target:

```yaml
SupplementDecision:
  recommend_or_continue:
    inputs:
      - latest_labs
      - symptoms
      - diet_pattern
      - medications
      - chronic_conditions
      - genotype_when_relevant
      - clinician_orders
    output: proposed_protocol_or_noop
  schedule:
    source: timing_solver
    constraints:
      - meal_anchor
      - medication_spacing
      - workout_context
      - sleep_context
  write_path:
    add_or_change: WriteIntent(manual_confirm)
    reminder: WriteIntent/manual_confirm or user setting
```

Hard rules:

- 新增补剂、停用补剂、剂量变化默认 `manual_confirm`。
- 基因不能直接生成个体化剂量。
- 与药物、慢病、孕产、肾肝功能等冲突时必须拒绝或升级到 clinician review。
- 补剂推荐需要说明依据来源:检查、饮食缺口、医嘱、症状、用户目标或一般指南。

### 8.6 预约医生、体检和慢病复查

目标:从“知道该复查”推进到“在合适时间准备、预约、完成、上传结果、复盘”。

Current:

- `HealthProblem`/agenda 已能表达 follow-up。
- `recheck_floor` 和 timing schedule 方向已强调不能缩短医嘱/生物下限。

Target:

```yaml
Protocol:
  key: doctor_followup
  trigger:
    - clinician_order_due
    - chronic_condition_review_due
    - annual_or_quarterly_checkup_due
    - abnormal_lab_followup_due
  agenda_chain:
    - prepare_visit_summary
    - choose_department_or_doctor
    - propose_booking_slots
    - confirm_booking
    - pre_visit_reminder
    - post_visit_upload_and_review
```

Implementation notes:

- 后端生成 booking intent,Mac/Mobile/skill 执行外部查询或预约。
- 最终预约必须用户确认。
- 预约前生成摘要:最近检查、用药/补剂、症状、关键问题、要问医生的问题。
- 慢病复查周期由医嘱、指标、风险和安全下限共同决定;不能为提升活跃度而缩短。

### 8.7 锻炼时间:提前规划、前提醒、后恢复

目标:锻炼不是一个孤立日程块,而是一条可执行链。

Current:

- `day_schedule_service.workout_prescription()` 已基于 readiness、movement coach、gene bias、急性症状给出当天训练建议。
- `timing_solver.pick_workout_start` 已按用户偏好窗、日历忙碌、工作窗、餐、睡眠避让选择 workout start。
- `workout-coach` skill 已有训练前/后入口。
- Rokid push-up 已可承接部分动作观察。

Target:

```yaml
Protocol:
  key: workout_chain
  planning:
    horizon: weekly
    daily_resolution: readiness + calendar + sleep + training_load
  agenda_chain:
    - workout_plan_confirmed
    - pre_workout_reminder_20_30_min
    - pre_workout_check
    - workout_session
    - post_workout_stretch
    - shower
    - massage_or_foam_roll
    - post_workout_meal_or_protein
    - wearable_sync
    - recovery_review
```

Scheduling rules:

- 周计划先定训练目标和候选窗口。
- 当天根据 readiness、睡眠、急性症状、日历空窗和餐时确认或降级。
- 锻炼前 20-30 分钟提醒热身/补水/装备/能量。
- 锻炼后自动生成拉伸、洗澡、按摩/泡沫轴、餐后营养、Garmin/Watch 同步。
- readiness red、急性不适、疼痛等触发降级或拒绝,不硬推。

### 8.8 饮食:基因、检查、疾病治疗、用药、外卖和记录

目标:饮食建议不只是“吃健康”,而是与用户真实治疗/检查/训练/睡眠上下文对齐。

Current:

- `schedule_diet_sleep.nutrition_prescription()` 已能结合 HealthTwin、TDEE、protein target、训练前后碳水时点和部分基因倾向。
- `nutrition-advisor` skill 已能作为饮食建议和记录入口。
- Rokid/iOS 已有食物拍照相关能力和 fallback 经验。
- `ReorderIntent` 说明了外部购买必须手动确认的边界,可复用于食物下单意图。

Target:

```yaml
NutritionPlan:
  inputs:
    - genotype
    - latest_labs
    - chronic_conditions
    - medications
    - supplements
    - allergies_or_avoidances
    - training_plan
    - sleep_goal
    - recent_food_logs
  outputs:
    - meal_timing
    - meal_constraints
    - food_candidates
    - order_intent_optional
    - nutrition_log_after_meal
```

Skill contract:

- skill 可以根据后端给出的约束生成外卖候选。
- skill 不能把“推荐”直接变成付款。
- 用户确认前必须展示:
  - 菜品/商家/价格/配送地址摘要;
  - 营养估算;
  - 与用药、疾病、过敏、训练目标相关的约束摘要;
  - 替代选项。
- 成功下单后写 `ExecutionEvent(food_order_confirmed)` 并创建待确认饮食记录。
- 实际摄入可以来自订单、拍照、手动修正或外部营养库;卡路里/营养素必须标注估算来源。

### 8.9 睡眠:合理时间、饮食、咖啡因、闹钟

目标:从目标睡眠时间倒推出晚间行为和第二天唤醒。

Current:

- `schedule_diet_sleep.sleep_prescription()` 已能根据 HealthTwin 和 CYP1A2 等因素生成咖啡因 cutoff。
- `sleep_items()` 已能生成 winddown 和 caffeine cutoff。

Target:

```yaml
Protocol:
  key: sleep_winddown
  inputs:
    - sleep_debt
    - calendar_tomorrow
    - training_load
    - caffeine_metabolism
    - dinner_time
    - medication_timing
    - user_sleep_preference
  agenda_chain:
    - caffeine_cutoff
    - dinner_cutoff_or_light_meal
    - winddown_start
    - screen_dim_or_stop
    - alarm_set_confirm
    - sleep_target
    - morning_review
```

Implementation notes:

- 推荐睡眠时间是建议,不是医疗处方。
- 闹钟设置走 `ExternalActionIntent(alarm_set, manual_confirm)`。
- 如果第二天有早会/体检/训练,可以倒推睡眠窗口和提醒。
- 睡眠不足时,第二天训练/咖啡因/午睡建议要回流到 HealthTwin 和 schedule。

## 9. API And Data Contract

### 9.1 Extend `/schedule/today`

现有响应保留 `scheduled/rejected/deferred`,新增字段应向后兼容。

```yaml
scheduled[]:
  id: stable_key
  domain: medication | supplement | diet | movement | sleep | checkup | posture | eye | hygiene | respiratory
  protocol_key: optional
  title: user_visible
  start_at: iso_datetime
  end_at: optional
  anchor: optional
  trigger:
    type: clock | accumulated_duration | device_observation | calendar_gap | body_state | clinician_order
    source: optional
  lead_time_minutes: optional
  cooldown_minutes: optional
  surface:
    primary: mobile | watch | mac | rokid | skill
    alternates: []
  chain:
    previous_item_id: optional
    next_item_ids: []
  safety:
    status: ok | warning | rejected
    reasons: []
  execution:
    event_type: expected_execution_event
    confirmation_required: true | false
  evidence:
    sources: []
    freshness: optional
```

### 9.2 New Observation API

```yaml
apis:
  - POST /api/v1/device-observations
  - GET /api/v1/device-observations?date=YYYY-MM-DD&event_type=...
events:
  - posture_bad
  - posture_ok
  - screen_focus_started
  - screen_focus_ended
  - eye_break_completed
  - pushup_set_completed
  - nasal_wash_completed
  - hand_sanitize_completed
models:
  - DeviceObservation or ExecutionEvent extension
backward_compatibility:
  - Existing Rokid push-up APIs remain; later adapters can mirror them into DeviceObservation.
migration:
  - First slice can be append-only new table or reuse ExecutionEvent if schema is sufficient.
```

### 9.3 External Skill Intents

```yaml
apis:
  - POST /api/v1/write-intents
  - POST /api/v1/write-intents/{id}/confirm
  - optional future: POST /api/v1/external-action-intents
intent_types:
  - food_order
  - doctor_booking
  - supplement_reorder
  - alarm_set
  - reminder_set
hard_boundary:
  - all financial/booking/alarm actions require manual_confirm
```

## 10. Surface Contract

| Surface | Responsibility | Contract |
|---|---|---|
| Backend | Source of truth for time, safety, ranking, audit, user isolation. | Build schedule/agenda, gate safety, create write/external intents, store execution events. |
| Mobile | Primary daily timeline and confirmation surface. | Show today timeline, action chains, confirm/later/skip, approve external intents. |
| Watch | Low-friction execution. | Confirm due item, complete eye break/microbreak/supplement/water/sleep nudge. |
| Mac | Workbench and desktop signal source. | Provide screen focus/work block signals, review longer plans, upload labs, debug traces. |
| Rokid | Ambient execution and observation. | Push-up/posture/food capture/voice prompts through device observation and existing session APIs. |
| External skills | Controlled execution extension. | Nutrition, supplement, workout, reminder, ordering, booking; never bypass safety or manual confirm. |

## 11. Safety, Privacy, And Medical Boundary

- Health data class: most protocol inputs are L3; tokens/payment credentials are L4 and must not be stored by this feature.
- User isolation: every schedule, observation, intent, and execution event must be scoped by authenticated `user_id`.
- SafetyGuardian gates:
  - DDI/DSI/PGx for medication and supplement timing/recommendation.
  - readiness/acute symptoms/pain for workouts and microbreak intensity.
  - red-flag symptoms for nasal wash, eye health, posture discomfort and chronic disease follow-up.
  - clinician order and biological lower bound for recheck cadence.
- Camera/Rokid privacy:
  - default on-device feature extraction;
  - no raw frame upload unless user explicitly starts a capture workflow;
  - no raw images to LLM by default;
  - structured metrics only for posture/eye protocols.
- Financial boundary:
  - no auto-pay;
  - no saved payment credentials in Reva;
  - no order without per-order user confirmation.
- Medical wording:
  - use “建议/可考虑/按医嘱/请确认” language;
  - never claim diagnosis, cure, emergency clearance, or personalized dose from genotype.

## 12. AI Behavior

LLMs and external agents may:

- summarize why an action appears now;
- explain evidence and uncertainty;
- draft a doctor visit summary;
- translate nutrition/supplement constraints into food or product candidates;
- generate user-facing copy for reminders, after deterministic checks.

LLMs and external agents must not:

- change medication dose or stop/start prescription medication;
- override SafetyGuardian rejection;
- directly place paid orders, book appointments, or set alarms without confirmation;
- infer diagnosis from posture/camera/nasal/eye signals;
- receive calendar titles/locations/attendees through LLM paths unless explicitly required and consented.

Failure behavior:

- If skill call fails, keep the `HealthAgendaItem` and mark external intent failed; do not drop the health action.
- If device signal is missing, degrade to manual/Watch/Mobile confirmation.
- If safety context is stale or insufficient, downgrade to “ask/confirm” or reject, not auto-execute.

## 13. User Flow

Smallest end-to-end slice:

```text
User has workday + sleep preference + medication/supplement records + calendar
  -> backend builds HealthTwin and DayContext
  -> protocol registry emits eye_20_20_20, microbreak, supplement, sleep items
  -> timing_solver places clock-based items and defers event-driven items
  -> event_reminders sends due/pre-event nudges under notification budget
  -> user completes on Mobile/Watch/Rokid
  -> ExecutionEvent stored
  -> agenda/review adjusts next reminders and protocol burden
```

Illustrative day, not a prescription:

```text
07:00  wake target
07:10  nasal wash if protocol active
07:30  breakfast + allowed supplement/med items
09:20  screen focus reaches 20 min -> 20 sec eye break
10:30  calendar gap + readiness ok -> microbreak(push-up or mobility)
12:30  lunch; nutrition constraints reflect meds/labs/training plan
17:30  pre-workout reminder + readiness check
18:00  workout block
18:45  stretch
19:00  shower
19:15  massage/foam roll if protocol active
19:30  post-workout meal/protein timing
21:30  winddown + caffeine already cut off
22:30  sleep target + alarm confirm for tomorrow
```

## 14. Implementation Plan

### P0: Documentation and product alignment

- Add this spec.
- Keep existing `2026-06-17-day-timing-schedule`, `p1-pre-event-reminders`, `smart-agenda` as lower-level specs.
- Do not add code until object/contract names are accepted.

### P1: Protocol templates without new hardware

- Add protocol templates for:
  - `eye_20_20_20`
  - `work_microbreak`
  - `nasal_wash`
  - `sleep_winddown` extension
- Project them into schedule/agenda using existing day schedule context.
- Execution via Mobile/Watch manual confirm.

### P2: Generic device observation API

- Add `DeviceObservation` model/API or extend `ExecutionEvent` if sufficient.
- Mirror existing Rokid push-up events into the generic observation stream.
- Add Mac screen-focus adapter.
- Add privacy tests: no raw frame fields, user_id isolation, auth required.

### P3: Posture and eye hardware adapters

- Rokid posture adapter: local pose metrics -> `posture_bad/posture_ok` observations.
- Camera local adapter: on-device pose metrics, explicit consent and disable switch.
- Eye protocol: accumulated screen focus and completion events.

### P4: Workout chain

- Extend workout schedule item into chained agenda items: pre-check, workout, stretch, shower, massage, meal, sync/review.
- Add skip reasons and downgrade rules.
- Keep prescription/safety logic deterministic.

### P5: External action intents

- Food ordering intent from nutrition constraints.
- Doctor booking intent from follow-up protocol.
- Alarm set intent from sleep protocol.
- All remain `manual_confirm`; add audit and failure degradation.

### P6: Learning loop

- Aggregate completion/skip/fail reasons by protocol.
- Adjust burden, cooldown, timing windows and fallback surfaces.
- Review 7-day adherence and 4/8/12-week outcomes where relevant.

## 15. Acceptance Criteria

```gherkin
Given a user has screen-focus observations totaling 20 active minutes
When the scheduler builds the current timeline
Then it creates an eye-break agenda item with a 20-second completion event and no medical claim.

Given Rokid or camera reports posture_bad for longer than the threshold
When cooldown and notification budget allow
Then the user receives one posture correction prompt and the raw frame is not stored.

Given readiness is red or acute symptoms are present
When a work microbreak would normally choose push-ups
Then the system downgrades to mobility/rest or rejects the action with a safety reason.

Given a supplement conflicts with a medication or hard safety rule
When the supplement timing is scheduled
Then it is rejected or warned according to SafetyGuardian and no reminder is sent for unsafe execution.

Given a workout block is accepted for today
When the plan is projected
Then pre-workout reminder, workout, stretch, shower, massage/foam-roll, nutrition, and sync/review items are chained.

Given a food-order skill returns an option
When the user has not confirmed payment/order
Then no order is placed and no payment credential is stored.

Given a doctor follow-up is due
When the booking skill is available
Then Reva creates a booking intent plus visit summary, but final appointment confirmation remains user-driven.

Given sleep target requires an alarm
When the alarm skill is available
Then the system proposes an alarm-set intent and records success/failure after user confirmation.
```

## 16. Verification Plan

When implementing code slices:

```bash
# Backend schedule/agenda
cd backend
venv/bin/python -m pytest \
  tests/test_timing_solver.py \
  tests/test_day_schedule_service.py \
  tests/test_event_reminders.py \
  tests/test_agenda.py -q --no-cov

# Device observation slice
cd backend
venv/bin/python -m pytest tests/test_device_observations.py -q --no-cov

# Write/external intent slice
cd backend
venv/bin/python -m pytest \
  tests/test_write_intents.py \
  tests/test_reorder_intents.py -q --no-cov

# Repo hygiene
git diff --check
```

For this documentation-only slice:

```bash
git diff --check -- docs/specs/active/2026-06-22-time-driven-health-management.md
```

## 17. Rollout And Rollback

- Rollout is additive and protocol-by-protocol.
- P1 can be hidden behind backend feature flags or protocol allowlist.
- Device observation API should launch with a small provider allowlist.
- External intents launch in propose-only mode before execution integrations.
- Rollback:
  - disable protocol template;
  - ignore provider observation;
  - stop event reminder task;
  - keep existing medication/supplement/diet/sleep schedule untouched.

## 18. Open Questions

Must decide before P1:

- Should protocol templates live as DB rows, code constants, or hybrid seed data?
- Should `DeviceObservation` be a new model, or should generic observations be folded into `ExecutionEvent`?
- Which client owns the first eye-screen focus signal: Mac app, browser extension, or Mobile/Rokid?

Can defer:

- Which food-ordering provider/skill is first.
- Whether doctor booking uses a partner API, browser automation, or user-side deep link.
- Whether alarm setting is OS-level integration, Shortcuts, or external skill.
- Whether posture calibration is per-user or generic in the first hardware slice.

## 19. Changelog

| Date | Change | Reason |
|---|---|---|
| 2026-06-22 | Initial draft | Define time-driven health management as a unified Personal Health OS layer. |
| 2026-06-22 | Add §1.5 Reconciliation & Build Status | 对齐已建 Increment 1(HealthEvent 执行层闭环 = 本 spec ExecutionEvent 段);裁决 §18 三个开放问题;统一脊柱 seam(`/timeline/today` 为首页脊柱);给出 P0-P6 ⇄ Increment 合并路线图。Codex 输入侧 spec 与 Claude 已建执行侧互补。 |
| 2026-06-22 | 完成回路打通(后端 `f845ff9f` + 移动端 `4d940a79`)| med/supplement 完成不再 422:`complete_item` 加分支(复用幂等 `log_medication`)+ `complete_by_ref` 核 + `can_complete` 扩展 + 修推送端点占位符 + AGENDA_ACTION 推送 handler(完成/跳过)。safety re-review GO;幂等 HIGH 已修(DB 原子认领 + 确定性 taken_time)。§1.5.4 路线图前置项 → 已建。未部署。 |
| 2026-06-22 | P1a 协议模板地基(后端 `c93077e8`)| `protocol_templates.py` 注册表(nasal_wash×2 + sleep_winddown)+ 幂等 seeding + `/protocols/seed/behavior` + 提醒桥(`time_window→HH:MM`、protocol 进 `_collect_timed_items`、P1 tier)+ nasal 红旗 fail-safe 抑制 + R4 措辞。`respiratory` 入 PROTOCOL_DOMAINS。safety self-review GO。64+167 测试绿。未部署。P1b(eye 移动计时器 + microbreak 安全门)与 §7.2 recurrence 重构待做。 |
| 2026-06-22 | council-review + 修复(后端 `40af18e9`)| 三方(Claude A+B+Codex/GPT-5.5)评审完成回路+P1a,一致 CONDITIONAL_ACCEPT,共识 F1–F4 部署前必修(已修):F1 skip 也校验类型+归属(→400/404,非跨用户泄露,只是缺校验);F2 skip 经同一 dispatcher 写真实 source skip 事实 → today_status/提醒/视图一致不再误推,后到 done **supersede** 先前 skip(skipped→taken upsert;done 不可被 skip 降级);F3 nasal 红旗查询异常 **fail-closed** + 警示语进推送正文;F4 **实测**旧幂等测试还原 `_slot_time`→now() 仍绿(假护栏)→ 加 `taken_time==scheduled_for 槽`断言 + clock-straddle 测试,红绿实测确认。F5a 窄缝留+sentinel 覆盖;F5b(complete_ref 缺 dose-slot/BID 折叠)加 TODO。safety re-review GO。101+167+372 测试绿。未部署。 |
| 2026-06-23 | 自主全量建成 P1b/P2/P4/P5/P6 + 上线 | 顺序建+逐个安全评审:P1b eye 计时器(`a8f339a9`)+ microbreak §8.3 门(`edf075e3`)+ skip-原因 UI(`02ca8b88`);P2 DeviceObservation(`04032c97`);P4 workout chain(`07f8403a`);P5 external intents draft-only(`105e7749`);P6 learning loop(`caed55f8`)。每增量 safety self-review GO。**集成闸**(全增量测试合跑)抓出 2 个 CI-红跨增量回归:① device 完成双写 ② microbreak 误降级——根因=**CI UTC-runner vs 应用 Asia/Shanghai 午夜 date-base flake**(含真生产 bug:上海午夜 `_auto_observe` 双写虚高依从);修=CI `TZ=Asia/Shanghai` + date 对齐(`fd37225a`,4015 测试绿)。**Codex 跨家 capstone** 评审又抓出 BLOCKING:`/write-intents` 嵌套 L4 支付 key 只查顶层 → 递归拒(`578ee9a1`)+ device/chain China-day 归一 + 文案软化。**全部已部署生产**(后端 `578ee9a1`,health 60/60)+ `generate-types`(`33f7e65a`)+ 移动端 OTA(update `c2757163`,build 184)+ TestFlight build 184。auto-seed 因 不劫持 故意不做。P3 硬件/真外卖挂号 provider/支付=用户侧外部边界。 |
