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

**本文新增(整合关键)**:
> ⑧ **双轨录入,手工与协议同为一等公民。** 每个健康环节同时支持「**协议轨**」(固定容器 / 预承诺 / 被动设备 → 完成式确认或自动观测)与「**手工轨**」(逐量录入,随时可用)。两轨**写同一份底层记录、产生同一条 agenda 事件**;分析/outcome 不关心数据从哪轨来。协议轨降摩擦,手工轨保兜底与自由——**协议永不取代手工,只是默认更省力的那条路**。

---

## 3. 主循环与信息架构(沿用 Codex,插入协议层)

```text
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
Health Agenda(today/week/month/quarter 的 HealthAgendaItem,由 Program×Protocol 投影)
  ↓
Surface Router(Watch / Mobile / Mac / Web / external agent)
  ↓
Execution Events(completed/skipped/adjusted/auto_observed/confirmed)  ← 协议轨与手工轨在此合流
  ↓
Operating Review(7/30/90 outcome + 个人响应 + 下一议程)
```

**Mobile 5 一等入口(沿用 Codex)**:Today / Agenda / **Capture(双轨录入入口)** / Programs / Review。
**三端分工(沿用 Codex)**:Mobile 主体验;Mac 桌面工作台/导入复盘;Web 后台/报告/历史兼容/Apple Health XML fallback;Watch 腕上执行器;小程序降级历史兼容。

---

## 4. 一等产品对象(Codex 三个 + 本文第四个)

沿用 Codex:**`HealthAgendaItem`**(从现有模型投影的统一执行层,字段见 Codex §5.1,含 `device_context.automation_path: healthkit|garmin|manual|...` —— **manual 本就是一条合法路径**)、**`HealthProgram`**(5 类:代谢/恢复训练/睡眠/用药补剂/检查)、**`Personal Health Router`**(指标级 winning_source/freshness/reliability/agreement/safety_policy)。

### ✦ 4.1 新增一等对象:`HealthProtocol`

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

---

## 6. 需求清单整合(Codex R1–R10 + 本文 R11/R12)

**沿用 Codex R1–R10**(逐条见 Codex §6):R1 Health Agenda 服务端统一层 · R2 时间/日程驱动 · R3 Wearable Router v2 · R4 Apple Watch Companion · R5 Food Voice Capture 协议 · R6 Measurement Automation Protocol · R7 Checkup & Screening Planner · R8 Training Prescription & Readiness Gate · R9 Outcome Proof · R10 三端职责。

**本文新增**:
- **R11 HealthProtocol 协议层 + 双轨录入**
  - 新增 `HealthProtocol`(§4.1),Program 与 Agenda 间的投影层;每域可选/可空。
  - **每个 Capture 域必须同时实现协议轨 + 手工轨**,两轨写同一 `source_models` + 同一 agenda event;验收:同一 item 用任一轨完成,Today/Agenda/Review 表现一致,outcome 不区分来源。
  - 协议参数可被 `decision_light`/`cadence_engine`/`safety_guardian` 动态调(如训练强度、检查提前)。
  - R5/R6/R7 是 R11 在「食物/测量/检查」域的具体实例,应统一在 `HealthProtocol.mechanism` 下表达,避免各做一套。
- **R12 协议健康度护栏**:协议轨「完成式确认」不得退化为「假装完成」——若协议依赖被动设备而设备无数据(如戒指昨晚没戴),不得静默判为完成,须产 `data_quality` agenda item(对齐 Codex R3 设备缺失项 + AS-IS Rule #1)。

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

**必须在重设计中处理的债(AS-IS §7)**:
- 能力:个人预测模型未落地;多源置信度未回灌 Twin(R3/R11 解决);统一节律日历缺失(R2/R7);长期 PPI 安全规则空白;用药阶段切换 P1b 未做;watchOS 无代码(R4);Android 一等缺口。
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

---

*本文为重设计单一事实来源。TO-BE 需求细节见 Codex PRD;AS-IS 现状/不变量/技术债细节见 docs/PRD.md;用药协议见 docs/MEDICATION_AUTOPILOT.md;可穿戴 Router 见 docs/plans/2026-06-15-multi-wearable-health-router-roadmap.md。架构数字以 docs/ARCHITECTURE.md + check_doc_drift.py 为准。*
