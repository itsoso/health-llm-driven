# Reva Health Leverage Action OS 产品开发文档

日期: 2026-06-16
状态: v0.1, 用于后续产品演进和实现排期
范围: Backend, Mobile, Apple Watch, Mac, Web, Health Agenda, InterventionCycle, SafetyGuardian, 多可穿戴与复测闭环

## 0. 文档定位

本文把「如何找到改善个人健康的杠杆点」这份方法论沉淀为可开发的产品方案。它不是创业建议,也不是替代现有 PRD。

关系如下:

- `docs/prd/reva-personal-health-os-prd.md`: 全局产品 PRD, 仍是 Personal Health OS 的主文档。
- `docs/prd/2026-06-16-enter-key-leverage-thesis.md`: 策略层, 回答为什么护城河在 Write 权限、个人先验和闭环验证。
- `docs/plans/2026-06-16-apple-watch-health-opportunities-roadmap.md`: Watch 路线图, 回答手腕端能做什么。
- 本文: 产品开发层, 回答如何把「杠杆点」变成可排序、可执行、可验证、可复盘的产品对象。

一句话:

> Reva 不应该只解释健康数据, 而应该持续找到每个用户当前最高杠杆的少数健康动作, 在正确时间和设备上促成执行, 并在 1/4/8/12 周后验证它是否真的有效。

## 1. 要采纳的核心洞察

### 1.1 杠杆点不是最严重的问题

健康产品常见错误是从异常指标直接反推行动:

- 血压高就只盯血压。
- 睡眠差就只推褪黑素。
- 体检异常项最多就优先处理它。

Reva 的正确做法是先区分三类对象:

| 类型 | 例子 | 产品处理 |
|---|---|---|
| 结果指标 | HbA1c, ALT, LDL-C, 血压, HRV, 深睡比例 | 用于判断状态和验证结果 |
| 风险/安全信号 | ECG AFib, 持续低 SpO2, 急性胸痛, 严重血压异常 | 先进入 Safety Gate 和就医/复查流程 |
| 可写入变量 | 餐后步行, 咖啡因截止时间, 补剂/药物依从, 晚餐时间, 训练强度, 复测日期 | 作为 ActionRanker 的候选动作 |

产品原则:

> 仪表盘展示的是结果, 操作系统要调度的是可写入变量。

### 1.2 四个筛选器成为产品排序规则

方法论中的四个筛选器应沉淀为 ActionRanker 的基础特征:

| 筛选器 | 产品含义 | 示例 |
|---|---|---|
| 上游度 | 改善后能带动多少下游指标 | 睡眠、餐后活动、体重/腰围、用药依从 |
| 可操作性 | 用户或系统能否直接执行 | 14:00 后不喝咖啡比“提高 HRV”更可操作 |
| 高频度 | 一年内有多少次执行机会 | 餐后散步 > 年度体检 |
| 可验证性 | 能否在合理周期内看到变化 | 1 周看可穿戴趋势, 4-12 周看体检/家庭测量 |

需要补充两个产品因子:

| 补充因子 | 原因 |
|---|---|
| 安全优先级 | 低频但高风险事件不能被高频动作挤掉 |
| 执行摩擦 | 同样有效时, 优先推低摩擦动作, 尤其是 Watch 可一键完成的动作 |

建议排序公式:

```text
action_score =
  safety_gate_boost_or_block
  + upstreamness * actionability * frequency * verifiability * confidence
  - friction
  - notification_fatigue_penalty
```

注意: `safety_gate_boost_or_block` 不是普通加权项。急性红线和医疗边界必须先裁决, 不能让排序模型覆盖。

### 1.3 高频小动作是中年健康复利的主战场

对中年人最有价值的不是一年一次的健康热情, 而是每天重复发生的小动作:

- 餐后 10-15 分钟步行。
- 服药/补剂按时确认。
- 咖啡因截止时间。
- 晚餐时间和夜宵控制。
- Zone 2 或轻力量训练。
- 久坐打断。
- 睡前准备。
- 血压、体重、腰围、症状的低摩擦记录。

这些动作应该优先进入 Watch / Mobile 的短闭环, 而不是埋在 Web 报告里。

### 1.4 复测召回是外环飞轮

任何健康行动如果不能验证, 就会退化成建议堆叠。Reva 必须让每个重要干预绑定验证计划:

| 干预类型 | 近期验证 | 中期验证 | 长期验证 |
|---|---|---|---|
| 睡眠调整 | 3-7 天 HRV/RHR/睡眠时长 | 2-4 周主观精力 | 长期恢复趋势 |
| 餐后步行/饮食结构 | 1-2 周体重/腰围/步数 | 4-8 周空腹血糖/CGM/HbA1c 趋势 | 季度代谢指标 |
| 训练计划 | 1 周 RPE/睡眠/HRV | 4-8 周 RHR/VO2max/训练负荷 | 伤病率和体能趋势 |
| 补剂/药物依从 | 每日完成率 | 4-12 周目标指标 | 安全副作用和医生复查 |
| 体检异常随访 | 到期提醒 | 复查结果入库 | 趋势和风险重估 |

## 2. 产品目标

### 2.1 用户目标

用户每天只需要回答三个问题:

1. 今天最该做的一件健康行动是什么?
2. 为什么是它, 而不是其他动作?
3. 做完后多久知道它有没有用?

### 2.2 产品目标

在现有 Personal Health OS 上增加一条清晰链路:

```text
Health Twin / Labs / Wearables / Calendar / Symptoms
  -> LeveragePoint candidates
  -> Safety Gate
  -> ActionRanker
  -> Health Agenda top action
  -> Watch/Mobile/Mac/Web execution
  -> ExecutionEvent
  -> VerificationPlan
  -> N=1 outcome review
```

### 2.3 北极星指标

建议把本模块的北极星指标定义为:

> 每周完成的、通过安全裁决、绑定验证计划的高杠杆健康动作数。

辅助指标:

- `top_action_completion_rate`: 今日最高杠杆动作完成率。
- `watch_action_confirm_rate`: Watch 提醒后的完成/稍后/跳过比例。
- `verification_plan_attached_rate`: 干预绑定验证计划比例。
- `recheck_completion_rate`: 到期复测完成率。
- `n_of_1_review_generated_rate`: 干预周期结束后生成复盘比例。
- `notification_disable_rate`: 提醒关闭率, 用来约束过度打扰。

## 3. 产品对象

### 3.1 LeveragePoint

`LeveragePoint` 是候选健康杠杆点, 不是用户动作本身。它描述“当前值得撬动的变量”。

示例:

- `post_meal_walk_after_lunch`: 午餐后步行窗口。
- `caffeine_cutoff_14_00`: 咖啡因截止时间。
- `supplement_adherence_morning_slot`: 早间补剂依从。
- `bp_home_measurement_weekly`: 每周家庭血压测量。
- `sleep_winddown_22_30`: 睡前准备。
- `training_load_downshift_today`: 今日训练降级。
- `spo2_followup_check`: 血氧异常复测/就医协助。

建议字段:

| 字段 | 含义 |
|---|---|
| `id` | 稳定 ID |
| `user_id` | 用户 |
| `domain` | metabolic / sleep / movement / medication / supplement / cardiovascular / respiratory / checkup |
| `trigger_source` | wearable / lab / symptom / calendar / user_goal / protocol / safety |
| `upstreamness` | 1-5 |
| `actionability` | 1-5 |
| `frequency` | 1-5 |
| `verifiability` | 1-5 |
| `confidence` | low / medium / high |
| `risk_level` | info / low / medium / high / critical |
| `friction` | 1-5 |
| `verification_window_days` | 推荐验证周期 |
| `candidate_actions` | 可生成的动作模板 |
| `claim_boundary` | 不能夸大的医学边界 |
| `evidence_refs` | 证据或内部规则来源 |

### 3.2 LeverageAction

`LeverageAction` 是用户今天可执行的一步动作, 可进入 Health Agenda。

示例:

- “午餐后 20 分钟内走 10 分钟。”
- “今天早间补剂只确认 A/B/C, 其他暂不提醒。”
- “今晚 22:30 开始睡前流程。”
- “今天训练降一级, 做 Zone 2 30 分钟或休息。”
- “本周完成一次袖带血压测量。”

建议字段:

| 字段 | 含义 |
|---|---|
| `id` | 动作 ID |
| `leverage_point_id` | 来源杠杆点 |
| `user_id` | 用户 |
| `title` | 用户可见标题 |
| `rationale` | 为什么是这个动作 |
| `time_window_start/end` | 执行窗口 |
| `surface` | watch / mobile / mac / web / calendar |
| `interaction_mode` | confirm / quick_record / voice / passive_observed / calendar |
| `priority_tier` | P0-P4 |
| `safety_status` | passed / blocked / needs_doctor / emergency |
| `verification_plan_id` | 绑定验证计划 |
| `status` | pending / completed / snoozed / skipped / expired / failed |
| `skip_reason` | 用户跳过原因 |
| `created_by` | system / user / clinician / agent |

### 3.3 VerificationPlan

每个重要干预必须说明如何验证。

建议字段:

| 字段 | 含义 |
|---|---|
| `id` | 验证计划 ID |
| `user_id` | 用户 |
| `leverage_point_id` | 关联杠杆点 |
| `primary_metric` | 主验证指标 |
| `secondary_metrics` | 次要指标 |
| `baseline_snapshot_id` | 起点 TwinSnapshot |
| `baseline_value` | 起点值 |
| `target_direction` | up / down / stable / range |
| `review_after_days` | 复盘周期 |
| `recheck_task_id` | 复查任务 |
| `confidence_method` | RCV / trend / user_report / clinical_followup |
| `claim_boundary` | 结果解释边界 |

### 3.4 ActionRanker

`ActionRanker` 是服务层, 输入候选 `LeveragePoint`, 输出今天最值得推的 `LeverageAction`。

输入:

- Health Twin 和最近 TwinSnapshot。
- BiomarkerObservation。
- WearableSignalSnapshot / GarminData / HealthKit import。
- InterventionCycle 和 OutcomeMetric。
- Health Agenda / Daily Plan / ActionCard。
- Medication / Supplement / Diet / Workout / Sleep / Symptom。
- Calendar / time window / user preference。
- SafetyGuardian / AdviceGuard 结果。

输出:

- 今日 top action。
- 今日 1-3 个次要 action。
- 不展示但保留的候选项和被压制原因。
- 每个动作的排序解释。

排序解释必须人能看懂:

```text
今天优先“午餐后走 10 分钟”, 因为:
- 它直接作用于餐后血糖波动和活动量, 比单纯查看血糖更可操作。
- 今天上午步数偏低, 午餐后存在 20 分钟空档。
- 该动作摩擦低, Watch 可一键确认。
- 4-8 周后可用体重、腰围、HbA1c/CGM 趋势验证。
```

## 4. 端侧体验

### 4.1 Apple Watch

Watch 只做高杠杆动作的最后一米:

- 显示今日 top action。
- 到点触觉提醒。
- 一键完成/稍后/跳过。
- 语音记餐和语音记症状。
- 补剂/药物确认。
- RPE、疲劳、疼痛 1-5/1-10 快速记录。
- 数据新鲜度和状态灯。

Watch 不做:

- 长报告。
- 复杂解释。
- ECG 波形解读。
- 医学诊断。
- 大量补剂逐项轰炸。

### 4.2 Mobile

Mobile 是健康动作和权限的主操作面:

- 查看今日/本周 Health Agenda。
- 管理提醒频率、静默时间、动作偏好。
- 确认语音/图片/饮食草稿。
- 查看为什么推荐某个 action。
- 管理 HealthKit 权限和数据新鲜度。
- 接收需要手机完成的补充输入。

### 4.3 Mac

Mac 是复盘和配置工作台:

- 查看 LeveragePoint 排序解释。
- 配置干预周期和验证指标。
- 审阅 N=1 实验报告。
- 导入体检、基因、PDF、外部文件。
- 管理补剂/药物/体检计划。

### 4.4 Web

Web 保留为深度分析和后台入口:

- 历史趋势。
- 管理型页面。
- 外部 Agent / OpenClaw / MCP 入口说明。
- 体检、知识库、PRD、权限审计。

## 5. Safety Gate

### 5.1 安全先于排序

`ActionRanker` 不能直接决定所有动作。必须先经过 Safety Gate:

```text
candidate leverage point
  -> emergency / clinical red-line check
  -> contraindication / DDI / DSI / PGx check
  -> data quality / source confidence check
  -> action ranking
```

### 5.2 Safety Gate 输出

| 输出 | 产品行为 |
|---|---|
| `blocked` | 不生成用户动作, 记录原因 |
| `needs_doctor` | 生成复查/就医协助任务, 不给自我干预建议 |
| `emergency` | 强提醒, 明确急症处理, 不做普通排序 |
| `allowed_with_boundary` | 可推 action, 但文案必须带边界 |
| `allowed` | 正常进入排序 |

### 5.3 医疗措辞边界

禁止:

- “诊断为……”
- “这个动作会治好……”
- “已证明对你有效”, 除非有足够复测证据且仍应表达为趋势/相关。

允许:

- “筛查信号。”
- “建议复测/就医沟通。”
- “与个人基线相比出现偏离。”
- “本次干预后指标趋势改善, 仍需更多周期确认。”

## 6. Nudge 与写入权限

### 6.1 通知预算

默认:

- 每天 1 个主动作。
- 每天最多 2-4 个轻提醒。
- P0 安全提醒不计入普通预算, 但必须严格触发。
- 同类连续跳过 3 次自动降频。
- 睡前 90 分钟后只允许 P0 和用户主动开启的睡眠流程。

### 6.2 写入权限分级

| 等级 | 权限 | 示例 | 默认 |
|---|---|---|---|
| L0 | 只读解释 | 展示趋势和建议 | 默认开启 |
| L1 | 一键提议 | Watch 上确认补剂/散步 | 默认可用 |
| L2 | 日历/提醒写入 | 自动加复测提醒、训练窗口 | 用户授权 |
| L3 | 外部服务草稿 | 购物车/外卖替换建议草稿 | 长期信任后 |
| L4 | 受限自治写入 | 仅对多周期验证有效的低风险动作 | 远期 |

原则:

> 当前阶段优先做 L1/L2, 不急于 L3/L4。Write 自治必须由复测闭环和 Safety Gate 限速。

## 7. MVP 范围

### 7.1 Phase 0: 排序和观测地基

目标: 让系统知道“为什么推这个动作”和“用户是否执行”。

功能:

- 定义 `LeveragePoint` 候选生成接口。
- 实现 `ActionRanker` v0: 四筛选器 + 安全门 + 摩擦扣分。
- Watch/Mobile action event: shown, tapped, completed, snoozed, skipped, failed。
- `top_action` 增加 `rationale`, `leverage_score`, `verification_window_days`。
- 数据新鲜度进入排序: 缺数据时降置信, 不假装准确。

验收:

- 每个 top action 都能解释来源和排序原因。
- 每次 Watch/Mobile 动作都有事件记录。
- 无 HealthKit 新鲜数据时不会给高置信训练/恢复建议。

### 7.2 Phase 1: 三个高杠杆动作闭环

目标: 用最少场景跑通杠杆点闭环。

建议只做三个:

1. 补剂/药物时段确认。
2. 语音记餐后的餐后步行动作。
3. 今日训练降级/恢复动作。

每个动作必须包含:

- 触发条件。
- Safety Gate。
- 排序解释。
- Watch/Mobile 执行。
- 跳过原因。
- 验证计划。

验收:

- 用户能在 Watch 完成或跳过动作。
- 系统能统计完成率、跳过原因和提醒疲劳。
- 每个动作至少绑定一个 1-12 周验证指标。

### 7.3 Phase 2: 复测召回和 N=1 报告

目标: 让外环真的转起来。

功能:

- 干预开始时自动创建 `VerificationPlan`。
- 到期生成复测任务。
- 复测结果回流后生成 N=1 review。
- Review 明确区分: 已改善 / 无明显变化 / 数据不足 / 可能受混杂因素影响。

验收:

- 复测任务能进入 Health Agenda 和 Watch/Mobile 提醒。
- 复盘引用 baseline snapshot 和 latest observation。
- 不把相关性夸大为因果。

### 7.4 Phase 3: 权限扩展

目标: 对已验证有效、低风险、低摩擦动作扩展写入权限。

候选:

- 自动写入日历: 复测、训练窗口、睡前流程。
- 外部服务草稿: 购物车/外卖替换建议, 只生成草稿。
- 家庭/医生共享包: 仅在明确授权后。

不做:

- 自动下单。
- 自动改处方药。
- 自动诊断。
- 高频自治提醒。

## 8. 数据和 API 建议

### 8.1 Backend 服务

新增服务:

- `backend/app/services/leverage_points.py`
- `backend/app/services/action_ranker.py`
- `backend/app/services/verification_plans.py`

可先复用现有模型:

- `ActionCard`
- `InterventionCycle`
- `OutcomeMetric`
- `InterventionEvent`
- `TwinSnapshot`
- `BiomarkerObservation`
- `agenda_service`
- `watch_summary`

### 8.2 API

建议新增或扩展:

- `GET /api/v1/leverage-points/today`
- `POST /api/v1/leverage-points/{id}/actions`
- `GET /api/v1/actions/top`
- `POST /api/v1/actions/{id}/events`
- `POST /api/v1/actions/{id}/skip`
- `POST /api/v1/actions/{id}/complete`
- `GET /api/v1/verification-plans`
- `POST /api/v1/verification-plans`
- `POST /api/v1/verification-plans/{id}/review`

Watch 可先不直接调用新 API, 继续通过 `/api/v1/watch/summary` 投影:

```json
{
  "top_action": {
    "id": "action_123",
    "title": "午餐后走 10 分钟",
    "kind": "post_meal_walk",
    "time_window": "12:40-13:10",
    "priority_tier": "P2",
    "leverage_score": 82,
    "rationale_short": "餐后窗口 + 今日步数偏低",
    "verification_window_days": 28
  }
}
```

### 8.3 数据隔离

所有接口必须:

- 从 auth 用户取 `user_id`, 不信任客户端传入。
- 敏感健康动作写 audit log。
- 跳过原因和症状记录按 L3 机密数据处理。
- 导出/删除路径纳入用户数据治理。

## 9. 排序样例

### 9.1 代谢风险用户

候选:

- 餐后走路。
- 减少晚餐主食。
- 记录午餐。
- 复测 HbA1c。

今日 top action:

> 午餐后 20 分钟内走 10 分钟。

原因:

- 上游影响餐后血糖、体重、脂肪肝风险和活动量。
- 今天有午餐记录和可用时间窗。
- Watch 可低摩擦提醒和确认。
- 4-8 周后可用体重、腰围、HbA1c/CGM 趋势验证。

### 9.2 补剂过载用户

候选:

- 24 种补剂逐项提醒。
- 4 时段补剂确认。
- 暂停高风险补剂。
- 复查肝肾功能。

今日 top action:

> 只确认早间时段保留的 3 项补剂, 其他不推送。

原因:

- 依从率是更上游的问题, 逐项提醒会增加失败。
- 分时段确认降低摩擦。
- 可在 4 周内验证依从率, 8-12 周看目标指标和副作用。

### 9.3 恢复/训练用户

候选:

- 按原计划高强度训练。
- 降级到 Zone 2。
- 休息。
- 记录 RPE。

今日 top action:

> 今日训练降一级, 做 Zone 2 30 分钟或休息。

原因:

- 睡眠/HRV/RHR 相对个人基线显示恢复不足。
- 训练强度是直接可操作变量。
- 可通过第二天 HRV/RHR/RPE 验证。

### 9.4 安全红线用户

候选:

- 餐后步行。
- 睡眠优化。
- SpO2 异常复测。
- 呼吸/胸痛症状确认。

今日 top action:

> 先完成血氧复测和症状确认, 必要时就医沟通。

原因:

- 安全红线先于普通杠杆排序。
- 单次可穿戴读数可能有误差, 但持续异常或伴随症状必须进入 follow-up。
- 此处不生成自我干预建议。

## 10. Reader-facing UX 文案

### 10.1 好文案

- “今天只推这一件, 因为它最可执行、最常发生、也最容易验证。”
- “这不是诊断, 是相对你个人基线的偏离提醒。”
- “如果你连续跳过, 我会降低这类提醒频率。”
- “这个动作的效果将在 4 周后用腰围/体重趋势复盘。”

### 10.2 禁止文案

- “系统判断你已经患有……”
- “做这个一定会改善……”
- “你必须……”
- “你的 HRV 低, 所以你应该吃……”
- “已证明该补剂对你有效”, 除非已有多周期验证, 且仍需保留边界。

## 11. 非目标

本阶段不做:

- 完整 A2A 外卖/电商自动执行。
- 医疗诊断。
- 自动处方药调整。
- 腕上长聊天。
- 新的指标仪表盘。
- 每天 100 个健康指令。
- 无验证计划的补剂推荐扩张。

## 12. 验收清单

产品验收:

- 每个 `top_action` 都有 `rationale` 和 `verification_plan`。
- 每个高优先级动作都经过 Safety Gate。
- 每个提醒都有完成/稍后/跳过/关闭此类入口。
- Watch 只显示 1 个主动作, 不堆列表。
- Mobile 能解释为什么推荐该动作。
- Mac/Web 能复盘动作执行和结果指标。

工程验收:

- 后端 route 强制当前用户隔离。
- 敏感动作写 audit/client event。
- ActionRanker 有纯函数测试。
- Safety Gate 有红线回归测试。
- Watch/Mobile 事件上报有失败重试或明确失败状态。
- HealthKit 数据缺失/过期时降置信。

数据验收:

- 能查到某个用户过去 30 天所有 top action、完成率和跳过原因。
- 能查到某个干预绑定的 baseline、latest 和复测状态。
- 能区分 completed、auto_observed、snoozed、skipped、expired。
- 能解释为什么某个候选动作被压制。

## 13. 建议下一刀

下一刀不应直接做更多 Watch UI, 而应做最小闭环:

1. `watch_action_events` 或统一 `action_events`: 记录 shown/completed/snoozed/skipped/failed。
2. `ActionRanker v0`: 用四筛选器 + Safety Gate 生成 `top_action.rationale`。
3. `VerificationPlan v0`: 对补剂确认、餐后步行、训练降级三类动作绑定验证周期。
4. Watch summary 扩展: 展示 top action 的短理由和数据新鲜度。
5. Mobile/Mac 增加调试/复盘入口: 看今天为什么推这件事。

这样能把方法论、Watch 路线图和 Enter 键战略合并成一个可验证的产品增量:

> 少推一点, 推准一点, 记录是否执行, 到期验证是否有效。

