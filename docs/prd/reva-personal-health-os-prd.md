# Reva Personal Health OS — 全局产品需求说明书(PRD · 合并统一蓝图)

> **状态**: **v1 合并基线 + 2026-08-15 Mobile IA reconciliation。这是唯一全局权威 PRD**,已把以下全部输入合并、内联成一份自洽文档(下列输入自此降级为历史素材,一切以本文为准;focused feature 的已接受增量裁决通过本文件 §0 回写后生效):
> 1. **TO-BE 目标形态** ← Codex 全局 PRD(HealthAgenda / HealthProgram / Router / R1–R10 / WSCLA / 5 入口)
> 2. **AS-IS 现状基线 + 不变量 + 技术债** ← docs/PRD.md(逐子系统逆向 review,~85% 已建成的复用清单)
> 3. **容器化/协议化最佳实践 + 手工/协议双轨** ← 产品决策
> 4. **多轮外部分析**:ChatGPT Pro 8 层框架 + HealthProblem;多模型(数据/状态/计划/执行/复盘五层 + 慢病抗衰循证)→ L1–L4 健康定义、打卡三铁律、状态机护城河、三级通知、n=1 严谨化、临床默认配置附录、诚实声明。
>
> **本 PRD 的两个原创内核**:① 在 `HealthAgendaItem` 之上引入一等对象 **`HealthProblem`(医学问题登记)** 与 **`HealthProtocol`(协议层)**,形成 `Problem → Program → Protocol → AgendaItem` 完整层级;② **双轨录入模型**(协议轨 + 手工轨,写同一份数据、同一议程,手工永不被取代)。
>
> **读法**:§1–§3 定方向(定位/原则/架构);§4 一等对象;§5 双轨录入;§6 需求 R1–R16(全自洽);§7 不变量(验收 gate);§8 复用与债;§9 路线图;§10 待拍板;附录 A/B 临床默认配置与同行参考;§11 诚实声明。

---

## 0. 2026-08-15 Mobile IA Reconciliation

Mobile 已于 2026-07-03 落地 Chat-first agent-native shell:`/(tabs)/index` 重定向 `/chat`,底部 Tab Bar 隐藏。
因此本文 v1 所称“Today / Agenda / Capture / Programs / Review 五个一等入口”自此解释为**五个上下文能力目的地**,
不是五个并列 tab 或首页。唯一一级日常入口是小巴 Chat shell;它承载 Health Day 摘要、查询、快速执行和路由,
再按上下文进入 Today/Agenda/Capture/Programs/Review 详情。

Health Day v2 focused contract 见 `docs/specs/active/2026-08-15-quiet-proactive-health-day.md`。它不得改变本文的一等健康对象、
医疗边界或跨端 ownership;本文后续历史段落若仍把五能力写成并列入口,以本节的 Chat-first 解释为准。

## 1. 北极星与定位(沿用 Codex,确认)

- **定位**:Reva Personal Health OS —— 面向 35–60 岁中年代谢/恢复人群的个人健康操作系统。承诺不是「回答健康问题」,而是「帮你把每天/每周/每季该做的健康行动安排好、在对的设备上提醒执行、用指标验证是否真变好」。
- **第一目标用户画像(产品锚点)**:糖前(HbA1c 6.3)× 脂肪肝 × 长期 PPI × 12 药 × 同戴 Apple Watch Ultra 3 + RingConn Gen3 + Garmin Enduro 2(跑步两块同戴)。多模型进一步收窄为「**35–55 高知中年男性,精力恢复 + 慢病自动化管理**」;**对外回避「抗衰」措辞**(已被 NMN/医美污染)。

### 1.1 健康的四层定义(多模型整合,L1–L4)
| 层 | 含义 | 关键指标 |
|---|---|---|
| **L1 体征** | 当下参数 | 体重/腰围/血压/RHR/HRV/SpO2/深睡比 |
| **L2 慢病** | 病灶进展 | 鼻炎发作频率、脂肪肝、肾结石、甲状腺/肺结节、ALT/GGT/尿酸 |
| **L3 精力** | 每日可用能量 | **主观精力 0–10(北极星)**、深度工作时长、午后困倦 |
| **L4 Healthspan** | 10 年复利 | **ApoB、Lp(a)、hs-CRP、HbA1c、同型半胱氨酸** |

### 1.2 双层北极星
- **结果北极星(最终裁决)**:**L3 主观精力 0–10 的 30 日移动均线** + **L4 抗衰生化(ApoB/hs-CRP/HbA1c)**;评价标准只有一个——**3–6 个月后 L3 与 L4 能否同时改善**。
- **行为北极星(过程量,= 原 WSCLA)**:每周完成的、**安全 + 证据可追溯 + 被安排 + 已执行 + 可验证**的健康行动闭环数量。
- **护城河判断**:只在 L1 转的产品 = Apple Health 看板,卷不过原生;**真壁垒在 L3+L4 的个人纵向归因**(状态机 + 「打卡→改变下一次决策」闭环)。

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
> ⑬ **打卡三铁律(多模型决断版)**:**被动 > 主动**(传感器能抓的绝不让用户点)· **物理 > 数字**(2000ml 杯/7 格药盒/Box 餐让「目标完成」物理性完成)· **可归因 > 连续天数**(每条数据必须**至少触发状态机一个分支**,否则就是噪声;不为 streak 服务,只为「3 个月后能告诉你做了 X 所以 Y 改善」服务)。这是原则 ⑧⑩⑪ 的统一收口,也是协议轨的理论根基。
> ⑭ **数据自持(数字资产主权)**:原始数据进**自己的 DB**(极简时序 schema `ts,category,metric,value,unit,source,confidence`),设备/SaaS 只作显示终端与采集源(**单向推 Garmin,不让 Garmin Connect 成为唯一存储/黑洞**);被动传感器矩阵优先(腕表+戒指+床垫+CO2+季度 CGM);基因 raw data 端到端加密、**不上传通用 LLM**。设备生命周期 < 数据生命周期。

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
>
> **对齐多模型 5 层工程视图**:数据层(自持 Data Lake + 被动传感器矩阵,原则 ⑭)· **状态层(= 真护城河:DAG + 规则引擎 + LLM「信息索取」三明治,LLM 不出诊断只索取信息;PRS/PGx 作先验权重调阈值;干预设 7–14 天 washout)** · 计划层(Program×Protocol 供应链工程)· 执行层(三级通知预算)· 复盘层(15 分钟 3 问 + n=1 A/B/A/B + L1↔L4 对账)。我们现有 orchestrator/specialists 确定性裁决 + personal_baseline 即状态层雏形;缺的是 washout/对账/状态机回测的严谨化。

**Mobile 单一主壳 + 5 个上下文能力目的地(v2 reconciliation)**:小巴 Chat shell 是唯一一级日常入口;Today / Agenda / **Capture(双轨录入入口)** / Programs / Review(其中 Programs 视图含「健康问题」子页)由主壳按上下文展开,不是并列 tab。
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

## 6. 需求清单 R1–R16(自洽,本节即完整需求)

**R1–R10(目标形态需求,源自 Codex,已内联)**:
- **R1 Health Agenda 服务端统一层**:把 Daily Plan/ActionCard/InterventionCycle/Reminder/Medication/Supplement/Training/Measurement/ReviewSchedule 统一成可查询/执行/审计的议程;`GET /agenda/today`、`/agenda/range`、`POST /agenda/items/{id}/events`、`/agenda/rebuild`;item 引用 source object 不复制业务事实;三端看到同一批 item,任一端完成全端同步。
- **R2 时间/日程驱动**:支持时间窗(起床后/饭后/运动前/睡前/周末/季度复查)+ cadence(日/周/月/季/8-12 周/异常触发)+ event-triggered(饭后 20-40min/训练后/睡眠同步后/体检上传后)+ quiet hours + calendar-aware 占位。
- **R3 Multi-Wearable Router v2**:指标级输出 winning_source/agreement/freshness/confidence;训练决策用 recovery_decision 的 green/yellow/red 作 Agenda input;冲突降置信不平均;设备缺失生成 data_quality item;安全指标保留多源证据。
- **R4 Apple Watch Wrist Companion**:Today Status(灯+置信+最重要行动)/Action Feedback(完成/跳过/稍后/调整)/Food Voice Capture/Quick Record/Smart Stack-Complication/分级通知;**不做**腕上长对话/影像/本地诊断/常驻监听;不开 iPhone 也能完成今日最重要反馈。
- **R5 Food Voice Capture 协议**:语音记食物成稳定事实流(raw_text/source/meal_type/foods[]/confidence/risk_tags/confirmation_state);v1 不新表,写 DietRecord + raw 入 notes;腕上最多追问 1 个问题;不追克级精确,优先长期行为分析。
- **R6 Measurement Automation Protocol**:每个测量 item 带 automation_path(vendor/HealthKit 自动 > 外部设备 > 手动 > 提醒上传);袖带血压/智能秤/化验为 ground truth,穿戴趋势只触发提示;过期指标自动进 Agenda。
- **R7 Checkup & Specialty Screening Planner**:按年龄/性别/家族史/既往异常/症状/可穿戴异常/医生指令生成检查建议(区分 wellness/复查/就诊/急性红旗),输出 项目+时间窗+理由+来源+风险边界+是否需医生确认,全进 Agenda;不越界为诊断。
- **R8 Training Prescription & Readiness Gate**:recovery_decision green/yellow/red 作训练 gate;输入 RingConn 睡眠/HRV/SpO2/皮温 + Garmin readiness/load/recovery + Apple 活动/主观疲劳 + 症状;训练前 30-60min 在 Watch/Mobile 出现;训练后捕获 RPE/疼痛 + Garmin workout 事实;**急性病/低氧/症状优先于 Garmin readiness**。
- **R9 Outcome Proof**:每个 Program 绑 primary/secondary metrics;每个 action 标是否影响 outcome;7/30/90 复盘 = 执行率+指标变化+复查结果+个人响应强弱+下周期调整;temporal association 明确「非因果」;代谢周期输出 baseline→latest→target。
- **R10 三端职责**:Mobile 主体验(Chat-first 小巴单一主壳,按上下文进入 Today/Agenda/Capture/Programs/Review + HealthKit/Watch 配对/语音/照片饮食);Mac 深度工作台(快速记录/导入/Agent 长对话/Trace,不复制健康判断);Web 后台/报告/历史兼容/Apple Health XML fallback;Watch 腕上执行;Agent/MCP 受控外部入口(最小权限+审计)。

**R11–R16(本 PRD 新增)**:
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
- **R15 三级通知预算(多模型)**:提醒是稀缺中断预算。**P0 必响应**(腕表强震+手机:处方药/复查当天/异常血压,**≤3 条/周**)· **P1 可忽略**(腕表轻震:运动开始/睡前降光/补水不足,不要求确认)· **P2 纯日志**(不推送:步数/体重同步,周复盘看)。睡前 90min 后仅 P0;周主动提醒 ≤15 条。升级现有 `proactive_coordinator`(从单一全局周预算 → 分级预算)。
- **R16 n=1 严谨化(多模型)**:升级现有 episode/intervention_cycle 为 **A/B/A/B crossover + 3–14 天 washout + 7 日移动均线/30 日基线 Z-score 去噪 + L1↔L4 季度对账**(L1 代理指标失真则换);新干预 14 天评测通过才固化进状态机,失败回滚。涉处方药/激素的实验必须医生在场。诚实标注置信度(见 §11)。

- **R17 任务线 / JITAI 执行层(时间×日历驱动的引导式执行 + 被动采集 + 即时归因)**
  - **定义**:`HealthAgendaItem` 到点(或 event-triggered)→ **readiness 门控决策** → Surface Router 选面 → **引导式执行**(音视频/语音/节拍)→ 双轨采集(被动优先)→ **即时反馈 + 周度结果归因**。是 R2(时间/事件触发)× R4(Watch)× R8(readiness gate)× R11(协议)在「执行」环节的合流,**运动域先行**。学理对应 **JITAI(Just-In-Time Adaptive Intervention)**——身体活动域有循证支持;但须守下列五条硬裁决(它们决定这个需求成败)。
  - **裁决①「Agent 而非闹钟」**:到点 ≠ 硬推。必须经 `recovery_decision`/`MovementCoach` 门控——RED → 改拉伸/休息(不推力量);日历冲突 → 顺延空档;按个体进阶(上次完成度/RPE/ACWR)调量与难度;低电量/睡眠差降量。**「在低 readiness / 会议中硬推俯卧撑」= 退化成闹钟,验收不通过。**
  - **裁决②「Wearable-triggered, multi-surface-executed」**:腕上发起 + 被动计数(次数/HR/组间歇)+ 语音节拍 + 震动;音视频教程走手机/投屏(表盘太小不塞视频);voice 贯穿(锻炼手不空)。真 wearable-first 内核 = **传感器替代记录**(做完自动记),不是「在手表上做一切」。
  - **裁决③「降摩擦不劫持(autonomy)」**:**不自动打开 App 劫持屏幕**;是可一眼接受的 nudge(`俯卧撑·3×15·开始?`),点了才进;给「现在做 / 晚点 / 今天跳过(带原因)」,失败原因驱动协议自纠偏(R14)。守自我决定论:外部强制短期推依从、长期削内在动机 + 招反感(尤其高知人群)。提醒守 **R15 三级预算**。
  - **裁决④「循证内容 + 确定性进阶,LLM 只合成」**:动作要领/教程来自**带证据级的内容库**(exercise content,`evidence_tier` + 媒体引用 + 进阶规则);进阶按确定性规则(ACWR/RPE/完成度);**LLM 只做个体化讲解合成,不发明 form cue / 处方**(错 form → 受伤 = 运动版医疗边界,守原则①确定性优先)。覆盖 **力量×2 + 柔韧 + Z2**(不只跑步,补中年肌少/柔韧盲区,见 §8)。
  - **裁决⑤「飞轮」**:运动域**反馈环最短**(当天完成感 / RPE,几周力量、HRV、RHR 变化)+ **被动可采集** + **可归因** → 正踩三铁律(被动>主动、物理>数字、可归因>连续天数,原则 ⑬)。环:腕上 nudge → 多端引导执行 → 被动采集 → 当天即时肯定 → 周度结果归因(标**相关非因果**)→ 信任↑ → 授予更多自治(让 agent 排课表)→ 转更快。与首页「今日时间线」(已上线)同一飞轮:时间线=看见该做+证明有用,任务线=到点零摩擦执行掉。
  - **对象/数据**:复用 `HealthProtocol`(domain=training/activity 的 mechanism + implied_quantity + verification)+ `HealthAgendaItem`(time_window/cadence/event_triggered)+ `recovery_decision`(gate)+ 双轨 Execution Event;**新增**动作内容库(exercise content:`evidence_tier` / 媒体引用 / 进阶规则)。
  - **验收**:① 到点项经 readiness 门控(RED 不推力量,改拉伸/休息);② 单域(拉伸或俯卧撑)端到端:nudge → 接受 → 引导执行(语音 +(手机)视频)→ 双轨记 → 当天完成卡 + 周度归因(标非因果);③ **不 hijack**(用户不点不进);④ 内容来自库非 LLM 现编;⑤ 守 R15 预算。
  - **首批域**:**拉伸 或 俯卧撑**(无器械 / 在家 / 短 / 可计数 / 低受伤),验证范式后推 跑步 / 力量 / Z2。

- **R18 手表作为时间线执行器(R4 × R17 × R2 交叉)**
  - **定位**:手机 = 规划面 + 证明面(完整时间线、结果归因);**手表 = 执行面 + 被动采集面**。"精细日程"的颗粒度(时间窗 + 事件触发:服药/饮水/饭后散步/拉伸/睡前降光)只有手表能**不打扰地**承接(在身上、always-on、传感器知情境)。手表是让精细时间线从"看板"变成"自动发生"的那块屏——不是手机缩小版,是飞轮的**执行 + 采集引擎**。
  - **功能矩阵(按 JITAI 闭环 × 三铁律排序)**:
    - **★1 Complication = 时间线脊柱**:表盘一眼「下一项该做什么 + readiness 灯 + 待办数」。复用 `RevaComplication`。最高频曝光,不开 App 就知道现在该干嘛。
    - **★2 到点 nudge + 三出口**:时间窗/事件触发轻震 + 一眼卡片(`俯卧撑 3×15 · 现在做/晚点/今天跳过(带原因)`)。原因驱动 R14 自纠偏。**不劫持**(抬腕可接受,不点不进)。
    - **★3 腕上引导执行**:运动自动计数(CoreMotion)+ 实时 HR(`HKWorkoutSession`)+ 组间歇震动节拍 + 一键完成(R17 在手表;手机放视频)。被动>主动。
    - **★4 被动采集自动打勾**:workout 自动检测、HRV/RHR/SpO2、心率异常 → 时间线对应项**自动完成/记录**(被动>主动核心,做完不用点)。
    - **★5 服药/补剂到点 + 一键「已吃」**:物理药盒/分装到点轻震,腕上一键确认(物理>数字)。
    - **★6 事件锚点触发**:饭后 20-40min 散步、睡前 90min 降光、晨起户外光(R2 event-triggered;手表知道"刚记了一餐/到睡点")。
  - **第一刀**:**★1 Complication + ★2 到点 nudge 闭环**——把"下一项该做什么"放表盘 + 到点抬腕可执行。`TodayStatusView` 已显示 `topAction`/`agenda.pending`,扩成"按时间窗推下一项"即可。
  - **边界**:守 R4 不做(腕上长对话/视频教程/本地诊断/常驻监听);守 **R15 三级预算**(P0 强震 ≤3/周、P1 轻震、P2 纯表盘不推)——别把每项推成通知=报警疲劳;守 autonomy 不劫持;续航走 HealthKit 后台投递,不常驻高频轮询。
  - **飞轮闭合**:手表补上 enter 键飞轮**最难两环**——「到点零摩擦执行」(★2★3)+「被动采集」(★4):做完自动记 → 时间线自转、结果可归因 → 手机端证明 → 信任↑ → 授予更多自治。
  - **验收**:① 表盘 Complication 显示下一项 + readiness;② 一个时间窗项端到端:到点轻震 → 抬腕一眼 → 现在做/跳过(带原因)→(运动类)腕上计数 + 一键完成 → 时间线**自动打勾**;③ 不 hijack;④ 守 R15 预算不刷屏;⑤ 被动采集项做完无需手动点。

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
- 多模型新增能力缺口:**数据自持/原始数据进自有 DB + 单向推 Garmin**(原则 ⑭,当前依赖 Garmin Connect/HealthKit 透传)· **被动传感器矩阵扩容**(戒指/床垫/CO2 室内环境/季度 CGM)· **三级通知预算 P0/P1/P2 + 硬上限**(R15,当前 proactive_coordinator 只有全局周预算无分级)· **n=1 严谨化**(A/B/A/B crossover + washout + L1↔L4 对账,当前 episode/intervention_cycle 无 washout/对账)· **力量训练域缺失**(只跑步,抗肌少盲区)· **基因解读外包 PRS/PGx**(SLCO1B1→他汀,不自研 LLM 解读)。
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

## 附录 A:临床默认配置(多模型 + 循证,填充 HealthProblem.red_lines / follow_up 与 HealthProtocol 默认参数)

> 证据级 **[A]** 多 RCT/Meta+强指南 · **[B]** 单 RCT/大样本观察 · **[C]** 机制合理人体证据不足。这是 OS 的**默认配置不是医嘱**;个体化(基因/合并症/用药)永远 > 通用协议。**有红线交医生,Agent 不解读影像、不开方。**

### A.1 L2 慢病协议(进 HealthProblem)
- **鼻炎**:盐水冲洗 1–3 次/日(**蒸馏/无菌/煮沸冷却水**,CDC)+ **鼻用激素**(糠酸莫米松/氟替卡松,ARIA/EPOS 一线,全身吸收<1%)+ sIgE 一次定型 + STOP-BANG≥3 必做居家 PSG + 卧室 HEPA;单一过敏原控制不佳→SLIT 3 年[A]。🚨 单侧鼻塞+鼻出血/嗅觉丧失>3 月/息肉激素 12 周无效→ENT。
- **脂肪肝 MASLD**:F0-F1 可逆,**F2+ 才是死亡率拐点**;减重 7%→MASH 缓解、10%→纤维化改善[A];Z2+力量、黑咖啡 2-3 杯、**酒精目标 0**、砍液体糖;FibroScan 每 1-2 年;司美格鲁肽 2.4mg 入 MASH F2-F3[A] AASLD 2025-11 (PMID 41201884)。🚨 LSM≥10kPa/FIB-4≥2.67/ALT 持续>2×ULN→肝病科。
- **血脂一级预防**:ASCVD 由 **ApoB 颗粒数**驱动(LDL-C 在高 TG/糖前低估);ApoB<80(高危<65)、**Lp(a) 一生一次**、**CAC 40+ 一次**;阶梯 他汀→依折麦布→PCSK9i/Inclisiran;TG150-499+他汀者 Vascepa 4g[A]。🚨 LDL>190 疑 FH;胸痛→急诊不经 OS。
- **结节随访(避免过度活检)**:甲状腺 TIRADS TR4≥1.5cm/TR5≥1cm 才 FNA,<1cm 不查不焦虑;肺结节 Fleischner/Lung-RADS 实性<6mm 不随访、GGN≥6mm 6-12 月 CT 稳定 5 年才停;**保留原始影像不只存结论,不让 Agent 解读影像**。
- **肾结石二级预防**:第二次/高危→24h 尿液[A];**尿量≥2.5L/日(不是喝水量)**、柠檬酸钾、钠<2.3g、**不要低钙**(饮食钙 1000-1200mg 同餐)。🚨 发热+腰痛+结石=急诊。

### A.2 L4 抗衰真伪表(进证据级门控)
| 干预 | 证据 | 裁决 |
|---|---|---|
| 运动 + 减重 | [A] | **一级方阵,无可替代** |
| GLP-1(司美格鲁肽) | [A] SELECT/FLOW/MASH | **指征内一级方阵**(BMI≥27+代谢病/MASH/ASCVD),必配抗阻+蛋白 1.6g/kg 防肌少 |
| ApoB/Lp(a)/CAC 三件套 · PGx(SLCO1B1→他汀) | [A] | **必做 / 最成熟 PGx 落地** |
| TRT | [A] 适应症内 | 两次晨 T<300+症状由专科评估,不自购 |
| Rapamycin [B-] / Metformin 抗衰 [B 矛盾] / NMN·NR [C] / Senolytics [C] | 降级 | **旁路:不自购、非糖尿病不吃 Metformin、NMN 营销>证据** |

### A.3 监测频率日历(进 cadence_engine 默认)
日:体重/HRV/RHR/SpO2/精力 0-10 · 周:腰围/Z2 时长/力量次数/鼻炎发作日 · 月:血压 7 日均值/体成分 · 季:HbA1c/肝酶/eGFR(+季度 2 周 CGM n=1)· 年:全套血脂(含 ApoB)/hs-CRP/维 D/睾酮/TSH/PSA(50+)/FibroScan/甲状腺腹部超声/皮肤镜 · 一次性:**Lp(a)/PGx/PRS/居家 PSG/CAC(40+)** · 5-10 年:结肠镜(45+)/LDCT(高危)。**不必做**:全身 PET/MRI 商业包、肿瘤标志物大套餐、头发微量元素。

### A.4 协议默认参数(进 HealthProtocol.implied_quantity)
- **饮食**:蛋白 1.6g/kg(每餐 35-50g)· 纤维 25-35g · 酒精周预算 ≤2 次×2 杯睡前 4h 停 · 咖啡 14:00 后无咖啡因 · Box 餐筛选 蛋白≥35g/蔬菜≥300g/钠<800mg/可复购 4 周。
- **运动**:Z2×3(≥150min/周)+ 力量×2 + HIIT×1 + 极化 80/20;降级规则(睡<6h/RHR+8/HRV 低/关节痛>3/连 2 天疲劳→降级)。
- **睡眠**:卧室 18-19℃ · CO2<800ppm · 起床 30min 内户外光 10-20min · 睡前 90min 降光 · 周末起床偏差<30min · 午睡≤20min。

---

## 附录 B:同行参考(抄什么 / 防什么)
Blueprint(抄:测量密度+自动化 SOP/盒餐;防:数十补剂叠加+逆龄叙事)· Attia/Outlive(抄:ApoB 死守线+VO2max+Z2/力量+四骑士)· Levels(抄:CGM 做 n=1;防:追求血糖全平)· WHOOP/Oura(抄:极简单分输出+戒指消灭摘表;防:算法黑盒只看趋势)· Promethease/SelfDecode(抄:PRS+PGx 外包;防:通用 LLM 解 SNP=占星)。

---

## §11 诚实声明与风险(魔鬼代言人,守原则②不假装)

多模型自我攻击,**保留以校准野心**:
1. **「状态机有护城河」可能是工程师自我感动** —— L2/L4 协议全来自公开指南,任何团队接 LLM+指南 2 周可复刻;真正不可复制的是**你的纵向数据 + 习惯惯性**,前提是真能跑 3 年。
2. **n=1 归因可能是事后叙事偏差** —— 多变量混杂+短时序+均值回归,A/B/A/B 在医学界都是边缘设计;**只追求「决策有用」(Bayesian 先验更新),不假装统计显著,且必须诚实标注置信度**(对接 ⑫ 证据级)。
3. **工程化救不了生活动荡** —— Box 餐遇出差停摆、药盒遇孩子生病停摆;**社会决定因素(配偶/收入/工作强度/练习伙伴)> 个人 OS**;OS 只承诺把「非动荡日」执行率从 40%→80%。
4. **季度自检(写进复盘层)**:「若删掉这套 OS,只保留『每周睡 7h×5 + 练 5h + ApoB<80 + 酒≤2』,我的 L3/L4 会差多少?」差不多 → OS 的边际价值是工程兴趣本身,**这没问题,但要诚实标注**,并警惕「量化焦虑」反噬精力(必要时主动『关掉 OS』也是一种协议)。

---

*本文是**唯一权威 PRD**,已自洽合并 Codex 全局 PRD(TO-BE)、docs/PRD.md(AS-IS 基线/不变量/技术债)、协议双轨与多轮外部分析——这些输入降级为历史素材,一切以本文为准。子领域深规可继续参考:用药 docs/MEDICATION_AUTOPILOT.md、可穿戴 Router docs/plans/2026-06-15-multi-wearable-health-router-roadmap.md。临床附录 A 是默认配置非医嘱。架构数字以 docs/ARCHITECTURE.md + check_doc_drift.py 为准。*
