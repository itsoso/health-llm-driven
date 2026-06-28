# 健康运行时治理产品规划

> 状态：草案
> 更新时间：2026-06-27
> 负责人：Reva / Personal Health OS
> 关联 PRD：`docs/prd/2026-06-27-code-derived-product-prd-and-10m-goal.md`
> 关联文档/代码：`docs/specs/reva-product-governance-spec.md`、`docs/design-personal-predictive-model.md`、`docs/PRODUCT_ROADMAP.md`、`docs/plans/2026-06-15-smart-bedroom-sleep-environment-devices.md`、`docs/specs/active/2026-06-19-p3-reorder-detection.md`、`docs/specs/active/2026-06-22-p5-reorder-ordering.md`、`backend/app/services/health_trajectory.py`、`backend/app/services/personal_models/`、`backend/app/services/action_ranker.py`、`backend/app/services/agenda_service.py`、`backend/app/services/causal_memory.py`、`backend/app/models/bedroom_environment.py`

## 1. 规划主张

本计划把“健康是可观测、可预测、可干预、可治理的运行时系统”落成 Reva 下一阶段产品主线。

核心判断：

- Reva 当前能力已经足够多，下一阶段不是继续堆健康功能，而是把现有 `HealthTwin`、`HealthTrajectory`、`SafetyGuardian`、`ActionRanker`、`Agenda`、`InterventionCycle`、`CausalMemory` 和 `personal_models` 收束成一个用户每天能理解、能执行、能复盘的治理闭环。
- 预测能力不能成为独立炫技模块。预测必须服务于行动排序、安全边界、复测计划和个人规律沉淀。
- 基因、甲基化、VO2max、生物年龄、血糖、血压等数据不能被包装成宿命或确定性抗衰承诺。它们只能作为边界、倾向、代理指标、运行时信号或验证反馈。
- IoT、补剂补货、环境控制和个性化供应链不能绕过治理。它们是低摩擦采集、环境默认和受控执行层，不是独立医疗判断层。

## 2. 需求准入判断

```yaml
RequirementAdmission:
  需求: 基于健康运行时治理世界观修改 PRD 并制定新规划
  分类: 文档 | 产品变化 | 规划
  首批用户: 35-60 岁高强度工作者, 有代谢/恢复/睡眠/慢病风险和多源健康数据
  核心闭环: Health Twin -> Health Trajectory -> Safety Gate -> ActionRanker -> Agenda -> Execution -> Outcome Review
  一等对象:
    - HealthTwin
    - DataConnection
    - ConsentGrant
    - ProvenanceRecord
    - ConnectorPolicy
    - DomainKnowledgeBase
    - RealtimeHealthSignal
    - HealthTrajectory
    - PersonalPrediction
    - SafetyGuardian
    - LeverageAction
    - HealthAgendaItem
    - InterventionCycle
    - ExecutionEvent
    - CausalMemory
    - IoTActuationIntent
    - SupplyIntent
    - OrganSystemProgram
    - ProgramTemplate
    - EvaluationScenario
    - SafetyRegressionSuite
    - SyntheticUserTwin
  目标端: Backend 真相源, Mobile Today/Agenda/Review, Watch top action, Mac workbench
  真相源: backend objects and services
  安全等级: medical_boundary | privacy_sensitive
  处方或因果结论: clinician_review_downgraded
  自主等级: manual_confirm
  证据来源: reviewed knowledge, user data, device signals, clinical anchors, per-user observations
  表述边界: hedged
  验证窗口: 1 day, 7 days, 4 weeks, 8-12 weeks, retest date
  成功指标: 每周完成带验证计划的安全高杠杆行动
  新增用户负担: low
  负担理由: 复用已有数据和当前每日闭环，只在能改变决策时才询问用户
  非目标:
    - fine-tune personal LLM on health facts
    - deterministic gene destiny claims
    - autonomous clinical or medication changes
    - new standalone prediction dashboard
    - more specialist pages without execution or review
    - LLM-only IoT control
    - silent supplement purchase or recurring order
    - personalized supplement manufacturing without regulatory, quality and safety review
  最小端到端切片: Today top action 显示目标状态变量、轨迹原因、安全边界、执行控制和验证信号
  需要移除或归档的过期入口: 不接入 Agenda 或 Review 的重复 Web/Mobile daily prediction 页面
  是否需要 spec: yes
```

## 3. 目标产品架构

```text
静态先验
  基因 / 年龄 / 性别 / 家族史 / 既往病史

专业知识
  饮食 / 睡眠 / 运动 / 补剂 / 药物 / 慢病 / 器官系统 / 安全规则

运行时输入
  睡眠 / 饮食 / 运动 / 压力 / 药物 / 补剂 / 天气 / 日程 / 社交约束

传感器
  化验 / 可穿戴 / CGM / 症状 / 影像 / 复测 / 用户反馈 / 家居设备 / 办公设备

互操作与授权
  FHIR Bundle / SMART on FHIR / HealthKit / device connectors / ConsentGrant / ProvenanceRecord / ConnectorPolicy

状态模型
  Health Twin

轨迹模型
  基线偏离 / 趋势 / 风险漂移 / 带不确定性的预测 / 数据缺口

安全边界
  SafetyGuardian / 证据边界 / 医生升级

LLM 与工具综合层
  解释 / 追问 / 工具使用 / 计划草拟 / 对象创建

控制输入与执行
  Agenda top action / protocol / write intent / environment default / IoT scene / supply intent / passive capture

反馈
  ExecutionEvent / OutcomeReview / CausalMemory / prediction backtest

评估与回归
  SyntheticUserTwin / EvaluationScenario / SafetyRegressionSuite / release gate / rollback evidence
```

## 4. PRD 实现缺口计划

本节追踪 PRD 已经提出、但当前系统尚未实现、仅有骨架、或还不够产品化的能力。它是 PRD 到后续实现 spec 之间的计划桥梁。

状态词：

| 状态 | 含义 |
|---|---|
| 未实现 | 还没有有效的生产级实现。 |
| 骨架 | 对象、API 或服务形状已经存在，但有意保持 inert，或尚未接到用户价值。 |
| 部分实现 | 已有一部分代码，但完整 PRD 闭环尚未完成。 |
| 待产品化 | 后端能力已经存在，但用户还看不见、看不懂，或没有进入每日闭环。 |

### P0：数据连接、授权与可追溯缺口

| 编号 | PRD 能力 | 当前证据 | 缺口工作 | 目标阶段 |
|---|---|---|---|---|
| D0.1 | `DataConnection` 统一外部数据源和设备连接 | HealthKit/Garmin/Oura/CGM/report/Home Assistant 等路径分散存在 | 缺少统一对象管理 provider、scope、token 状态、同步窗口、错误、最后成功时间、撤权和重连 | 阶段 0 / 阶段 1 |
| D0.2 | `ConsentGrant` 管理用户授权、共享和撤权 | 鉴权、审计、导出/删除路径已有局部能力 | 缺少产品化授权中心，区分本人、家庭、医生、外部 agent、研究统计和 IoT 控制范围 | 阶段 1 |
| D0.3 | `ProvenanceRecord` 支撑关键事实可追溯 | 多处已有 source/freshness/confidence 字段 | 缺少跨对象 provenance 合同，覆盖 observed_at、received_at、transformed_by、confidence、privacy_classification 和 user_correction | 阶段 1 |
| D0.4 | `ConnectorPolicy` 管理连接器运行策略 | scheduler、wearable router、device source priority 已存在 | 缺少统一 connector policy：rate limit、token refresh、失败降级、数据最小化、撤权后删除和审计 | 阶段 1 / 阶段 4 |
| D0.5 | FHIR/SMART 和报告导入成为优先医疗数据入口 | 报告、OCR、labs 和 patient record 相关能力已有基础 | 需要定义 FHIR Bundle import、SMART on FHIR 授权、非标准 PDF/OCR 到内部对象的映射和验证路径 | 阶段 1 |

### P0：核心闭环缺口

| 编号 | PRD 能力 | 当前证据 | 缺口工作 | 目标阶段 |
|---|---|---|---|---|
| G0.1 | `HealthTrajectory` 驱动每日行动选择 | `backend/app/services/health_trajectory.py` 和 `/trajectory/me` 已存在；测试覆盖 evidence、confidence、claim_boundary | `ActionRanker` 和 `Agenda` 尚未把 trajectory risk 作为一等评分输入；trajectory risk 结构还缺少完整 PRD 合同：`state_variable`、`horizon`、`uncertainty`、`verification_window` | 阶段 1 |
| G0.2 | Today top action 解释“控制输入”语义 | `Agenda` 和 Watch summary 已经暴露 top actions 和 verification windows | Top action 还没有在 Mobile/Watch 一致展示目标状态变量、预期影响窗口、成功信号、失败/安全信号和轨迹原因 | 阶段 1 |
| G0.3 | 预测与实际结果进入统一复盘闭环 | Health consultation predictions、outcome grader、specialist hit-rate 和 `InterventionCycle` 片段已存在 | 缺少统一 prediction record 合同，尚未附着到 `Agenda`、`Intervention`、`Specialist`、`Problem`；Review 还没有用户可见的“预测 -> 实际 -> 下一步”时间线 | 阶段 2 |
| G0.4 | `PersonalPrediction` 反哺 Twin/Trajectory | `backend/app/services/personal_models/treatment_effect.py` 和 priors 已存在 | 模型输出还不是稳定的 Twin/Trajectory 区块，Review 中没有广泛呈现，也没有作为结构化输入进入 `ActionRanker` | 阶段 3 |
| G0.5 | `CausalMemory` 成为用户可见的个人规律库 | `backend/app/services/causal_memory.py` 已能生成带 claim boundary 的观察性总结 | 缺少 Mobile/Review 的主入口展示“你的个人健康规律”；尚未接入 Today 排序或 program 下一步解释 | 阶段 2 |
| G0.6 | 首次使用 onboarding 生成初始健康闭环 | 数据上传、报告、基因、目标、问题、protocol 和 agenda 已散落存在 | 缺少统一 onboarding pipeline，把报告/设备/目标转成 `HealthTwin` + `HealthProblem` + `HealthProgram` + `Protocol` + 首个 `Agenda` | 阶段 1 |
| G0.7 | `ProgramTemplate` 支撑 8-12 周计划产品化 | `HealthProgram` model/API/tests 已存在；protocol 可以挂到 program | 缺少可审查、可版本化模板，声明适用人群、排除条件、必要数据、安全门、protocol 列表、复测窗口和退出条件 | 阶段 1 |

### P1：数据、知识、监控与安全缺口

| 编号 | PRD 能力 | 当前证据 | 缺口工作 | 目标阶段 |
|---|---|---|---|---|
| G1.1 | 有来源、时效、权限和置信度的真实个人数据层 | 化验、基因、表观遗传、可穿戴、症状、药物/补剂和报告分布在多个模块 | 仍缺少跨领域统一的 `DataSourceQuality` / provenance 合同，覆盖所有 PRD 输入的权限、时效、置信度和用户纠错 | 阶段 1 / 阶段 4 |
| G1.2 | 覆盖目标领域的 reviewed-first 专业知识库 | 系统 KB、reviewed-only gates、evidence boundaries 和大量知识测试已存在 | 饮食、睡眠、运动、补剂、药物、器官系统项目、IoT/环境的覆盖不均衡；用户侧引用和证据 UX 不稳定 | 阶段 2 / 阶段 4 |
| G1.3 | 实时监控覆盖血压、血糖、SpO2、body battery、环境和设备 | wearable router、device source priority、Garmin/Apple/Ring/Oura 路径和卧室/设备 observation 已存在 | CGM Libre/Dexcom adapter 仍是 `NotImplementedError`；智能血压计/体重计和部分 HealthKit 路径仍偏手动；缺少统一的 health + home/office realtime signal 合同 | 阶段 4 / 阶段 5 |
| G1.4 | 按用户配置数据源偏好和冲突仲裁 | wearable arbitration 和 source priority 已存在 | 部分仲裁仍是全局逻辑，不是按用户/疾病状态配置；用户无法在产品里稳定查看或覆盖 source preference | 阶段 4 |
| G1.5 | 轨迹安全事件仪表盘 | `SafetyGuardian`、proactive coordinator 和 admin SLOs 已存在 | 缺少专门视图审计 trajectory-driven actions、prediction-driven nudges、误报和安全升级正确性 | 阶段 4 |
| G1.6 | 派生记忆和预测的隐私控制 | 数据隔离、审计和部分导出/删除路径已存在 | 用户还不能在统一控制中心暂停/删除特定预测类别、派生 `CausalMemory` 或 IoT 派生行为 | 阶段 4 / 阶段 5 |
| G1.7 | `EvaluationScenario` 和 `SafetyRegressionSuite` 成为 release gate | agent eval、SafetyGuardian tests 和部分 specialist tests 已存在 | 缺少 SyntheticUserTwin、标准场景集、红线/相互作用/claim boundary/manual_confirm 回归，以及模型或 connector 切换的回滚证据 | 阶段 2 |

### P1：端侧体验与产品化缺口

| 编号 | PRD 能力 | 当前证据 | 缺口工作 | 目标阶段 |
|---|---|---|---|---|
| G1.8 | Mobile 收敛为 Today / Agenda / Capture / Programs / Review | 现有 Mobile routes 已覆盖这些概念，但仍有许多并行入口 | 还需要清理 route metadata 和导航；admin/debug/过期 daily flows 应从主导航隐藏或归档 | 阶段 0 / 阶段 1 |
| G1.9 | Programs 成为用户可见的 8-12 周运营单元 | `HealthProgram` model/API/tests 已存在；protocol 可以挂到 program | Program templates、跨对象进展、Review 集成和器官系统 program map 尚未在 Mobile Today/Programs 成为一等能力 | 阶段 1 / 阶段 2 |
| G1.10 | Mac 保持 workbench，Web 保持历史/admin/family/doctor 场景 | surface ownership doc 已存在 | 部分 Web/Mobile/Mac 工作流仍重叠；每日消费者流程需要在用户验证后更明确地归档或收敛 | 阶段 0 / 阶段 4 |
| G1.11 | 外部 agent 输出必须落到一等对象 | MCP/OpenClaw skills 和 tool registry 已存在 | 并非所有外部/LLM 分析路径都被强制创建 `Problem`、`Protocol`、`Agenda`、`WriteIntent`、`Review`，或显式标记为 explain-only | 阶段 2 |

### P2：IoT、环境与供应链缺口

| 编号 | PRD 能力 | 当前证据 | 缺口工作 | 目标阶段 |
|---|---|---|---|---|
| G2.1 | 卧室环境闭环 | `BedroomEnvironmentSnapshot`、`BedroomAutomationEvent`、`bedroom_environment_service`、Home Assistant webhook 和 `bedroom_outcome_analyzer` 已存在 | `HomeAssistantAdapter` scene allowlist、scene downlink、`BedroomSleepProtocol`、Agenda projection、Mobile UI 和睡眠复盘尚未完成 | 阶段 5 |
| G2.2 | 设备 observation 在不扩大隐私风险的前提下闭合 Agenda item | `device_observation` schema/service/API 和测试已存在；raw media 被阻断 | 还缺更多设备类型、provider auth、用户同意 UX、Agenda 映射和 Review 渲染 | 阶段 5 |
| G2.3 | 补剂物流和购买边界 | supplement inventory、reorder nudge、deep link 和 `ReorderIntent` 骨架已存在 | 真实下单有意保持 inert；OpenClaw/commerce skill contract、账号绑定、confirmation token、callbacks 和财务安全 review 待补 | 阶段 5 |
| G2.4 | 个性化补剂搭配或生产 | supplement recommendation 和 safety rules 已存在 | 缺少受监管供应链模型、批次质量、PGx/DDI/DSI 审批流、生产伙伴边界和上市后 outcome tracking | 阶段 5+ |
| G2.5 | 办公环境和工位健康闭环 | device observation 已支持 posture/screen events | 智能桌椅/屏幕集成、隐私 UX、人体工学 protocols 和 outcome linkage 尚未产品化 | 阶段 5 |

### P2：器官系统项目缺口

| 编号 | PRD 能力 | 当前证据 | 缺口工作 | 目标阶段 |
|---|---|---|---|---|
| G2.6 | 心血管项目 | 血压、血脂、VO2max、安全和 trajectory 片段已存在 | 缺少完整 cardiovascular `HealthProgram` template，覆盖 protocols、安全闸门、复测计划和 Review surface | 阶段 5 / 器官地图 |
| G2.7 | 代谢/内分泌项目 | metabolic cycle、腰围、化验和 nutrition 片段已存在 | 需要统一 self-serve template、CGM 路径、meal response 集成、复测节奏和 program review | 阶段 1 / 阶段 3 |
| G2.8 | 睡眠/恢复项目 | 睡眠、readiness、HRV 和卧室环境片段已存在 | 需要整合 wearable readiness、卧室环境和每日训练决策的 sleep/recovery `HealthProgram` | 阶段 5 |
| G2.9 | 呼吸/过敏项目 | rhinitis specialist、环境信号和 nasal wash protocol 片段已存在 | 需要完整 respiratory program，覆盖 AQI/湿度/花粉、用药依从、洗鼻和升级规则 | 阶段 5 |
| G2.10 | 消化/肝脏项目 | 胃病、肝脏、PPI、化验片段已存在 | 需要 digestive/liver program template，覆盖药物/补剂相互作用 review、随访和复测计划 | 阶段 5 |
| G2.11 | 肌肉骨骼与工位项目 | movement/training 和 posture observations 已存在 | 需要 strength/mobility/sarcopenia program 与办公人体工学闭环 | 阶段 5 |
| G2.12 | 神经认知/心理/社交项目 | mental、social connection 和 screen load 片段已存在 | 需要有边界的 program shape、红线处理、同意机制和 Review surface | 阶段 5 |

## 5. 阶段 0：PRD 与产品语言对齐

时间范围：现在到 1 周。

目标：让团队和后续 agents 使用同一套产品语言。

工作项：

- 将 `docs/prd/2026-06-27-code-derived-product-prd-and-10m-goal.md` 作为当前 code-derived baseline PRD。
- 采用“Health Runtime Governance”作为产品主张，但公开表达保持医疗保守。
- 标准化三个用户可理解概念：
  - Health Twin：现在什么是真的。
  - Health Trajectory：状态可能如何漂移。
  - Health Action：下一步选择什么安全控制输入。
- 增加治理规则：每个预测都必须声明 horizon、uncertainty、evidence tier、claim boundary，以及它影响的 action/review。
- 停止新增独立预测视图，除非它直接服务于 `Agenda`、`InterventionCycle` 或 `Review`。
- 将五层系统作为架构词汇：真实个人数据、reviewed knowledge、实时监控、模型/工具综合、受控 IoT/环境执行。
- 将 `DataConnection`、`ConsentGrant`、`ProvenanceRecord`、`ConnectorPolicy`、`ProgramTemplate`、`EvaluationScenario`、`SafetyRegressionSuite` 加入后续 spec 的标准对象清单。
- 明确所有新 connector、agent、ranker、prediction、ProgramTemplate 或 IoT 能力必须有评估/回归入口，不允许只靠人工体验判断。

验收标准：

- 新产品 spec 能填写 `state_variable_to_change` 和 `prediction_or_trajectory_claim`。
- 后续文档避免“宿命”“保证抗衰”“基因决定结果”和绝对因果结论。
- PRD 明确把 `HealthTrajectory` 和 `PersonalPrediction` 映射为一等产品对象。
- PRD 明确把 IoT/环境和供应链行为映射到受控执行对象，而不是自主健康判断。
- PRD 明确把标准互操作、授权、provenance 和评估回归作为 1000 万用户规模前的基础设施，而不是后期补丁。

## 6. 阶段 1：数据连接底座与 Trajectory 共同影响 Today

时间范围：1-4 周。

目标：在不扩大范围的前提下，让 trajectory 从 workbench/report 概念变成每日行动选择依据，并补齐最小数据连接、授权和 provenance 底座。

数据底座待规划工作：

- 定义最小 `DataConnection` 合同，先覆盖一个报告/FHIR Bundle 导入路径和一个 wearable/device connector。
- 定义最小 `ConsentGrant` 合同，覆盖本人使用、外部 agent read scope、撤权和删除。
- 定义关键事实的 `ProvenanceRecord`，让 Today top action 可以解释它使用了哪些来源、多久前更新、置信度如何。
- 定义 `ConnectorPolicy` 的最小字段：scope、last_success_at、sync_error、rate_limit、token_status、degraded_behavior。
- 明确 non-goal：不在本阶段做完整医院网络、支付级授权中心或所有设备 connector。

后端待规划工作：

- 审计 `backend/app/services/health_trajectory.py` 输出字段，并与 Agenda item 字段对齐。
- 增加 trajectory risk 产品合同：
  - `domain`
  - `state_variable`
  - `level`
  - `horizon`
  - `signals`
  - `modifiable_levers`
  - `confidence`
  - `uncertainty`
  - `evidence_tier`
  - `claim_boundary`
  - `primary_action`
  - `verification_window`
- 让 `ActionRanker` 把 trajectory risk 作为评分输入，而不是并行 recommendation source。
- 低置信 trajectory risk 应降级为 data-gap 或 watchlist item，而不是 urgent action。

Mobile/Watch 待规划工作：

- Today top action 展示：
  - 目标状态变量；
  - 为什么这个 trajectory 此刻重要；
  - 安全边界；
  - 具体行动；
  - 预期验证信号。
- Watch summary 保持压缩成一句话加 confirm/later/skip。

验收标准：

- 一个代谢/恢复 top action 能解释它试图改变哪一种未来漂移。
- 同一个 item 可以通过 Agenda 合同从 Mobile 或 Watch 完成。
- 不需要新增 daily route。
- Today top action 至少能展示一个关键事实的 provenance 摘要，避免用户只看到黑箱结论。

## 7. 阶段 2：让预测回测、评估和安全回归进入闭环

时间范围：1-2 个月。

目标：通过“预测 vs 实际”让用户信任逐步累积，同时让 agent/ranker/prediction/safety 的质量进入持续评估。

工作项：

- 定义可附着到 `InterventionCycle`、`HealthAgendaItem`、specialist output 或 `HealthProblem` follow-up 的 prediction record 结构。
- 存储：
  - 预测方向或范围；
  - horizon；
  - baseline；
  - expected signal；
  - actual result；
  - met / not_met / inconclusive；
  - 观察后的 confidence change。
- 在 Review 中展示 prediction backtests，而不是做 vanity score。
- 保持观察性措辞：
  - 允许：“这次观察支持继续当前策略。”
  - 允许：“数据不足，不能判断。”
  - 禁止：“这证明某补剂让你降低 LDL。”
- 建立 `SyntheticUserTwin` 最小 fixture：代谢、睡眠/恢复、红线、数据缺失、设备冲突和补剂相互作用。
- 建立 `EvaluationScenario`：对象落地率、top action 排序、claim boundary、预测校准、复测率和用户纠正后的调整。
- 建立 `SafetyRegressionSuite`：急症红线、DDI/DSI/PGx、训练风险、IoT actuation、补剂供应链和 manual_confirm。
- 将评估结果纳入模型、工具、ranker、ProgramTemplate 或 connector 切换前的 release gate。

验收标准：

- 用户能看到至少一个完整闭环：预测、行动、实际、解释、下一步。
- 系统维护者能看到 specialist hit-rate 或 prediction confidence。
- 低置信或混杂指标会被降级为 clinician_review 或 inconclusive。
- 维护者能运行一组稳定 EvaluationScenario，看到 agent/ranker/prediction/safety 是否相对上个版本退化。

## 8. 阶段 3：在不微调个人 LLM 的前提下建立个人预测模型

时间范围：2-4 个月，在积累足够闭环数据之后启动。

目标：只在数据支持的地方引入小型、可审计的预测模型。

优先顺序：

1. 基于可穿戴/化验时间序列的个人基线和异常检测。
2. 在积累足够 `InterventionCycle` 数据后，估计 N-of-1 干预效果。
3. 只有在同时存在 CGM 和饮食记录时，才做 CGM + meal response。

规则：

- 不在个人健康事实上微调 LLM。
- 个人模型参数保留在服务端，并按用户隔离。
- 只把摘要预测、不确定性和边界传给 LLM。
- 每个模型都必须能优雅降级到 baseline、data gap 或 human review。
- 每个模型输出都必须围绕 confidence、boundary text 和 unsafe escalation 建测试。

验收标准：

- `personal_models` 产出至少一个带 uncertainty 和 version 的模型输出。
- Twin 或 trajectory 以结构化 section 包含该 prediction。
- `ActionRanker` 可以使用该输出，而不是依赖 LLM-only reasoning。

## 9. 阶段 4：面向 1000 万用户扩展治理能力

时间范围：dogfood 和付费切口验证 retention 与 outcome signal 后启动。

目标：让健康运行时治理在大规模下仍然安全、低成本、可信。

工作项：

- 跟踪每次 Today/Agenda/Trajectory/DataConnection 调用的成本和延迟。
- 为 trajectory-driven actions 增加安全事件仪表盘。
- 为 prediction inputs、connector inputs 和 decisions 增加审计日志。
- 增加 per-user data source quality 和 source preference。
- 增加用户暂停 prediction category、connector scope 和删除 derived memory 的控制。
- 在大规模消费级推广前，补齐多区域隐私、删除、导出、consent 和 connector-token 路径。
- 增加多租户 connector 隔离、sync backoff 和 provider failure dashboard。

验收标准：

- 系统能解释为什么向用户展示某个 trajectory action。
- 用户能纠正、暂停或删除派生预测/记忆。
- 运营者能审计 prediction-driven actions，同时不查看不必要的原始敏感数据。
- 运营者能审计 connector failures、consent scope changes 和 provenance chains，同时不暴露不必要的原始记录。

## 10. 阶段 5：IoT、环境与供应链执行

时间范围：Today/Trajectory 和 Review 闭环稳定后启动；卧室环境可以更早做窄 pilots。

目标：让 Reva 从“建议行为”进化为受治理的执行层，能改变用户的物理环境和物流环境。

优先顺序：

1. 卧室睡眠环境：CO2、PM2.5、湿度、温度、灯光、窗帘、睡眠保护窗口。
2. 测量设备：智能血压计、智能体重计、CGM 和其他 ground-truth 采集设备。
3. 低风险依从设备：智能水杯、药盒 observation、坐姿/屏幕休息 observation。
4. 补剂库存与补货：先做物流提醒，再做手动购买，不做静默 recurring order。
5. 个性化补剂搭配或生产：仅作为长期方向，必须等 reviewed knowledge、DDI/DSI/PGx 安全、质量控制、监管审查和审计模型都存在后再推进。

规则：

- Reva 输出 health intents 和 scenes；Home Assistant、厂商 app 或设备生态执行实时控制。
- LLM 不直接控制设备。
- 设备 observation 是结构化标量事实；除非另有隐私 spec 授权，不持久化原始图片/音频/视频。
- 每条 actuation path 都必须有 manual override、audit、downgrade behavior 和 notification budget。
- 金融动作和补剂供应链动作默认是 `manual_confirm`；临床、处方和剂量变化动作永久保持 manual。
- IoT 数据不得进入 generic LLM context，除非隐私分类和最小化规则允许。

验收标准：

- 卧室环境闭环能展示 sensor state、executed scene、次日睡眠/恢复 outcome 和 manual override history。
- 补剂低库存闭环能提出 replenishment intent，但不把购买行为医疗化。
- 设备 observation 可以完成或影响 Agenda item，但不能创建独立 recommendation path。

## 11. 器官与系统项目地图

目标：围绕人体系统组织健康改善，同时不丢失全局交互。

初始领域：

- 心血管：血压、静息心率、HRV、VO2max、血脂、活动量。
- 代谢/内分泌：体重、腰围、HbA1c、CGM、甘油三酯、脂肪肝风险、进食时间。
- 睡眠/恢复：睡眠时长、睡眠质量、HRV、训练 readiness、卧室环境。
- 呼吸/过敏：SpO2、鼻炎、AQI、湿度、花粉、洗鼻、用药依从。
- 消化/肝脏：胃炎、PPI 安全、肝酶、酒精、餐食构成、药物/补剂相互作用。
- 肌肉骨骼：力量、活动度、肌少症预防、损伤恢复、姿势和工位。
- 神经认知/心理：压力、屏幕负荷、睡眠、社交连接、情绪和认知负担。
- 免疫/炎症与口腔健康：感染信号、牙周护理、可用时纳入炎症指标。

规则：

- 每个 domain program 仍必须映射到全局 `HealthTwin`、`SafetyGuardian`、`Agenda` 和 `InterventionCycle`。
- 器官级优化不能覆盖跨系统禁忌。
- Domain programs 必须定义可写变量，不能只定义 outcome metrics。

## 12. 近期实现计划

下一份实现 spec 应保持很小，但应拆成两个并行最小切片：

> A. 构建最小 DataConnection/Consent/Provenance 底座。
> B. 构建最小端到端“trajectory-informed top action”切片。

### 2026-06-28 执行状态

本轮按 PRD/Plan/Code 对比后，优先选择 B 的最小端到端切片，并把它收敛为“滚动 7 天健康运行时编排”的首个已发布版本。

已完成:

- 后端新增 `GET /api/v1/agenda/range?days=7&mode=runtime`，返回 7 天同构 runtime projection。
- 后端新增 `GET /api/v1/agenda/today?mode=runtime`，返回 1 天同构 projection，供 Watch/Home/Chat 复用。
- 每个 runtime item 带 `runtime_context`，包含 evidence、safety boundary、verification window、replan reason 和 replan triggers。
- Mobile 新增 `getRuntimeAgendaRange` / `useRuntimeAgendaRange`。
- Mobile Agenda 页面新增“7天运行时”面板，展示下一步行动和未来几天主要行动。
- 新增 active spec：`docs/specs/active/2026-06-28-rolling-7-day-health-runtime.md`。
- 新增 product-pipeline Dossier：`docs/dossiers/2026-06-28-rolling-health-runtime-next-slice.md`。
- 已发布：
  - 后端部署 SHA `e93cada43ad386e989a0ed8451e5b9124b37da87`，部署健康分 `60/60`。
  - Mobile OTA production update group `1a6b76e2-a74a-4d14-bccb-caec541ba29f`。
  - 生产 user_id=3 smoke：`mode=runtime horizon=7 days=7 next=True first_runtime_context=True`。

仍未完成，继续保留在后续计划:

- A 切片：DataConnection / ConsentGrant / ProvenanceRecord 最小底座。
- Home Daily Artifact 直接消费 runtime projection，并严格只展示一个 primary next action。
- Chat 动态 UI 卡片消费 runtime projection。
- Watch summary 使用 `today?mode=runtime` 的压缩行动合同。
- skip reason、snooze、completion 进入未来 7 天重排因子。

建议范围 A：

- 后端：定义 `DataConnection` / `ConsentGrant` / `ProvenanceRecord` 的最小 schema 或 contract。
- 导入：先支持一个报告/FHIR Bundle 风格输入和一个 wearable/device source 的统一 metadata。
- Mobile/Mac：能展示连接状态、授权 scope、最近同步、撤权入口或解释性占位。
- 测试：DataConnection contract test、ConsentGrant scope test、ProvenanceRecord serialization test、connector degraded behavior test。

建议范围 B：

- 后端：把现有 `health_trajectory.py` 输出适配为 Agenda/ActionRanker input contract。
- Mobile：在 Today top action 展示目标状态变量和验证信号。
- Watch：保留一句话行动，不新增复杂 UI。
- Review：增加一个后续 prediction backtest 的占位。
- 测试：trajectory risk shape contract test、ActionRanker scoring test、Agenda item serialization test、Mobile top action copy unit test。

阶段 2 紧随其后的实现 spec：

- `SyntheticUserTwin` fixture。
- `EvaluationScenario` 数据集与 runner。
- `SafetyRegressionSuite` 红线和 claim-boundary 回归。
- `ProgramTemplate` 最小模板：metabolic/recovery/sleep。

不做范围：

- 新 ML model。
- 新 prediction dashboard。
- 药物、剂量或临床治疗预测。
- CGM meal-response model。
- autonomous write actions。
- IoT device control。
- 补剂下单或个性化生产。
- 完整医院网络连接。
- 完整家庭/医生共享中心。
- 大规模多租户 connector 运维平台。

## 13. 变更记录

| 日期 | 变更 | 原因 |
|---|---|---|
| 2026-06-27 | 初始计划 | 围绕 Health Runtime Governance 对齐 PRD 与 roadmap。 |
| 2026-06-27 | 增加系统基座、IoT/环境、供应链和器官系统规划 | 捕获扩展后的系统理念，同时保留安全和执行边界。 |
| 2026-06-27 | 增加 PRD 实现缺口计划 | 追踪 PRD 已提出但尚未实现、仅有骨架、部分实现或尚未产品化的能力。 |
| 2026-06-27 | 将 Plan 改为中文表达 | 便于团队按中文 PRD 和规划继续演进。 |
| 2026-06-27 | 增加互操作、授权、provenance、评估回归和模板化计划 | 吸收 FHIR/PHR、闭环糖尿病系统、Home Assistant 和医疗 agent benchmark 的启发，补齐 1000 万用户规模前的基础设施。 |
| 2026-06-28 | 标记 B 切片首个实现：滚动 7 天健康运行时编排 | 先把 HealthTrajectory/Agenda 从单日 top action 推进到 7 天可执行路线，为 Home/Chat/Watch 共用 Daily Artifact 打底。 |
