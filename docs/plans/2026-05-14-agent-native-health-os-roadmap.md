# Agent Native Mobile First 个人健康操作系统完整规划

> 日期: 2026-05-14
> 目标: 以基因为先天底图, 融合体检、可穿戴、饮食、运动、睡眠、情绪和环境数据, 持续理解用户身体状态, 并把医学、营养、运动和行为科学转化为每天可执行的行动。
> 阶段 1 聚焦: 体重与代谢健康, 改善体重、腰围、血脂、血糖、血压、睡眠和运动表现。
> 定位边界: 不替代医生; 做日常健康管理第一入口、医生决策前后的数据助手和长期执行系统。

---

## 0. 结论

当前项目不是缺“AI 健康 app”的基础能力, 而是缺一个稳定的 **Health Operating Loop**:

```
感知数据 -> 形成今日身体状态 -> 生成可执行计划 -> 陪用户执行 -> 自动验证结果 -> 更新个人模型
```

代码里已经有可复用资产:

| 层 | 已实现资产 | 证据 |
|---|---|---|
| 身体状态 | HealthTwin 13 分区, 包含生理、身体成分、化验、CGM、药物、补剂、基因、环境、行为、心理、慢病、目标、freshness | `backend/app/twin/schema.py`, `backend/app/twin/builder.py` |
| Agent 裁决 | Orchestrator + specialists + Safety Guardian + cross review/arbitration | `backend/app/orchestrator/`, `backend/app/agents/` |
| 第一阶段领域 | 饮食方案、运动方案、睡眠分析、代谢专科、慢病风险、体检解释、基因报告 | `backend/app/services/diet_plan.py`, `movement_plan.py`, `chronic_risk_service.py`, `exam_explain_service.py`, `genetic_report.py` |
| 执行闭环 | ActionCard、WSCLA、outcome_grader、verify_outcomes、Open Loop、APNs/Telegram/doctor weekly | `backend/app/models/action_card.py`, `backend/app/tasks/outcome_grader.py`, `backend/app/api/admin_wscla.py` |
| Mobile First | Expo/RN 主入口, Today、饮食、运动、睡眠、体检、基因、目标、进度、doctor-loop、family 等路由 | `mobile/app/`, `mobile/services/` |

最大缺口是产品对象还不是“每天的操作计划”。首页目前是告警、周建议、快照、入口的组合; 饮食/运动/睡眠各自能问 Agent, 但还没有一个统一的 **Daily Operating Plan** 告诉用户今天吃什么、练什么、睡眠怎么调、补什么、哪些指标要测、何时需要问医生。

因此后续 12 周不要先加更多 specialist 或数据源, 应优先把体重与代谢健康做成一个可用的闭环产品。

---

## 1. 外部调研依据

### 1.1 监管与产品边界

- FDA Clinical Decision Support guidance 的核心边界是: 软件如果让医护/用户能独立审查建议基础, 且不替代专业判断, 风险更低; 这支持我们做“可解释建议 + evidence trace + doctor handoff”, 而不是做黑盒诊断或处方。参考: FDA Clinical Decision Support Software FAQ, https://www.fda.gov/medical-devices/software-medical-device-samd/clinical-decision-support-software-frequently-asked-questions-faqs
- FDA General Wellness guidance 对低风险健康生活方式软件相对友好, 但疾病诊断/治疗声明会进入医疗器械风险区。参考: FDA General Wellness Policy for Low Risk Devices, https://www.fda.gov/regulatory-information/search-fda-guidance-documents/general-wellness-policy-low-risk-devices
- 结论: 产品文案和 Agent 输出必须坚持“风险提示、生活方式建议、复查/就医建议、医生前后数据助手”, 避免“诊断你有 X / 调整药量 / 替代医生”。

### 1.2 体重与代谢第一阶段的证据锚点

- CDC National Diabetes Prevention Program 以减重 5-7% 和每周 150 分钟中等强度活动作为糖尿病预防生活方式项目的核心目标。参考: https://www.cdc.gov/diabetes-prevention/lifestyle-change-program/index.html
- CDC 成人运动建议: 每周至少 150 分钟中等强度活动, 并每周至少 2 天肌肉强化。参考: https://www.cdc.gov/physical-activity-basics/guidelines/adults.html
- USPSTF 建议对成人肥胖提供或转介密集、多组成部分行为干预。参考: https://www.uspreventiveservicestaskforce.org/uspstf/recommendation/obesity-in-adults-interventions
- AASM 成人睡眠共识建议成年人每晚睡 7 小时或以上。参考: https://aasm.org/resources/pdf/pressroom/adult-sleep-duration-consensus.pdf
- IDF 代谢综合征定义把中心性肥胖作为关键条件, 中国/南亚人群常用腰围阈值约男 90 cm、女 80 cm。参考: https://idf.org/media/uploads/2023/05/attachments-30.pdf

### 1.3 数据平台与移动端方向

- Apple HealthKit 是 iOS 读取和写入健康/健身数据的正式框架, 适合补齐 Apple Watch 用户数据。参考: https://developer.apple.com/documentation/healthkit
- 当前项目已有 Garmin、Withings、Apple Health export adapter 文档和部分实现。策略应是: 先把 Garmin/Withings/手动/体检/基因形成闭环; 当第一阶段真实用户需要 Apple Watch 且 Garmin 覆盖不足时, 再做 HealthKit native build, 不要为了“数据源完整”提前扩大维护面。

---

## 2. 当前代码完成度

### 2.1 Agent Native 底座

已实现:

- `HealthTwin` 是正确方向: 数据先进入结构化 twin, 再给 Agent 使用, 避免直接把数据库行拼 prompt。
- `AgentExecutor` 支持 streaming、多轮 tool call、写库前确认、上下文 deeplink 注入。
- `Orchestrator` 已有 specialist 并行、memory 注入、hit-rate、cross review/arbitration。
- `SafetyGuardian` 是 deterministic 层, 符合健康场景需要。
- `ActionCard` 已覆盖建议、用户决策、验证窗口、metric_key、baseline、target、accuracy、outcome、WSCLA 生命周期字段。

明显问题:

- `backend/app/services/agent_executor.py` 中 `sources_used.extend(...)` 位于 `sources_used: list = []` 初始化之前。这个路径需要加回归测试并修掉, 否则 done meta 的 sources_used 可能异常。
- `docs/HARNESS.md` 已列出 strict tool schema、context compaction、tool_choice 强制、LLM-as-judge eval 等缺口, 但代码尚未系统落地。
- Agent 输出和 ActionCard 之间还不是稳定协议: proposed cards、inline cards、weekly advice、manual cards 都存在, 但没有统一的 DailyPlan/InterventionEvent 语义。

### 2.2 体重与代谢能力

已实现:

- `WeightRecord` 记录体重、体脂、肌肉、BMI、BMR、代谢年龄等。
- `BloodPressureRecord` 记录血压并有统计。
- `BasicHealthData`/体检指标进入化验上下文。
- `MetabolicSpecialist` 能看血糖、HbA1c、血脂、BMI、CGM、能量平衡, 并产出 LDL/HbA1c/TG 实验卡。
- `ChronicRiskService` 有心血管风险、代谢综合征、90 天趋势。
- `DietPlan` 和 `MovementPlan` 已把 TDEE、蛋白、训练负荷、基因偏好、action_cards 关联到移动端。

关键缺口:

- 没有腰围模型和记录 API。代谢综合征当前用 BMI 替代中心性肥胖, 这在第一阶段不够。
- 没有“体重与代谢 program”对象: 目标体重、目标腰围、目标周期、每周热量赤字、蛋白目标、训练目标、复查计划都散落在目标/卡片/方案里。
- 缺血压家庭测量 protocol: 早晚/连续 7 天/平均值/测量姿势/设备来源/异常升级。
- CGM schema 和 API 存在, 但缺面向真实第一阶段的“是否需要 CGM、何时接入、如何解释餐后峰值”的产品门槛。
- outcome 评分有两套任务: `verify_outcomes.py` 和 `outcome_grader.py`, 语义重叠。应收敛到一条主评分路径, 否则 WSCLA 和 specialist hit-rate 口径会漂移。

### 2.3 移动端体验

已实现:

- Today tab 有环境、四入口、critical/high 告警、本周建议、身体快照、AI 会诊入口。
- 饮食页支持文字/拍照估算、编辑、删除、按天汇总, 并能带上下文进 chat。
- 睡眠页支持 7/14/30 天、睡眠债、SpO2、AI 深度分析、context chat。
- `mobile/utils/agentContext.ts` 已抽出饮食/睡眠/运动/安全/体检/Today 的 context 工具函数。
- Doctor loop、family、memory、reasoning trace、specialist、my-progress 等入口已存在。

关键缺口:

- Today 还不是“今日操作系统”。用户看到的是信息块, 不是“今天先做这 3 件事, 晚上我来验证”。
- 饮食/运动/睡眠页面能聊, 但不能从同一个计划对象进入: 饮食建议不知道今天训练强度, 运动建议不知道今日热量和睡眠债, 睡眠建议不知道咖啡因/晚餐/训练时间。
- Mobile 仍有 lint/test debt, 之前全量 mobile lint 已知在 `consultations.tsx`, `monthly-reports.tsx`, `workout-detail.tsx`, `ChatBubble.tsx` 等处失败。第一阶段不应在坏基础上继续堆 UI。

### 2.4 数据与医生协作

已实现:

- 体检 PDF/CSV/JSON/image OCR 导入和校正已较完整。
- 基因 TXT/PDF 导入、SNP 字典、基因报告、SNP 详情已经有较强基础。
- Doctor report、doctor-loop、clinical journal、family 初始能力存在。

关键缺口:

- 医生/家人权限模型仍弱: 谁能看什么、有效期、撤销、审计、导出边界没有形成主流程。
- 目前 doctor loop 更像“报告导出”, 还没有形成“医生建议 -> 用户确认 -> Agent 转成执行计划 -> 回传结果”的闭环。
- 基因数据属于高敏数据, 需要更强的导出/删除/加密/审计策略和 UI 告知。

---

## 3. 产品北极星

### 3.1 一句话体验

每天打开 App, 用户应该看到:

> 今天你的代谢目标是“稳血糖 + 保肌肉减脂”。上午测一次腰围/体重; 午餐蛋白补到 45g; 今天 readiness 偏低, 只做 35 分钟 Zone 2; 晚上 21:30 后停止进食; 我会在 7 天后用体重趋势、腰围、睡眠分、静息心率和饮食完成度评估是否有效。

### 3.2 北极星指标

第一阶段不能只看 DAU, 要看“操作系统是否真的改善代谢”。

| 指标 | 定义 | 目标 |
|---|---|---|
| WSCLA | safe completed learning actions / week | 4 周内 ≥ 3/周/活跃用户 |
| Metabolic Outcome Delta | 体重、腰围、血压、TG/LDL/HbA1c、睡眠、VO2max 的综合改善 | 12 周能展示趋势 |
| 7-day Data Completeness | 体重/腰围/饮食/睡眠/运动/BP 的 7 天完整度 | 核心用户 ≥ 70% |
| Plan Adherence | Daily Operating Plan 中行动完成比例, 按设备/自报置信度加权 | ≥ 60% |
| Trust Score | 建议有引用、有 fresh 数据、有验证结果、有纠错入口 | 逐周上升 |
| Safety Escalation Precision | high/critical 告警误报率、就医建议点击/确认 | 误报率下降 |

---

## 4. 目标架构

### 4.1 新增核心对象

#### DailyOperatingPlan

每天生成一次, 可被用户调整, 晚间/次日验证。

字段建议:

```text
id, user_id, plan_date, primary_goal
state_summary: {metabolic_status, readiness, sleep_debt, safety_flags, data_freshness}
actions: [
  {domain, title, why, when, duration, metric_key, target_value, evidence_level, safety_notes, source_ids}
]
nutrition_targets: {calories, protein_g, fiber_g, water_ml, meal_timing}
movement_targets: {intensity, zone_minutes, strength_plan, recovery_rule}
sleep_targets: {bedtime_window, caffeine_cutoff, dinner_cutoff, wind_down}
measurements: {weight, waist, bp, glucose, symptoms}
doctor_escalation: {needed, reason, suggested_specialty, report_id}
verification: {window_days, metrics, check_back_date}
status: draft | active | completed | archived
```

#### MetabolicProgram

跨 12 周的计划对象, 不是一天一张卡。

```text
goal_type: weight_loss | lipid | glucose | blood_pressure | recomposition
baseline: weight, waist, BMI, body_fat, BP, HbA1c, TG, LDL, HDL, sleep, VO2max
target: 5-7% weight loss, waist delta, lab target, BP target
protocol: calorie_deficit, protein_per_kg, exercise_minutes, strength_days, sleep_hours
review_cadence: weekly, monthly, lab_recheck_days
contraindications: meds, conditions, safety flags
```

#### InterventionEvent

ActionCard 是用户可见卡片, InterventionEvent 是事实流。

```text
event_type: suggested | accepted | adjusted | started | self_reported_done | device_verified | graded | dismissed
confidence: 0-1
source: mobile | agent | device | doctor | system
linked_card_id, linked_plan_id, linked_metric
```

这个对象能把 WSCLA、医生指令、daily plan、ActionCard、metric grading 串起来。

### 4.2 Agent 分层

| 层 | 责任 | 用 LLM 吗 |
|---|---|---|
| Data Ingestion | 接入、清洗、freshness、confidence、用户校正 | 少量 OCR/解析 |
| Deterministic Safety | 红线、药物/补剂/PGx、血压血糖、训练过载 | 不依赖 LLM |
| State Builder | HealthTwin + Daily State + data gap | 不依赖 LLM |
| Planner | 生成 DailyOperatingPlan, 引用目标/规则/用户约束 | LLM + structured schema |
| Specialist Review | 饮食、运动、睡眠、代谢、药物、心理等给建议 | 混合 |
| Arbiter | 冲突裁决、优先级、风险降级 | LLM + rules |
| Executor | 通知、打卡、下单、日历、医生报告 | 确认后执行 |
| Evaluator | 评分、WSCLA、长期个人响应模型 | 规则 + 统计, LLM 只做叙事 |

---

## 5. 12 周执行路线

### Phase 0: 稳定闭环和口径 (0-2 周)

原则: 不做大新功能, 先让闭环可信。

| 项 | 任务 | 文件/模块 | 验收 |
|---|---|---|---|
| P0.1 | 修 `agent_executor` sources_used 初始化 bug, 加回归测试 | `backend/app/services/agent_executor.py`, `backend/tests/` | streaming done meta 正常含 sources_used |
| P0.2 | 收敛 outcome 评分路径, 明确 `verify_outcomes` vs `outcome_grader` 谁是主路径 | `backend/app/tasks/` | WSCLA、specialist hit-rate、monthly report 口径一致 |
| P0.3 | 加腰围模型/API/schema/Twin 字段 | `backend/app/models/`, `api/`, `twin/schema.py` | 代谢综合征不再只能 BMI 替代 |
| P0.4 | DailyOperatingPlan schema + 只读 API v0 | `backend/app/models/daily_operating_plan.py`, `api/daily_plan.py` | 可返回今天 state/actions/verification |
| P0.5 | Today tab 读取 Daily Plan, 先只展示 3 件事 | `mobile/app/(tabs)/index.tsx` | 首页从 dashboard 变成 action plan |
| P0.6 | 全量关键测试与 mobile lint debt 建账 | `backend/tests`, `mobile` | 新增代码测试通过, 旧 lint debt 有清单 |

### Phase 1: 体重与代谢 MVP (2-6 周)

目标: 让单个用户完成一个 4 周可观察的代谢改善 loop。

| 项 | 任务 | 验收 |
|---|---|---|
| P1.1 | MetabolicProgram v0: 目标、baseline、12 周 target、每周 review | 创建 program 后自动生成周目标 |
| P1.2 | 代谢 intake: 体重、腰围、BP、饮食、睡眠、运动、化验完整度 | data gap 有明确下一步 |
| P1.3 | Daily Plan planner: 吃什么、怎么练、怎么睡、测什么 | 每日 3-5 条行动, 都有 metric/evidence/check_back |
| P1.4 | 饮食方案升级: TDEE + 蛋白 + fiber + meal timing + next meal | 和训练/睡眠状态联动 |
| P1.5 | 运动方案升级: readiness + ACWR + 150 min/week + strength 2 days | readiness 低时自动降级 |
| P1.6 | 睡眠方案升级: 7h 目标、睡眠债、咖啡因 cutoff、晚餐 cutoff | 睡眠目标进入 Daily Plan |
| P1.7 | 周复盘: 体重趋势、腰围、饮食完成度、运动分钟、睡眠、BP | 每周形成一份 plain-language review |

### Phase 2: 执行力和转化 (6-10 周)

目标: 从“建议”变成“帮用户做完”。

| 项 | 任务 | 验收 |
|---|---|---|
| P2.1 | InterventionEvent 落库和埋点 | 每个行动从建议到评分有事件链 |
| P2.2 | L2 一键下单: 饮食/补剂/食材 deeplink, 先用 URL, 不接 native SDK | 用户能从饮食计划进入购买/准备 |
| P2.3 | 智能提醒: 只提醒 Daily Plan 中当下可执行事项 | 通知点击进入对应行动 |
| P2.4 | 被动验证: 设备数据证实运动/睡眠; 饮食和腰围保留自报置信度 | adherence_confidence 不再全靠 checklist |
| P2.5 | WSCLA dashboard 加 series 和漏斗 | suggested -> accepted -> completed -> graded |

### Phase 3: 医生前后助手 (10-16 周)

目标: 不替代医生, 但把医生前后的数据准备和执行跟踪做好。

| 项 | 任务 | 验收 |
|---|---|---|
| P3.1 | Doctor Report v2: 30/90 天代谢包, 含数据源、freshness、趋势、行动、效果 | 一键导出给医生 |
| P3.2 | 医生建议录入: 用户手动/拍照/OCR 输入医嘱, Agent 转 action plan 前需用户确认 | 医嘱进入 UserDirective/ActionCard |
| P3.3 | 家人/医生权限模型: 分享范围、有效期、撤销、审计 | 不泄露基因/用药默认隐私 |
| P3.4 | 高风险升级路径: BP/血糖/胸痛/药物/PGx 等 | 告警有“现在做什么 + 告诉医生什么” |

### Phase 4: 个体响应模型 (4-6 个月)

目标: 从“循证建议”进化到“这个用户对什么有效”。

| 项 | 任务 |
|---|---|
| P4.1 | N-of-1 实验库: 晚餐提前、咖啡因 cutoff、Zone2、蛋白、fiber、钠摄入 |
| P4.2 | Personal Response Model: 哪类干预对体重/睡眠/HRV/BP 有效 |
| P4.3 | CGM optional track: 有明确糖代谢风险或用户愿意佩戴时再接 |
| P4.4 | Knowledge Graph 从事实记忆扩到 intervention response |

---

## 6. 第一阶段详细产品面

### 6.1 Today = 操作台, 不是首页

首页首屏顺序:

1. **Today Plan**: 今天最重要 3 件事。
2. **Why today**: 基于哪些数据, 数据有多新。
3. **Measure now**: 今天缺什么数据, 例如腰围/BP/体重。
4. **Safety first**: high/critical 告警。
5. **Progress**: 7 天/30 天改善。

### 6.2 Metabolic Program 首版

用户输入或系统建议:

- 当前体重、目标体重、腰围、身高、性别、年龄。
- 最近化验: LDL/TG/HDL/HbA1c/空腹血糖/ALT/尿酸。
- BP 最近 7 天。
- 睡眠、训练、步数、HRV。
- 饮食记录可信度。

系统输出:

- 12 周目标: 体重 5-7% 或更保守目标, 腰围变化, BP/lab 复查目标。
- 每周目标: 运动分钟、力量次数、蛋白、fiber、热量区间、睡眠窗口。
- 每天计划: next meal、运动处方、睡眠 cutoff、测量任务。

### 6.3 医疗安全文案

所有代谢/血压/血糖/药物相关输出加边界:

- “这不是诊断或处方。”
- “如果指标达到 X 风险阈值, 建议咨询医生/急诊。”
- “药物剂量不要自行调整。”
- “如有已诊断疾病或怀孕等特殊情况, 以医生建议为准。”

---

## 7. 工程任务拆解

### 7.1 Backend

| 任务 | 说明 | 测试 |
|---|---|---|
| Add `WaistRecord` | user_id/date/waist_cm/source/notes, PostgreSQL migration | CRUD + user_id 隔离 |
| Extend `BodyCompositionState` | waist_cm, waist_to_height_ratio, central_obesity_flag | Twin builder tests |
| Add `DailyOperatingPlan` model/API | plan_date unique per user, JSONB actions/state/verifications | API contract tests |
| Add `MetabolicProgram` model/API | 12 周 program + baseline/target/protocol | service unit tests |
| Add `InterventionEvent` | 事件流支撑 WSCLA funnel | lifecycle tests |
| Fix `agent_executor` sources_used | 初始化顺序 + test | streaming meta test |
| Consolidate graders | 明确主评分任务, 删除或降级重复任务 | outcome tests |
| Add strict plan schema | Pydantic schema for planner output | invalid JSON/schema tests |

### 7.2 Mobile

| 任务 | 说明 | 测试 |
|---|---|---|
| `mobile/services/dailyPlan.ts` | 拉取 DailyOperatingPlan | service tests |
| `TodayPlanPanel` | 首页首屏展示 3 件事 | component tests |
| `MetabolicProgramScreen` | baseline、目标、进度、周复盘 | route test |
| `MeasurementCapture` | 体重/腰围/BP 快速记录 | form tests |
| `PlanActionSheet` | 接受/调整/完成/稍后/不适合 | action lifecycle tests |
| `DataFreshnessChip` | 显示“基于昨晚睡眠/3 天前体重” | snapshot |
| Fix lint debt | 先修 touched files, 再逐步清全量 | `npm run lint` |

### 7.3 Ops/Privacy

| 任务 | 说明 |
|---|---|
| Sentry DSN 状态确认 | 代码已存在, 要确认线上 DSN 和 mobile build 注入 |
| Audit log for sharing/doctor export | 分享基因/体检/医生报告必须审计 |
| Data export/delete | 基因、体检、wearable、Action history 可导出和删除 |
| PII redaction | Sentry/logs 不记录聊天全文、基因明细、token |
| Deployment discipline | 代码走 main, commit/push 后按 `deploy.sh`; mobile JS-only 走 OTA, native 变更走 EAS/TestFlight |

---

## 8. 不做清单

| 不做 | 原因 | 触发条件 |
|---|---|---|
| 不做 AI 诊断/处方 | 合规风险高, 也不符合产品定位 | 有持牌医生闭环和法务边界后再评估 |
| 不接 native WeChat SDK | 破坏 OTA, 审核和维护成本高 | L2 URL deeplink 转化明显不足 |
| 不先做 IoT 厨电 | 数据价值低于腰围/BP/饮食执行 | Metabolic MVP 留存稳定后 |
| 不做通用心理/问诊大而全 | 第一阶段聚焦体重代谢 | 代谢闭环跑通后 |
| 不盲接更多 wearables | 数据源会扩大维护面 | 当前用户 Garmin/Withings/手动不足以支撑核心指标 |
| 不做 Android | iOS/TestFlight 反馈环更快 | 第 10 个外部活跃用户明确需要 |

---

## 9. 风险与对策

| 风险 | 表现 | 对策 |
|---|---|---|
| 医疗越界 | Agent 输出像诊断/处方 | deterministic safety + wording guard + doctor handoff |
| 数据缺失导致幻觉 | 没腰围/化验却给明确代谢判断 | data gap first, no data no conclusion |
| 用户执行成本高 | 建议多但做不完 | Daily Plan 最多 3-5 件事, 可调整 |
| 验证噪声 | 没做到但指标碰巧变好 | adherence_confidence + device verification |
| 隐私风险 | 基因/体检/聊天外泄 | 最小化日志、审计、导出/删除、分享权限 |
| 工程复杂度 | 多模型多任务口径漂移 | DailyOperatingPlan + InterventionEvent 收敛语义 |

---

## 10. 近期最小可执行切片

第一周建议只做下面 6 件:

1. 修 `agent_executor` sources_used bug。
2. 新增腰围记录模型/API/Twin 字段。
3. 新增 DailyOperatingPlan schema + mock planner service。
4. Today tab 首屏展示 Daily Plan 3 件事。
5. outcome 评分任务口径统一。
6. 写 1 个端到端测试: 用户有体重/腰围/BP/睡眠/饮食 -> 生成 today plan -> 接受行动 -> 到期评分 -> WSCLA 增加。

验收标准:

- 用户每天打开 App 看到的是“今天该做什么”, 不是指标面板。
- 每条建议都有数据依据、执行时间、验证指标和风险边界。
- 至少 1 条体重/代谢行动能从建议到完成到自动评分闭环。

---

## 11. 规划状态

这份文档应取代“继续散点加功能”的默认方向, 但不删除已有计划。与现有计划关系:

- `2026-05-14-share-and-context-rollout.md`: 保留, 其中 L2 下单和 WSCLA funnel 进入本规划 Phase 2。
- `2026-05-04-complete-product-plan.md`: 本文继承 Agent Native/Trust Loop 方向, 但把第一阶段重心收束到“体重与代谢 Daily Operating Plan”。
- `STRATEGY-2026.md`: 本文是基于当前代码状态和用户最新目标的执行化版本。

下一步如果进入实现, 应按 `docs/plans/2026-05-14-agent-native-health-os-roadmap.md` 的 Phase 0 切任务, 每个任务独立 commit/push, JS-only mobile 改动优先 OTA 验证。
