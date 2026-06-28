# Voice Concierge Loop — ConciergeIntent 设计 (电话/短信就医协助闭环)

> Status: Design draft
> Date: 2026-06-27
> Owner: Reva / Personal Health OS
> 方法: 4 维对抗式可行性分析(电信语音栈 / 中国合规 / 安全治理 / 产品闭环)→ 14 风险全部对抗验证 → 综合;承重事实已对代码核实。

## 0. 结论 (Verdict)

**能实现,且整条闭环的 ~80% 落在 Reva 现成轨道上,不需要任何自治外呼即可跑通。**

唯一的硬边界**不是 AI 质量,而是上游两堵墙**:① 中国没有"个人/自然人"开通外呼 PSTN 的通道(主叫号必须企业实名 + 运营商话术报备;400 号只进不出);② 用克隆声音对人类坐席讲话触发《深度合成管理规定》+《标识办法》(2025-09-01 起)的**强制 AI 披露**,且克隆声纹需 PIPL **单独同意**。

因此**自治克隆声音外呼 = 最后一公里**,网关永久先冻在 `NotImplementedError/501`(与现有 `food_order` / `kuaishou` 网关同范式);前面整条链路现在就能上。

---

## 1. 四问 (feature-plan)

**1) 用户价值**:把"膝盖不舒服 → 打 400 预约 → 短信确认 → 出发提醒 → 到院检查 → 结果入系统 → 分析 → 干预复查"从一堆割裂的手动动作,变成一条有记忆、可验证、低摩擦的闭环。用户当前 workaround = 自己打电话、自己记、结果靠纸质报告,断在多处。

**2) 边界 (What NOT)**:
- 不上自治外呼(Phase 2 才碰,且三关全过才解冻)。
- 不做实时家居控制、不做财务自动下单。
- 不新建结果回流管道(复用 OCR)。
- 不为本 MVP 新增骨科/MSK specialist(用通用合成兜底)。
- 入站自动接听/自动回短信默认关。

**3) 最简实现**:新增一个一等对象 `ConciergeIntent`(克隆 `reorder_intent.py`)+ `consent_grants` 同意账本 + 录音清除 cron;网关 `place_call` 冻 501。**Phase 0 = 系统拟脚本 → 用户自己拨 → App 录音转写 → 用户审自己的转写 → 批准后下游全自动**。

**4) 风险**:对外、难撤销、带身份、含生物特征、录第三方音——Reva 迄今**风险最高的写操作**。详见 §10 风险登记。

## 2. ASCII 数据流 (闭环)

```
膝关节不舒服 (Capture/语音/症状)
   ↓  orchestrator + SafetyGuardian.problem_red_lines
HealthProblem(左膝, P2, red_lines, follow_up)
   ↓  draft  (复用 doctor_booking WriteIntent 思路)
ConciergeIntent.kind='appointment_booking'  status=drafted
   ↓  [Phase 0] 用户自己拨打 (place_call = 501 占位)
   |  录音 → ASR 转写
   ↓
status=pending_human_review   ← 人工闸 (审转写 + 结构化承诺)
   ↓  human_approved = 一个「请求」, 还不是承诺
保险方短信/回拨 FINALIZE (inbound HealthEvent)
   ↓  ← 短信只是佐证, 不是授权; 不一致→重弹, 不自动对账
HealthAgendaItem(预约) + 出发日提醒 (NotificationDecision)
   ↓
ExecutionEvent(exam_completed)
   ↓  复用 OCR (lab_photo_parse / doctor_report_service / medical_exams / exam_explain)
HealthTwin(影像/化验分区) + BiomarkerObservation
   ↓
specialists + longitudinal_analyst + InterventionCycle(baseline)
   ↓
HealthProtocol(康复/负荷) + InterventionCycle(8-12wk) + HealthProblem.follow_up.next_due
   ↓  到期
WriteIntent(checkup_reminder) → 新 ConciergeIntent(约复查)   ⟲ 回到顶部
```

## 3. 复用地图 (已对代码核实 — 不是从零)

| 能力 | 现成位置 | 复用方式 |
|---|---|---|
| 声音复刻 TTS | `backend/app/services/tts/cosyvoice.py`(阿里云 CosyVoice,带 voice id) | 语音腿 ~80% 已就位;须从全局 voice id **改为按用户/按同意 scope** |
| 预约外部动作意图 | `write_intent_service.py` 的 `doctor_booking`(draft+人工确认+审计,有 `generate_doctor_booking_drafts`) | ConciergeIntent 是它的"电话执行层" |
| 网关熔断范式 | `food_order_skill_gateway.py` / `kuaishou_skill_gateway.py`(NotImplementedError→501) | 抄给 `voice_concierge_gateway.place_call` |
| 结果回流 | `lab_photo_parse.py` / `doctor_report_service.py` / `medical_exams.py` / `exam_explain_service.py` → Twin + BiomarkerObservation | **不新建管道** |
| 原始媒体清除 | `meal_privacy.py`(`raw_media_delete_at` + 3:05 cron + `raw_media_purged` 审计) | 复用做录音 TTL |
| 字段加密 / 租户隔离 | Fernet(`GARMIN/DEVICE_ENCRYPTION_KEY`) + force-RLS(同基因表) | 录音/转写/承诺存储 |
| 安全门 | `evaluate_rules_with_status`(查 `failed_rule_count==0`) | **不用** `evaluate_safety`(吞异常=under-alarm) |
| 脚本文本护栏 | `guidance_red_lines.py` / `guidance_validator.py` token 扫描 | LLM 拟的脚本过此门→不带 R4 诊断/处方 |

## 4. 新增一等对象

### 4.1 `ConciergeIntent` (= CommunicationActuationIntent)
独立表(克隆 `models/reorder_intent.py`,**不是**薄薄一个 `WriteIntent.kind`),`IoTActuationIntent` / `SupplyIntent` 的兄弟。

```
id, user_id,
kind            : 'appointment_booking' | 'followup_answer' | 'sms_reply'
target_type/id  : → health_problem / health_agenda_item   (幂等去重锚点)
provider        : 'cigna_cmb_400'
callee_number
status          : 见 §5 状态机
trust_tier      : 'manual_confirm'   non_graduating = True   ← 永不毕业
script_text     : LLM 拟、过 guidance 护栏
recording_ref   : 对象存储 key (不内联 PII)
transcript_ref
booking_details : JSONB (hospital/dept/date/time/prep)
consent_ref     : FK → consent_grants
raw_audio_delete_at / raw_audio_purged
failed_leg_count / brittleness 遥测
created_at / confirmed_at / placed_at
```
每次状态转移走**原子 rowcount-guarded** UPDATE(防并发双写);去重键 `(user_id, target_type, target_id, status)`。

### 4.2 声纹同意 — **复用已有 `ConsentGrant`,不新建表**
> 修正(2026-06-27,governance-plan review 收口):`models/data_connection.py` 已有 `ConsentGrant`(scopes JSONB + revoked_at)。声纹同意是它上面的一个 **scope**,不另起 `consent_grants` 表——对齐"统一授权中心"。
```
ConsentGrant.scopes 增 'voice_clone_outbound' (+ recording_disclosure_ack 入 evidence/metadata)
subject_user_id / beneficiary_user_id, revoked_at (撤销→fail-closed 禁用所有网关调用)
机器校验: subject_user_id == intent.user_id AND beneficiary == user_id  (fail-closed)
propose 时 + dial 时都校验 consent scope 有效且未撤销
```

### 4.3 `voice_concierge_gateway`
服务模块,`place_call` 抛 `NotImplementedError`(API→501),直到企业开线 + 合规过审。"通信硬门"。

### 4.4 managed 迁移
pg + sqlite 双文件(无 Alembic,仓库约定);ConciergeIntent + consent_grants 同一 PR 落库,**先于**任何电信集成。

## 5. ConciergeIntent 状态机

```
drafted
  → script_confirmed              (用户确认脚本 + 逐项 PII 拨前确认)
  → 〔SCAFFOLD STOP: place_call=501〕   ← Phase 0 在此由用户自己拨
  → call_placed
  → recording_captured
  → transcript_ready
  → pending_human_review          ← 人工闸 (审转写 + 结构化承诺)
  → human_approved                (= 一个「请求」)
  → booking_confirmed             ← 仅当保险方 SMS/回拨 FINALIZE 才到
旁路: call_failed | aborted | cancelled  (任何 fail-closed 落点, 写失败 + 暴露部分转写)
```

## 6. 治理设计 (写自治阶梯)

- **永久 manual_confirm,non-graduating**:打电话、读身份证/保单号/支付、定稿预约、用克隆声音——**永远不能升级到 auto**(与已有 `doctor_booking` 同族:"外部动作 · 永久人确认 · 只增不减")。
- **人工闸卡在承诺定稿前**:`pending_human_review` 强制态,退出需用户同时批准**转写 + 结构化承诺**。
- **转写批准 ≠ 预约定稿**:human_approved 只是"请求";**出发提醒只在保险方 SMS/回拨 finalize 后才 arm**;短信是佐证非授权,不一致→重弹,绝不自动对账。
- **线上话术固定白名单**:LLM 绝不在线自由发挥;遇付款/读身份/"您确认吗"/开放提问 → 念预设缓冲语 + 挂断。
- **PII 数字按策略恒人工确认**(非置信度门控——8kHz 数字 ASR 置信度不可靠,自信的错位不会触发阈值)。
- **fail-closed + fail-loud + 加层不减层**贯穿;每子腿 `failed_leg_count` + `raise_on_error`。

## 7. 闭环对象映射

(见 §2 ASCII)逐步对象已列于表格化数据流。要点:**约复查时再生成一个 ConciergeIntent**,闭环自闭合。

## 8. 分期 MVP

| Phase | 风险 | 范围 |
|---|---|---|
| **Phase 0 (先上)** | 低 | ConciergeIntent + consent_grants + 录音清除 cron + force-RLS(一个 PR);系统拟脚本→**用户自己拨**→录音转写→审自己转写→批准后**下游全自动**(议程+出发提醒+检查事件+OCR 结果+InterventionCycle 立基线+复查再触发)。`place_call` 冻 501。**交付你描述的整条闭环,只少拨号机器人,零外呼/身份/合规/克隆声音风险。** |
| **Phase 1** | 中 | 辅助 IVR/DTMF 导航(ASR+意图匹配,非硬编码 DTMF);检测占线;**任何真人坐席对话 + 全部身份认证轮交给用户**;线上不用克隆声音;若发任何合成提示音必带 AI 披露。可走"本机通话桥接"绕开开线墙。 |
| **Phase 2 (最后)** | 高 | 监督式克隆声音外呼:仅念**已披露**的白名单协助内容;开场强制 AI 披露;身份认证轮路由真人;固定白名单话术;booking_confirmed 前 `pending_human_review`;处处 abort/fail-closed。**仅在 (a) 企业开线+话术过审 (b) 招商信诺确认接受授权 AI (c) 身份/财务级专项合规+council 对抗评审 三关全过后**才 un-stub。status 在此前永不到 `call_placed`。 |

## 9. Phase 0 PR 清单

- [ ] managed 迁移(pg+sqlite):`concierge_intents` + `consent_grants` 表
- [ ] `models/concierge_intent.py`(克隆 reorder_intent;原子 rowcount 转移;去重键)
- [ ] `services/voice_concierge_gateway.py`:`place_call` → `NotImplementedError`(API 501)
- [ ] `consent_grants` 专用同意屏(mobile,**独立于 onboarding ToS**;一键撤销删声纹模型)+ ConsentEvent 审计
- [ ] 脚本生成:从 HealthProblem + 保单信息拟 `script_text`,过 `guidance_validator` 护栏
- [ ] 录音/转写:录音 → ASR → `transcript_ref`;`raw_audio_delete_at` ≤72h + 复用 meal_privacy 清除 cron + `raw_audio_purged` 审计
- [ ] 人工复核屏:审转写 + 结构化承诺(医院/科室/日期/准备)→ human_approved
- [ ] inbound SMS finalize → upsert HealthAgendaItem(按 booking key,非盲插)
- [ ] 出发提醒:HealthAgendaItem 投影(复用 agenda ≤14d 窗 + 打扰预算)**仅 finalize 后 arm**
- [ ] 安全门:propose + dial 两处 `evaluate_rules_with_status`(`failed_rule_count==0` + consent 有效 + 录音同意 + 披露 flag)
- [ ] 并发集成测试:call_placed + sms_inbound + manual_confirm 并发 → 断言**恰好一个** HealthAgendaItem,且**跨分钟边界**(幂等测试必须在受控变量上取不同值)
- [ ] 结果回流:复用 OCR 路径,不新建

## 10. 风险登记 (14 风险全部对抗验证通过)

| # | 级别 | 风险 | 缓解 |
|---|---|---|---|
| 0 | blocking | 中国无个人外呼 PSTN 通道(企业实名+话术报备;400 只进不出) | 自治外呼冻 501;Phase 0 用户自拨兜底;开线须企业主体+诚实话术,且会把性质变成"企业代用户自动外呼"引入企业电信合规 |
| 1 | blocking | 线上自治做财务/身份承诺;8kHz 数字 ASR 错位订错身份 | 固定话术白名单;越界→缓冲语+挂断;读 ID/保单恒拨前逐项确认,绝不中途;PII 数字按策略恒人工 |
| 2 | blocking | 未定稿预约被当确认推进下游(到院才发现错) | 强制 `pending_human_review`;转写批准=请求,**仅保险方 finalize 才 arm 提醒**;短信佐证非授权,不一致不自动对账 |
| 3 | blocking | 未披露的合成声音对坐席(违深度合成+标识办法) | 每通**开场不可跳过**强制 AI 披露 TTS;披露失败即不打(加层不减层);隐式标识归存储/导出录音 |
| 4 | major | 克隆声纹无 PIPL 单独同意(声纹=敏感生物信息) | 独立同意屏(非 ToS);ConsentEvent 机器校验主体==受益==本人 fail-closed;propose+dial 双查;境内加密 |
| 5 | major | 录第三方坐席声纹无最小化/保留限制 | 原始音短 TTL ephemeral,转写后人审,fail-loud 清除;最小化声纹而非过度脱敏转写 |
| 6 | major | 入站自动接听/回短信把对端话语变成 prompt(可被社工) | 入站仅 display/draft 级:转写→分类→草稿;**精确白名单 fail-closed**(非黑名单);默认关,出站挣到信任后再议 |
| 7 | major | IVR 改版/长占线/半双工延迟打断硬编码 DTMF | ASR+意图匹配选支(非硬 DTMF);占线 VAD 上限;墙钟预算+困惑计数→needs_human;超时/掉线→abort+缓冲语+挂断,暴露部分转写,不静默重拨 |
| 8 | major | 违招商信诺"仅限被保险人本人"ToS;克隆声纹撞反欺诈 | 克隆声音只念已披露协助内容;身份认证轮交真人;**Phase 2 前先核手册/直接问是否允许授权 AI**;不暴力闯反欺诈 |
| 9 | major | 预约幂等 + 入站短信竞态 → 双建议程项 | 抄 ReorderIntent 原子 rowcount 转移;去重键;SMS 按 booking key upsert;并发集成测试跨分钟边界 |

## 11. 开放问题 (Phase 2 前必答)

- **招商信诺"就医协助"是否允许授权 AI/代理致电**,还是严格"仅限被保险人本人"?(翻增值服务手册或直接打那通电话核实——决定 Phase 2 是否可能)
- 是否存在任何企业主体下、话术("AI 助理代用户致电预约,已获授权")能过运营商审核的外呼通道,还是运营商对 AI 语音直接拒绝→永久依赖用户自拨兜底?
- 企业主体开线(vs 个人自动化)是否引入额外企业电信合规 + 被叫方告知/授权存证义务?
- 8kHz 电信 ASR 在关键数字字段(保单号/身份证后4位/手机号)能到多少准确率?是否曾足够好到放松 PII 数字的策略性人工确认?(大概率否)
- 选用的 CosyVoice/生成式语音厂商是否已完成大模型备案/算法备案?其 ToS 是否禁止克隆声音用于第三方通话?
- 原始录音确切 TTL(≤72h vs 审完即清)+ GB 45438-2025 隐式标识格式
- Phase 1 辅助 IVR 走企业线还是用户本机通话桥接(后者绕开开线墙)?

## 12. 硬禁止

不上自治外呼;线上不自由发挥;身份/保单/支付绝不中途读、必须拨前逐项确认;不靠单次通话自动定预约;出发提醒不在转写批准时 arm(等保险方 finalize);克隆声音必开场强制 AI 披露(失败即不打);声纹同意不进总 ToS;声纹认证轮交真人;入站默认关;安全门不用 `evaluate_safety`;不新建结果管道;不为本 MVP 阻塞在加 MSK specialist;原始录音短 TTL 清除、不存坐席声纹;只用境内厂商。
