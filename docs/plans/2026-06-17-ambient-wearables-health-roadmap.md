# Ambient Wearables Health Roadmap

日期: 2026-06-17
状态: v0.1 规划稿
范围: 智能眼镜、耳机/助听耳机、智能鞋/鞋垫、恢复鞋/热压设备, 以及它们与 Reva Personal Health OS 的结合。

> 医疗边界: 本文涉及听力、步态、跌倒、糖代谢、运动伤病、认知风险和恢复建议, 均按筛查、风险提示、行为支持和就医协助设计, 不表达为诊断、治疗或自动处方。任何安全相关判断仍由后端 `SafetyGuardian` 和确定性规则裁决。

---

## 0. Executive Summary

Reva 已经有 Apple Watch、RingConn、Garmin 这组三件核心设备:

```text
RingConn -> 夜间恢复和低打扰基线
Garmin   -> 训练、户外、负荷和路线事实源
Watch    -> 腕上执行、提醒、确认和短输入
```

智能眼镜、耳机和鞋类设备不应该再被当成平级健康数据源。它们更适合作为 **ambient wearables**:

```text
智能眼镜 -> 看见场景
耳机     -> 听见/说出/低打扰提醒
鞋/鞋垫  -> 看见走路和跑步质量
恢复鞋   -> 执行恢复 protocol
```

它们补的是现有系统的四个缺口:

1. **视觉上下文**: 食物、药盒、营养标签、超市选择、运动环境。
2. **听觉健康与语音入口**: 听力测试、噪音暴露、会议疲劳、语音记录。
3. **步态和足底负荷**: 左右不对称、足压、步频、跑姿、伤病风险。
4. **恢复动作执行**: 热疗、气压、足踝恢复、训练后协议依从。

因此下一阶段不是做一个眼镜 App、耳机 App 或鞋 App, 而是建设:

```text
Ambient Wearables Layer
  -> Personal Health Router
  -> Health Agenda
  -> Watch / Mobile / Mac execution
  -> per-user causal ledger
```

北极星问题仍然不变:

> 今天我该怎样安排身体、工作、饮食、训练、睡眠和恢复, 才能持续变健康?

---

## 1. Product Admission

按 `docs/specs/reva-product-governance-spec.md` 做需求准入:

```yaml
RequirementAdmission:
  request: 将智能眼镜、耳机、鞋/鞋垫、恢复鞋纳入 Health OS
  classification: new_product_behavior / docs / experiment
  first_user_fit: 35-55 岁高强度工作者, 有代谢、恢复、训练、听力、久坐或伤病风险压力
  core_loop_step:
    - passive/physical execution
    - low-friction capture
    - agenda top action
    - execution event
    - outcome review
  first_class_objects:
    - HealthProtocol
    - HealthAgendaItem
    - LeverageAction
    - SafetyGuardian
    - ExecutionEvent
    - InterventionCycle
    - HealthTwin
  target_surface:
    - Watch: 即时确认和执行
    - Mobile: 权限、拍照/视觉确认、耳机设置、HealthKit 桥
    - Mac/Web: 长期复盘、设备配置、医生摘要
    - Backend: 路由、仲裁、安全、归因
  source_of_truth: Backend Health Router + HealthKit/Garmin/source ledger
  safety_level: medical_boundary + privacy_sensitive
  prescription_or_causal_verdict: clinician_review_downgraded where applicable
  autonomy_tier: manual_confirm first, shadow only after evidence, clinical writes capped at manual_confirm
  evidence_provenance: device docs, HealthKit, user events, clinician orders, N-of-1 review
  claim_hedging: hedged
  verification_window: same day / 1 week / 4 weeks / 12 weeks depending on protocol
  success_metric:
    - completed_high_leverage_actions
    - input_latency
    - action_completion_rate
    - skip_reason_capture_rate
    - notification_disable_rate
    - outcome_review_generated_rate
```

准入结论: 可以做, 但只能按 **输入、执行、验证和归因** 做。不能做成硬件展示页、健康炫技页或全天候摄像头/麦克风监控系统。

---

## 2. Device Roles

### 2.1 设备分工

| 设备 | 最适合做 | 不该做 |
|---|---|---|
| 智能眼镜 | 食物/药盒/标签/运动环境的视觉输入, 户外训练的短语音反馈, 无手拍摄证据 | 全天候录制, 公共场所隐形采集, 长报告, 医疗判断 |
| 耳机 / AirPods | 语音记录, 音频提醒, 听力测试, 听力辅助, 噪音暴露, 会议疲劳反馈 | 替代医生听力评估, 高频打扰, 长对话健康教练 |
| 运动耳机 | workout 中心率/体温辅助信号, 语音配速/强度反馈 | 替代 Garmin/Watch 训练事实源 |
| 智能鞋/鞋垫 | 步态、足压、左右不对称、跑姿、伤病风险趋势 | 诊断足病、神经系统疾病或糖尿病足 |
| 恢复鞋/热压设备 | 训练后和久坐后的恢复 protocol 执行 | 输出健康诊断, 替代睡眠/HRV 恢复判断 |
| Apple Watch | 最高到达率的执行和确认层 | 被新设备替代 |
| Mobile | 权限、拍照、编辑确认、HealthKit bridge | 做即时行动主入口 |
| Backend | 安全、路由、仲裁、归因、计划生成 | 直接信任消费级设备结论 |

### 2.2 核心原则

新增 ambient wearable 必须回答四个问题:

1. 它带来的信号是否改变下一步行动?
2. 它是否降低记录和执行摩擦?
3. 它是否能产生 `ExecutionEvent` 或验证某个 `HealthProtocol`?
4. 它是否有明确的隐私、噪音和安全边界?

如果答案是否定的, 就不接入。

---

## 3. Smart Glasses

### 3.1 产品判断

智能眼镜的健康价值不是“眼镜上显示健康数据”, 而是 **在手不方便拿手机时看见场景、记录上下文、触发下一步**。

最有价值的场景:

| 场景 | 输入 | Reva 动作 |
|---|---|---|
| 饮食 | 拍餐、菜单、营养标签 | 生成饮食草稿, 让 Watch/Mobile 确认 |
| 药物/补剂 | 看药盒、瓶身、剂型 | 对照已确认方案, 只做提醒和确认 |
| 超市/外卖 | 看商品标签、配料表 | 标记高糖/高盐/酒精/咖啡因风险, 不做恐吓 |
| 户外训练 | 看路况、地形、天气 | 用 Garmin/Watch 数据给短反馈 |
| 安全事件 | 用户主动触发拍摄现场 | 生成给家人的上下文包, 必须显式同意 |

### 3.2 不做眼镜健康 App

眼镜不应该承载:

- 今日健康长报告。
- 复杂营养分析。
- 聊天式健康咨询。
- 连续后台录制。
- 公司/公共场所的被动采集。

眼镜只做三种输出:

```text
1. 视觉草稿 -> 待确认
2. 短提示 -> 可忽略
3. 现场证据 -> 用户显式触发
```

### 3.3 视觉输入契约

建议新增对象:

```text
VisualContextCapture
  id
  user_id
  captured_at
  device_type: glasses | phone_camera
  source_app
  capture_kind: food | medication_label | supplement_label | nutrition_label | environment | workout_context
  media_ref
  extracted_text
  extracted_entities
  confidence
  privacy_zone: private | public | workplace | medical | unknown
  user_confirmed
  resulting_write_intent_id
```

默认写入策略:

- 视觉识别只生成 `WriteIntent`。
- 饮食、补剂、药物、症状、医疗信息都必须用户确认。
- 低置信度或高隐私区域只存摘要, 不保留原图, 除非用户明确保存。
- 后端不信任设备侧识别结论, 只把它当候选。

### 3.4 MVP

第一阶段不需要等智能眼镜硬件。先用 Mobile 相机实现同一契约:

1. 手机拍餐/标签 -> `VisualContextCapture`。
2. 后端生成饮食/补剂/药物草稿。
3. Watch 显示 “确认 / 稍后手机补全 / 丢弃”。
4. 确认后写入饮食记录、补剂执行或药物依从事件。

等眼镜成熟后, 只新增 adapter, 不改 Health OS 对象。

---

## 4. Hearables

### 4.1 为什么耳机优先级高

耳机的优先级高于眼镜和智能鞋, 因为它已经覆盖三个高频入口:

1. **语音输入**: 记餐、症状、补剂、疲劳、会议后状态。
2. **低打扰提醒**: 会议间隙、通勤、运动中, 比手机通知更自然。
3. **听力健康**: 中年人可干预但常被忽视的风险领域。

AirPods Pro 2/3 已提供听力测试、听力辅助和听力保护能力; 运动耳机如 Sennheiser Momentum Sport 还提供 workout 心率和体温传感。Reva 不需要替代这些原生能力, 应该把它们放进健康账本。

### 4.2 HearableHealth 模块

建议新增对象:

```text
HearingHealthSnapshot
  user_id
  measured_at
  source
  hearing_test_available
  audiogram_ref
  left_summary
  right_summary
  user_reported_difficulty
  followup_needed
  clinician_review

NoiseExposureEvent
  user_id
  started_at
  ended_at
  source
  exposure_level_bucket
  context: commute | office | gym | concert | sleep | unknown
  action_taken: none | warned | reduced_volume | left_environment | hearing_protection

AudioInputEvent
  user_id
  captured_at
  device_type
  intent: food | symptom | supplement | medication | fatigue | mood | note
  transcript
  confidence
  write_intent_id
  confirmed_at
```

### 4.3 具体健康闭环

| 闭环 | 触发 | 行动 | 验证 |
|---|---|---|---|
| 语音记餐 | 耳机/Watch 说一句 | 生成饮食草稿, Watch 确认 | 10 秒内完成记录率 |
| 语音记症状 | “胸口闷 / 反酸 / 头晕” | `SafetyGuardian` 急性规则裁决 | red flag 召回和误报复盘 |
| 会议疲劳 | 长会议后主观疲劳评分 | 下午微休息或降强度 | 当天完成率和晚间疲劳 |
| 听力健康 | 听力测试或自述困难 | 建议年度听力复查或听力保护 | 复查任务完成 |
| 噪音暴露 | 健身房/通勤高噪音 | 提醒降音量或换环境 | 噪音暴露趋势 |

### 4.4 耳机提醒策略

耳机提醒必须更克制:

- 只用于正在佩戴耳机的场景。
- 优先短音频/触觉, 不打断会议讲话。
- P0 安全事件可穿透, 但仍要短。
- P1/P2 行为提醒默认可关闭。
- 连续 3 次忽略同类音频提醒, 自动降级为 Watch/Mobile 静默卡。

---

## 5. Smart Shoes And Insoles

### 5.1 产品判断

中年人持续变健康, 关键不是多跑一点, 而是:

- 少受伤。
- 能持续走。
- 能持续做力量训练。
- 能用餐后步行改善代谢。
- 能从步态变化中及早发现身体状态下滑。

智能鞋/鞋垫的价值是补 Watch/Garmin 看不到的 **运动质量**:

```text
Garmin/Watch -> 做了多少、心率多少、路线如何
鞋/鞋垫      -> 怎么走、怎么跑、左右是否不对称、足底如何受力
```

### 5.2 GaitHealth 模块

建议新增对象:

```text
GaitSession
  user_id
  started_at
  ended_at
  source_device
  activity_type: walk | run | hike | rehab | daily
  cadence
  stride_length
  ground_contact_time
  left_right_balance
  pronation_bucket
  footstrike_bucket
  pressure_distribution
  asymmetry_score
  confidence
  linked_workout_id

WalkingQualitySnapshot
  user_id
  date
  source
  walking_steadiness
  walking_asymmetry
  double_support_time
  step_length
  trend_bucket
  action_needed
```

### 5.3 先不用等智能鞋垫

P0 可以先吃现有数据:

- Apple Health 的步行稳定性、步长、双脚支撑时间、步行不对称。
- Garmin 的步频、垂直振幅、触地时间、训练负荷。
- Watch 的步数、心率和 workout。
- 用户主观疼痛、膝/髋/腰不适、足底疼痛。

智能鞋垫是 P2 adapter, 不是 P0 依赖。

### 5.4 高价值用例

| 用例 | 输入 | 输出 |
|---|---|---|
| 跑步伤病预警 | 步态不对称 + 负荷上升 + 疼痛 | 降低跑量, 改 Zone 2 走路或力量恢复 |
| 餐后步行质量 | 饭后步数 + 步速 + 心率 | 判断是否完成代谢微干预 |
| 肌少/跌倒风险趋势 | 步长下降 + 双脚支撑上升 + 稳定性下降 | 建议力量/平衡 protocol 或专项检查 |
| 足底/膝髋腰痛关联 | 足压/左右不对称 + 疼痛日志 | 生成给康复/骨科的摘要 |
| 徒步/长跑恢复 | 下肢负荷 + 次日 HRV/RHR/酸痛 | 调整训练和恢复鞋 protocol |

### 5.5 安全边界

步态系统只说:

- “步态质量较个人基线下降。”
- “左右不对称增加。”
- “建议降低跑步冲击, 改成低冲击活动或复查。”

不说:

- “你有帕金森。”
- “你有糖尿病足。”
- “你一定会受伤。”

---

## 6. Recovery Shoes And Heat/Compression Devices

### 6.1 产品判断

Nike x Hyperice Hyperboot 这类设备不是主要数据源, 而是 **恢复 protocol 执行器**。

它的 Reva 价值在于:

```text
训练/久坐/徒步/出差后
  -> 安排恢复 protocol
  -> 记录是否执行、时长和强度
  -> 次日看 HRV/RHR/酸痛/RPE/步态
  -> 判断对这个人是否值得保留
```

### 6.2 RecoveryDeviceProtocol

建议新增对象:

```text
RecoverySession
  user_id
  started_at
  ended_at
  device_type: hyperboot | compression_boot | massage | heat | cold | manual
  body_region: foot | ankle | calf | leg | back | full_body
  protocol_name
  duration_minutes
  intensity_level
  trigger_context: post_workout | long_sit | travel | soreness | sleep_prep
  user_reported_effect
  next_day_outcome_ref
```

### 6.3 适用人群

优先给这些场景:

- Garmin 显示训练负荷高。
- 长距离徒步/跑步后足踝不适。
- 久坐出差后下肢僵硬。
- 餐后步行或 Zone 2 行走想提高可持续性。
- 晚间放松和睡前 routine 需要低认知负荷动作。

不作为普通用户每天必做的 P0。

---

## 7. Router And Data Architecture

### 7.1 新设备不直接进建议层

所有 ambient wearable 数据都必须经过 Router:

```text
Device/App raw event
  -> source ledger
  -> normalization
  -> confidence / freshness / privacy level
  -> HealthTwin
  -> SafetyGuardian
  -> ActionRanker / HealthAgenda
  -> Watch/Mobile/Mac execution
  -> ExecutionEvent
  -> InterventionCycle review
```

### 7.2 Source policy

| 指标/事件 | 主来源 | 备用来源 | 处理逻辑 |
|---|---|---|---|
| 食物视觉草稿 | Mobile/Glasses camera | 语音 | 只产草稿, 必须确认 |
| 药盒/补剂标签 | Mobile/Glasses camera | 手动录入 | 只能匹配已确认方案, 不自动改剂量 |
| 语音症状 | Watch/earbuds | Mobile | 急性关键词进 SafetyGuardian |
| 听力测试 | Apple hearing health / audiogram | 手动上传 | 只做筛查和复查任务 |
| 噪音暴露 | HealthKit / earbuds | 手动场景 | 用于听力保护和环境建议 |
| 步态 | Apple Health / Garmin | smart insole | 趋势优先, 不诊断 |
| 足压/跑姿 | smart insole | 无 | 仅作训练和康复辅助 |
| 恢复执行 | recovery device / manual | Watch confirmation | 与次日恢复状态做 N-of-1 |

### 7.3 新增抽象

为了避免每个设备写一套业务逻辑, 建议新增一个统一层:

```text
AmbientSignal
  kind: visual | audio | gait | recovery_device
  source
  raw_payload
  normalized_payload
  confidence
  freshness
  privacy_class
  linked_object_type
  linked_object_id
  created_at
```

业务层只消费 `AmbientSignal`, 不直接依赖 Ray-Ban、AirPods、Sennheiser、Nike、NURVV 等品牌。

---

## 8. Product Surfaces

### 8.1 Watch

Watch 继续是第一执行面:

- 显示视觉/语音草稿的确认卡。
- 对语音症状做 “已记录 / 需要补充 / 可能需要就医” 的短反馈。
- 对餐后步行、久坐打断、恢复 protocol 做一键开始/完成。
- 对步态风险只显示行动, 不显示复杂图表。

### 8.2 Mobile

Mobile 是权限和编辑确认面:

- 相机拍餐、拍药盒、拍标签。
- 眼镜输入的内容在手机上复核。
- AirPods/HealthKit 权限说明。
- 步态、听力、恢复设备数据的来源配置。

### 8.3 Mac/Web

Mac/Web 是复盘和配置面:

- 长期听力趋势和复查任务。
- 步态/伤病/训练负荷的周报。
- 饮食视觉识别错误纠正。
- 恢复 protocol N-of-1 复盘。
- Doctor packet: 症状、步态、听力、训练和恢复摘要。

### 8.4 Backend

Backend 是唯一决策源:

- 数据归一化。
- 来源可信度。
- 安全裁决。
- 计划生成。
- 提醒降噪。
- 因果账本。

---

## 9. Privacy And Safety

### 9.1 眼镜隐私

硬规则:

- 默认不连续录制。
- 默认不在 workplace/public/privacy-sensitive 区域保存原图。
- 必须有显式触发和用户确认。
- 第三方人脸、车牌、屏幕内容默认模糊或不保存。
- 眼镜 capture 只产草稿, 不直接写健康记录。

### 9.2 麦克风隐私

硬规则:

- 默认 push-to-talk。
- 不做持续监听。
- 转录文本按健康数据处理。
- 症状、药物、补剂、心理状态输入走 L3/L4 数据保护。
- 低置信语音不执行写入, 只提示确认。

### 9.3 鞋垫和步态安全

硬规则:

- 不诊断神经系统疾病、足病或运动损伤。
- 不用单次步态异常触发高等级警报。
- 必须结合疼痛、训练负荷、近期变化和数据质量。
- 建议必须落到可执行动作: 降负荷、换低冲击、做力量/平衡、复查。

### 9.4 恢复设备安全

硬规则:

- 恢复设备不能替代医疗处理。
- 疼痛、肿胀、急性损伤、血栓风险等场景必须提示停止并就医/咨询医生。
- 不输出 “热疗一定有效” 之类因果结论。
- 只做个人实验和依从记录。

---

## 10. Roadmap

### P0: Earbuds-first, no new hardware

目标: 先把耳机作为低摩擦输入和听力健康入口。

- 复用现有 Watch/Mobile 快速记录, 增加 `AudioInputEvent` 概念。
- 语音记餐、语音记症状、语音疲劳评分统一进入 `WriteIntent`。
- 增加听力健康任务: 听力测试提醒、噪音暴露回顾、年度听力复查。
- 接入 Watch action event, 记录用户是否确认/跳过。
- 所有写入默认 manual_confirm。

验收:

- 语音记餐从说完到 Watch 确认小于 10 秒。
- 症状语音能进入 SafetyGuardian 急性规则。
- 听力健康只产生复查/保护任务, 不做诊断。

### P1: Visual capture contract

目标: 先用手机相机跑通眼镜未来会复用的数据契约。

- 新增 `VisualContextCapture`。
- 手机拍餐/标签/药盒, 生成草稿。
- Watch/Mobile 确认后写入饮食/补剂/药物执行事件。
- 加隐私分类和原图保留策略。

验收:

- 饮食图片能生成待确认草稿。
- 药盒/补剂标签不能直接改方案, 只能匹配已确认 protocol。
- 低置信识别不写入。

### P1: Gait v0 from existing data

目标: 不等智能鞋垫, 先用 Apple Health/Garmin 做步态趋势。

- 建 `WalkingQualitySnapshot`。
- 读取步行稳定性、步长、双脚支撑时间、步行不对称、Garmin 步频/触地类指标。
- 和膝/髋/腰/足底疼痛 micro-log 关联。
- 把风险转成 HealthAgenda 动作: 降负荷、拉伸、力量、低冲击活动。

验收:

- 步态趋势只在数据足够时显示。
- 所有建议都落到可做动作。
- 不输出诊断。

### P2: Smart glasses adapter

目标: 接入眼镜作为视觉输入器。

- 只支持显式拍摄/语音触发。
- 复用 `VisualContextCapture`。
- 公共/工作场景默认只存摘要。
- 户外训练中支持短语音询问: “我现在该降强度吗?”

验收:

- 眼镜输入与手机拍照走同一后端契约。
- 不出现隐式采集路径。
- 眼镜不承载长报告。

### P2: Smart insole adapter

目标: 为有跑步伤痛、足踝问题或高训练负荷的用户引入更高精度步态数据。

- 接入足压、左右平衡、footstrike、pronation、cadence。
- 与 Garmin workout 和 Watch subjective RPE 对齐。
- 给训练降级和康复建议提供证据。

验收:

- 数据新鲜度、置信度和设备来源可见。
- 单设备异常不直接触发高等级结论。
- 训练建议能解释依据。

### P3: Recovery device N-of-1

目标: 把恢复鞋/热压/按摩设备作为可验证 protocol。

- 记录 `RecoverySession`。
- 和次日 HRV/RHR/睡眠/酸痛/RPE/步态关联。
- 4 周生成 N-of-1 回顾: 保留、调整或停止。

验收:

- 每个恢复 protocol 有开始条件、停止条件和验证窗口。
- 不表达未经证实的疗效承诺。

---

## 11. Do Not Build

不要做:

- 眼镜全天候健康记录。
- 眼镜上的完整健康 dashboard。
- 耳机常驻监听。
- 用耳机/鞋垫替代 Watch/Garmin/RingConn 的核心事实源。
- 智能鞋垫疾病诊断。
- 恢复鞋疗效承诺。
- 多设备数据简单平均。
- 因为一个新硬件存在就接入。

一票否决问题:

> 这个设备输入会不会改变今天的行动、降低执行摩擦或验证某个 protocol? 如果不会, 不接。

---

## 12. Suggested Next Slice

推荐下一刀:

```text
AudioInputEvent + hearing health task + voice symptom/food write intent
```

理由:

1. 不需要新硬件。
2. 复用现有 Watch/Mobile 快速记录能力。
3. 与 Apple Watch 独立展示和 Watch-first scheduler 当前路线一致。
4. 能直接改善输入摩擦。
5. 能把听力健康这个中年高价值但常被忽视的风险纳入 Health OS。

工程拆分:

1. 后端新增 `AudioInputEvent` / 或先用现有 client event 扩展 schema。
2. 统一 food/symptom/fatigue 语音 intent。
3. SafetyGuardian 增加症状语音入口测试。
4. Watch 显示语音草稿确认卡。
5. Mobile 增加听力健康任务和噪音暴露说明页。
6. Mac/Web 做听力/语音输入的长期复盘。

---

## 13. References

- Apple AirPods Pro hearing health: https://www.apple.com/airpods-pro/hearing-health/
- Apple AirPods hearing health support: https://support.apple.com/en-us/120992
- Ray-Ban Meta AI glasses: https://www.ray-ban.com/usa/ray-ban-meta-ai-glasses
- Meta Ray-Ban Display and Neural Band: https://about.fb.com/news/2025/09/meta-ray-ban-display-ai-glasses-emg-wristband/
- Sennheiser Momentum Sport: https://eu.sennheiser-hearing.com/en-de/products/momentum-sport
- Nike x Hyperice Hyperboot: https://www.nike.com/t/hyperice-hyperboot-shoes-0v8aYsXz/65000-001
- Smart insole systems for health monitoring review: https://pmc.ncbi.nlm.nih.gov/articles/PMC8780030/
- Johns Hopkins hearing loss health risks: https://www.hopkinsmedicine.org/health/wellness-and-prevention/the-hidden-risks-of-hearing-loss
