# 多源可穿戴健康 OS:置信度脊柱 + 决策引擎 + Ground-Truth 校准

> **状态**: 规划草案 (2026-06-15)
> **关系**: 本文是**引擎/大脑层**;[`2026-06-15-apple-watch-ultra3-health-wrist-companion.md`](2026-06-15-apple-watch-ultra3-health-wrist-companion.md) 是本引擎的 **Apple 输入/输出 surface 层**(语音食物、companion app、通知投递)。两份组合,不重叠:那份回答"腕上怎么输入/确认",本份回答"三块设备的数据怎么融合成一个可信的每日决策"。
> **设备**: Apple Watch Ultra 3(交互层)+ RingConn Gen3(夜间恢复基线)+ Garmin Enduro 2(训练/户外事实)+ iPhone/OpenClaw(大脑)。

---

## 0. 核心判断(先钉死)

四轮头脑风暴(含多份外部评审)反复指向"做一个 Multi-Wearable Personal Health OS"。但对照本仓库代码:**这套 OS 的后端已经建成约 85%。** 真正的空间不是"造系统",而是**补四层薄的**:

1. **置信度脊柱** —— 把三设备+个人基线+主观事件揉成一个会 gate 决策的统一可信度。
2. **决策灯 + 双 surface** —— "今天 GREEN/YELLOW/RED + 为什么 + 一个动作",送到 Apple(通知/Complication)**和 Garmin(Connect IQ data field)**。
3. **腕上输入线** —— Action Button / 语音 → 写入**已存在的** `HealthEvent` 事件流。
4. **Ground-Truth 校准** —— 用已入库的 CGM/化验/血压去锚定、校准可穿戴趋势。

**Killer MVP**: 多源恢复/训练决策引擎 —— 每天回答一句"今天身体/训练怎么安排"。它几乎全是**在既有数据上做合成 + surface**,新基建极少。

---

## 1. 定位:三设备分工(已是代码现实)

| 设备 | 角色 | 不该承担 |
|---|---|---|
| Apple Watch Ultra 3 | 主动交互:输入、提醒、Action Button、Siri/App Intents、ECG/AFib、急性事件 | 不当"睡眠/训练的唯一真相" |
| RingConn Gen3 | 安静的夜间恢复基线:睡眠/HRV/SpO2/腕温,14 天续航,低打扰 | 无开放 API、震动不可编程 → **不做 ring app** |
| Garmin Enduro 2 | 训练/户外事实:训练准备度、负荷(ACWR)、VO2max、双频 GPS、长续航 | 不做日常 AI 聊天/高频提醒中心 |
| iPhone / OpenClaw | 大脑:融合、判断、记忆、调度、医生摘要 | — |

> Watch 是 Personal Health Agent 的**腕上接口**,不是 Watch 版健康 App。

---

## 2. 不重造,补四层 —— "已建成"对照(本文最重要的一节)

外部评审把下列当作"要造的护城河/机会";对照代码,**多数已是既成事实**:

| 评审说的"机会" | 仓库现状(文件) | 判定 |
|---|---|---|
| Multi-Wearable Router(per-metric 谁说了算) | `backend/app/services/device_source_priority.py`(METRIC_SOURCE_PRIORITY:睡眠→ring/训练→garmin/活动→apple;SpO2 取最差值)+ `multi_source_merger.py` | ✅ 已建 |
| 用个人基线不看绝对值(7/30/90 天 z-score) | `backend/app/services/personal_baseline.py`(#170 已合,接进 Twin) | ✅ 已建 |
| 跨源一致性裁决 | `backend/app/agents/cross_source_validator/specialist.py`(差异过大→标可疑+暂以谁为准) | ✅ 已建(只裁决,见 L1) |
| N-of-1 个人实验平台 | `models/episode.py` + `models/intervention_cycle.py` + `services/intervention_cycle_service.py` + `services/episode/` + SupplementAdvisor 12 周闭环 | ✅ 已建 |
| 统一事件流 / ETL 数据护城河 | `models/health_event.py`(`HealthEvent`:confidence + pending/auto_confirmed/confirmed/corrected/dismissed 状态机 + voice/nfc/ble 源 + 目标表回写;`EventSource` 设备注册表) | ✅ 已建(惊人完整) |
| Ground-truth 点测(CGM/血压/化验) | `services/cgm/` + 6 条 CGM 安全规则、`medical_exams`、BP/体重 collectors | ✅ 已接入 |
| Actionable 腕上通知(完成/推迟/跳过) | `mobile/services/behaviorLoopReminders.ts`(#175,镜像到 Watch,后台 POST 事件) | ✅ 已建 |
| 每日"现在最该做的一件事" | `services/daily_operating_plan.py` | ✅ 已建 |
| 症状→传感器因果 | `agents/longitudinal_analyst`(干预事件×指标因果叙事) | ✅ 已建(缺事件输入,见 L3) |
| Siri / App Intents | `mobile/ios/HealthPilot/SiriIntents/HealthPilotSiri.swift`(3 个 intent)+ `SharedKeychain` | 🟡 部分 |
| 打扰预算 / 提醒不泛滥 | `services/proactive_coordinator.can_notify_proactively()` | 🟡 有原型(缺学习,见 L2) |

**结论:别再问"造什么"。下面四层是仅剩的薄层。**

---

## 3. 四问

**用户价值**:你戴三块设备(被动数据极充足),却**缺一个会权衡可信度、给出一句可执行决策的大脑**。现在的痛点不是"没数据",是"三块设备打架时信谁 + 今天到底该练还是该休"。做到极致:每天 0 思考,看一眼手腕/Garmin 就知道今天怎么安排身体。

**边界(不做)**:不做 RingConn app(无 API);不做 Garmin 上的聊天机器人(只做 data field);不做诊断/改药量;不重造已建的 router/baseline/N-of-1/事件流;不在 Watch 上跑大模型。

**最简实现**:决策引擎 = 在**已有**的 RecoveryCoach readiness + Garmin training_readiness + personal_baseline + CrossSourceValidator 之上加一个**置信度合成 + 决策灯**服务,经现有通知/Complication(#175)和新增 Garmin data field 投递。新数据依赖极小。

**风险**:RingConn 数据可得性(只能走 Apple Health/导出);Garmin Connect IQ 是独立技术栈(Monkey C);watchOS 26 Controls 能否免 App 调 intent 待实测;提醒泛滥(多设备最大风险)→ 必须经 proactive_coordinator gate;医疗边界(分级措辞,不诊断)。

---

## 4. 数据流(端到端)

```
RingConn ─┐ (Apple Health/导出)
Garmin  ──┤ (Garmin Connect / Apple Health)        Apple Watch ─┐ (HealthKit)
Apple ────┘                                          主观事件输入 ─┘ (Action Button/语音→HealthEvent)
        ↓ ingest(已有:appleHealth 多源拆分 / garmin collectors)
   Per-metric Router(device_source_priority)        ← 已建
        ↓
   ┌─ L1 置信度脊柱(Device Agreement + 基线偏离 + 主观一致)── ← 新增(扩 CrossSourceValidator)
        ↓
   ┌─ L4 Ground-Truth 校准(CGM/化验/血压 锚定/校准趋势)── ← 新增
        ↓
   多源恢复/训练决策引擎  → GREEN/YELLOW/RED + 置信度 + 一个动作   ← 新增(合成 RecoveryCoach+Garmin+baseline)
        ↓                          ↓                         ↓
   Apple(通知/Complication #175)  Garmin(Connect IQ data field)  iPhone/OpenClaw(展开解释/医生摘要)
                                                                ↑ L3 腕上输入回灌 HealthEvent → LongitudinalAnalyst 因果
```

---

## 5. 四层补全详解

### L1 — 置信度脊柱(最高 ROI,多设备真正的杠杆)
现在:`CrossSourceValidator` 裁决"信谁",`HealthEvent.confidence` 是单事件级,`personal_baseline` 给 z-score —— 但**没有把它们合成一个会 gate 决策/告警的统一可信度**。
- **新增** `RecoveryConfidence / DeviceAgreementIndex`:三设备同向(HRV↓ + RHR↑ + 深睡↓ + 主观疲劳)→ 高置信"恢复不足";仅单设备异常 → 低置信、不升级。
- **回灌 Twin**:成为一等信号,下游(Safety/决策引擎/预测模型)读它——**临界告警若被另两块否定则降级,减少假阳性**(单设备做不到)。
- 复用:`cross_source_validator`、`personal_baseline`、`HealthEvent.confidence`。新增:合成函数 + Twin freshness/confidence 分区扩展。

### L2 — 决策灯 + 双 surface
- **新增**决策服务:合成 RecoveryCoach readiness + Garmin training_readiness + L1 置信度 + Daily Plan → `{light: green/yellow/red, confidence, reason[], next_action}`。
- **Apple surface**:复用 #175 actionable 通知 + 新增 Complication(常显恢复色)。
- **Garmin surface**:**Connect IQ data field / glance** 训练前/中显示 `AI Load Gate GREEN/YELLOW/RED`——直接落在你跑步戴的 Garmin 上(解决"训练戴 Garmin 不戴 Apple")。
- **提醒不泛滥**:决策灯的推送经 `proactive_coordinator` 评分 gate;进化成 importance/urgency/context_fit/接受率/忽略率 评分(目标:提醒越来越少越准)。

### L3 — 腕上输入线(接已有 HealthEvent,不造新系统)
- `HealthEvent` 事件流(含 confidence + 确认/修正状态机 + EventSource)**已就绪**。缺的只是腕上低摩擦采集:Action Button / Control / 语音 → 写 `HealthEvent`(主观:疲劳/头痛/心悸/喝酒/咖啡/压力 + 时间戳 + 当时上下文快照)。
- 价值:被动数据满了,**缺的就是主观标签和"为什么"**;喂 `LongitudinalAnalyst` 已有的"干预事件×指标因果叙事"。
- 食物语音那条由 [wrist-companion 文档](2026-06-15-apple-watch-ultra3-health-wrist-companion.md) 负责,本层只负责"非食物主观事件"的通用捕获合同。

### L4 — Ground-Truth 校准
- CGM/化验/血压/体重**已入库**,但未用于**校准**可穿戴趋势。
- **新增**校准回路:血压计锚定戒指的血管/RHR 趋势、化验锚定、CGM 锚定饮食-血糖环;校准结果回灌 L1 置信度(有 ground-truth 的指标置信度更高)。
- 评审建议"下一步别再买 wearable,加 ground-truth 点测设备"——我们**已具备入口**,差的是用起来。

---

## 6. Killer MVP:多源恢复/训练决策引擎

**第一灯(默认)= 训练向**:"今天该不该练 / 怎么调"。理由:Garmin training_readiness + 你的训练数据最硬,最快出可信的灯。(认知/日程向 = 第二灯,见 §12 待拍板。)

```
输入(全部已有):
  RingConn  → 睡眠时长/结构、夜间 HRV、SpO2、腕温(via 多源 router)
  Garmin    → training_readiness_score、acute_load/load_ratio(ACWR)、body_battery、HRV status
  Apple     → 全天活动、RHR、主观事件(L3)
  baseline  → 各指标 7/30/90 天个人 z-score(personal_baseline)
        ↓ L1 置信度合成
  决策:
    GREEN  正常训练
    YELLOW 降一级(改 Zone 2)
    RED    恢复/休息
  + confidence(高/中/低)+ reason[](哪几项偏离基线)+ next_action(一条)
        ↓
  surface:Apple 通知/Complication + Garmin Connect IQ data field;展开解释在 iPhone/OpenClaw
```
算法骨架:**相对个人基线**(不看绝对值)+ **一致性加权**(同向源越多置信越高)+ ACWR 过载/欠训练 → 灯色;高风险走 SafetyGuardian 升级。

---

## 7. 与 wrist-companion 文档的分工(避免重叠)

| 维度 | 本文(引擎层) | wrist-companion 文档(Apple surface 层) |
|---|---|---|
| 焦点 | 三设备融合、置信度、决策灯、Garmin、ground-truth | Apple Watch 本体:语音食物、companion app、通知投递、Complication UI |
| Killer | 多源恢复/训练决策引擎 | 语音记录食物 |
| 设备 | RingConn + Garmin + Apple ensemble | Apple Watch |
| 输出 | `{light, confidence, reason, next_action}` 决策合同 | 腕上 UI / 食物 draft 确认 |

两者共用:`HealthEvent` 事件流、`daily_operating_plan`、#175 通知基建、device_source_priority。

---

## 8. 分期路线(反馈环优先)

| 阶段 | 内容 | 新硬件? | 反馈环 |
|---|---|---|---|
| **P0 置信度脊柱 + 决策灯(在既有数据上)** | L1 合成 + L2 决策服务 + Apple 通知(复用 #175)。**不建 watchOS target、不碰 Garmin** | ❌ | 后端 pytest;OTA 推通知 |
| **P1 双 surface + 腕上输入** | Garmin Connect IQ data field(决策灯)+ Action Button/语音 → HealthEvent(L3) | ⚠️ Connect IQ 独立栈 | 真机 |
| **P2 Ground-Truth 校准** | L4:CGM/化验/血压 校准趋势 + 回灌置信度 | ❌ | 后端 |
| **P3 与 companion 合流** | Apple Complication + 食物语音(companion 文档 Phase 1)+ workout gate | ✅ watchOS target | 真机/EAS |

**先做 P0**:它独立交付"每天一句可信决策",零新硬件、零 watchOS、最快见效,且是后面所有 surface 的内容来源。

---

## 9. 复用清单(别重造)
`device_source_priority.py` · `multi_source_merger.py` · `cross_source_validator/` · `personal_baseline.py` · `twin/{builder,schema,formatter}.py` · `models/health_event.py`(HealthEvent+EventSource)· `models/{episode,intervention_cycle,intervention_event,symptom_entry}.py` · `intervention_cycle_service.py` · `services/episode/` · `daily_operating_plan.py` · `agents/recovery_coach`(readiness)· `agents/longitudinal_analyst` · `services/cgm/` + CGM 规则 · `medical_exams` · `proactive_coordinator` · `behaviorLoopReminders.ts`(#175)· `appleHealth.ts`(多源拆分)· `HealthPilotSiri.swift`(App Intents)· `/api/v1/agent/stream`、`/api/v1/siri/shortcut`。

---

## 10. 设备 doctrine + 不做
- Apple = active interface;Garmin = sport interface(Connect IQ only);RingConn = passive sensor(no app);iPhone/OpenClaw = brain。
- ❌ ring app;❌ Garmin 聊天;❌ 诊断/改药量/替代医生;❌ Watch 跑大模型;❌ 重造已建模块。
- **隐私最小化**:Watch 只拿当前任务最小信息;原始基因/化验/病历/私密对话**永不下发 Watch**;LLM prompt 只给最小集(守 Tier 5 + AGENTS.md)。
- **医疗分级措辞**:低=建议 / 中=建议记录关注 / 高=立即就医;复用 SafetyGuardian 五档 → 通知 Time Sensitive,高危才申 Critical Alert。

---

## 11. 风险
- RingConn 无开放 API、震动不可编程 → 只能 Apple Health/导出,别规划 ring 端能力。
- Garmin Connect IQ = 独立 Monkey C 栈 + 独立构建,投入前确认值得(取决于 §12)。
- watchOS 26 Controls 免 App 调 intent 的能力需半天 spike 实测(知识截止 2026-01)。
- EAS 对 watchOS target 有摩擦 → P3 才碰,前面全走后端/OTA。
- **并发**:`feat/wrist-behavior-loop-notify`、companion 文档(#已合)、#170/#175 在动这片区,动手先对齐。

---

## 12. 待拍板(就三个)
1. **决策引擎第一灯**:训练向("今天该不该练")【默认推荐】 vs 认知/日程向("今天身体+工作怎么安排")。
2. **跑步到底戴哪块**:Apple 还是 Garmin?→ 决定 P1 是否投 Garmin Connect IQ data field(若只戴 Garmin,这是必投)。
3. **是否做个人工具优先**:先服务你自己(HealthKit + 导出 + 本地库,最快),还是一开始就考虑公开用户(需 Garmin API 申请/合规)。

---

## 13. 推荐下一步
**做 P0(置信度脊柱 + 决策灯,在既有数据上,OTA)**:
1. 写 `RecoveryConfidence` 合成函数(L1)+ 单测(三源同向→高置信、单源异常→低置信)。
2. 写决策服务 → `{light, confidence, reason, next_action}`,合成 RecoveryCoach + Garmin readiness + baseline。
3. 经 #175 通知基建推"今日决策灯"(经 proactive_coordinator gate)。
4. 验证后再决定 P1 是否投 Garmin Connect IQ(取决于 §12.2)。

> 一句话:OS 已经在了。补"置信度脊柱 + 决策灯 + 腕上输入 + ground-truth 校准"四层薄的,让三块设备的冗余变成一句每天可信的决策。
