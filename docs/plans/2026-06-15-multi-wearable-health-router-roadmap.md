# Multi-Wearable Health Router 规划

> 日期: 2026-06-15
> 目标: 把 Apple Watch Ultra 3、RingConn Gen3、Garmin Enduro 2 从“三个设备”整合成一个多源可信健康操作系统, 用设备分工、数据仲裁、提醒路由和个人实验, 持续改善中年人的恢复、代谢、训练和慢病风险。
> 结论: 下一阶段的核心不是再做一个单设备 App, 而是建设 **Personal Health Router**。Apple Watch 是主动交互层, RingConn 是夜间和恢复基线, Garmin 是训练和户外事实源, 后端是融合、判断、计划和复盘大脑。
> 关系: 本文是系统级规划; `docs/plans/2026-06-15-apple-watch-ultra3-health-wrist-companion.md` 是它下面的 Apple Watch 子系统规划。

---

## 0. Executive Summary

用户现在的设备组合已经足够强:

```text
RingConn Gen3        -> 安静、长期、夜间、恢复、血氧、呼吸、皮温、血管趋势
Garmin Enduro 2     -> 训练、户外、GPS、路线、训练负荷、恢复时间、Training Readiness
Apple Watch Ultra 3 -> 输入、提醒、Action Button、Siri/App Intents、通知确认、HealthKit 桥
```

真正的产品机会不在“哪个设备更准”, 而在:

1. 哪个指标应该信哪个设备?
2. 多设备冲突时如何降级置信度?
3. 什么提醒应该发到哪台设备?
4. 今天该训练、恢复、补觉、控制饮食, 还是复查?
5. 某个行为对用户本人到底有没有用?

所以系统应从 “可穿戴数据聚合” 升级为:

```text
Multi-Wearable Health Router
  -> Health Vault
  -> Source Arbitration
  -> Device Agreement Score
  -> Recovery & Training Decision Engine
  -> Silent Nudge Router
  -> Personal Experiment Platform
```

北极星问题:

> 今天我该怎么安排身体、训练、饮食、睡眠和工作?

第一阶段 MVP 不应先做 Garmin 插件或复杂 Watch App, 而应先做数据路由和决策层:

1. 统一 Apple Watch / RingConn / Garmin 数据入口。
2. 为每个指标输出 `winning_source`、`confidence`、`agreement`、`reason`。
3. 生成每日 `recovery_state_v2` 和 `training_gate`。
4. 让 Apple Watch 做输入和行动确认。
5. 用 Garmin 做训练事实源。
6. 用 RingConn 做夜间恢复和低干扰哨兵。

---

## 1. 设备角色

### 1.1 设备分工

| 设备 | 最适合的角色 | 不该承担的角色 |
|---|---|---|
| Apple Watch Ultra 3 | 输入、提醒、Action Button、Siri/App Intents、Smart Stack、即时确认、HealthKit 桥 | 不做唯一训练事实源; 不做完整 Agent; 不做夜间唯一真相 |
| RingConn Gen3 | 夜间睡眠、HRV、SpO2、呼吸、皮温、血管趋势、低打扰长期佩戴、轻震提醒 | 不做复杂交互; 不做通用通知中心; 不做医疗诊断 |
| Garmin Enduro 2 | 户外、耐力训练、GPS、路线、海拔、训练负荷、Training Readiness、Recovery Time、Body Battery | 不做日常 AI 聊天入口; 不做高频生活提醒 |
| iPhone App | HealthKit bridge、照片饮食、编辑确认、推送、复杂输入、离线队列 | 不替代 Watch 的即时输入 |
| Mac/Web/OpenClaw | 深度分析、医生摘要、实验复盘、长期趋势、知识库和 Agent 工作台 | 不承担外出即时执行 |

### 1.2 系统口径

设备不是平级投票器, 而是不同场景的传感器:

- **RingConn**: 夜间恢复、睡眠呼吸和低干扰长期基线。
- **Garmin**: 训练和户外场景的高可信事实源。
- **Apple Watch**: 用户意图、输入、确认和提醒反馈的主入口。

任何需要“今天该做什么”的建议, 都必须经过 Router:

```text
Raw device data -> Source arbitration -> Confidence -> Safety rules -> Plan/action
```

---

## 2. Personal Health Router

### 2.1 Router 的职责

| 职责 | 说明 |
|---|---|
| Ingest | 从 HealthKit、Garmin Connect、RingConn via Apple Health/export、manual logs 进入统一层 |
| Normalize | 时间、单位、指标命名、睡眠阶段、HRV 单位、source app、device id |
| Deduplicate | 同源重复、HealthKit 汇总重复、跨源同指标重复 |
| Source Arbitration | 每个指标选择默认可信来源和备用来源 |
| Agreement Scoring | 多设备一致性评分, 识别冲突和测量波动 |
| Confidence | 输出指标级、日级、状态级置信度 |
| Derived State | 生成恢复、睡眠、训练、异常、数据缺口状态 |
| Nudge Routing | 决定提醒发到 RingConn / Watch / Garmin / iPhone / Mac |
| Experiment | 将行为干预和结果指标关联, 形成个人响应模型 |

### 2.2 Router 不做什么

- 不把多个设备简单平均。
- 不让 LLM 直接读原始设备表后做健康判断。
- 不让任何消费级传感器输出医疗诊断。
- 不在设备冲突时假装有确定答案。
- 不为了“数据完整”牺牲提醒克制。

---

## 3. 指标来源策略

### 3.1 默认 source of truth

| 指标/场景 | 主来源 | 备用来源 | 处理逻辑 |
|---|---|---|---|
| 睡眠总时长 | RingConn | Apple Watch / Garmin | RingConn 主导; 差异大时降低睡眠置信度 |
| 睡眠阶段 | RingConn | Apple Watch / Garmin | 只用于趋势, 不做绝对诊断 |
| 夜间 HRV | RingConn + Garmin | Apple Watch | 用个人 7/30/90 日基线, 不看单日绝对值 |
| 静息心率 | Garmin / RingConn | Apple Watch | 看趋势和设备一致性 |
| SpO2 平均/最低 | RingConn + Apple Watch | Garmin | 安全相关取最差值, 不让正常源掩盖低值 |
| 呼吸率 | RingConn | Apple Watch / Garmin | 夜间趋势优先 |
| 皮温/体温偏移 | RingConn | Apple Watch | 用于恢复/感染风险提示, 不做诊断 |
| 血管/血压趋势 | RingConn trend | 家用袖带血压计 | RingConn 只做趋势提示; 袖带是 ground truth |
| Training Readiness | Garmin | Router 自建 readiness | Garmin 是训练准备度主参考 |
| Acute Load / Recovery Time | Garmin | workout-derived load | Garmin 优先 |
| GPS/路线/爬升 | Garmin | Apple Watch | 户外训练优先 Garmin |
| Zone / 心率训练 | Garmin | Apple Watch / chest strap | 高强度可引入胸带校准 |
| 饮食/症状/疲劳输入 | Apple Watch | iPhone / Mac | Watch 是低摩擦入口 |
| 行动反馈 | Apple Watch | iPhone / Mac | done/skip/snooze/adjust 写入事件流 |

### 3.2 安全指标处理

以下指标不能简单按优先级取值, 需要 safety-biased 处理:

| 指标 | 规则 |
|---|---|
| SpO2 min / avg | 跨源取最差值或保留所有低值证据 |
| 异常高心率 | 任何设备触发都保留, 但结合活动状态和主观症状判定级别 |
| 胸闷/气促/晕厥 | 主观症状高优先级, 不被设备正常值覆盖 |
| 血压异常 | 家用袖带优先; RingConn/Apple Watch 只提示趋势或通知 |
| 训练过载 | Garmin load + RingConn recovery + subjective fatigue 联合判定 |

### 3.3 数据新鲜度

每个决策都需要附带 freshness:

```text
metric_freshness:
  sleep: 12h, source=ringconn
  hrv: 12h, source=ringconn
  training_load: 3h, source=garmin
  food_log: 2h, source=apple_watch_voice
  weight: 4d, source=withings/manual
```

过期数据不能无提示参与高置信建议。

---

## 4. Device Agreement Score

### 4.1 为什么需要一致性评分

多设备最大的价值不是多几个数字, 而是可以互相校验:

```text
RingConn HRV 下降
Garmin HRV Status 低
Apple Watch RHR 上升
用户记录疲劳 4/5
睡眠低于个人基线

=> 恢复不足置信度: 高
=> 今日训练降级
```

如果只有一个设备异常:

```text
RingConn HRV 下降
Garmin 正常
RHR 正常
睡眠正常
无主观疲劳

=> 可能为单设备波动
=> 保持观察, 不升级提醒
```

### 4.2 建议分数

| 分数 | 含义 |
|---|---|
| `device_agreement_index` | 同一指标跨设备一致性 |
| `recovery_confidence_score` | 恢复状态判断可信度 |
| `sleep_confidence_score` | 睡眠判断可信度 |
| `training_readiness_confidence` | 训练建议可信度 |
| `anomaly_confidence_score` | 异常是否可信 |
| `measurement_quality_score` | 佩戴/数据完整性质量 |
| `missing_data_risk` | 缺失关键数据导致判断不稳的风险 |

### 4.3 输出示例

```json
{
  "date": "2026-06-15",
  "state": "yellow",
  "confidence": 0.84,
  "agreement": {
    "hrv": {"score": 0.78, "sources": ["ringconn", "garmin"]},
    "sleep_duration": {"score": 0.91, "sources": ["ringconn", "apple-watch"]},
    "rhr": {"score": 0.67, "sources": ["garmin", "apple-watch", "ringconn"]}
  },
  "reasons": [
    "RingConn 夜间 HRV 低于 30 日基线",
    "Garmin acute load 偏高",
    "睡眠时长低于个人近 30 日均值",
    "静息心率较基线上升"
  ],
  "decision": "今天高强度训练降级为 Zone 2 或恢复活动"
}
```

---

## 5. Recovery & Training Decision Engine

### 5.1 每天回答的问题

第一 MVP 的核心问题:

> 今天我能不能练? 如果练, 练什么强度?

输出必须简单:

| 状态 | 决策 |
|---|---|
| Green | 照计划训练 |
| Yellow | 降低一级, 优先 Zone 2 / 技术 / 轻力量 |
| Red | 恢复/休息, 暂停高强度 |

### 5.2 输入信号

| 类型 | 信号 |
|---|---|
| 夜间恢复 | RingConn sleep, HRV, SpO2, respiration, skin temp |
| 训练负荷 | Garmin acute load, recovery time, training readiness, HRV status |
| 日常压力 | Garmin stress, Body Battery, Apple Watch activity |
| 主观输入 | Apple Watch fatigue, soreness, pain, illness, mood, RPE |
| 饮食行为 | late meal, alcohol, caffeine, protein, calories |
| 安全规则 | low SpO2, abnormal HR, symptoms, acute illness |

### 5.3 决策优先级

```text
safety > acute illness > doctor directive > severe recovery debt > training load > metabolic goal > preference
```

示例:

- Garmin readiness 高, 但 RingConn 低氧明显 + 用户气促: Red。
- RingConn 睡眠差, Garmin load 正常: Yellow。
- Garmin acute load 高, RingConn 恢复好: Yellow, 不做 VO2max。
- 三源恢复正常, 用户无症状: Green。

### 5.4 与 Daily Operating Plan 的关系

Router 不单独生成一套计划, 而是给 Daily Plan 提供状态:

```text
recovery_state_v2
training_gate
source_by_metric
confidence_by_metric
arbitration_notes
device_disagreement_warnings
```

Daily Plan 负责把它转成行动:

- 今天运动降级。
- 今天优先睡眠窗口。
- 午后散步替代高强度。
- 晚餐控制主食。
- 明早复查恢复状态。

---

## 6. Silent Nudge Router

### 6.1 提醒分级

| Level | 设备 | 场景 |
|---|---|---|
| L0 | 不提醒 | 只记录, 不打扰 |
| L1 | RingConn 轻震 | 久坐、轻恢复提醒、低打扰 nudges |
| L2 | Apple Watch actionable notification | 需要确认/选择的提醒 |
| L3 | Garmin workout alert | 训练中补给、心率区间、配速/爬升/风险 |
| L4 | iPhone / OpenClaw | 需要解释、复盘、查看计划 |
| L5 | iPhone + 明确就医边界 | 高风险症状或连续异常 |

### 6.2 路由原则

- 能不提醒就不提醒。
- 轻提醒优先低干扰。
- 需要用户选择时发 Apple Watch。
- 训练中只发 Garmin 或运动中界面。
- 复杂解释留给 iPhone/Mac/OpenClaw。
- 高风险提醒必须写清医疗边界。

### 6.3 场景示例

| 场景 | 路由 |
|---|---|
| 午餐碳水偏高 | Apple Watch: 饭后 10 分钟走路 |
| 久坐 + 压力高 | RingConn 轻震或 Watch 低优先级 |
| 睡眠差 + 晚上计划高强度 | Apple Watch: 接受降级 / 保持 / 问原因 |
| 跑步 40 分钟后补水补碳 | Garmin alert |
| 连续 3 天恢复异常 + 主观不适 | Apple Watch + iPhone, 建议暂停训练并考虑咨询医生 |
| 夜间 SpO2 低值反复 | iPhone/Mac 医生摘要入口, Watch 只提示复查 |

---

## 7. Personal Health Experiment Platform

### 7.1 为什么这是壁垒

普通健康 App 给通用建议:

```text
少喝酒, 早睡, 多运动, 饭后散步
```

Personal Health OS 应该回答:

```text
这些建议对你本人是否有效? 影响多大? 多久能看到变化?
```

三设备组合让 N-of-1 实验可行:

- Apple Watch 记录干预和执行。
- RingConn 观察夜间恢复反应。
- Garmin 观察训练表现和负荷。
- Backend 做个人基线、统计和复盘。

### 7.2 第一批实验模板

| 实验 | 干预 | 主要指标 | 数据来源 |
|---|---|---|---|
| 咖啡因截止时间 | 12:00 后不喝咖啡, 14 天 | 入睡时间、觉醒、HRV、RHR、主观精力 | Apple Watch input + RingConn |
| 酒精影响 | 记录酒精量, 对比 72h 恢复 | SpO2、RHR、HRV、睡眠、疲劳 | Watch + RingConn |
| 晚餐时间 | 晚餐提前 2 小时, 14 天 | 睡眠、HRV、体重趋势、夜醒 | Watch food + RingConn |
| 饭后步行 | 午/晚餐后走 10 分钟 | 体重、腰围、睡眠、主观胃胀 | Watch action + wearable |
| 恢复日策略 | 睡眠差时降级训练 | 48h HRV、RHR、训练表现、疲劳 | Garmin + RingConn |
| Zone 2 频率 | 每周 3 次 Zone 2, 4 周 | RHR、VO2max、HRV、体重 | Garmin + Watch |

### 7.3 实验输出

```text
实验: 咖啡因截止时间
周期: 2026-06-01 至 2026-06-14
执行率: 78%
结果:
  - 入睡时间中位数提前 18 分钟
  - RingConn HRV 中位数 +6%
  - 夜醒次数下降
可信度: medium
建议: 继续保持 12:00 后不喝咖啡, 2 周后复查
边界: 样本量小, 出差和训练负荷可能混杂
```

---

## 8. 数据架构

### 8.1 建议核心表/对象

#### DeviceMeasurement

```text
id
user_id
metric_type          -- hrv, rhr, spo2, sleep_duration, acute_load
value
unit
start_time
end_time
record_date
source_device        -- apple_watch, ringconn, garmin, manual, withings
source_app           -- healthkit, garmin_connect, ringconn_export
source_record_id
raw_payload_ref
confidence_score
quality_flags[]
created_at
```

#### DailyMetricArbitration

```text
user_id
record_date
metric_type
winning_source
winning_value
source_values[]
agreement_score
confidence_score
freshness
arbitration_reason
quality_flags[]
```

#### DerivedHealthState

```text
user_id
date
recovery_state
training_gate
sleep_confidence
recovery_confidence
anomaly_score
missing_data_risk
source_by_metric
explanation
created_at
```

#### NudgeEvent

```text
id
user_id
trigger_type
level
target_device
message
actions[]
sent_at
responded_at
response
linked_plan_action
linked_experiment
```

#### PersonalExperiment

```text
id
user_id
template
hypothesis
start_date
end_date
intervention_rule
primary_metrics[]
secondary_metrics[]
adherence_events[]
result_summary
confidence
status
```

### 8.2 与现有模型的关系

| 现有对象 | Router 关系 |
|---|---|
| `GarminData.data_source` | 当前多源 daily 的兼容层, 可继续作为 P0 落地载体 |
| `device_source_priority.py` | P0 继续作为 source priority 单一真相, 后续升级成 arbitration policy |
| `device_comparison_service.py` | 可扩展为 Device Agreement Dashboard |
| `cross_source_validator.py` | 可升级为 anomaly confidence 输入 |
| `HealthTwin` | 消费已仲裁的状态, 不直接判断原始冲突 |
| `DailyOperatingPlan` | 消费 recovery/training gate, 输出行动 |
| `InterventionEvent` / action feedback | 记录提醒和行动执行 |
| `DietRecord` | 接收 Apple Watch 食物语音结构化记录 |

### 8.3 代码勘察:已建成 vs 真正要新建(别重造,2026-06-15)

> 对照仓库实际代码 —— 本 roadmap 的"建议新建"里有几样**已经存在**,P0 应据此大幅收缩。

| 本文提议的组件 | 仓库现状(文件) | 判定 |
|---|---|---|
| **PersonalExperiment 表 + 实验平台(§7,称"壁垒")** | `models/episode.py` + `models/intervention_cycle.py` + `services/intervention_cycle_service.py` + `services/episode/` + SupplementAdvisor 12 周 N-of-1 | ✅ **已建,别重造** —— §7 改为"复用 episode/intervention_cycle,补实验模板即可" |
| 用 7/30/90 日基线不看绝对值(§3.1) | `services/personal_baseline.py`(#170,z-score 进 Twin) | ✅ 已建 |
| Device Agreement Score / Dashboard(§4、§9.2) | `services/device_comparison_service.py` 的 `compare_sources()` **已算 per-metric agreement**(1−极差/均值)+ `GET /devices/sources/summary` | ✅ 已建,**扩聚合成 index 即可** |
| Source Arbitration(§2/§3) | `device_source_priority.py` + `multi_source_merger.py` | ✅ 已建 |
| NudgeEvent + Silent Nudge Router L2 Apple actionable(§6) | `mobile/services/behaviorLoopReminders.ts`(#175 已上线,镜像到 Watch)+ notification model + `proactive_coordinator`(限流) | 🟡 部分,扩路由 |
| 统一事件流 / 行动反馈 / 食物 draft 落地 | `models/health_event.py`(`HealthEvent` confidence + 确认/修正状态机 + `EventSource`)—— 本文未提到,但它就是 NudgeEvent/事件捕获的现成家 | ✅ 已建 |
| Symptom-to-Sensor 因果(§9.4) | `agents/longitudinal_analyst`(干预事件×指标因果) | ✅ 已建(缺事件输入) |
| Ground-truth(CGM/血压/化验,§11) | `services/cgm/`+6 规则、`medical_exams`、BP/体重 collectors | ✅ 已接入(校准用=新) |
| DeviceMeasurement 表 | `GarminData.data_source` 漏斗(§8.2 已承认) | 🟡 兼容层在,物化可选 |
| **`recovery_state_v2` / `training_gate`(决策引擎,§5)** | grep 全仓库**无** | 🔴 **真正要新建**(但 `compute_readiness()` 已返回 0-100 分 + zone rest/light/moderate/hard;`twin.behavioral.acwr_zone` 已有 → 决策灯是薄映射) |

**结论:§12 的 P0「建设 Router」约 70% 已在仓库里。** 真正要写的只有:① 决策引擎 `recovery_state_v2`/`training_gate`(映射已有 readiness zone + acwr_zone + 急性病兜底)② 统一置信度合成(聚合已有 `compare_sources` 的 agreement + cross_source_validator + 新鲜度)③ 腕上输入 → 已有 `HealthEvent` 那条线 ④ Garmin Connect IQ(后置)。其余复用。

> **两处需就地修正**:§6.1 的"L1 RingConn 轻震"——RingConn **无开放 API、震动不可编程**,该层不可由我们主动触发,降级为"靠 RingConn 自带健康震动";§7 的 PersonalExperiment 不是"新建壁垒",是复用已建的 episode/intervention_cycle。

---

## 9. 产品模块

### 9.1 Multi-Device Recovery Score

输入:

- RingConn: sleep, HRV, SpO2, respiration, skin temp。
- Garmin: Training Readiness, Body Battery, HRV Status, acute load。
- Apple Watch: subjective fatigue, food, symptoms, action feedback。

输出:

```text
今日恢复: Yellow
置信度: High
原因:
  - RingConn 夜间 HRV 低于 30 日均值
  - Garmin 急性训练负荷偏高
  - 昨晚睡眠低于个人基线
建议:
  - 高强度训练降级
  - Zone 2 30-45 分钟
  - 睡前提前 30 分钟
```

### 9.2 Device Agreement Dashboard

给 power user / 你自己看:

```text
过去 30 天:
- RingConn 与 Garmin 睡眠总时长差异: 平均 22 分钟
- RingConn 与 Apple Watch 静息心率差异: 平均 3 bpm
- Garmin 高负荷训练日后, RingConn 次日 HRV 平均下降 12%
```

### 9.3 Training Decision Gate

训练前只回答:

```text
GREEN: 照计划
YELLOW: 降一级
RED: 恢复/休息
```

解释可以在 iPhone/OpenClaw 展开。

### 9.4 Symptom-to-Sensor Correlation

Apple Watch 输入:

- 头痛 4/5
- 胃不适
- 焦虑
- 疲劳
- 心悸

系统自动查前后 24-72 小时:

- 睡眠
- HRV
- 咖啡
- 酒精
- 训练
- 压力日程
- 心率
- 血氧

输出:

```text
过去 6 次头痛中, 4 次发生在睡眠不足 + 午后咖啡 + 高压力日之后。
```

### 9.5 Doctor Summary

生成医生可读摘要:

- 近 90 天睡眠趋势。
- HRV/RHR/SpO2 趋势。
- 训练负荷和恢复异常。
- 饮食、酒精、咖啡因、夜宵。
- 症状时间线。
- 血压/血糖/体检指标。
- 设备来源和置信度。

Watch 上只给入口:

```text
[生成摘要] [发送到手机]
```

---

## 10. 三类设备 App 策略

### 10.1 Apple Watch: 要做, 但薄

做:

- Action Button / Shortcuts。
- App Intents。
- Siri 语音记录食物。
- Smart Stack。
- 通知按钮。
- 今日状态。
- 快速记录。

不做:

- 复杂 dashboard。
- 大段聊天。
- 完整病历浏览。
- 后台常驻监听。

### 10.2 Garmin: 可做 Connect IQ, 但只做训练场景

做:

- Data Field: GREEN/YELLOW/RED training gate。
- Widget/Glance: 今日训练建议。
- 训练中补给提醒。
- 心率区间和恢复风险。
- 运动后 RPE 标记。

不做:

- Garmin 上的完整 AI 助手。
- 全天候提醒中心。
- 自然语言聊天。

### 10.3 RingConn: 不按开放平台预期设计

现实路线:

- 通过 Apple Health / Health Connect / export 拿数据。
- 作为 passive baseline。
- 利用 RingConn 自身健康震动提醒。
- 不依赖第三方开发 API。

RingConn 是 **passive sensor**, 不是交互平台。

---

## 11. Ground Truth Sensor 策略

已有三件 wearable 后, 不建议再优先买新手表/戒指。新增价值更高的是 ground truth:

| 设备/数据 | 价值 |
|---|---|
| 袖带血压计 | 校准血压/血管趋势, 家庭 7 天血压 protocol |
| CGM | 饮食、压力、睡眠、运动对血糖反应的个人模型 |
| 体脂秤/体重秤 | 体重、体脂、肌肉、代谢长期趋势 |
| 胸带心率 | 高强度训练中心率更稳定 |
| 体温计 | 感染/恢复状态校准 |
| 血检/体检 | 校准可穿戴代理指标 |
| 主观日志 | 疲劳、疼痛、情绪、压力, 是 AI 最缺的输入 |

Router 应将 wearable 作为连续代理指标, 将 ground truth 作为校准锚点。

---

## 12. 分期路线

### P0: 数据融合和 Router 基线

目标: 不做新硬件功能, 先让多源数据可解释。

任务:

1. 扩展 `device_source_priority.py` 为可解释 arbitration policy。
2. 扩展 `/devices/sources/summary`, 返回 freshness、source_by_metric、quality flags。
3. 扩展 `device_comparison_service.py`, 输出 agreement score。
4. 将 cross-source anomalies 进入 Health Guardrail / Daily Plan context。
5. 生成 `recovery_state_v2` 的 deterministic 版本。

验收:

- 每个关键指标能看到采用来源和原因。
- 多设备冲突不会被简单平均。
- 今日恢复状态能输出置信度和证据。

### P1: Apple Watch 输入和提醒

目标: 让 Watch 成为主动交互层。

任务:

1. 结构化食物语音记录。
2. Action Button / App Intent 分流到 food voice path。
3. Watch action feedback: done / skip / snooze / adjust。
4. Smart Stack 显示下一步行动。
5. Watch 通知只发可执行提醒。

验收:

- 用户能抬腕完成一餐记录。
- 饭后/睡前/运动前提醒有反馈。
- 反馈进入 Daily Plan / Outcome Review。

### P2: Recovery & Training Decision Engine

目标: 每天可靠回答“今天能不能练”。

任务:

1. 融合 RingConn recovery、Garmin readiness/load、Apple Watch subjective input。
2. 训练前输出 GREEN/YELLOW/RED。
3. Daily Plan 根据 gate 自动降级。
4. 运动后回写 RPE 和恢复观察。

验收:

- 黄/红状态不默认推高强度训练。
- 系统能解释为什么降级。
- 训练后 24-48 小时自动复盘。

### P3: Garmin Connect IQ 训练界面

目标: 在训练中提供最小有效反馈。

任务:

1. Garmin Data Field: AI Load Gate。
2. Garmin Glance: 今日训练建议。
3. 补水/补碳提醒。
4. 运动后 RPE 标记。

验收:

- 训练中不用看手机。
- Garmin 只展示灯号和最小提示。
- 详细解释回到 iPhone/Mac。

### P4: Personal Experiment Platform

目标: 从建议系统变成个人响应模型。

任务:

1. 咖啡因、酒精、晚餐、Zone 2、恢复日实验模板。
2. 实验执行率统计。
3. 干预和指标变化关联。
4. Outcome Proof 展示“哪些行为对你有效”。

验收:

- 4 周能生成至少一个个人实验报告。
- 能区分“建议没效”与“没有执行”。
- 能把结果反哺 Daily Plan。

### P5: Doctor / Family Summary

目标: 把多源数据整理成可沟通证据。

任务:

1. 90 天恢复/睡眠/训练/症状摘要。
2. 低氧/血压/心率异常医生摘要。
3. 数据来源和置信度说明。
4. 可分享/可撤销/可审计。

验收:

- 医生摘要不堆原始数据, 而是结构化趋势和异常。
- 不包含诊断性表述。
- 用户可以控制分享范围。

---

## 13. 成功指标

| 指标 | 目标 |
|---|---|
| Source explainability | 关键指标 100% 有 winning source 和 reason |
| Agreement coverage | HRV/RHR/sleep/SpO2 至少 4 类指标有 agreement score |
| Recovery decision reliability | 每日 recovery_state_v2 输出 confidence |
| Training gate adoption | 训练日前 gate 查看/触发率持续上升 |
| Watch input success | 食物/症状/疲劳语音记录成功率 >= 80% |
| Reminder restraint | 每天主动提醒 <= 5 条, 反馈率 >= 50% |
| Outcome linkage | 至少 3 类行动能进入 outcome proof |
| Experiment completion | 每 4 周至少完成 1 个个人实验 |
| Safety boundary | 所有高风险输出包含复测/就医边界 |

---

## 14. 风险和取舍

### 14.1 技术风险

| 风险 | 处理 |
|---|---|
| RingConn 没有稳定公开 API | P0 走 Apple Health / Health Connect / export |
| Garmin API 权限复杂 | 先复用现有 Garmin Connect/同步路径, Connect IQ 后置 |
| HealthKit 多源重复 | Router 做 source app + device id + time window 去重 |
| HRV 算法差异 | 不比较绝对值, 比较个人基线偏离 |
| 睡眠阶段差异 | 阶段只看趋势, 不做跨设备绝对真相 |
| 提醒泛滥 | Silent Nudge Router 限流和路由 |
| LLM 误判 | LLM 只读 derived states, 不直接裁决安全 |

### 14.2 产品风险

| 风险 | 处理 |
|---|---|
| 用户被设备冲突困扰 | 默认只展示结论, 细节放 power view |
| 置信度让人不安 | 文案使用“数据一致/数据不足/建议观察” |
| 多设备佩戴负担 | 系统给出佩戴策略, 不要求 24h 全戴 |
| 医疗化风险 | 明确 wellness / training /复查/医生沟通边界 |
| 过早做 Garmin 插件 | 先做数据融合和训练 gate, 插件后置 |

---

## 15. 推荐佩戴策略

| 时间/场景 | 推荐佩戴 |
|---|---|
| 睡觉 | RingConn 必戴; Garmin 可选; Apple Watch 视充电策略 |
| 日常工作 | Apple Watch 负责输入和提醒; RingConn 低干扰监测 |
| 跑步/骑行/徒步 | Garmin 主记录; Apple Watch 辅助交互; RingConn 可不参与 |
| 恢复异常观察期 | RingConn + Garmin 都戴, 提升置信度 |
| 饮食/症状记录 | Apple Watch / iPhone |
| 医生/复盘 | Mac/Web/OpenClaw |

---

## 16. 与 Watch Companion 文档的关系

本规划是系统级 Router。已有 Watch 文档应保留, 但定位调整为:

```text
Multi-Wearable Health Router
  ├── Apple Watch Wrist Companion
  │   ├── Food Voice Capture
  │   ├── Action Button / App Intents
  │   ├── Smart Stack / Notifications
  │   └── Action Feedback
  ├── Garmin Training Interface
  │   ├── Training Gate
  │   ├── Data Field / Glance
  │   └── Workout RPE / Fueling
  ├── RingConn Passive Baseline
  │   ├── Sleep / HRV / SpO2 / Respiration
  │   ├── Vascular trend
  │   └── Low-noise nudge
  └── Backend Router
      ├── Arbitration
      ├── Agreement
      ├── Derived State
      ├── Daily Plan
      └── Personal Experiments
```

Watch Companion 是第一块交互实现, 不是系统全部。

---

## 17. 下一步实施建议

如果继续拆 implementation plan, 先不要从 UI 开始, 而是从后端可测协议开始:

1. 后端: 为 `device_source_priority` 增加 explanation 输出。
2. 后端: 扩展 source summary, 返回 freshness + source_by_metric。
3. 后端: 扩展 device comparison, 生成 agreement score。
4. 后端: 建 `recovery_state_v2` 纯函数和测试。
5. Mobile/Web/Mac: 展示“今天的来源解释”和“恢复状态置信度”。
6. Mobile/Watch: 结构化食物语音记录。
7. Daily Plan: 训练 gate 接入行动生成。
8. Outcome Proof: 记录训练降级/饭后步行/咖啡因实验的效果。

推荐第一个可交付版本:

```text
Multi-Wearable Recovery & Training Decision Engine v0
```

它只回答一个问题:

> 今天能不能练? 为什么? 如果不练, 做什么替代?

这个 MVP 能同时用到 RingConn、Garmin、Apple Watch, 也能直接产生长期健康价值。

---

## 18. References

- Apple Watch Ultra 3 technical specifications: https://www.apple.com/apple-watch-ultra-3/specs/
- Apple Watch Ultra 3 announcement: https://www.apple.com/newsroom/2025/09/introducing-apple-watch-ultra-3/
- watchOS 26 announcement: https://www.apple.com/newsroom/2025/06/watchos-26-delivers-more-personalized-ways-to-stay-active-and-connected/
- Smart Stack guide: https://support.apple.com/guide/watch/see-widgets-in-the-smart-stack-apdecf142fb9/watchos
- RingConn Gen3: https://ringconn.com/pages/ringconn-gen-3
- Garmin Enduro 2 Training Readiness: https://www8.garmin.com/manuals/webhelp/GUID-2CD92989-7336-4BF3-96CC-50DDBD63B109/EN-US/GUID-C21BE0C8-A08E-4DA1-B6C6-2E0E2DDDB372.html
- Garmin Enduro 2 HRV Status: https://www8.garmin.com/manuals/webhelp/GUID-2CD92989-7336-4BF3-96CC-50DDBD63B109/EN-US/GUID-9282196F-D969-404D-B678-F48A13D8D0CB.html
- Garmin Body Battery: https://www.garmin.com/en-US/garmin-technology/health-science/body-battery/

