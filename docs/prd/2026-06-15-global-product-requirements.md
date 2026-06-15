# Reva Personal Health OS 全局产品需求说明书

> ⚠️ **已被取代(2026-06-15)**:本文为历史素材。唯一权威 PRD 见 [`reva-personal-health-os-prd.md`](reva-personal-health-os-prd.md),已自洽合并本文(TO-BE)+ AS-IS 基线 + 协议双轨 + 多轮外部分析。请勿据本文做新设计。

> 日期: 2026-06-15  
> 状态: v0.1 代码事实驱动 PRD, 用于下一轮产品重设计  
> 范围: 后端、Mobile、Mac App、Web、Apple Watch / HealthKit、OpenClaw / MCP 外部 Agent 入口  
> 目标: 把现有健康系统从“功能集合”重构为“面向中年人持续变健康的时间、日程和可穿戴驱动 Personal Health OS”

---

## 0. 一句话结论

当前项目已经不是早期健康记录应用。代码里已经存在 Digital Health Twin、Biomarker 标准化、InterventionCycle、DailyOperatingPlan、ActionCard、InterventionEvent、Health Operating Review、多专家 Agent、安全规则、多可穿戴数据源、Mobile 主体验、Mac 桌面工作台、Web 管理/历史体验、OpenClaw/MCP 外部 Agent 能力。

真正的下一阶段不是继续横向加功能,而是把这些能力收敛成一个一等公民产品对象:

> **Health Agenda: 基于时间、日程、可穿戴状态、体检/化验、训练计划、用药/补剂和个人目标生成的健康执行日程。**

用户每天不应该面对一堆指标和入口,而应该得到:

1. 今天身体状态如何。
2. 今天最重要的 1-3 件事是什么。
3. 哪些提醒会在什么设备上出现。
4. 哪些测量、体检、复查、训练应该被安排。
5. 8-12 周后如何验证自己是否变健康。

---

## 1. 阅读和 Review 边界

### 1.1 本轮实际阅读范围

本 PRD 基于仓库当前代码和文档。阅读方法是“全局清点 + 关键链路深读 + 三端核对”,不是把依赖、构建产物和缓存文件当作产品代码逐行复述。

排除项:

- `node_modules`, `.venv`, `venv`, `.next`, `dist`, `build`, `coverage`, `htmlcov`, `__pycache__`, `.pyc`。
- Swift build 缓存、mini-program dist 构建产物等生成文件。

清点结果:

- 一方代码/文档约 2700+ 文件。
- 后端最大,其次是 Mobile、Frontend、Packages、Docs、Mac App。
- 后端 API 覆盖 auth/admin/profile/vitals/diet/supplements/exercise/devices/AI/agent/analytics/environment/scheduling/genetics/family/lifestyle 等大量域。
- Mobile 是当前主体验,Mac 是桌面执行和导入工作台,Web 是历史功能、深度页面和后台集合。

### 1.2 深读的关键证据链

后端:

- `backend/app/api/main.py`: API 注册和产品域分层。
- `backend/app/twin/schema.py`, `builder.py`, `snapshots.py`: Health Twin、快照和数据来源。
- `backend/app/models/twin_snapshot.py`: 版本化 Twin 快照。
- `backend/app/models/biomarker_observation.py`, `backend/app/biomarkers/definitions.py`, `backend/app/services/biomarker_sync.py`: biomarker 标准化。
- `backend/app/models/intervention_cycle.py`, `backend/app/services/intervention_cycle_service.py`: 8-12 周干预周期和 outcome metric。
- `backend/app/services/daily_operating_plan.py`, `backend/app/api/daily_plan.py`: 每日计划、行动反馈和事件。
- `backend/app/services/health_operating_review.py`: 7/30/90 天复盘。
- `backend/app/models/action_card.py`, `backend/app/models/intervention_event.py`: 用户可见行动和执行事件。
- `backend/app/orchestrator/*`, `backend/app/agents/safety_guardian/*`, `backend/app/services/advice_guard.py`: 多专家、冲突审查、安全规则和建议守门。
- `backend/app/services/device_source_priority.py`, `device_comparison_service.py`, `recovery_decision.py`: 多设备来源优先级、一致性评分、训练决策灯。
- `backend/app/api/devices.py`, `backend/app/services/device_adapters/healthkit.py`: HealthKit / Apple Watch / RingConn / Garmin 等来源导入。
- `backend/app/api/quick_record.py`, `backend/app/api/diet.py`, `backend/app/services/llm/tool_validator.py`: 文本/语音/图像食物记录和工具守门。
- `backend/eval/`, `backend/tests/`: safety/recovery/insight/orchestrator/retrieval eval 与大量回归测试。

Mobile:

- `mobile/app/(tabs)/index.tsx`: 当前主首页和 Agent 工作区。
- `mobile/components/dashboard/TodayPlanPanel.tsx`: Daily Plan 的移动端执行卡。
- `mobile/services/dailyPlan.ts`, `mobile/services/behaviorLoopReminders.ts`, `mobile/hooks/useBehaviorLoopReminders.ts`: 行动反馈和 Apple Watch 镜像通知。
- `mobile/services/appleHealth.ts`, `mobile/app/device-sources.tsx`: HealthKit 多来源读取、设备来源展示。
- `mobile/services/agentAgenda.ts`, `mobile/components/dashboard/AgentAgendaPanel.tsx`: 移动端已有前端聚合型 Agenda 雏形。
- `mobile/app/voice-chat.tsx`, `mobile/hooks/useVoiceConversation.ts`: 语音对话、云端 TTS、health_record 工具捕捉。
- `mobile/app/diet.tsx`, `mobile/services/diet.ts`: 饮食文本/图片/常吃食物入口。

Mac:

- `apps/mac/README.md`: Swift-native Mac App 定位和 P0 状态。
- `apps/mac/Sources/HealthAgentMac/App/AppRootView.swift`: 三栏导航和桌面入口。
- `apps/mac/Sources/HealthAgentMacCore/DesktopBootstrapService.swift`: 桌面 bootstrap API。
- `apps/mac/Sources/HealthAgentMacCore/DesktopDashboardPresentation.swift`: 今日驾驶舱、行动、记录、任务、输入 inbox。
- `apps/mac/Sources/HealthAgentMac/Features/QuickCapture/QuickCaptureManager.swift`: 全局快捷记录。
- `apps/mac/Sources/HealthAgentMacCore/FileIntakeService.swift`: 本地文件分类和 hash。
- `apps/mac/Sources/HealthAgentMacCore/DeviceSourcesClient.swift`: 桌面端设备来源可视化。

Web / 外部入口:

- `frontend/src/app/page.tsx`, `dashboard/page.tsx`, `digital-twin/page.tsx`, `settings/components/AppleWatchSection.tsx`: Web 首页、仪表盘、数字孪生、Apple Health 文件导入。
- `packages/mini-program/src/app.config.ts`: 小程序历史入口。
- `mcp-server/README.md`: MCP 暴露健康查询/记录/分析工具。
- `openclaw-skills/README.md`: OpenClaw 多渠道技能分发。

文档:

- `docs/prd/personal-health-os-prd.md`
- `docs/plans/2026-05-18-health-operating-loop-plan.md`
- `docs/plans/2026-05-20-protocol-first-health-agent-design.md`
- `docs/plans/2026-06-15-apple-watch-ultra3-health-wrist-companion.md`
- `docs/plans/2026-06-15-multi-wearable-health-router-roadmap.md`
- `docs/AGENT_NATIVE_HEALTH_OS_ARCHITECTURE.md`
- `docs/HARNESS.md`

---

## 2. 产品北极星

### 2.1 定位

**Reva Personal Health OS** 是一个面向中年人的个人健康操作系统。它把可穿戴设备、体检/化验、日常饮食、训练、药物/补剂、症状、环境、日程和知识库融合成可执行、可验证、可复盘的健康议程。

对用户的承诺不是“回答健康问题”,而是:

> 帮你把每天、每周、每季度该做的健康行动安排好,在合适的设备上提醒你执行,并用指标验证是否真的变好。

### 2.2 第一目标用户

35-60 岁中年高强度工作人群:

- 有代谢风险: 体重、腰围、血压、血脂、血糖、脂肪肝、尿酸、HbA1c、肝酶等。
- 有恢复/训练问题: 睡眠不足、HRV 低、RHR 上升、训练过载、久坐、精力波动。
- 已佩戴或愿意佩戴可穿戴设备: Apple Watch、RingConn、Garmin、Withings、CGM、家用血压计、智能秤。
- 有付费意愿,愿意做 8-12 周个人健康实验。
- 需要系统替他安排“什么时候测、什么时候练、什么时候复查、什么时候别练”。

### 2.3 北极星指标

建议把 North Star 从泛化 DAU 改为:

> **每周完成的、安全、证据可追溯、能进入结果验证的健康行动闭环数量。**

简称 WSCLA,但定义要收紧:

- safe: 通过 Safety Guardian / Advice Guard / contraindication 检查。
- evidence-backed: 有证据来源或明确标注为低置信观察。
- scheduled: 被 Health Agenda 安排到具体时间或时间窗。
- executed: 有用户确认、设备自动记录或人工记录。
- measurable: 绑定至少一个验证指标或复查节点。

---

## 3. 当前产品能力地图

### 3.1 已经具备的一等能力

| 能力 | 代码现状 | 产品判断 |
|---|---|---|
| Digital Health Twin | `HealthTwin` schema 覆盖生理、体成分、实验室、CGM、用药、补剂、基因、表观遗传、环境等; builder 并行填充多域 | 已是中枢,下一步重点是质量分、快照引用和议程消费 |
| Twin Snapshot | `TwinSnapshot` 已存在,按 hash 去重,支持 purpose 和 quality_grade | 旧 PRD 的 G1 已部分完成; quality 仍过粗 |
| Biomarker 标准化 | `BiomarkerObservation`、定义表、medical_indicators 同步已经存在 | 旧 PRD 的 G3 已部分完成;仍需更完整参考范围、单位和实验室上下文 |
| InterventionCycle | `InterventionCycle` + `OutcomeMetric` + start/recheck/active API 已存在 | 旧 PRD 的 G4 已完成基础;需要从代谢扩到通用 Health Program |
| Daily Operating Plan | 每日行动、急性病训练休息、测量自动化、行动反馈 API 已存在 | 是 Agenda 的当日视图,但还不是跨日程/跨对象统一议程 |
| Action Feedback | `InterventionEvent` 记录 completed/skipped/adjusted 等事件 | 事件流是个人学习和 outcome 的关键资产 |
| 7/30/90 Review | `health_operating_review.py` 已按执行事件和部分指标做复盘 | 需要扩到 labs、训练、检查、体检和 program 级 outcome |
| Multi-agent | Orchestrator + specialists + cross review + safety | 不缺专家数量,缺统一计划/议程和人机执行协议 |
| Safety Guardian | 50+ 规则模块、DDI/DSI/PGx/训练/CGM/症状等 | 产品主线必须把它前置成所有建议的硬闸门 |
| Advice Guard | 用户可见建议要求 evidence_tier/confidence/claim_boundary 等 | 应成为所有新 PRD 需求的验收条件 |
| Multi-wearable | HealthKit 导入、多源优先级、一致性比较、训练决策灯已存在 | 下一步是正式产品化为 Wearable Router |
| Voice / food input | 语音对话、quick-record、饮食文本估算、拍照识别、tool validator | 应合并成低摩擦 Food Capture 协议 |
| Mac App | Swift-native 今日驾驶舱、Agent、快速记录、导入中心、任务中心、Trace | 是桌面工作台,不是移动端替代品 |
| Web | 大量历史页面、仪表盘、后台、Apple Health XML 导入 | 需要收敛为后台/深度分析/历史兼容,不再承担主体验 |
| OpenClaw / MCP | 多渠道技能和健康 MCP server | 是外部 Agent 接入层,需按权限和可审计性治理 |

### 3.2 当前最大产品债

| 债务 | 现象 | 影响 |
|---|---|---|
| 缺统一 Health Agenda | Daily Plan、ActionCard、ReviewSchedule、Reminder、Medication、Training、InterventionCycle、体检复查分散 | 用户不知道“什么时候该做什么”,三端也难统一 |
| 入口过多 | Mobile/Web/Mini Program/Mac/Skills 都有相似记录和分析 | 重设计成本高,用户路径不清 |
| 文档漂移 | README/ARCHITECTURE/PRD 部分仍描述旧状态 | 影响后续设计和开发判断 |
| 数据质量仍粗 | Twin snapshot quality_grade 主要按 source count; freshness/reliability/completeness 未统一 | 建议置信度不能稳定解释 |
| 状态枚举不统一 | Daily Plan 反馈、事件、ActionCard lifecycle、通知 action 存在语义差异 | Outcome 和学习链路容易统计错 |
| Watch 形态未产品化 | 当前主要靠 iOS 本地通知镜像到 Apple Watch,没有完整 Watch companion app | 低摩擦输入和确认还没充分发挥 |
| Web/Mini Program 历史沉积 | Web 有大量独立页面,小程序仍有旧主路径 | 产品叙事和研发重心被稀释 |
| 安全复核需持续 | 既往 review 提到 user_id 旧路由、HTML/XSS、token/localStorage、AutoAddPolicy 等风险 | 健康数据产品必须把安全纳入 PRD 验收 |

---

## 4. 目标产品形态

### 4.1 核心体验

用户每天看到的不是“仪表盘”,而是:

```text
今天身体状态: 黄灯, 可训练但降一级
今天最重要行动:
  1. 午饭后走 10 分钟
  2. 晚餐前优先蛋白, 主食减半
  3. 今晚 22:30 前上床
需要补的数据:
  - 明早空腹体重和腰围
  - 本周补一次袖带血压
  - 8 周后复查 LDL/TG/ALT/尿酸
```

### 4.2 产品主循环

```text
Data In
  Wearables / HealthKit / Garmin / RingConn / BP / scale / CGM / labs / food / voice / symptoms / calendar
    ↓
Health Vault + Source Arbitration
  normalized metrics + source + freshness + confidence
    ↓
Health Twin + Snapshot
  current state + baseline + risk + uncertainty
    ↓
Health Programs
  metabolic / recovery / sleep / training / medication / supplement / checkup
    ↓
Health Agenda
  today / week / month / quarter items
    ↓
Surface Router
  Watch / Mobile / Mac / Web / external agent
    ↓
Execution Events
  completed / skipped / adjusted / auto_observed / confirmed / failed
    ↓
Operating Review
  7 / 30 / 90 day outcome, personal response, next agenda
```

### 4.3 重新设计的信息架构

Mobile 主导航建议收敛为 5 个一等入口:

1. **Today**: 今日状态、最重要行动、Watch/通知反馈、异常和安全提示。
2. **Agenda**: 本周、本月、季度健康日程;测量、训练、体检、复查、用药、补剂。
3. **Capture**: 食物、饮水、症状、体重、腰围、血压、补剂、用药、运动 RPE;支持语音/照片/文本/设备。
4. **Programs**: 代谢、恢复/训练、睡眠、用药/补剂、专项检查等 8-12 周项目。
5. **Review**: 是否变好;指标、执行率、复查结果、个人响应。

Mac 主导航建议保留为桌面工作台:

- Today Dashboard
- Agent
- Record / Quick Capture
- Data Sources
- Imports / Jobs
- Trace
- Labs / Genetics / Knowledge
- Workouts / Goals
- Settings

Web 建议转为:

- Admin / Ops / Observability
- Deep report / shared report
- Historical compatibility pages
- Data import fallback, especially Apple Health XML
- User account / privacy / export / deletion

Mini Program:

- 不作为下一轮核心体验。
- 作为中国渠道历史兼容或轻量记录入口。
- 新功能默认不优先落小程序,除非用户渠道验证需要。

---

## 5. 一等产品对象

### 5.1 HealthAgendaItem

新一轮设计的核心对象是 `HealthAgendaItem`。它不是替代现有模型,而是从现有对象投影出来的统一执行层。

建议字段:

```yaml
id: string
user_id: int
agenda_date: YYYY-MM-DD
time_window:
  start: datetime | null
  end: datetime | null
  label: morning | noon | afternoon | evening | bedtime | anytime
type:
  measurement | training | food | hydration | medication | supplement |
  sleep | recovery | symptom | checkup | lab_recheck | doctor |
  education | review | data_quality | safety
title: string
body: string
priority: 0-100
status:
  scheduled | due | completed | skipped | snoozed | adjusted |
  auto_observed | expired | cancelled | blocked
source:
  object_type: daily_plan_action | action_card | intervention_cycle |
               reminder | medication | supplement | measurement |
               review_schedule | training_plan | safety_alert
  object_id: string | int | null
program_id: string | int | null
cycle_id: string | int | null
evidence:
  evidence_tier: S1 | S2 | S3 | S4 | S5 | D | unknown
  confidence: high | medium | low
  claim_boundary: string
verification:
  metric_codes: string[]
  window_days: int | null
  expected_direction: up | down | stable | none
surface_targets:
  watch: boolean
  mobile: boolean
  mac: boolean
  web: boolean
  external_agent: boolean
notification_policy:
  level: none | passive | normal | critical
  max_prompts_per_day: int
  quiet_hours_respected: boolean
device_context:
  preferred_device: apple_watch | iphone | mac | garmin | ringconn | none
  automation_path: healthkit | garmin | manual | vendor_api | lab_upload | none
audit:
  created_by: system | agent | user | clinician | import
  created_at: datetime
  last_decision_trace_id: string | null
```

### 5.2 HealthProgram

`HealthProgram` 是比 Daily Plan 更长期的目标容器。先做 5 类:

| Program | 目标 | 当前可复用 |
|---|---|---|
| Metabolic Program | 体重、腰围、血压、LDL/TG/HDL/HbA1c/ALT/GGT/尿酸 | BiomarkerObservation, InterventionCycle, DailyPlan, Diet, Review |
| Recovery & Training Program | 今天能不能练、训练负荷、Zone 2、力量、恢复 | Garmin, RingConn, Apple Watch, recovery_decision, workouts |
| Sleep & Breathing Program | 睡眠窗口、HRV、SpO2、呼吸、OSA 风险提示 | Sleep, SpO2 analysis, RingConn, Watch, Garmin |
| Medication & Supplement Program | 用药/补剂依从、安全、DDI/DSI/PGx、疗程 | Medication, Supplement, Safety Guardian |
| Checkup & Screening Program | 年度体检、专项检查、复查、医生沟通 | MedicalExams, Biomarkers, ReviewSchedule, Doctor Loop |

### 5.3 Personal Health Router

把现有 `device_source_priority.py`, `multi_source_merger.py`, `device_comparison_service.py`, `recovery_decision.py` 升级为产品化 Router:

```yaml
metric:
  value: number
  unit: string
  winning_source: ringconn | garmin | apple-watch | withings-app | manual | lab | cgm
  source_reason: string
  freshness_hours: number
  reliability: high | medium | low
  agreement_score: number | null
  safety_policy: normal | worst_value | clinician_ground_truth
```

默认原则:

- RingConn: 睡眠、HRV、夜间血氧、呼吸、皮温、长期低干扰恢复基线。
- Garmin Enduro 2: 训练、户外、GPS、急性负荷、训练准备度、恢复时间、VO2max。
- Apple Watch Ultra 3: 输入、提醒、确认、活动量、步数、即时心率、HealthKit 桥。
- 袖带血压计/智能秤/实验室: 血压、体重、化验等临床或准临床 ground truth。
- 对 SpO2 这类安全下限指标,保留或取最差值,不能让正常来源掩盖危险低值。

---

## 6. 需求清单

### R1. Health Agenda 服务端统一层

目标: 把分散的 Daily Plan、ActionCard、InterventionCycle、Reminder、Medication、Supplement、Training、Measurement、ReviewSchedule 统一成一个可查询、可执行、可审计的议程。

需求:

- `GET /agenda/today`: 返回今天所有 HealthAgendaItem,按时间窗和优先级分组。
- `GET /agenda/range?start=&end=`: 返回周/月/季度议程。
- `POST /agenda/items/{id}/events`: 记录 completed/skipped/snoozed/adjusted/confirmed。
- `POST /agenda/rebuild`: 按最新 Twin、Router、Programs 重新生成议程投影。
- Agenda item 必须引用 source object,避免复制业务事实。
- Daily Plan 仍可保留,但应成为 agenda 的 today view 或一个 source。

验收:

- Mobile、Mac、Watch 看到的是同一批 agenda item。
- 同一个行动在任一端完成后,其他端状态同步。
- 7/30/90 Review 能从 agenda events 复盘执行率。

### R2. 时间和日程驱动的健康管理

目标: 系统不只“建议”,还要安排“什么时候做”。

需求:

- 支持时间窗: 起床后、早餐后、午饭后、运动前、晚餐前、睡前、周末、季度复查。
- 支持 cadence: 每天、每周、每月、每季度、8/12 周复查、按异常触发。
- 支持 event-triggered: 饭后 20-40 分钟、训练结束后 5 分钟、睡眠同步后、体检上传后。
- 支持 quiet hours 和提醒预算。
- 支持 calendar-aware 占位,未来可接系统日历。

验收:

- 用户能看到“本周要测什么、练什么、什么时候复查”。
- 可穿戴状态变化可触发当日训练降级或恢复日程调整。
- 低价值提醒不会超过每日预算。

### R3. Multi-Wearable Health Router v2

目标: 让 Apple Watch、RingConn、Garmin 不是三个 dashboard,而是一个可信状态引擎。

需求:

- 指标级输出 winning_source、source_by_metric、agreement_score、freshness、confidence。
- 训练决策使用 `recovery_decision.py` 的 green/yellow/red 作为 P0,扩展为 Agenda input。
- 设备冲突时降低置信度,而不是平均或假装确定。
- 设备缺失时生成 data_quality agenda item,例如“RingConn 昨晚无睡眠数据,请检查佩戴/同步”。
- 血氧、异常高心率、症状、血压等安全指标保留多源证据。

验收:

- 用户能看到“为什么今天黄灯”。
- 每个关键指标能解释来自哪个设备。
- 无两个设备同一指标时仍可工作,但置信度降低。

### R4. Apple Watch Wrist Companion

目标: Apple Watch 是腕上执行器,不是完整聊天机器人。

v1 功能:

- Today Status: green/yellow/red、置信度、今日最重要行动。
- Action Feedback: 做到了、跳过、稍后、调整。
- Food Voice Capture: 一句话记录食物,手机/后端结构化,手表确认。
- Quick Record: 饮水、补剂、症状、疲劳、情绪、RPE。
- Smart Stack / Complication: 显示当前最该做的一件事或今日完成度。
- 通知: 饭后走路、运动前降级、睡前窗口、用药/补剂、数据缺口。

不做:

- Watch 上长对话。
- Watch 上体检/基因/文档浏览。
- Watch 本地健康判断。
- Watch 常驻监听。

验收:

- 不打开 iPhone 也能完成今日最重要行动反馈。
- 食物语音记录从说完到确认小于 20 秒。
- Watch 通知都能写入 Agenda / InterventionEvent。

### R5. Food Voice Capture 协议

目标: 让“语音记录食物”成为稳定事实流,而不是散落在 chat/quick-record 的副作用。

建议模型:

```yaml
FoodCapture:
  raw_text: string
  captured_at: datetime
  source: apple_watch | siri | mobile_voice | mobile_text | mac_quick_capture
  meal_type: breakfast | lunch | dinner | snack | unknown
  foods:
    - name: string
      quantity_text: string | null
      calories_estimate: number | null
      protein_g: number | null
      carbs_g: number | null
      fat_g: number | null
      confidence: high | medium | low
  total_calories: number | null
  total_protein_g: number | null
  risk_tags: string[]
  confirmation_state: pending | confirmed | edited | discarded
  linked_diet_record_id: int | null
```

v1 可以先不新表:

- 用后端解析服务写 `DietRecord`。
- 把 raw_text、source、confidence、risk_tags 存入 notes/raw JSON。
- 确认/编辑/丢弃写 `HealthEvent` 或 `InterventionEvent`。

追问原则:

- Watch 上最多追问 1 个问题。
- “米饭半碗还是一碗?” “牛肉一掌心还是两掌心?” “无糖还是加糖?”
- 不回答也记录低置信原文。

验收:

- 能稳定记录餐次、食物列表、热量区间、蛋白估计。
- 不追求克级精确,优先支持长期行为分析。
- 饭后走路、睡眠、体重、腰围、血糖/尿酸/血脂 outcome 可关联饮食事件。

### R6. Measurement Automation Protocol

目标: 中年健康改善依赖低频高价值测量,系统必须安排并自动化。

测量类型:

- 每日/每周: 体重、腰围、血压、睡眠、HRV、RHR、步数、训练负荷。
- 条件触发: CGM、SpO2 夜间异常复核、症状加重、训练后 RPE。
- 8-12 周: LDL/TG/HDL、HbA1c、ALT/GGT、尿酸、肾功能、炎症指标等。
- 年度/半年度: 体检、专项检查、医生随访。

需求:

- 每个 measurement item 都要有 automation_path。
- 优先级: vendor/HealthKit 自动 > 外部设备 > 手动输入 > 提醒上传。
- 袖带血压、智能秤、实验室检查作为 ground truth,穿戴趋势只触发提示。
- 过期指标自动进入 Agenda。

验收:

- 用户能看到“为什么系统让他明早测腰围/本周测血压/8 周后复查 LDL”。
- 每个测量要求都有执行说明和替代路径。

### R7. Checkup & Specialty Screening Planner

目标: 把“定期体检、专项检查、复查”产品化,不要只在体检上传后被动解读。

需求:

- 基于年龄、性别、家族史、既往异常 biomarker、症状、可穿戴异常和医生指令生成检查建议。
- 区分 wellness screening、复查、医生就诊、急性红旗。
- 输出:
  - 检查项目
  - 推荐时间窗
  - 理由
  - 数据来源
  - 风险边界
  - 是否需要医生确认
- 所有检查计划进入 HealthAgenda。

中年优先检查域:

- 心血管: 血脂、血压、HbA1c、hs-CRP、Lp(a) 可选、心电/医生判断。
- 代谢: 肝功能、脂肪肝相关、尿酸、肾功能、腰围、体脂。
- 睡眠呼吸: 夜间 SpO2 异常、打鼾/白天嗜睡时提示进一步筛查。
- 运动安全: 高强度训练前风险自查、疼痛/胸闷/晕厥红旗。
- 消化/肠道、肿瘤筛查等应按权威指南和年龄边界,不由 LLM 自由发挥。

验收:

- 用户能看到一个季度/年度检查日历。
- 检查建议不能越界为诊断。
- 高风险建议进入人审或医生确认路径。

### R8. Training Prescription and Readiness Gate

目标: 把“今天能不能练”变成系统每天回答的核心问题。

需求:

- 使用 recovery_decision green/yellow/red 作为训练 gate。
- 输入: RingConn 睡眠/HRV/SpO2/皮温, Garmin training readiness/acute load/recovery time, Apple Watch 活动和主观疲劳,症状/疾病。
- 输出:
  - green: 按计划训练。
  - yellow: 降一级,Zone 2/技术/轻力量。
  - red: 恢复/休息,暂停高强度。
- 训练前 30-60 分钟在 Watch/Mobile 出现。
- 训练后捕获 RPE、疼痛、异常感受和 Garmin workout 事实。

验收:

- 急性病/低血氧/胸闷/高风险症状优先于 Garmin readiness。
- Daily Plan / Agenda 不再出现“休息”和“高强度”冲突。
- 训练决策有 reasons 和 confidence。

### R9. Outcome Proof

目标: 用户持续变健康必须被验证,否则系统只是建议生成器。

需求:

- 每个 HealthProgram 绑定 primary/secondary metrics。
- 每个 agenda action 标注是否影响 outcome。
- 7/30/90 天复盘扩展为:
  - 执行率
  - 指标变化
  - 复查结果
  - 个人响应强弱
  - 下一周期调整
- 支持 temporal association,明确“不等于因果”。
- 对 8-12 周代谢周期输出 baseline -> latest -> target。

验收:

- 用户能回答“我有没有变好,哪些行为可能有用”。
- 系统能给出“继续/调整/停止”建议。

### R10. 三端职责

Mobile:

- 主体验。
- Today、Agenda、Capture、Programs、Review。
- HealthKit 同步、Apple Watch companion 配对、通知、照片饮食、语音对话。

Mac App:

- 深度工作台。
- 快速记录、文件导入、体检/基因/知识导入、Agent 长对话、Trace、任务中心。
- 适合办公场景下复盘和整理。
- 不复制健康判断逻辑。

Web:

- 后台、运维、管理、深度报告、历史兼容、分享页、Apple Health XML fallback。
- 不作为新主体验默认落点。

Apple Watch:

- 腕上执行和反馈。
- 只做轻量 companion。

OpenClaw / MCP:

- 外部 Agent 通道。
- 需要最小权限、审计日志、scope/token 治理。

---

## 7. 非目标和降级项

下一轮重设计应明确不优先做:

- 社交/PK/好友排名。
- Watch 上完整 Agent 聊天。
- 把 Garmin/RingConn/Apple Watch 原厂 App 全量替代。
- 以基因作为第一卖点。
- 补剂电商化作为主路径。
- 宠物健康混入同一产品。
- 小程序作为新功能首发平台。
- 对医疗诊断、治疗、处方做确定性承诺。

保留但降级:

- family health
- NFC
- rhinitis / illness / women's health 单病种追踪
- doctor-loop / consultations
- supplement-products
- legacy Web dashboard pages

---

## 8. 安全、隐私和合规需求

### 8.1 产品级硬约束

- 所有用户数据查询必须经过当前用户身份约束。
- 所有健康建议必须带 evidence/confidence/boundary。
- 高风险建议必须走安全规则和必要的人审/医生确认。
- 可穿戴数据不能被表达成诊断。
- 基因/表观遗传只能作为先验或低置信辅助,不能单独导出复杂疾病行动。
- 用户可导出、删除、撤回授权。
- Token、设备凭证、基因、医疗文件应分域加密和审计。

### 8.2 必须纳入重设计验收的技术 review 项

既往 review 指出过以下风险,新 PRD 下应作为上线前 gate:

- 旧 `/user/{user_id}` 风格路由是否仍可越权。
- Web unsafe HTML rendering/XSS surface。
- localStorage token 暴露面。
- 远程管理 SSH host key policy。
- 依赖安全审计。
- 体检/基因/设备凭证加密 key 分离。
- 重要操作审计日志和隐私导出/删除链路。

---

## 9. 成功指标

### 9.1 用户健康结果

- 8-12 周复查完成率。
- 体重、腰围、血压、LDL/TG/HDL、HbA1c、ALT/GGT、尿酸等改善比例。
- 睡眠时长、HRV、RHR、SpO2 低氧事件、训练负荷平衡改善。
- 用户主观精力、疲劳、运动恢复评分。

### 9.2 行为闭环

- 每周 safe closed-loop actions 数。
- Agenda 完成率、跳过率、调整率、snooze 率。
- 饮食记录天数、蛋白达标天数、饭后步行完成率。
- 测量遵从率: 体重/腰围/BP/复查。
- 训练 gate 遵从率和训练后 RPE 记录率。

### 9.3 数据质量

- 设备连接率。
- HealthKit 同步成功率。
- 各关键指标 freshness。
- 多源 agreement score。
- unknown sourceName 数量和修复速度。

### 9.4 产品体验

- 每日通知数量。
- Watch 行动确认耗时。
- 食物语音记录从发起到确认耗时。
- 首页用户能否在 5 秒内理解“今天该做什么”。
- 7/30/90 Review 打开率。

### 9.5 安全

- Safety Guardian 拦截数。
- Advice Guard 拒绝/降级数。
- 高风险建议人审通过率。
- 工具 validator coercion/rejection 分布。
- 越权/XSS/敏感信息泄露回归测试通过率。

---

## 10. 路线图

### P0: PRD 和 IA 收敛

目标: 让团队围绕同一个产品对象工作。

交付:

- 本 PRD 批准。
- 新信息架构图。
- 三端职责边界。
- HealthAgenda 技术设计。
- 状态枚举统一: action status/event status/notification action。
- README/ARCHITECTURE 更新到当前真实状态。

### P1: Health Agenda MVP

目标: 统一“今天/本周该做什么”。

交付:

- 后端 Agenda projection service。
- Mobile Agenda 页面和 Today 接入。
- Mac Today Dashboard 接入 Agenda。
- Watch 先继续用通知镜像,但事件写入 Agenda。
- Daily Plan action feedback 迁移/兼容 Agenda events。

### P2: Wearable Router + Training Gate 产品化

目标: 让多设备真正驱动每天训练/恢复。

交付:

- Router confidence API。
- Device Agreement Dashboard。
- `exercise-recovery/decision` 接入 Today/Agenda。
- RingConn/Garmin/Apple Watch source explanation。
- 训练前提醒和训练后 RPE capture。

### P3: Food Voice Capture + Watch Companion v1

目标: 用 Watch 解决饮食记录可持续性。

交付:

- Food capture parser。
- Watch companion 三屏: Today Status, Quick Record, Action Feedback。
- Siri/App Intents 食物记录。
- Mobile review/edit food capture。
- 饭后步行 agenda trigger。

### P4: Measurement / Checkup Planner

目标: 把定期体检、专项检查、复查纳入日程。

交付:

- Measurement automation protocol。
- Checkup planner。
- 8-12 周 lab recheck agenda。
- 医生/人审路径。
- Review 扩展 biomarker outcome。

### P5: Outcome Proof 和商业化试点

目标: 跑通 100-300 个付费种子用户的健康结果。

交付:

- Program 级 outcome report。
- 用户可分享医生摘要。
- 安全和合规文档。
- 种子用户 cohort dashboard。
- 付费转化、执行率、复查改善数据。

---

## 11. 下一轮设计的关键页面需求

### Mobile Today

必须回答:

- 今天身体灯号是什么?
- 为什么?
- 今天只做哪 1-3 件事?
- 哪些行动已经完成?
- 有无安全/异常?

### Mobile Agenda

必须回答:

- 今天、本周、本月、季度分别要做什么?
- 哪些是设备自动完成,哪些需要用户手动?
- 哪些是复查/体检/医生相关?
- 哪些被系统因为恢复差而调整?

### Mobile Capture

必须支持:

- 语音食物。
- 照片食物。
- 常吃食物复用。
- 饮水、补剂、用药、症状、体重、腰围、BP、RPE。
- 捕获后确认/编辑/撤销。

### Mobile Programs

必须展示:

- 正在进行的 8-12 周周期。
- 目标指标和当前进度。
- 本周策略。
- 停止条件和安全边界。

### Mobile Review

必须展示:

- 7/30/90 天执行和结果。
- 哪些行为可能有效。
- 哪些指标没改善。
- 下一周期调整。

### Mac

必须强化:

- Desktop bootstrap 一屏汇总 Agenda。
- Quick Capture 进入同一 capture/agenda/event 协议。
- Import Center 上传体检/基因/知识后生成 agenda 或 review item。
- Trace 能追踪建议从 Twin -> Program -> Agenda -> Event -> Review 的路径。

### Web

必须收敛:

- Admin/ops/observability。
- Deep reports。
- Shared report。
- Privacy/export/delete。
- 旧页面保留但不作为新设计主路径。

### Apple Watch

必须极简:

- 一个状态。
- 一个行动。
- 一个记录入口。
- 四个反馈动作: done/skip/snooze/adjust。

---

## 12. 产品风险

| 风险 | 应对 |
|---|---|
| 功能继续发散 | 所有新增需求必须能落到 HealthAgenda、HealthProgram 或 HealthRouter |
| 用户被提醒打扰 | 通知预算、quiet hours、只推可执行 item |
| 可穿戴冲突导致不信任 | 显示 source 和 confidence,冲突时承认不确定 |
| 食物记录不精确 | v1 目标是行为趋势和蛋白/热量区间,不是克级营养师 |
| 医疗越界 | Safety/Advice Guard、人审、医生确认、边界文案 |
| 三端重复开发 | 明确 Mobile 主体验、Mac 工作台、Web 后台/深度、Watch 执行 |
| 历史代码拖累 | 保留但降级 legacy paths,不要在重设计中继续扩展 |

---

## 13. 待拍板问题

1. 下一轮重设计是否确认以 **Health Agenda** 为核心对象?
2. MVP 是否确认聚焦 **中年代谢 + 恢复/训练 + 测量/复查**?
3. Apple Watch 是否进入 v1 companion,还是先继续本地通知镜像?
4. HealthAgenda 是新表物化,还是先做 projection API?建议:先 projection + event table,稳定后物化。
5. 小程序是否降级为历史兼容?
6. Web 是否停止新增主体验页面,只做后台/报告/兼容?
7. 高风险建议的人审由谁承担: 自己、医生顾问、还是先只做“建议就医/咨询医生”的升级路径?

---

## 附录 A: 当前三端产品边界

| 端 | 当前能力 | 下一步定位 |
|---|---|---|
| Mobile | 主首页、Daily Plan、Agent、语音、HealthKit、饮食/运动/体检/基因/睡眠/设备源等大量页面 | 主体验: Today / Agenda / Capture / Programs / Review |
| Mac App | Swift-native,今日驾驶舱、Agent、快速记录、文件导入、任务中心、Trace、设备来源 | 桌面工作台和导入/复盘中心 |
| Web | 历史功能、dashboard、digital twin、admin、settings、Apple Health XML 导入 | 后台、报告、隐私、兼容 |
| Apple Watch | iOS 通知镜像、HealthKit 数据来源 | 轻量 companion: 状态、记录、确认 |
| Mini Program | 多历史页面和打卡/AI/设备绑定 | 历史兼容或渠道实验 |
| OpenClaw/MCP | 外部 Agent 技能和工具 | 受控外部入口 |

---

## 附录 B: 与旧 PRD 的差异

`docs/prd/personal-health-os-prd.md` 中很多“待建”对象在当前代码已实现或部分实现:

- `TwinSnapshot` 已存在。
- `BiomarkerObservation` 已存在,且有 medical_indicators 同步。
- `InterventionCycle` / `OutcomeMetric` 已存在。
- Daily Plan 行动反馈、InterventionEvent、7/30/90 Review 已存在。
- Multi-wearable Router 的关键底层已经出现: source priority、multi-source merge、device comparison、recovery decision。

因此新 PRD 不再主张“从零补这些表”,而是主张:

- 把它们收敛到 HealthAgenda。
- 把 Wearable Router 产品化。
- 把测量、体检、训练和复查变成日程。
- 把三端体验重新分工。
