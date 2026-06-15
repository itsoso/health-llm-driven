# Reva Personal Health OS — 统一重设计蓝图(协议层 + 手工录入双轨)

> **状态**: 重设计纲领 v1(2026-06-15)。本文**整合三个输入**,作为下一轮重设计的单一事实来源:
> 1. **TO-BE 目标形态** ← Codex《全局产品需求说明书》[`docs/prd/2026-06-15-global-product-requirements.md`](2026-06-15-global-product-requirements.md)(HealthAgenda / HealthProgram / Router / R1–R10 / WSCLA / 5 入口)
> 2. **AS-IS 现状基线 + 不变量 + 技术债** ← [`docs/PRD.md`](../PRD.md)(逐子系统逆向 review;PR #181)
> 3. **「容器化/协议化健康」最佳实践 + 手工/协议双轨原则** ← 本轮产品决策
>
> **本文新增的核心**:在 Codex 的 `HealthAgendaItem` 之上引入一等对象 **`HealthProtocol`**,并确立 **双轨录入模型(协议轨 + 手工轨,两轨写同一份数据、同一议程)**——这是把「最佳实践 = 一次设定 + 完成确认 + 被动采集」与「手工录入永远可用」统一进 Codex 目标架构的关键。
>
> **关系**:本文不另立北极星/IA,沿用 Codex PRD;只在「一等对象」「录入模型」「需求清单」「路线图」上**增补 + 收口**。Codex PRD 与本文有冲突时,以本文为准(本文是更晚的整合)。

---

## 1. 北极星与定位(沿用 Codex,确认)

- **定位**:Reva Personal Health OS —— 面向 35–60 岁中年代谢/恢复人群的个人健康操作系统。承诺不是「回答健康问题」,而是「帮你把每天/每周/每季该做的健康行动安排好、在对的设备上提醒执行、用指标验证是否真变好」。
- **北极星 WSCLA**:每周完成的、**安全 + 证据可追溯 + 被安排 + 已执行 + 可验证**的健康行动闭环数量。
- **第一目标用户画像(产品锚点)**:糖前(HbA1c 6.3)× 脂肪肝 × 长期 PPI × 12 药 × 同戴 Apple Watch Ultra 3 + RingConn Gen3 + Garmin Enduro 2(跑步两块同戴)。

---

## 2. 核心设计原则(合并三源)

**来自 AS-IS 不变量(必须保留)**:① 确定性优先,LLM 只合成;② 不假装成功(写前确认、撞药不静默);③ 医疗边界(不诊断/开方/调量、分级措辞、claim_boundary);④ 行为闭环 + N-of-1 验证;⑤ 删码优先、复杂度预算。

**来自 Codex(收敛纪律)**:⑥ 任何新增需求必须能落到 **HealthAgenda / HealthProgram / HealthRouter** 三者之一,否则不做;⑦ 三端分工(Mobile 主体验 / Mac 工作台 / Web 后台 / Watch 执行)。

**第一性原理(ChatGPT Pro 反馈,定问题)**:健康产品要解决的不是「不知道怎么做」,而是四个断点 —— **① 知道但不执行**(缺执行环境)**② 执行但不可见**(缺自动采集)**③ 有数据但不决策**(数据垃圾)**④ 优化但缺医学边界**(慢病/结节需诊断/随访/阈值)。一句话定位:**让正确的健康行为在正确时间以最低认知成本自动发生,并把慢病风险纳入长期闭环。** 成功标准不是「用户打开多少次」,而是「用户不用打开,健康行为仍稳定发生」。

**本文新增(整合关键)**:
> ⑧ **双轨录入,手工与协议同为一等公民。** 每个环节同时支持「**协议轨**」(固定容器 / 预承诺 / 被动设备 → 完成式/自动观测)与「**手工轨**」(逐量录入,随时可用)。两轨**写同一份底层记录、同一条 agenda 事件**;outcome 不关心来自哪轨。**协议永不取代手工,只是默认更省力的那条路。**
> ⑨ **医学边界优先 + 优先级排序。** 慢病/结节不是「每日习惯」而是「标准化随访 + 红线阈值 + 升级路径」。注意力排序硬性为 **医学风险控制 > 代谢改善 > 睡眠恢复 > 运动能力 > 皮肤/外观/抗衰**;抗衰/补剂/基因不得抢占 P0/P1 医学问题的注意力。
> ⑩ **打卡第一性原理(决定要不要记)。** 一个观测只有同时能 ①验证关键行为发生 ②(未发生时)解释失败原因 ③改变下一步计划,才值得存在。**不改变下一步行动的打卡一律删除。** 终极目标是打卡被环境/设备替代到「消灭自己」。
> ⑪ **失败是系统参数,不是人格。** 完成事件必须能捕获**失败原因**(没时间/忘了/物品不在/太累/地点不对/计划太难/身体不适/社交打断),系统据此**自动纠偏协议**(改时间/补耗材/降目标),措辞是「系统哪里设计得不够好」而非「你失败了」。
> ⑫ **证据等级 A/B/C/D。** 每条协议/建议标证据级(A 指南强推/医生要求 · B 较好证据低风险 · C 个人实验有逻辑 · D 体验型不影响核心),低证据项不得污染核心健康决策。

---

## 3. 主循环与信息架构(沿用 Codex,插入协议层)

```text
✦ Health Problems(医学问题登记:慢病/结节/异常 → 风险分层 + 红线 + 随访 + 升级)  ← 本文新增,目标/边界层
  ↓ (问题驱动目标)
Data In(穿戴/HealthKit/Garmin/RingConn/BP/秤/CGM/化验/食物/语音/症状/日历)
  ↓
Health Vault + Source Arbitration(归一 + winning_source + freshness + confidence)
  ↓
Health Twin + Snapshot(当前态 + 基线 + 风险 + 不确定度)
  ↓
Health Programs(代谢/恢复训练/睡眠/用药补剂/检查 —— 8–12 周目标容器)
  ↓
✦ Health Protocols(每域用户选定的最佳实践:容器/预承诺/被动/环境默认)  ← 本文新增层
  ↓
Health Agenda(today/week/month/quarter 的 HealthAgendaItem,由 Problem×Program×Protocol 投影)
  ↓
Surface Router(Watch 执行 / Mobile 主体验 / Mac 复盘 / Web 后台 / external agent)
  ↓
Execution Events(completed/skipped[+失败原因]/adjusted/auto_observed/confirmed)  ← 双轨合流
  ↓
Operating Review(7/30/90 outcome + 个人响应 + 协议纠偏 + 下一议程)
  ↓
✦ Safety & Escalation(红线阈值命中 / 复查到期 / 趋势恶化 → 医生/科室/急诊路径)  ← 贯穿层
```

> **对齐 ChatGPT 8 层框架**:目标层 = Problems 的目标函数;医学边界层 = Problems 的风险分层+红线;数据感知层 = Data In + Router;协议层 = Protocols;规划层 = Programs+Agenda;执行层 = Surface Router(可穿戴轻中断);反馈控制层 = Operating Review(每周一次,非每天深度);安全升级层 = Safety & Escalation。

**Mobile 5 一等入口(沿用 Codex)**:Today / Agenda / **Capture(双轨录入入口)** / Programs / Review(其中 Programs 视图含「健康问题」子页)。
**三端分工(沿用 Codex)**:Mobile 主体验;Mac 桌面工作台/导入复盘;Web 后台/报告/历史兼容/Apple Health XML fallback;Watch 腕上执行器;小程序降级历史兼容。

---

## 4. 一等产品对象(Codex 三个 + 本文两个)

沿用 Codex:**`HealthAgendaItem`**(从现有模型投影的统一执行层,字段见 Codex §5.1,含 `device_context.automation_path: healthkit|garmin|manual|...` —— **manual 本就是一条合法路径**)、**`HealthProgram`**(5 类:代谢/恢复训练/睡眠/用药补剂/检查)、**`Personal Health Router`**(指标级 winning_source/freshness/reliability/agreement/safety_policy)。

完整对象层级:**`HealthProblem`(医学问题/目标)→ `HealthProgram`(8–12 周容器)→ `HealthProtocol`(每域怎么做)→ `HealthAgendaItem`(今天何时做)→ Execution Event(双轨合流)**。

### ✦ 4.1 新增一等对象:`HealthProblem`(医学问题登记 —— Health OS 与 habit tracker 的分水岭)

ChatGPT 反馈的最强论点:慢病/结节/异常不是「每日打卡」,而是**标准化随访 + 风险分层 + 红线阈值 + 升级路径**。普通 habit tracker 没有这层,Health OS 必须有。它是目标层 + 医学边界层的载体,**驱动** Program / Protocol / Checkup Planner。

```yaml
HealthProblem:
  id; user_id
  name: 鼻炎 | 肥胖 | 脂肪肝 | 高血压 | 肾结石 | 甲状腺结节 | 肺结节 | 糖尿病前期 | ...
  risk_level: P0 | P1 | P2          # 医学风险优先级(P0/P1 压过抗衰/外观)
  status: active | monitoring | resolved
  diagnosis: {分型/分期, 证据来源(影像/化验/症状), evidence_grade: A|B|C|D}
  risk_stratification: 标准化框架引用   # 甲状腺→ACR TI-RADS;肺结节→Fleischner;脂肪肝→纤维化分期
  red_lines: [{metric, threshold, action}]   # 红线阈值 → 命中即升级(对接 Safety Guardian)
  responsible: {doctor/科室}          # 耳鼻喉/内分泌/消化/泌尿/呼吸/心内…
  managing_programs: [program_id]      # 由哪些 Program/Protocol 管理(如脂肪肝←代谢 Program)
  follow_up: {last_checkup, cadence, next_due, what_to_check}  # 随访日历(投影成 Agenda)
  escalation_path: string             # 异常/到期/恶化 → 谁、做什么
  evidence_tier: A | B | C | D
```

要点:
- **复查产品化**:`follow_up.next_due` 自动投影成 Agenda item;到期/红线命中 → Safety & Escalation 层升级。把「上次查/风险分层/下次查/医生结论/到期提醒/异常升级」闭环 —— 这正是 Codex R7(Checkup Planner)的上游驱动。
- **优先级守门**:`risk_level` 让 Agenda 排序时 P0/P1 医学问题压过抗衰/补剂(原则 ⑨)。
- **不诊断红线**:风险分层引用权威框架(TI-RADS/Fleischner/NAFLD 分期),系统**呈现 + 随访 + 升级**,不替代医生分级/诊断(原则 ③)。

### ✦ 4.2 新增一等对象:`HealthProtocol`

`HealthProtocol` 是用户为某个域**一次设定的最佳实践**,它把「量」外包给容器/预承诺、把「采集」外包给被动设备,然后**投影出 HealthAgendaItem**。它位于 Program 与 Agenda 之间:`HealthProgram(长期目标) → HealthProtocol(怎么做,每域) → HealthAgendaItem(今天何时做)`。

```yaml
HealthProtocol:
  id; user_id
  domain: hydration | diet | sleep | training | medication | supplement |
          measurement | mood | activity | checkup
  name: "2000ml 温水杯" | "Wagas 标准餐" | "周二四六晨 Zone2" | "周药盒" | "生日周年度体检"
  status: active | paused | archived
  mechanism: fixed_container | pre_commit | passive_device | environment_default  # 量为何隐式
  implied_quantity: {...}        # 协议先验(2000ml/50°C;模板 kcal+protein;课表 zone+时长)
  completion:
    protocol_track:              # 协议轨:完成如何隐式判定
      mode: auto_observed | device_synced | one_tap
      signal: "杯子喝完一键✓" | "Garmin workout 同步" | "智能秤上传" | "药盒格子取空"
    manual_track_allowed: true   # 手工轨:始终为 true(双轨原则 ⑧)
  cadence: daily | per_meal_slot | weekly | event_triggered | quarterly | annual
  time_window: morning | noon | afternoon | evening | bedtime | anytime
  adjustable_by: [decision_light, cadence_engine, safety_guardian]   # 参数当天可被动态调
  verification: {metric_codes: [...], window_days: int}
  links: {program_id, source_models: [DietRecord|WaterRecord|WorkoutRecord|MedicationLog|...]}
```

要点:
- **协议轨 + 手工轨写同一 `source_models`**(同一份 DietRecord/WaterRecord/…),并发同一条 agenda `Execution Event`。Review/outcome 统计天然无视来源。
- 协议**只固定「量与默认」,不固定「强度/时机」**——那些交给 `decision_light`(训练强度)与 `cadence_engine`(检查/复查到期)动态调(`adjustable_by`)。
- 缺协议时,该域仍可纯手工录入(手工轨独立成立)。

---

## 5. 双轨录入模型 —— 每个环节的最佳实践(本文核心)

每域同时给出:**协议轨**(默认省力路径,落实「容器化/协议化」)与**手工轨**(随时可用的逐量录入)。两轨等价写库。⚙️=已建可复用 / 🔜=待建。

| 域 | 协议轨(默认,低摩擦) | 完成判定 | 手工轨(始终可用) | 复用/待建 |
|---|---|---|---|---|
| 💧 饮水 | 2000ml 温水杯(矿泉+沸水兑 50°C),全天喝完 | 一键「今日水杯 ✓」/默认完成,只标未完成 | `+250ml` 计量录入 | water quick API ⚙️;杯协议 🔜 |
| 🍱 饮食/减肥 | 3–5 个标准餐模板(低 GI/高蛋白,先验 kcal+protein);选模板=记一餐 | 选模板一下;缺口=模板和−Garmin 被动消耗 | 拍照识别 / 文本 / 语音逐餐估算 | recognize-and-save / 语音解析 ⚙️;餐模板 🔜 |
| 😴 睡眠 | 固定起床锚点 + 固定睡前触发(关屏/手机出卧室/恒温) | RingConn 24h 被动测(零录入);只确认睡前流程是否按时启动 | 手填上床/起床/质量 | RingConn 多源摄入 + 睡眠分析 ⚙️;睡前协议信号 🔜 |
| 🏃 运动 | 固定训练档期 + 默认课表;强度交给决策灯当天调 | Garmin 被动记录;去做即可 | 手填运动类型/时长/RPE | recovery_decision(GREEN/YELLOW/RED P0)⚙️;workout_sync ⚙️;课表协议 🔜 |
| 💊 用药 | 方案模板录入排时点 + 周药盒;到点提醒 | 手腕一键「已吃」/药盒取空 | 手动加药 + 逐次服药日志 | 用药自动驾驶(#174/#176)⚙️;阶段切换 P1b 🔜 |
| 💊 补剂 | 一周一次分装入周药盒(装什么由 N-of-1 定) | 取空即达成 | 逐次补剂打卡 | supplement N-of-1 ⚙️;分装协议+图 🔜 |
| 📋 体检/专项 | 固定年度档期 + 标准 panel;病情驱动加项(HbA1c q3–6 月、长期 PPI→B12/镁/骨密度、脂肪肝→肝功+超声)自动排 | 节律引擎排期 + 到期提醒;结果 OCR 入趋势 | 手动上传体检报告 | 5 通道化验录入 + 复查映射 ⚙️;Checkup Planner(R7)🔜 |
| ⚖️ 测量(体重/血压/血糖) | 连接式设备 + 固定触发点(晨起踩秤/晨咖啡后测压/季度 CGM 战役) | 设备自动同步,零手记 | 手填体重/血压/血糖 | 多源摄入 + measurement_automation ⚙️;连接设备协议(R6)🔜 |
| 🧠 情绪/压力 | HRV 被动兜底(RingConn);只异常打标 | 异常一键事件(心悸/焦虑,带时间戳) | 手填情绪/精力/压力 | HealthEvent 事件流 ⚙️;一键打标 surface 🔜 |
| 🚶 日常活动 | 环境默认(站立办公)+ 饭后固定散步 | 步数任意穿戴被动;饭后步行 nudge 确认 | 手填步数/活动 | behaviorLoopReminders ⚙️;环境协议 🔜 |

> 设计含义:**Capture 入口(Mobile 第 3 入口)= 一个域选择器 + 双轨切换**。默认呈现协议轨的「✓ 完成」式交互;手工轨永远一个点击之遥。Today/Agenda 上的 item 既可被协议轨自动/一键满足,也可被手工录入满足。

**每条完成事件捕获最少字段(原则 ⑩⑪)**:`是否完成` + `量/剂量`(协议轨为先验,可省)+ `未完成时的失败原因`(没时间/忘了/物品不在/太累/地点不对/计划太难/身体不适/社交打断);症状类加一个 0–10 评分(鼻塞/精力/疼痛/睡醒恢复感)。**失败原因驱动协议自纠偏**(见 R14),不制造羞耻。

**协议轨的医学边界精修(每域不只降摩擦,还要守证据,对接 §4.1 HealthProblem 的 red_lines)**:
- 🤧 **鼻炎**:洗鼻**必须用蒸馏/无菌/煮沸冷却水**(CDC,未处理水有罕见致命感染风险)—— 协议把「安全水源」设成默认耗材;剂量/频率/品牌**保持可调**(症状+医生校准),不固化成唯一真理;过敏性鼻炎药物/免疫治疗按指南走 HealthProblem。
- 🍱 **脂肪肝**:用**结果指标**不只「我少吃了」—— 减重 3–5% 改善脂肪变性,改善炎症/纤维化常需 **>10%**(AASLD);进 HealthProblem 的 verification。
- 💧 **饮水(有结石史)**:目标从「喝了多少」升级为「**尿量 ~2.5L / 尿色稀释**」(NKF)+ 结石成分个性化;2000ml 杯是默认最低协议,最终按 24h 尿液/医生调。碱性水不进核心。
- ⚖️ **血压**:医学级协议,看**周均值**不看单次,固定姿势/时段;连续异常 → 升级,不自行停药(AHA)。
- 🏃 **运动**:补**力量(每周≥2 次主要肌群)+ 柔韧**,WHO 每周 150min 中强度(或 75min 高强度);只跑步是盲区。
- 🧬 **基因**:ACCE 框架(分析效度/临床效度/临床效用/ELSI);v1 只做「少量高置信、可行动」解读 + 需医生/遗传咨询确认,不做全量 AI 解读(防解释幻觉)。

---

## 6. 需求清单整合(Codex R1–R10 + 本文 R11–R14)

**沿用 Codex R1–R10**(逐条见 Codex §6):R1 Health Agenda 服务端统一层 · R2 时间/日程驱动 · R3 Wearable Router v2 · R4 Apple Watch Companion · R5 Food Voice Capture 协议 · R6 Measurement Automation Protocol · R7 Checkup & Screening Planner · R8 Training Prescription & Readiness Gate · R9 Outcome Proof · R10 三端职责。

**本文新增**:
- **R11 HealthProtocol 协议层 + 双轨录入**
  - 新增 `HealthProtocol`(§4.2),Program 与 Agenda 间的投影层;每域可选/可空。
  - **每个 Capture 域必须同时实现协议轨 + 手工轨**,两轨写同一 `source_models` + 同一 agenda event;验收:同一 item 用任一轨完成,Today/Agenda/Review 表现一致,outcome 不区分来源。
  - 协议参数可被 `decision_light`/`cadence_engine`/`safety_guardian` 动态调;协议保持可校准(症状+医生反馈,原则 ⑪)。
  - R5/R6/R7 是 R11 在「食物/测量/检查」域的具体实例,统一在 `HealthProtocol.mechanism` 下表达,避免各做一套。
- **R12 协议健康度护栏**:协议轨「完成式确认」不得退化为「假装完成」——若协议依赖被动设备而设备无数据(如戒指昨晚没戴),不得静默判完成,须产 `data_quality` agenda item(对齐 Codex R3 + Rule #1)。各域**「可否默认完成」需逐一定义**:饮水可默认完成只标未达;用药/测量**禁止默认完成**(必须显式信号/设备数据)。
- **R13 HealthProblem 登记 + 复查/升级产品化(分水岭需求)**
  - 新增 `HealthProblem`(§4.1):用户医学问题清单(慢病/结节/异常)带风险分层(TI-RADS/Fleischner/NAFLD 分期)、红线阈值、负责科室、随访 cadence、升级路径。
  - `follow_up.next_due` **自动投影成 Agenda item**;红线命中 / 到期 / 趋势恶化 → **Safety & Escalation 层**升级到医生/科室/急诊路径。
  - `risk_level` 参与 Agenda 排序,P0/P1 医学问题压过抗衰/补剂(原则 ⑨)。
  - R7 Checkup Planner 是本需求的下游执行;复用现有复查映射(medication_course_service)+ 5 通道化验录入。
  - 验收:用户能看到一张「健康问题 × 风险 × 下次复查 × 负责科室」的表,且无逾期失访;系统呈现风险分层但**不替代医生诊断**。
- **R14 失败原因捕获 + 协议自纠偏**:完成事件捕获 `skip_reason`(枚举);连续偏离触发系统动作(连 2 天没洗鼻→改时间/查耗材;连 3 天饮水不足→晨起强制装杯;连 7 天体重均线升→下周热量下调;连 2 周鼻炎评分高→建议复查)。措辞「系统哪里设计不够好」,不羞辱用户。复用 InterventionEvent(已有 skipped 状态,补结构化原因)。

---

## 7. 不可变约束(从 AS-IS PRD §6 承继,重设计验收 gate)

> 任何重设计不得破坏。详见 [`docs/PRD.md` §6](../PRD.md) + `AGENTS.md` + `docs/governance/*`。

- **医疗安全**:不诊断/开方/调量;确定性规则裁决安全(LLM 不参与「能否吃/是否告警」);高危 CRITICAL + requires_medical_attention + 引导就医;**引入新药写入前必过 DDI 闸门**;无数据 short-circuit 不让 LLM 编;补剂/抗衰带 claim_boundary;HFE 等硬阻断保留。
- **隐私**:L3 健康/L4 密钥分域加密 + 访问审计;日志脱敏;**所有查询强制 user_id 隔离**;基因 genotype 列加密;Mental Health Tier 5(原始文本不出 specialist/不上外部 LLM);家庭代管须 proxy JWT;用户可导出/删除/撤权。
- **韧性**:审计/记忆/KG 全旁路失败不影响主流程;Twin 缺数据降级而非报错;provider 故障回退。
- **工程**:移动端只走 RN;部署健康度 <35 自动回滚;CI 四道闸 + doc-drift;单文件 ≤500 行(约定)。
- **Codex §8.2 上线前技术 review gate**:旧 `/user/{id}` 越权面、Web XSS、localStorage token、SSH host key、依赖审计。

---

## 8. 复用与技术债(从 AS-IS PRD §7,重设计「收口而非重造」)

**核心判断(两份 PRD 一致)**:四层内核已验证,且 Codex/AS-IS 都确认**多数「看似要造的」已建成 ~80%** —— `TwinSnapshot`/`BiomarkerObservation`/`InterventionCycle`/Daily Plan 反馈/7-30-90 Review/多源 Router 底层(source priority/merge/comparison/recovery_decision)/HealthEvent 事件流/复查映射/N-of-1 实验平台**都已存在**。重设计 = **收敛到 Agenda + 产品化 Router + 协议层统起来**,不是从零补表。

**中年健康盲区(ChatGPT 反馈,产品域缺口,优先级见原则 ⑨)**:
- **力量/肌肉量**(只跑步不够,肌肉是代谢/血糖/抗衰/防伤核心)· **腰围/内脏脂肪**(比体重更反映代谢风险)· **口腔健康**(牙周炎×慢性炎症×睡眠,需洁牙/牙线协议)· **室内空气/环境**(PM2.5/湿度/温度/CO2,影响鼻炎/睡眠/精力,应自动采集)· **精神压力/认知负荷**(精力管理当一等公民)· **补剂-药物相互作用**(记「为什么吃/预期改善哪个指标/是否冲突/何时停评」而非只「吃没吃」)。

**必须在重设计中处理的债(AS-IS §7)**:
- 能力:个人预测模型未落地;多源置信度未回灌 Twin(R3/R11 解决);统一节律日历缺失(R2/R7/R13);长期 PPI 安全规则空白;用药阶段切换 P1b 未做;**慢病/结节复查未产品化(R13 解决,Health OS 分水岭)**;watchOS 无代码(R4);Android 一等缺口。
- 正确性:**决策强度三套口径(rest…peak / zone / intensity / 新 GREEN-YELLOW-RED)未收口** → 重设计统一到 `recovery_decision` 一处,作 Agenda/Protocol 的训练 input(R8);无 LLM-as-judge eval;意图/needs_skill 纯正则脆弱;症状匹配无否定检测。
- 代码债(可独立清):`fuel_strategist` 死代码;Twin `_collectors.py` 过渡债 + cache TTL 注释漂移(5min vs 60s);`family_health.py` 1110 行超预算;`cross_source_validator` σ 死代码;**CLAUDE.md feature-parity 表严重过时(mobile ~15 vs 实况 ~60)**。

---

## 9. 路线图(Codex P0–P5 + 协议层/双轨嵌入)

| 阶段 | 内容(Codex)+ 本文增补 |
|---|---|
| **P0 PRD/IA 收敛** | 确认本蓝图为单一来源;收敛文档(本文 + Codex PRD + AS-IS PRD + plans 的关系钉死);清 §8 代码债中的「parity 表过时 / cache 注释 / fuel 死代码」 |
| **P1 Health Agenda MVP** | R1 Agenda projection API + event table(先 projection 后物化)+ **R11 `HealthProtocol` 模型 + 双轨录入(先做饮水/饮食/用药三域)**;决策灯接 Agenda(收口三套强度口径) |
| **P2 Wearable Router + Training Gate 产品化** | R3 + R8;置信度回灌 Twin;决策灯双 surface(Apple 通知/Complication + Garmin Connect IQ,因跑步两块同戴) |
| **P3 Food Voice Capture + Watch Companion v1** | R4 + R5(= R11 在食物域的实例);腕上协议轨「✓ 完成」+ 一键打标 |
| **P4 Measurement / Checkup Planner** | R6 + R7(= R11 在测量/检查域);病情驱动检查日历(补长期 PPI 监测);连接设备协议 |
| **P5 Outcome Proof + 商业化试点** | R9;Program 级 baseline→latest→target;协议依从×指标改善关联 |

> 建议先做 P1 的 **`HealthProtocol` + 双轨(饮水/饮食/用药)**:最小、即时见价值、且把「最佳实践哲学」落成可演进的抽象,后续各域照搬。

---

## 10. 待拍板(Codex §13 + 本文新增)

沿用 Codex 7 问(Agenda 为核心对象?MVP 聚焦代谢+恢复+测量复查?Watch v1 还是先镜像?Agenda 先 projection 后物化?小程序降级?Web 停新主体验?高风险人审谁担?)。

**本文新增**:
1. **协议层 P1 首批做哪三域?** 建议 饮水 / 饮食 / 用药(覆盖容器、预承诺、被动三种 mechanism,且用药已建大半)。
2. **手工轨在 UI 上的呈现**:默认折叠在协议轨「✓」之后(一点展开),还是 Capture 内并列双 tab?(建议前者:协议默认、手工一点即达)
3. **餐模板从哪来**:用户自建 / 预置(针对糖前+脂肪肝的低 GI 高蛋白模板库)/ 接外部食物库?(建议 v1 预置 + 自建,外部库 v2)
4. **协议轨「默认完成」的边界**:饮水可默认完成只标未达;但用药/测量这类**不能默认完成**(必须显式信号或设备数据),否则违反 R12/Rule#1 —— 各域的「可否默认完成」需逐一拍板。
5. **HealthProblem 首批登记哪些**:建议先录你已知的 P0/P1(脂肪肝/糖前/长期 PPI/血压;若有结节则甲状腺/肺结节)—— 这批直接驱动复查日历与升级。其余慢病(鼻炎等)按需补。
6. **复查/升级的人审由谁担**(同 Codex 第 7 问):自己 / 医生顾问 / 还是 v1 只做「建议就医+生成可带给医生的摘要」?(建议 v1 后者,最安全)

---

*本文为重设计单一事实来源。TO-BE 需求细节见 Codex PRD;AS-IS 现状/不变量/技术债细节见 docs/PRD.md;用药协议见 docs/MEDICATION_AUTOPILOT.md;可穿戴 Router 见 docs/plans/2026-06-15-multi-wearable-health-router-roadmap.md。架构数字以 docs/ARCHITECTURE.md + check_doc_drift.py 为准。*
