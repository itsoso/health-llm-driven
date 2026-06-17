# 个人健康 OS · 统一设计

> **状态**:设计文档(非实现规范)。本文产出自一次**多视角设计面板 + 对抗批判**:4 组织论纲各出完整设计 → 评审择主轴 + 跨设计嫁接 → 综合 → 对抗批判逐条核实代码实况。**§9 完整记录了对抗批判推翻/修正了哪些初稿结论**——读到任何「复用现有 X」「真缺 Y」处,出处都已对代码核实。
>
> **不 fork 上游**:产品方向唯一权威是 [`docs/prd/reva-personal-health-os-prd.md`](../../prd/reva-personal-health-os-prd.md);本文是"如何把它实现成一个 OS"的工程视角,与 [`architecture-lens.md`](architecture-lens.md)(OS 部件→模块→状态的速查表)、[`../../plans/2026-06-17-workday-health-scheduler-watch-first-design.md`](../../plans/2026-06-17-workday-health-scheduler-watch-first-design.md)(调度器 watch-first 设计)、`planning-methodology.md`(调度器方法论,另线产出中)互补。战略锚见记忆 `project_enter_key_leverage_thesis`。

---

## 定调一句话

> **把这套系统读成一个 per-user 闭环控制系统:状态估计是 Digital Twin,误差估计器是 13 个 specialist,执行器是 Write 层(对身体世界的唯一受控写入),执行器的硬限幅是 SafetyGuardian,执行器增益(自治权)由"这次干预对你到底有没有效"的季度辨识逐类挣得 —— 安全限幅永远先于控制律,医疗边界是永久封顶而非默认。**

**关于"OS / 控制论"这层隐喻的诚实声明**(对抗批判 #over_engineering 的回应):控制论是一个**透镜**,它的价值是逼问每一层"谁是 setpoint / 谁估计 / 谁执行 / 谁验证 / 谁限幅",从而把"13 个 agent 的拼盘"读成"一条主回路 + N 个子环"。但隐喻**不产出**任何机械可推导的工程决策——每个真缺口(加一个 beat、抽一个 router、插一道执行前限幅)都是独立工程项,各自成立。**别让隐喻驱动决策;它只负责组织叙事。** 若哪天它增加阅读成本而不增加洞察,删掉包装、保留工程项即可。

---

## 0. 论纲选择:一主两嵌

设计面板出了三条主线,本文以 **闭环控制系统** 为主组织框架,另两条作为嵌入子系统(评审打分 8.7 / 8.5 / 8.2):

| 角色 | 来源论纲 | 在 OS 里的位置 |
|---|---|---|
| **主轴 / 叙事骨架** | 闭环控制系统 | 七层架构 + 三层控制环 + 增益整定 + 限幅语义 |
| **嵌入①:系统辨识 + 护城河载体** | 因果推断机器 | per-user 因果辨识结果的**可查询落点**(见 §6 —— 复用 `OutcomeMetric`,**不**新建平行表) |
| **嵌入②:I/O 表面物理分布** | 贴身环境计算 | 按"到身体距离 × 是否常驻 × 是否知情境"切三端(见 §5) |

选主轴的理由:只有控制论同时覆盖**实时控制(日环)、执行迁移(Write=执行器接线)、验证(季环=系统辨识)、安全(限幅在控制律前)**四个轴,且最贴合既有连续原语(`intervention_significance` 的置信度)。但它单用有两处真空——护城河怎么物化、执行器/传感器落在哪块屏——由两条嵌入论纲填实。

---

## 1. 设计原则

1. **限幅先于控制律(limiter-before-law)**。任何 syscall、任何自治档、任何 specialist 建议,施加前必过 SafetyGuardian;CRITICAL→饱和到 0(禁执行)。**但见 §4 的诚实修正**:对良性 kind(建提醒/补水),现有 59 条规则不会触发——限幅器对它们是空门,安全靠"kind 本身良性 + allowlist",不能假装限幅器在保护。
2. **执行器与传感器尽量合一**。零摩擦执行的极限是"做完不用点":high-confidence HealthEvent → 协议匹配 → 自动写观测 → 时间线自动打勾。只能落在常驻贴身的腕上。
3. **辨识结果必须有可查询落点**,供增益整定器读"这次干预对这个用户有没有效"。**该落点已存在 = `OutcomeMetric`**(§6),不新建。
4. **冷启动先于 Write**。对新用户一无所知时全手动确认、先攒先验;**自治是挣来的,不是默认给的**(已被 `WriteIntent.trust_tier` 默认 `manual_confirm` 物化)。
5. **医疗边界是永久封顶,不是默认档**。涉处方/激素/调量的 syscall 增益整定器**无升级权**;且不止禁执行,连"对你有效/恶化"的因果裁决都禁出(降级 `clinician_review`)。
6. **删零件 > 加抽象**。本文的收口动作(`surface_router`、辨识落点收口到 `OutcomeMetric`)净效应是减少重复路径,不是新建平行系统。**对抗批判已砍掉初稿里一个违反此原则的新表(`CausalLedgerEntry`),见 §9。**
7. **默认拒绝(allowlist),不是默认放行(blacklist)**。新 kind 未经显式标记可自治前,增益整定器对它无升级权——而非"不在 `medication_*` 黑名单就可升"。黑名单制在安全边界上是已知反模式(扣 `project_endpoint_default_masks_weak_model_dropped_param`:靠约定 ≠ 靠强制)。

---

## 2. OS 七层架构

每层给「设计 / 复用(已核实)/ 缺口(已核实)」。

### 2.1 内核 = SafetyGuardian 限幅器(Kernel / clamp)
- **设计**:59 条确定性规则构成饱和限幅器,在所有控制律之前运行,不依赖 LLM。
- **复用**:`agents/safety_guardian/`(59 规则,8 类);`engine.py` 已暴露 `failed_rule_count` + `_fill(raise_on_error=...)` fail-loud 范式;`models/agent_audit_log.py` 旁路审计。
- **缺口(诚实)**:① 限幅器作用于"全局健康告警输出",**尚未被接为 Write 层的强制前置门**;② **对良性写 kind 是空门**——`checkup_reminder`/补水提醒不会触发任何 BP/HR/labs/DDI 规则。所谓"执行前过限幅、CRITICAL→0"对当前所有候选 auto kind **不拦截任何东西**。需求见 §4:为每个 auto kind 定义显式的「执行前安全前置条件」,或诚实承认安全靠 kind 良性 + allowlist,**不给虚假安全感**。

### 2.2 对象模型 = Digital Health Twin(Object model / state)
- **设计**:14 语义分区的统一状态视图 = 系统的"内存映像"。进程读它,不直接读设备。
- **复用**:`twin/`(`schema.py` 14 分区、`builder.py` Redis 函数级缓存、`formatter.py`→prompt blob)。
- **缺口**:Twin 是**瞬时快照**(知道"你现在 LDL=X",不知道"鱼油对你的 LDL 有没有效")。后者是 §6 的辨识结果,**语义不同(now vs learned-over-time),不做成 Twin 第 15 分区**。
- **避坑(已核实)**:读字段先核 `schema.py` 确切键名;静息心率源优先级 Apple Watch + RingConn,Garmin fallback;血氧基于 RingConn,不采纳 Garmin。键名漂移会静默回退到未合并的 `/garmin/me days[0]` → "--"(扣 `project_twin_field_key_drift`)。预检/事务内别用 `build_twin`(它自开 SessionLocal 连真库,看不到未提交数据 → 扣 `project_build_twin_sessionlocal_ignores_db`)。

### 2.3 调度器 = 三层控制环(Scheduler)
- **设计**:Celery beat 是调度时钟;把现有定时任务**理解为**三个嵌套控制环(日/周/季,见 §3)。
- **复用**:`celery_app.py` 日级任务(晨报 7:30 / 计划提醒 8:00 / 趋势 8:30 / 晚间洞察 20:30 / 异常 23:00)+ 周报(周一 9:00);时区 `Asia/Shanghai`。
- **缺口(修正——比初稿小)**:季级外环的**计算链已存在**(`intervention_cycle_service.record_recheck → classify_change → 写 OutcomeMetric.significant/confidence`,见 intervention_cycle_service.py:129),**只是由 API 端点手动触发,缺一个定时 beat**。且系统**已有 5 个闭环 task**(`intervention_assessment` 周一11:00、`outcome_grader` 每日8:00、`open_loop_manager`、`trajectory_watch`、`adherence_watch`)——新季环 beat **必须先盘点这 5 个,明确是合并还是并列**,不能在 5 个评估环旁无脑加第 6 个(违反"删一个重复 > 加一个抽象")。

### 2.4 进程 = 13 Specialist + Orchestrator(Processes)
- **设计**:13 specialist = 用户态进程(读 Twin、产结构化 Finding);Orchestrator = init/调度(意图路由 + 依赖顺序 + LLM 合成 + provider failover)。
- **复用**:`agents/*`、`orchestrator/`(`intent.py`/`specialists.py`/`orchestrator.py`、共享 context 传递)。
- **架构红线**:specialist 输出**不直接驱动执行器**——只算误差和建议,执行量必须经 Write 层 propose → 限幅 → 自治闸(把"感知精度"与"执行权"解耦,对应战略锚"矛盾在执行迁移非感知")。
- **缺口**:无重大缺口(全仓最成熟层)。注意循环导入约定(`__init__.py` 不 import specialist 类)。

### 2.5 IO = 多端表面 + surface_router(I/O surfaces)
- **设计**:表面职责按"到身体距离 × 常驻 × 知情境"切(§5),抽出显式 `surface_router` 集中三端投影策略。
- **复用**:`watch_summary.py` / `today_timeline_service.py` / `action_ranker.py` 三套投影已存在。
- **缺口(已核实)**:`surface_router.py` 不存在;三套各自 `import agenda_service` + 各自拼装。**但**(对抗批判提醒)三套排序口径真有差异(`watch_summary` 走 `action_ranker` 重排序、`today_timeline` 复用 `_TW_ORDER` 时间窗排序),不是可无脑合并的重复 —— 抽 Router **先量化三套到底有多少行真重复**,共享层只收口真正一致的部分(白名单/上限),保留各端排序差异为参数,**避免为对称性硬抽出参数爆炸的中间层**。

### 2.6 syscall = Write 层(System calls / the only writes to the body-world)
- **设计**:OS 唯一真缺的自治层。每个 syscall 是一个 `WriteIntent`(kind/payload/执行产物引用),执行前过限幅、按自治档决定自动还是确认。
- **复用(比预期成熟,已核实)**:`models/write_intent.py` 已有 `kind/title/payload/executed_ref/status/trust_tier(默认 manual_confirm)/source` + `(id,user_id,status=pending)` 原子确认门 + `ix_write_intents_user_status`;`write_intent_service.py` 有 `propose`(幂等)/`confirm`(原子)/`_execute`。依从写回的幂等 DB 兜底范式已沉淀(`UniqueConstraint` + 原子 `UPDATE...WHERE status!=completed` rowcount 门 + IntegrityError 重读,扣 `feedback_adherence_writeback_idempotency_db_guard`)。
- **缺口(修正——真承重墙在此)**:
  1. **`_execute` 只认 1 个 kind(`checkup_reminder`)**,其余 fail-loud。syscall 字典要分级扩展(良性写:加日历/装周药盒清单/补水提醒 → 中风险:改协议参数 → 高风险:改药=**永久禁止**)。
  2. **服务端自治执行路径整段不存在**——`propose` 当前只在 `GET /write-intents` 请求处理器里惰性跑,`confirm`/`_execute` 只由用户点击触发。**没有任何 Celery worker 在服务端 propose 或 execute**。"自动执行(仅事后审计可见)"在物理上跑不起来。这是整个自治论纲的承重墙,**应是落地第一性问题**(见 §7),而非末位。它需要:(a) 一个 task 负责服务端 propose;(b) 一个 task 负责对 `auto` 档 intent 执行;(c) **后台执行的鉴权**(worker 以何身份写、如何只动该 user 数据)+ **幂等**(后台重复 propose/execute 去重)+ **限幅适配**。当前 IDOR 守卫与原子门都假定有 `confirm` 这步人工动作,后台路径需要全新安全模型。
  3. syscall 与辨识结果未关联(无 `write_intent_id` 关联,无法回答"这条放权基于哪条辨识结论")。

### 2.7 权限分级 = 自治档整定(Permission tiers / earned autonomy)
- **设计**:自治权按"这次干预对你显著吗"的辨识置信度逐类挣得。三档:`manual_confirm` → `shadow` → `auto`。
- **重要修正(已核实代码,勿假装现状)**:
  - `intervention_significance.classify_change()` 返回**离散** `(bool, "low"/"moderate"/"high")`,**不是连续 float**。"连续自适应增益"是 roadmap,不是现状。短期:三档置信度映射升档步长(`high`→可升一档 / `moderate`→留档 / `low`→不动);中期再升连续。**文档不假装已连续。**
  - **不改 `WriteIntent.trust_tier` 列名**(对抗批判 #contradiction):它与 `system_knowledge_service` 的知识源 `trust_tier` 虽同名,但一个是 DB 列、一个是 service 内部 dict 字符串字段,**永不在同一行代码/同一条 SQL 相遇**。为纯命名学顾虑迁移一张已上线表违反 Frozen Core "改 schema 需 review"且风险/收益倒挂。**做法**:新模块/新代码措辞用 `autonomy_tier`,既有列保留 `trust_tier` 不动。`WriteIntent.trust_tier` 语义上**就是**自治档,无需改名。
- **缺口**:增益整定器(`trust_elevator`:读辨识结果 → 算该升哪档 → 写回自治档)不存在。**头号 risk = 误升级误放权**,缓解见 §2.8 + §4 的默认拒绝/独立二次校验。

### 2.8 保护模式 = trust_elevator 影子模式(Protected mode / shadow before live)
- **设计**:`trust_elevator` 先上**影子模式**:只**计算**每个 `(user,kind)` 该升到哪档并**写审计**,**不真放权**;人工核对它不乱升、跑稳数周后再启用真自治。
- **复用**:`models/agent_audit_log.py` 旁路审计是影子落点。
- **缺口 + 运行时硬约束(对抗批判 #safety)**:影子模式只是"上线前观察",**不是运行时 fail-safe**。必须再加一道**与 elevator 解耦的运行时硬编码 allowlist 二次校验**:execute 前独立确认"这个 kind 真在可自治白名单里吗",消除"elevator 单点 bug 直达放权"。安全惯例 = 默认拒绝 + 独立二次确认,**单一判定源不可接受**。

### 2.9 Shell = 多端客户端(Shell / per-surface UX)
- **设计**:腕(被动采集+零摩擦执行)、手机(控制台+Write 确认面)、Mac/Web(深析归因)。投影由 §2.5 `surface_router` 统一供给。
- **复用**:`mobile/`(RN 唯一原生 App,5 tab)、`frontend/`(Next.js Web 深析)、watch 伴生 App(已发版,过了 4 层构建修复 + EAS 凭据;扣 `project_watch_companion_eas_build_signing`)。
- **缺口/不对称**:三端投影未统一(同 §2.5);Android 的 widget/extension 是 noop fallback(`modules/shared-keychain/` iOS-only)——标注为已知不对称,非本设计目标。Shell 不持业务逻辑,`user_id` 一律取自 token(腕上不持 token,经 iPhone bridge)。

---

## 3. 三层控制环

```
┌─ 季环 (Quarterly · 系统辨识外环) ── setpoint: 你的真实因果系数 ───────────────┐
│  每 12 周: 收尾 intervention_cycle → washout → 复测 → record_recheck         │
│  → classify_change → 写 OutcomeMetric.significant/confidence                 │
│  → trust_elevator(影子)算升档 → 整定该 kind 的 autonomy_tier                 │
│  ⚠ 计算链已存在(intervention_cycle_service.py:129),真缺 = 一个定时 beat       │
│     且须先盘点已有 5 个 loop task(见 §2.3)决定合并/并列                       │
│  ┌─ 周环 (Weekly · 计划整定中环) ── setpoint: 本周训练/营养/恢复目标 ──┐      │
│  │  周一 9:00 周报 → ACWR / readiness 趋势 → 回写下周 Write 计划        │      │
│  │  ⚠ 周报现多是只读叙事,缺"回写成下周 Write 计划"这一步             │      │
│  │  ┌─ 日环 (Daily · 执行内环 · 已基本存在) ──────────────────────┐   │      │
│  │  │  晨报估计 → 时间线下发 syscall → 限幅 → 执行/确认            │   │      │
│  │  │  → 腕上被动采集观测(传感器=执行器合一)→ 自动打勾           │   │      │
│  │  │  → 异常检查 23:00 = 内环误差检测 → 必要时 CRITICAL 饱和      │   │      │
│  │  └──────────────────────────────────────────────────────────┘   │      │
│  └─────────────────────────────────────────────────────────────────┘      │
└────────────────────────────────────────────────────────────────────────────┘
```

**关键耦合(护城河发动机)**:外环写辨识结果(§6)→ 喂增益整定器(§2.7)→ 整定 `autonomy_tier`(§2.8 影子先行)→ 改变日环里 syscall 是自动还是确认。这条链 = "学到的因果 → 挣到的自治"的物理实现。washout 子系统目前**全仓零实现**——它的语义(停哪些干预、多久、如何区分 carryover vs 真效应、对他汀 LDL 这类长半衰期指标如何取窗)是一个**完整待设计的子系统**,不能用一个名词糊过去(对抗批判 #gap)。

---

## 4. Write 层放权路线(冷启动 → 自治)

**总原则:自治逐 kind、逐用户、由外环验证收敛挣来,默认拒绝,且永远过限幅。**

| 阶段 | autonomy_tier | 行为 | 升档条件 |
|---|---|---|---|
| 冷启动(现状,全 kind) | `manual_confirm` | 每条 syscall 在手机 Write 确认面等用户点确认 | — |
| 影子 | `shadow` | elevator 算"本该自动"并写审计,**仍要用户确认** | 该 (user,kind) 累计 ≥N 条 `OutcomeMetric.significant=true`(N 待定)且影子判定连续数周稳定无误升 |
| 自治 | `auto` | 低风险 kind 自动执行,事后审计可见 | 影子期人工放行 + 在 allowlist 内 |

**放权硬约束(多为对抗批判补强)**:
1. **默认拒绝**:kind 未经 safety review 显式标 `autonomy_eligible=true` 前,elevator 对它**无升级权**。每个 kind 注册带**强制 `risk_class` 字段**(由 `safety-privacy-reviewer` 填),**不靠 `medication_*` 名字前缀判 clinical**(`dose_adjust_reminder`/`hormone_followup` 不匹配前缀就漏网——扣"靠约定而非强制"教训)。
2. **clinical 类 actuator 永久封顶 `manual_confirm`**:涉处方/激素/调量,elevator 无升级权、直接短路。
3. **双闸覆盖"辨识→放权"路径**(扣 `feedback_personalized_effect_no_prescription_verdict`):`record_recheck` 写的 `significant` 不区分处方指标(statin 拉低 LDL 也会记 `significant=true`)。elevator 读 `OutcomeMetric` 升档时,**对 `metric_code` 属处方/激素类的条目一律不计入升档信号**(复用 `personal_models` 已有的处方指标判定)。否则处方混杂的"效应"绕过 `personal_models` 已落地的 `clinician_review` 降级,从"辨识→放权"这条没设闸的路径污染放权。
4. **限幅永远在前**,但**对每个 auto kind 写出显式"执行前安全前置条件"契约**(检查什么 twin 状态、什么条件拒绝),否则限幅器对良性写是空门(§2.1)。
5. **服务端执行路径先于自治档开通**(§2.6 缺口 2):没有后台 propose/execute worker + 鉴权 + 幂等,`auto` 档物理上不成立。
6. **幂等兜底**:自治写回沿用 DB 兜底范式;内层 service `commit=False` 交外层同事务,防虚高依从污染 DDI/PGx。

---

## 5. 多端表面职责(IO 物理分布)

| 表面 | 距离/常驻/情境 | 职责 | 为什么物理上只能是它 |
|---|---|---|---|
| **腕** | 贴身/常驻/强情境 | **被动采集 + 零摩擦执行** | 只有常驻贴身设备能做"执行器=传感器合一":做完动作时它就在身上,直接测到、自动打勾 |
| **手机** | 近身/高频/中情境 | **控制台 + Write 确认面** | Write 确认需清晰卡片 + 一次明确手势;腕屏太小、Web 不常在手边 |
| **Mac/Web** | 远身/偶尔/大屏 | **深析归因 + 季度复测阅读** | 因果趋势叙事、N-of-1 结果需大屏长阅读 |

**被动采集 = 执行器与传感器合一(扣 R12 门控 + sentinel v0 已落地)**:
- high-confidence `HealthEvent`(≥0.8)→ 协议匹配 → 自动写 `auto_observed` → 时间线自动打勾(做完不用点)。
- **低置信 / 跨用户协议不自动闭环**(R12 门控),避免误判污染辨识结果。
- **freshness 上腕**:没同步显示"待同步"**而非旧值**(扣 `project_twin_field_key_drift`)。
- **复用(已核实)**:`baseline_deviation_sentinel.py`(v0)、`health_event_service.py`、`health_protocol_service.py`、`models/health_event.py`(带 confidence)。
- 自动观测 = 高密度低噪声数据,**直接喂 §6 辨识** —— 腕上表面对护城河的核心贡献。

---

## 6. 护城河 = per-user 因果辨识结果(复用 OutcomeMetric,不新建表)

**对抗批判推翻了初稿的核心动作**(详见 §9):初稿要新建一等对象 `CausalLedgerEntry`,理由是"辨识结果无可查询落点"。**该前提经核实为假**——落点已存在:

**`OutcomeMetric`(intervention_cycle.py:63)已是持久、可查询对象**,含:`metric_code` / `baseline_value` / `latest_value` / `delta` / `delta_pct` / `direction` / `status` / **`significant`(Boolean)** / **`confidence`(String)** / `baseline_observed_at` / `latest_observed_at` / FK `cycle_id`(→ `InterventionCycle.user_id`)/ 索引。且 `personal_models.py` 已在其上做 per-user 效应估计 + 处方指标 `clinician_review` 降级。

**正确动作 = 收口到 OutcomeMetric,而非造平行表**:
- **增益整定器直接读 `OutcomeMetric.significant`**(不新建对象)。
- **唯一真缺的关联** = 一条 `write_intent_id` 关联(回答"这条放权基于哪条辨识"):在 `WriteIntent` 或一张轻量关联里加,**不为此新建一等持久对象**。
- 四个散落零件(`models/episode.py` / `models/intervention_cycle.py` / `services/causal_memory.py` 派生因果笔记 / `services/causal_links.py` 出 prompt blob)中,**`causal_memory`/`causal_links` 是无状态 derive-on-read 纯函数,本就不该被"收口"成持久表**(那是净增复杂度,违反删>写)。若有真重复,在 `medication_intervention_effects` 与 `OutcomeMetric` 的 delta 计算之间——按需收口那一处即可。

**为什么这是护城河**:per-user 因果系数**不可跨用户外推**(扣 `project_genotype_effect_prior_verified_empty`:基线关联 ≠ 治疗交互、群体 ≠ 个体)。`OutcomeMetric` 是靠这个用户自己的季度复测一条条攒出来的,新对手每个新用户从零——这是真数据资产。增长指标 = 单用户**验证过的闭环轮次**,非用户数。

---

## 7. 落地次序(扣现有代码,每刀可独立回归)

按"最薄、最可回归、最先解锁后续"排序。**自治通道在最后且影子先行;服务端执行路径提前(它是承重墙)。**

**第 0 刀 · `surface_router` 抽取(地基 / 0 native / 纯重构)**
先量化 `watch_summary`/`today_timeline`/`action_ranker` 三套真重复行数 → 只收口真正一致的(白名单/上限),排序差异留参数。三端输出 shape 不变可回归(`tests/test_watch_summary.py` 当前正改动中 → 同 PR 对齐)。

**第 1 刀 · Write 层服务端执行路径(承重墙,自治的前置一性问题)**
(a) Celery task 服务端 propose;(b) task 对 `auto` 档 intent 执行;(c) 后台鉴权(worker 身份)+ 幂等 + 限幅适配。**没有这三件,后面所有自治都是空中楼阁。** 可回归:合成 intent 跑后台 propose→execute,验幂等(重复不双写)+ 鉴权(只动该 user)。

**第 2 刀 · Write 层限幅前置 + per-kind 安全契约**
在 `write_intent_service` 执行路径插"执行前过限幅"拦截点;**为每个 auto kind 写显式执行前安全前置条件**(否则是空门)。可回归:对抗测试——CRITICAL 用例让自动执行饱和到 0,换回旧版必红。

**第 3 刀 · 季环 beat(注意:是加 beat,不是从零搭外环)**
新建季度 beat 对 active cycle 调已存在的 `record_recheck`;**先盘点 5 个已有 loop task,明确合并/并列**。`write_intent_id` 关联在此接。可回归:合成历史数据跑完整 12 周端到端。washout 子系统单独设计(§3)。

**第 4 刀 · trust_elevator 影子模式 + 默认拒绝 + 双闸(自治前强制闸)**
读 `OutcomeMetric.significant`(**跳过处方/激素 metric_code**)→ 算 `proposed_autonomy_tier` → 写审计,**不真放权**。默认拒绝(allowlist) + clinical 短路。**此步未跑稳数周、人工核对无误升前,第 5 刀不得开。**

**第 5 刀 · 逐 kind 开自治(低风险先行)**
影子期人工放行的低风险 kind(补水/拉伸提醒)→ `auto`,且过运行时独立 allowlist 二次校验(§2.8)。**永不开**:`medication_*` 及一切处方/激素/调量 kind。

**异步执行约定**:build/长 test 后台跑;手写迁移本地 in-memory + 真 PostgreSQL 各验一遍(SQLite 仅测试 fixture;`JSONB`/`TIMESTAMP WITH TIME ZONE` 依赖)。并发有 Codex 在同仓时,提交走 `git push origin HEAD:main`,只 stage 自己的文件。

---

## 8. 不做什么(复杂度预算 / YAGNI / 医疗边界)

**不做(YAGNI)**:
- ❌ **不新建 `CausalLedgerEntry` 平行表** —— 复用 `OutcomeMetric`(§6 / §9)。
- ❌ **不迁移 `WriteIntent.trust_tier` 列名** —— 撞名永不同处出现,新代码用 `autonomy_tier` 措辞即可(§2.7)。
- ❌ **不在 5 个已有 loop task 旁无脑加第 6 个** —— 先盘点合并(§2.3)。
- ❌ **不建空的"基因型→干预效应先验"通道** —— 12 对对抗核实全杀,是假放大器(扣 `project_genotype_effect_prior_verified_empty`)。
- ❌ **不把辨识结果做成 Twin 第 15 分区** —— 语义不同(now vs learned)。
- ❌ **不为"连续增益"提前重写 `classify_change`** —— 短期三档映射够用。
- ❌ **不加后端路由别名迁就错误 skill 调用**;**不追 mobile/Web feature parity**(RN first);**不动 Android widget 通道**(noop fallback)。
- ❌ **不让 OS/控制论隐喻驱动决策** —— 它是叙事透镜,工程项各自独立成立。

**医疗边界(永久封顶)**:不诊断、不开方、不调量。处方/激素指标**双闸**(禁自治执行 + 禁出"对你有效/恶化"裁决 → `clinician_review`),且双闸覆盖"辨识→放权"读路径(§4.3)。危机/急症 CRITICAL 饱和优先一切。安全评估每个吞异常点都是 under-alarm 漏洞 → fail-loud(`failed_rule_count` + `evaluation_failed` 注入 HIGH fail-safe advisory),失败仍跑兜底(扣 `feedback_safety_eval_swallow_points_fail_loud`)。

---

## 9. 审查修正记录(对抗批判推翻/修正了什么)

本文经一轮对抗批判 + 逐条代码核实,以下初稿(综合阶段)结论被**推翻或下调**——保留此记录是为让未来读者看到决策出处,不重复踩坑:

| 初稿结论 | 对抗批判 + 代码核实 | 本文采纳 |
|---|---|---|
| 新建一等对象 `CausalLedgerEntry`,因"辨识结果无可查询落点" | **前提为假**:`OutcomeMetric`(intervention_cycle.py:63)已有 `significant`/`confidence`/`delta`/FK/索引,`personal_models.py` 已在其上做 per-user 效应 | **砍掉新表,复用 OutcomeMetric**(§6);只补 `write_intent_id` 关联 |
| 季环"从零搭建" | 链已存在(intervention_cycle_service.py:129 `record_recheck`→`classify_change`→写 OutcomeMetric),只是手动触发 | **降级为"加一个 beat" + 盘点 5 个已有 loop**(§2.3/§3/§7) |
| 迁移 `WriteIntent.trust_tier`→`autonomy_tier` 避撞名 | 撞名是 DB 列 vs service dict 字符串,永不同处;迁移已上线表违反 Frozen Core | **不迁移**,新代码用 `autonomy_tier` 措辞(§2.7) |
| "限幅器执行前 CRITICAL→0"作为 auto kind 的 fail-safe | SafetyGuardian 59 规则不会因"建提醒"触发 → 对良性 kind 是空门、虚假安全感 | **诚实标注空门**,要求 per-kind 安全契约(§2.1/§4.4) |
| (初稿未覆盖)`auto` 档执行 | propose 只在 GET 惰性跑、execute 只由 confirm 触发,**无服务端 worker** | **新增为承重墙,提到落地第 1 刀**(§2.6/§7) |
| clinical 封禁靠 `medication_*` 前缀(黑名单) | 前缀漏网(`dose_adjust_reminder`);黑名单是反模式 | **改默认拒绝 allowlist + 强制 `risk_class`**(§1.7/§4.1) |
| 双闸只在"辨识输出展示层" | elevator 读 `significant` 升档绕过 `clinician_review`(statin→LDL 假效应) | **双闸延伸到"辨识→放权"路径**(§4.3) |
| OS/控制论隐喻贯穿全文当设计骨架 | 隐喻不产出可推导决策,每个缺口是独立工程项 | **降级为叙事透镜**,工程项独立成立(定调段 + §8) |

> 这是设计面板的价值:**初稿(单一综合视角)在 8 处过度设计或与代码现实冲突,对抗批判逐条用 repo 行号驳回。** 没有这一轮,文档会引导去建一张冗余表 + 迁移一张上线表 + 在空安全门上建自治 —— 三个真实的坑。

---

## 关键文件索引(绝对路径)

**复用基座**:
- `backend/app/agents/safety_guardian/engine.py`(限幅器,`failed_rule_count` fail-loud)
- `backend/app/twin/schema.py`(14 分区,读字段先核键名)
- `backend/app/models/write_intent.py`(syscall 模型,`trust_tier` = 自治档,不改名)
- `backend/app/services/write_intent_service.py`(`propose`/`confirm`/`_execute` —— `_execute` 仅认 `checkup_reminder`,无服务端 worker)
- `backend/app/models/intervention_cycle.py`(**`OutcomeMetric` = 辨识结果落点**)
- `backend/app/services/intervention_cycle_service.py`(`record_recheck` —— 季环计算链,缺 beat)
- `backend/app/services/intervention_significance.py`(`classify_change` 返回离散三档,非连续)
- `backend/app/api/personal_models.py`(处方指标 `clinician_review` 降级 —— elevator 须复用)
- `backend/app/services/baseline_deviation_sentinel.py`(被动采集 v0)

**待统一的三投影(→ `surface_router`,先量化真重复)**:
- `backend/app/services/watch_summary.py` · `today_timeline_service.py` · `action_ranker.py`

**撞名警示(勿迁移)**:
- `backend/app/services/system_knowledge_service.py` 的 `trust_tier` = 知识源可信度,与 `WriteIntent.trust_tier` 永不同处。
