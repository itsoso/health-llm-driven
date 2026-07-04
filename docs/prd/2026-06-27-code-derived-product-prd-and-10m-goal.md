# Reva 当前产品 PRD 与 1000 万用户长期目标

> Status: code-derived baseline
> Updated: 2026-06-27
> Owner: Reva / Personal Health OS
> Source basis: repo-wide inventory plus focused reading of `README.md`, `docs/specs/reva-product-governance-spec.md`, `docs/prd/reva-personal-health-os-prd.md`, `docs/prd/2026-06-16-health-leverage-action-os-pdd.md`, `docs/rfc-agent-native-health-os.md`, `docs/ARCHITECTURE.md`, `docs/specs/active/2026-06-26-surface-ownership-inventory.md`, backend domain models/services/APIs/tests, and Mobile/Watch/Mac/Web/Agent/MCP surfaces.
> Competitive correction: incorporates [`../reports/2026-06-27-competitive-benchmark-and-prd-critique.md`](../reports/2026-06-27-competitive-benchmark-and-prd-critique.md). The long-term strategy now treats Daily Artifact, trust-custodianship, deterministic safety, honest evidence language, heterogeneous-user validation, and 5-minute on-ramp as first-order roadmap constraints.

## 1. One-Line Product Definition

Reva 是一个个人健康操作系统（Personal Health OS）：把用户的长期健康数据、医学风险、日常行为和可执行计划汇聚成一个安全约束下的每日健康行动系统，帮助用户持续完成更高杠杆、更可验证的健康改善。

### 1.1 Foundational Worldview

Reva 的底层世界观是：健康不是玄学，也不只是自律。健康是一个由先天参数、物理规律、生物规律、社会环境、个人行为和反馈机制共同驱动的复杂运行时系统。

更准确地说：

- 基因、年龄、性别、家族史和既往病史提供先天参数和边界条件。
- 睡眠、饮食、运动、药物、补剂、压力、天气、工作节律和社会关系是运行时输入。
- 体检、可穿戴、症状、CGM、影像、复查和用户反馈是传感器信号。
- Health Twin 是状态空间。
- Agenda、Protocol 和 WriteIntent 是控制输入。
- SafetyGuardian 是不能跨越的安全边界。
- Outcome Review 和 CausalMemory 是反馈学习系统。

因此，Reva 的目标不是宣称未来被完全决定，也不是做“基因命运论”。未来不能被精确预言，但健康轨迹可以被持续观测、概率预测、提前预警、主动干预和闭环治理。

### 1.2 Product Translation

这个世界观对应的产品定义是：

> Reva 是人的健康运行时治理系统。它持续读取身体状态，识别风险和趋势，选择最有杠杆的控制输入，通过安全门约束执行，再用结果数据验证什么对这个人有效。

### 1.3 System Substrate

Reva 的系统由五层组成：

1. 真实个人数据层：个人基因数据、表观遗传数据、医院检查报告、体检报告、年龄、性别、体重、腰围、既往病史、家族史、用药、补剂、症状和用户目标。所有数据必须保留来源、时间、置信度、权限和用户归属。
2. 专业知识库层：饮食、睡眠、运动、补剂、药物、慢病、器官系统、环境暴露、检测复查和安全禁忌等领域知识。健康知识默认 reviewed-first，LLM 不能把未审内容包装成权威结论。
3. 实时监测层：可穿戴设备和家用设备提供心率、血压、血糖、HRV、睡眠、压力、身体电量、血氧、训练负荷、体重、体脂、环境 CO2/PM2.5/温湿度等信号。后端负责 source arbitration、freshness、confidence 和冲突处理。
4. 大模型推断与工具层：LLM 负责综合解释、提出问题、归纳计划和调用工具；确定性系统负责安全门、排序、状态机、审计和写入。LLM 不能单独做诊断、处方、剂量、红线解除或自动购买决策。
5. IoT 与环境执行层：空气净化器、除湿器、加湿器、窗帘、灯光、智能血压计、体重计、水杯、床垫、办公座椅、办公屏幕、药盒和补剂库存等设备负责低摩擦采集、环境默认和受控执行。Reva 输出健康意图和场景建议，不做不受审计的任意设备控制。

这五层之外还需要三条横向能力：

- 标准互操作与连接治理：优先支持 FHIR Bundle、SMART on FHIR、HealthKit、Garmin/Oura/Withings/CGM、Home Assistant 和未来 provider connectors，把每个外部来源建模为 DataConnection，而不是把导入脚本散落在业务逻辑里。
- 授权、来源和可追溯：每个连接、报告、设备和 agent 调用都要有 ConsentGrant、ProvenanceRecord、ConnectorPolicy 和撤权路径；用户能知道数据从哪里来、谁能用、何时失效、如何删除。
- 评估与安全回归：所有 agent、ranker、prediction 和 safety 变化都要进入 EvaluationScenario / SafetyRegressionSuite，用合成用户、历史样本和红线案例持续验证，避免只靠线上用户试错。

长期看，Reva 可以按器官和系统组织 program，例如心血管、代谢/内分泌、睡眠/恢复、呼吸/鼻炎、消化/肝胆、肌肉骨骼、神经认知、心理压力、免疫/炎症和口腔健康。但器官系统只是组织方式，不能削弱整体 Health Twin、安全门和跨系统相互作用判断。

它不是：

- 通用健康聊天机器人。
- 只展示数据的 dashboard。
- 只记录习惯或打卡的 tracker。
- 替代医生做诊断、处方、急救或剂量决策的医疗系统。
- 基因命运论、绝对预测工具或抗衰确定性承诺。

## 2. Current Product PRD

### 2.1 Target User

当前产品最适合先服务一类高价值、强痛点、能闭环验证的用户：

- 35-60 岁，有代谢、睡眠、恢复、血压、血脂、脂肪肝、尿酸、运动损伤、鼻炎、胃病、补剂或长期精力压力的中年高强度工作者。
- 已经有部分健康数据来源：体检报告、Apple Watch/Garmin/Oura/手环、CGM、体重体脂秤、症状记录、用药/补剂记录、运动记录。
- 既不满足于泛泛建议，也不希望自己每天解读复杂数据；希望系统直接告诉自己今天最值得做的一件事，并说明为什么、怎么做、何时验证。

长期可扩展到家庭健康管理、慢病陪跑、体检后管理、运动恢复、企业健康和医生协作，但第一阶段不应把这些都做成并列入口。

### 2.2 Core Problem

用户拥有越来越多健康数据，但真实改善经常失败在五个地方：

1. 数据分散：体检、可穿戴、饮食、运动、药物、补剂、症状和医生建议互相割裂。
2. 风险不清：用户不知道哪些信号需要立即处理，哪些只是普通波动。
3. 行动过多：系统给出一堆建议，但没有排序，也没有结合用户今天的状态和约束。
4. 执行摩擦大：健康建议无法落到手表、手机、日历、提醒、购物、复查等真实生活动作。
5. 没有验证闭环：做了什么、是否有效、什么时候复测、下一步如何调整没有形成长期记忆。

### 2.3 Product Promise

Reva 每天为用户完成五件事：

1. 看懂今天身体和风险状态。
2. 判断在当前运行时输入下，健康状态可能往哪个方向漂移。
3. 选出最值得做、最安全、最能验证的一件或少数几件健康行动。
4. 把行动放到最合适的 surface 上执行。
5. 把执行结果和后续指标变化写回长期健康记忆，用于下一轮决策。

### 2.4 North Star

主北极星：

- 每周完成的高杠杆健康行动数：行动必须通过安全门、绑定用户真实上下文、完成执行记录，并有验证计划。

结果北极星：

- 30/90/180 天内，用户关键健康目标的趋势改善。优先包括能量/恢复主观评分、睡眠质量、血压、体重/腰围、血糖波动、血脂/肝肾代谢指标、训练恢复和复查完成率。

1000 万用户阶段的规模指标：

- 日活/周活用户中，有多少人完成了当天健康 top action。
- 每个活跃用户每周完成多少个安全门通过的健康行动。
- 有多少行动完成了复测、复盘或可穿戴指标验证。
- 有多少用户持续 12 周形成完整 InterventionCycle。
- 安全事件率、误触达率、通知关闭率、人工确认率、成本/延迟和数据新鲜度。

## 3. Core Product Loop

当前代码已经围绕下面的产品链路成型：

```text
Data Connection / Consent / Provenance
  -> Data Intake
  + Domain Knowledge
  + Realtime Monitoring
  -> Health Twin
  -> Health Trajectory / Prediction Layer
  -> Safety Guardian
  -> LLM / Tool Synthesis
  -> Action Ranker
  -> Agenda / Watch Summary / Daily Plan / WriteIntent
  -> Surface / IoT / Environment Execution
  -> Execution Event
  -> Outcome Review / Causal Memory
  -> Evaluation / Safety Regression
  -> Next Action
```

### 3.1 Data Intake

输入包括：

- 个人基因、表观遗传、家族史、年龄、性别、既往病史、当前体重/腰围等先天和长期参数。
- 医院检查报告、体检报告、化验、影像、指标 OCR 和历史报告。
- Apple Health、Garmin、Oura、CGM、智能血压计、智能体重计、体脂秤、手表、戒指等设备数据。
- 饮食、饮水、运动、睡眠、症状、情绪、药物、补剂、日程、地点、天气和环境。
- 家居与办公 IoT 环境信号：CO2、PM2.5、温度、湿度、照度、占用、床上状态、屏幕/坐姿等结构化观察。
- 用户目标、健康问题、医生建议、复查计划和家庭健康信息。

要求：

- 每个数据点必须尽量保留来源、时间、新鲜度、置信度和用户归属。
- 冲突数据必须交给后端路由和 arbitration，而不是客户端自行判断。
- 高风险数据和医疗含义数据必须进入安全门和审计。

### 3.1.1 Standards, Consent And Provenance

真实数据层不能只靠“能导入”。它必须成为可授权、可撤销、可审计、可映射的连接系统。

产品要求：

- FHIR Bundle 和 SMART on FHIR 是医院/患者门户接入的优先标准；非标准报告、OCR、PDF 和图片导入必须映射到内部对象，并保留原始来源和转换链。
- HealthKit、Garmin、Oura、Withings、CGM、智能血压计、智能体重计和 Home Assistant 等都必须建模为 DataConnection，记录 provider、scope、token 状态、同步窗口、错误和最后成功时间。
- 用户授权必须建模为 ConsentGrant，区分本人使用、家庭共享、医生查看、外部 agent、研究/匿名统计和 IoT 设备控制。
- 每条关键事实必须有 ProvenanceRecord，至少包含 source、observed_at、received_at、transformed_by、confidence、privacy_classification 和 user_correction 状态。
- ConnectorPolicy 必须定义 rate limit、token refresh、失败降级、数据最小化、撤权后删除和审计策略。

### 3.2 Health Twin

Health Twin 是用户当前健康状态的结构化镜像，当前代码中已经覆盖生理、体成分、实验室指标、CGM、药物、补剂、基因、环境、行为、急性症状、心理、慢病、目标和 freshness 等 section。

产品要求：

- Twin 不是展示层，而是决策上下文。
- Twin 必须能解释：这个结论来自哪个数据源、多久前更新、是否冲突、是否缺失关键数据。
- Twin 必须能服务日常 action、长期 program、医生沟通和 agent 分析。
- Twin 必须区分先天参数、当前状态、运行时输入、社会约束和可干预变量，避免把“状态展示”误认为“治理能力”。

### 3.3 Health Trajectory And Prediction Layer

Health Trajectory / Prediction Layer 是把 Health Twin 从“状态快照”升级为“状态空间模型”的关键层。当前系统已有 `health_trajectory.py`、`personal_models` 目录、个人预测模型设计文档、trajectory API 和多处“预测 vs 实际”产品痕迹，下一阶段应把这些收敛成统一产品能力。

产品要求：

- 预测层不是 LLM fine-tune，也不是把个人健康事实写进大模型权重。
- 预测层优先使用规则、趋势、个人 baseline、可穿戴偏离、临床锚点和小型统计模型。
- 每个预测必须包含 horizon、confidence、uncertainty、evidence_tier、claim_boundary 和需要补齐的数据。
- 基因只能提供边界、倾向、禁忌和阈值调谐，不能输出宿命式个体结论。
- 预测结果必须进入 ActionRanker、Agenda、InterventionCycle 或 Review，而不是变成孤立 dashboard。
- 低置信预测必须降级为 data_gap、watchlist 或 clinician_review，而不是强行动作。

### 3.4 Safety Guardian

Safety Guardian 是所有健康建议、执行和自动化前的硬约束层。当前系统已经有生命体征、化验、药物相互作用、补剂相互作用、药物基因组、CGM、训练、症状、心脏、问题红线和指导红线等规则族。

产品要求：

- 客户端只能展示安全结论，不能覆盖安全门。
- 涉及急症、红线、用药、剂量、禁忌、相互作用和高风险训练的路径必须 fail closed。
- AI 可以生成解释和候选方案，但不能绕过确定性安全规则。
- 预测越强，安全边界越重要；系统必须明确哪些轨迹只能观察、哪些可以生活方式干预、哪些必须升级医生。

### 3.5 LLM And Tool Synthesis

大模型推断层负责把个人数据、专业知识库、实时信号、历史干预和用户约束综合成可理解、可执行的计划。它的职责是 synthesize，不是替代确定性系统。

产品要求：

- LLM 输出必须转化为 HealthProblem、HealthProgram、HealthProtocol、HealthAgendaItem、WriteIntent、InterventionCycle、Review 或 explain-only 结果。
- LLM 可以给出饮食、睡眠、运动、补剂、环境和复查建议，但必须附带证据边界、安全状态和验证窗口。
- 药物、补剂、基因、疾病、怀孕、儿童、肝肾功能、相互作用和红线症状相关建议必须经过 SafetyGuardian。
- 补剂购买、补货、个性化搭配或未来个性化生产只能作为受控供应链意图，默认 manual_confirm，不得自动下单、不得替代医生处方、不得输出未经审查的疗效承诺。

### 3.6 Action Ranker

Action Ranker 把候选健康动作按杠杆排序。排序维度应包括：

- 上游性：是否影响多个下游指标或长期风险。
- 轨迹影响：是否有机会改变未来健康状态的方向，而不是只改善今日体验。
- 可执行性：今天是否能做。
- 频率和复利：是否能形成稳定收益。
- 可验证性：是否能在明确窗口内观察结果。
- 置信度：数据和证据是否足够。
- 摩擦：执行成本、时间、场景是否合适。
- 安全性：是否通过安全门，是否需要人工确认或医生介入。

输出必须回答用户的三个问题：

1. 今天为什么是这件事？
2. 我现在具体做什么？
3. 什么时候知道它有没有用？

### 3.7 Agenda

Agenda 是当前产品最重要的统一执行 contract。它应把 HealthProtocol、HealthProblem follow-up、训练 readiness、数据质量、日程、Daily Operating Plan、智能优先级和 Watch summary 收敛成一个可跨 surface 消费的列表。

产品要求：

- Agenda item 必须包含来源、状态、surface、优先级、为什么现在、执行方式、验证窗口和 replan 策略。
- Agenda item 必须说明它试图改变哪个状态变量、预计影响窗口、成功信号、失败/副作用信号。
- 完成、跳过、稍后、自动观察、手动补录必须写回统一事件。
- 医疗级 source model 和高风险行为不能通过语音或轻量入口绕过 domain safety。

### 3.8 IoT And Environment Execution

IoT 和环境设备是 Reva 的低摩擦执行层。它们可以帮助用户把健康行动从“记得做”变成“环境默认发生”，例如空气净化、湿度控制、灯光节律、窗帘、睡眠环境、智能水杯、血压/体重自动测量、坐姿提醒、屏幕休息和药盒/补剂库存观察。

产品要求：

- Reva 输出健康意图、场景触发和复盘任务；Home Assistant、厂商 App 或设备生态负责实时设备控制。
- 所有设备观察必须是结构化标量，不持久化原始图像、音频、视频或隐私过重的媒体。
- 设备自动化必须有 manual override、审计、降级路径和通知预算。
- 设备不能自行产生医疗判断；设备数据进入 Health Twin、Agenda 或 Review 前必须带 source、freshness、confidence 和 privacy classification。
- 高风险设备动作、财务动作和外部购买必须通过 WriteIntent 或独立一等对象逐笔确认。

### 3.9 Execution Event

Execution Event 是产品长期资产的关键原子。每次用户执行、跳过、延后、确认、自动观察或复查，都必须沉淀为可追溯事件。

产品要求：

- 事件要能连接到 HealthProtocol、HealthProblem、HealthProgram、InterventionCycle、WriteIntent 或具体 domain record。
- 跳过原因不能只做统计，要进入后续自我修正：时间不合适、难度过高、身体不适、无效、提醒太多等都应影响后续排序和通知。

### 3.10 Outcome Review And Causal Memory

当前系统已经有 InterventionCycle、OutcomeMetric、HealthOperatingReview、PersonalOutcomeService 和 CausalMemory 的雏形。它们应共同形成长期闭环：

- 记录 baseline。
- 执行动作。
- 到期复测或观察指标。
- 判断变化方向、显著性和噪声。
- 生成下一轮策略。

产品要求：

- 默认只声称 temporal association / observational signal，不轻易声称因果。
- 当系统建议继续、停止、调整时，必须能引用用户自己的历史数据和安全约束。
- 用户应能看到自己的“个人健康规律库”：哪些输入经常让某些指标变好或变差，哪些只是低置信观察，哪些需要更多数据。

### 3.11 Evaluation And Safety Regression

Reva 的 AI 能力不能只通过人工感觉判断好坏。系统必须有持续评估环境，用于验证 agent、ranker、prediction、SafetyGuardian 和 surface copy 是否仍然符合产品边界。

产品要求：

- EvaluationScenario 应覆盖正常用户、数据缺失、冲突数据、红线症状、药物/补剂相互作用、训练风险、IoT 失败、错误预测和用户拒绝等场景。
- SyntheticUserTwin 用于构造可复现的测试用户，不能包含真实用户敏感数据。
- SafetyRegressionSuite 必须在每次安全、agent、ranker 或 prediction 变化后验证 fail-closed、claim boundary、escalation 和 manual_confirm 行为。
- 评估指标不能只看回答是否流畅，还要看对象落地率、红线识别率、错误行动拦截率、预测校准、执行率、复测率和用户纠正后的调整质量。
- 评估结果应成为上线门槛和模型/工具切换依据，而不是一次性研究报告。

## 4. First-Class Product Objects

| Object | Product Meaning | Current Code Direction | Long-Term Requirement |
|---|---|---|---|
| HealthTwin | 用户当前健康状态镜像 | `backend/app/services/twin/*` | 成为所有推荐、分析和 surface 展示的上下文源 |
| DataConnection | 外部数据或设备连接 | HealthKit/Garmin/Oura/CGM/FHIR/Home Assistant connectors | 统一 provider、scope、token、同步窗口、错误、最后成功时间和撤权路径 |
| ConsentGrant | 用户授权和共享范围 | auth/audit/export/delete paths | 区分本人、家庭、医生、外部 agent、研究统计和 IoT 控制权限 |
| ProvenanceRecord | 数据来源和转换链 | source/freshness/confidence fields, import jobs | 让关键事实可追溯、可纠错、可删除，支撑信任和审计 |
| ConnectorPolicy | 连接器运行策略 | connector configs, sync jobs, rate limits | 管理速率、token refresh、失败降级、数据最小化和撤权后处理 |
| DomainKnowledgeBase | 专业健康知识与证据层 | `backend/data/system_kb_v2_seed/*`, `system_knowledge_service.py` | 为饮食、睡眠、运动、补剂、药物、慢病和环境建议提供 reviewed-first 证据 |
| RealtimeHealthSignal | 实时健康与环境信号 | wearable router, device source priority, bedroom/device observations | 统一实时监控数据的新鲜度、置信度、来源和隐私分类 |
| SafetyGuardian | 确定性安全门 | `backend/app/agents/safety_guardian/*` | 所有行动、通知和写操作前置安全检查 |
| HealthTrajectory | 健康轨迹和风险漂移视图 | `backend/app/services/health_trajectory.py` | 把先天底图、临床锚点、实时状态、可干预变量和下一步行动统一起来 |
| PersonalPrediction | 小型个人预测器 | `backend/app/services/personal_models/*` | 用人群先验 + 个人后验更新输出带不确定度的预测，不 fine-tune LLM |
| OrganSystemProgram | 器官/系统级改善计划 | `HealthProgram`, specialists, health domains | 按心血管、代谢、睡眠恢复、呼吸、消化、肌骨等组织行动，但保持全局安全和相互作用判断 |
| HealthProblem | 被管理的健康问题或风险 | `backend/app/models/health_problem.py` | 承载红线、负责人、复查、升级路径 |
| HealthProgram | 8-12 周健康改善计划 | `backend/app/models/health_program.py` | 把多个 protocol/action/metric 组织成长期计划 |
| ProgramTemplate | 可审查、可版本化的计划模板 | future template registry, `HealthProgram` seeds | 定义适用人群、排除条件、必要数据、安全门、protocol 列表、复测窗口和退出条件 |
| HealthProtocol | 可重复执行的健康协议 | `backend/app/models/health_protocol.py` | 支持自动观察、手动补录、跳过原因、自我调整 |
| HealthAgendaItem | 每日/近期执行单元 | `backend/app/services/agenda_service.py` | 成为 Mobile、Watch、Mac、Rokid、Web 的共同 contract |
| ExecutionEvent | 用户真实执行结果 | protocol events、intervention events、domain records | 成为长期健康 ledger 的核心原子 |
| InterventionCycle | N-of-1 改善闭环 | `backend/app/models/intervention_cycle.py` | 负责 baseline、目标、复测、显著性和下一步 |
| WriteIntent | 可控写操作意图 | `backend/app/models/write_intent.py` | 从 manual_confirm 逐步演进到 earned autonomy |
| IoTActuationIntent | 环境和设备执行意图 | `BedroomAutomationEvent`, `DeviceObservation`, Home Assistant design | 把健康意图转成受控设备场景、观察事件和复盘任务 |
| SupplyIntent | 补剂/耗材/健康商品供应链意图 | supplement inventory, reorder nudges, `ReorderIntent` scaffold | 只做物流/财务受控动作，逐笔确认，不自动医疗化、不静默下单 |
| CausalMemory | 观察性长期记忆 | `backend/app/services/causal_memory.py` | 存储“动作 -> 指标变化”的可解释个人证据 |
| SystemKnowledge | 系统知识和证据层 | `backend/data/system_kb_v2_seed/*` | 以 reviewed knowledge 为主，支持安全可追溯检索 |
| EvaluationScenario | 标准评估场景 | agent eval services, tests, future eval datasets | 持续评估 agent/ranker/prediction/surface 行为是否符合产品边界 |
| SafetyRegressionSuite | 安全回归集 | SafetyGuardian tests, red-line fixtures | 在安全、agent、prediction 变化后验证 fail-closed、manual_confirm 和升级路径 |
| SyntheticUserTwin | 合成测试用户 | test fixtures, synthetic datasets | 用非真实敏感数据复现高风险、缺失、冲突和长期闭环场景 |

## 5. Surface PRD

### 5.1 Mobile

定位：主日常产品。

Mobile 应拥有五个主入口：

- Today：今天状态、一个 top action、紧急风险、下一个 due item。
- Agenda：日/周/月/季度健康日程。
- Capture：饮食、饮水、症状、药物、补剂、测量、语音、照片和手动记录。
- Programs：代谢、恢复、睡眠、训练、药物/补剂、复查等 8-12 周计划。
- Review：执行、指标、复测、N-of-1 复盘和长期 ledger。

当前代码中 `mobile/app/(tabs)/index.tsx`、`mobile/app/(tabs)/record.tsx`、`mobile/app/agenda.tsx`、`mobile/app/intervention-cycle.tsx` 和 progress/review 页面已经对应这些方向。下一阶段重点不是新增页面，而是把主线收敛成这五个入口。

### 5.2 Apple Watch

定位：低摩擦执行器。

Watch 应只做：

- 显示 readiness、freshness、headline 和 top action。
- 展示 due items。
- 支持已做、稍后、跳过、快速记录、语音症状、饮水/食物等轻量动作。
- 尊重后端 WatchSummary、Agenda 和 NotificationDecision。

Watch 不应拥有复杂编辑、长报告、模型选择或独立健康判断。

### 5.3 Mac

定位：健康工作台。

Mac 适合：

- 文件、体检、化验、报告和本地资料导入。
- 长 agent workflow。
- trace、jobs、数据源、知识库和计划审查。
- 日历、处方、基因、数据完整性等复杂工作流。

Mac 不应替代 Mobile 的每日主循环，也不应产生与后端 Agenda 不一致的独立健康判断。

### 5.4 Web

定位：历史、报告、医生/家庭、管理和兼容 surface。

Web 可以保留：

- admin/ops。
- report/history/review。
- doctor/family。
- generated API/types 和兼容页面。

Web 不应继续作为主 consumer daily loop 的竞争入口。

### 5.5 Rokid / Ambient Devices

定位：实验性 hands-free 执行和捕捉 surface。

适合：

- 食物拍照/语音。
- 训练指导。
- 工作中低干扰提醒。
- 已经 command-ready 的语音 agenda。

不适合：

- 多页 dashboard。
- 噪声式 proactive broadcast。
- 绕过 auth、BLE、CustomView、voice readiness、session persistence 和 safety gate 的写操作。

### 5.6 Agent / MCP

定位：受控外部 agent 扩展。

外部 agent 可以通过 documented skills/API 查询、记录和分析健康数据，但必须遵守：

- auth。
- audit。
- source ownership。
- SafetyGuardian。
- WriteIntent / manual confirmation。
- 最小权限和隐私边界。

## 6. Core User Workflows

### W1. Daily Top Action

用户打开 Mobile 或 Watch 后，系统应该直接给出今天最值得做的一件事：

1. 读取 Twin、Agenda、Safety、日程和最新设备数据。
2. Action Ranker 选择 top action。
3. 系统解释 why now、do now、verify by。
4. 用户完成、跳过或稍后。
5. 事件写回，并影响后续排序和提醒。

### W2. Capture And Record

用户应能用最低摩擦记录关键健康行为：

- 语音、拍照、点击、手动输入。
- 高频入口优先：饮食、饮水、症状、运动、体重、药物、补剂、测量。
- 记录成功后不只进入日志，还应进入 Agenda、Twin、Program 或 Outcome Review。

### W3. Health Problem Follow-Up

对胃病、血压、脂肪肝、结节、鼻炎、用药、复查等问题，系统应维护：

- 风险等级。
- 当前状态。
- 红线。
- follow-up 日期。
- 负责人。
- 升级路径。
- 关联行动和复测。

到期 follow-up 必须进入 Agenda，而不是埋在记录页。

### W4. Health Protocol Execution

系统把长期建议拆成可执行 protocol：

- 饮水。
- 饮食模板。
- 餐后散步。
- 药物/补剂提醒。
- 训练、睡眠、测量、复查。

每个 protocol 必须支持 completed、skipped、snoozed、auto_observed 和 manual track，并将跳过原因用于后续调整。

### W5. Intervention Cycle

针对一个健康目标，系统应启动 8-12 周闭环：

1. 锁定 baseline。
2. 设置目标 metric 和安全边界。
3. 生成行动和 agenda。
4. 执行并持续记录。
5. 到期复测。
6. 输出结果、置信度、噪声说明和下一步。

### W6. Agent Analysis

Agent 应服务于 health loop，而不是替代 health loop：

- 使用 Twin、Knowledge、Safety、Agenda 和历史事件作为上下文。
- 专家能力逐步工具化，而不是只靠 prompt orchestration。
- 输出应转化为 HealthProblem、Protocol、AgendaItem、WriteIntent、InterventionCycle 或 Review。
- 不允许生成不可追踪、不可执行、不可验证的泛建议作为主结果。

### W7. Controlled Write

系统可以产生写操作意图，例如：

- 创建提醒。
- 安排复查。
- 生成日历事件。
- 打开外部服务。
- 提醒补货。
- 准备医生沟通材料。

但当前阶段默认必须是 manual_confirm。只有当低风险、可撤销、可审计、用户长期信任和安全评估都满足后，才能逐步进入 earned autonomy。

## 7. Functional Requirements

| ID | Requirement | Acceptance Signal |
|---|---|---|
| FR1 | 构建统一 Health Twin | 每个关键推荐都能回溯到 Twin section、数据源、新鲜度和缺失项 |
| FR2 | 所有健康行动经过 SafetyGuardian | 高风险、红线、用药、相互作用、训练风险路径 fail closed |
| FR3 | Agenda 成为跨端执行 contract | Mobile/Watch/Mac/Web/Rokid 使用同一 item/status/source 语义 |
| FR4 | 每日只突出一个最高杠杆行动 | Today/Watch 有清晰 top action，而不是信息瀑布 |
| FR5 | Capture 写入 domain record 和 execution ledger | 记录不孤立，能影响 Twin、Agenda、Review |
| FR6 | HealthProblem follow-up 进入 Agenda | 到期复查、红线和升级路径可见可执行 |
| FR7 | HealthProtocol 支持双轨输入 | protocol track 和 manual track 写同一事件语义 |
| FR8 | 跳过原因触发自我修正 | 系统能降低不合适提醒、调整时间窗或降低摩擦 |
| FR9 | InterventionCycle 形成 8-12 周闭环 | baseline、行动、复测、变化、下一步完整可见 |
| FR10 | Agent 输出必须落到对象 | 分析结果可转化为 Problem/Protocol/Agenda/WriteIntent/Review |
| FR11 | WriteIntent 默认人工确认 | 没有显式确认不执行外部写操作或高风险动作 |
| FR12 | 通知有预算和等级 | P0/P1/P2、quiet hours、weekly budget、surface provenance 可追踪 |
| FR13 | Wearable Router 统一仲裁 | 客户端展示 winning source、confidence、freshness，不本地裁决 |
| FR14 | Knowledge 使用 reviewed-first 原则 | 健康知识默认来自受控知识库，运行时 web search 不能成为主权威 |
| FR15 | 所有用户数据按 user_id/权限隔离 | 健康数据查询、导出、外部 agent 调用都有鉴权和审计 |
| FR16 | Twin 区分先天参数、状态、运行时输入和可干预变量 | 用户建议不把基因/状态/行为混为一谈 |
| FR17 | HealthTrajectory 成为预测和治理入口 | 每个轨迹风险都有 horizon、confidence、evidence_tier、claim_boundary 和 next action |
| FR18 | 预测必须有不确定度和边界 | 低置信预测降级为观察/补数据/医生复核，不直接驱动高风险行动 |
| FR19 | Agenda 行动表达控制输入语义 | 每个 top action 说明目标状态变量、预期窗口、成功信号和失败信号 |
| FR20 | 用户可见个人健康规律库 | CausalMemory/OutcomeReview 以“观察性关联”方式呈现个人输入和指标变化 |
| FR21 | 真实个人数据层可追溯 | 基因、表观遗传、报告、体检、年龄性别体重等数据都有来源、时间、权限和置信度 |
| FR22 | 专业知识库 reviewed-first | 饮食、睡眠、运动、补剂、药物和慢病建议能引用受控知识或明确低置信边界 |
| FR23 | 实时监测数据统一仲裁 | 心率、血压、血糖、HRV、睡眠、压力、身体电量、血氧和环境信号进入统一 source/freshness/confidence contract |
| FR24 | IoT 只作为受控执行层 | 空气、湿度、灯光、窗帘、水杯、床垫、座椅、屏幕等设备只能执行健康意图和观察事实，不产生独立医疗判断 |
| FR25 | 补剂和供应链动作受控 | 补剂建议、库存、补货、购买和未来个性化搭配/生产必须经过 DDI/DSI/PGx、安全审计和 manual_confirm |
| FR26 | 器官系统 program 统一到全局 Twin | 心血管、代谢、睡眠恢复、呼吸、消化、肌骨、认知心理等 program 不得局部优化破坏全局风险 |
| FR27 | 标准互操作优先 | FHIR Bundle、SMART on FHIR、HealthKit 和主流设备连接进入统一 DataConnection，而不是临时导入脚本 |
| FR28 | 授权和撤权产品化 | 用户能查看、暂停、撤销、删除或限制每个 DataConnection、agent scope 和共享对象 |
| FR29 | 关键事实可追溯 | 每个影响建议的事实都能展示 ProvenanceRecord、转换链、置信度和用户纠错状态 |
| FR30 | ProgramTemplate 可审查可版本化 | 8-12 周计划由模板生成，模板声明适用人群、排除条件、安全门、协议、复测和退出条件 |
| FR31 | Agent 和 ranker 必须持续评估 | 每次模型、工具、ranker 或提示变化都跑 EvaluationScenario，记录质量和安全回归结果 |
| FR32 | SafetyRegressionSuite 阻止危险回归 | 红线、用药/补剂相互作用、训练风险、IoT/供应链写操作必须有 fail-closed 回归用例 |
| FR33 | IoT observation 先于 actuation | 设备先作为结构化观察和低摩擦确认进入 Agenda/Review，自动控制必须等 allowlist、manual override 和审计成熟 |
| FR34 | ConnectorPolicy 管理外部连接 | 每个 provider connector 定义 scope、rate limit、token refresh、同步失败降级、数据最小化和撤权后处理 |

## 8. Non-Functional Requirements

### Safety And Privacy

- L3/L4 健康数据、token、药物、基因、报告和家庭数据必须按最小权限处理。
- 所有用户数据访问必须带用户隔离。
- 外部 agent、MCP 和 proactive writes 必须可审计。
- 系统不得把“观察性关联”包装成确定性因果。

### Reliability

- Daily loop 必须在后端局部失败时可降级：某个数据源或 specialist 失败不应导致整个 Today 不可用。
- SafetyGuardian 失败应 fail closed。
- 设备数据 stale/conflict 时必须显式展示，而不是默默使用。

### Performance

- Today/Agenda/Watch summary 是高频路径，应优先控制延迟。
- AI 分析可以慢，但必须和每日执行路径解耦。
- 1000 万用户目标要求从现在开始记录成本、延迟、缓存命中、工具调用次数和失败类型。

### Trust And Explainability

- 每个建议要说明来源、推理摘要、安全状态和验证窗口。
- 用户必须能知道系统为什么提醒、为什么不提醒、为什么换了行动。
- 用户必须能纠正、跳过、暂停和删除某类建议。

### Interoperability And Consent

- FHIR/SMART、HealthKit、Garmin/Oura/Withings/CGM 和 Home Assistant 等连接必须通过统一 DataConnection/ConsentGrant/ConnectorPolicy 运行。
- 连接授权、撤权、token refresh、同步失败和数据删除必须可见、可审计、可恢复。
- 家庭、医生、外部 agent 和研究/匿名统计必须使用不同 consent scope，不能复用默认全量权限。

### Evaluation And Release Gates

- agent、ranker、prediction、SafetyGuardian、ProgramTemplate 和 IoT/supply-chain 行为变化必须有 EvaluationScenario 或 SafetyRegressionSuite 覆盖。
- 评估必须覆盖对象落地率、安全拦截率、claim boundary、预测校准、执行率、复测率和用户纠错后的调整。
- 大模型、工具或 connector 切换不能只凭离线主观判断，必须保留评估结果和回滚路径。

## 9. Current AS-IS Assessment From Code

### 9.1 Strongly Implemented

代码已经明显超出普通健康应用原型，核心能力包括：

- FastAPI 后端、统一路由、鉴权、scheduler、Sentry、rate limit 和配置校验。
- HealthProblem、HealthProgram、HealthProtocol、InterventionCycle、WriteIntent 等核心对象。
- AgendaService、HealthProtocolService、HealthProblemService、WatchSummary、ActionRanker、ProactiveCoordinator。
- Digital Health Twin、SafetyGuardian、WearableRouter、DeviceSourcePriority。
- Agent Executor、Orchestrator、specialists、tool schema、specialist tools feature flag。
- Mobile Today/Record/Agenda/Intervention/Review，Watch Today/quick actions，Mac workbench，Web history/admin，Agent/MCP skills。
- 测试已经覆盖 HealthProtocol、Agenda contract、Health OS API、surface ownership 等关键路径。

### 9.2 Partially Implemented Or Fragmented

当前主要问题不是能力不足，而是产品主线需要收敛：

- 现有 surface 太多，部分 Web/Mobile 页面仍像并列产品，而不是同一 loop 的不同入口。
- HealthProgram 与 Protocol、Problem、InterventionCycle 的关系还需要更清晰地产品化。
- Outcome proof 已有服务和模型，但在主 UI 中还不够可见。
- HealthTrajectory、personal_models、健康预测设计文档和“预测 vs 实际”能力已经存在，但还没有统一为一条主产品线。
- Agent specialist orchestration 和 toolized specialist 能力并存，长期应向工具化、可评估、可审计迁移。
- CausalMemory 目前更接近观察性总结，还没有成为用户能直接感知的长期资产。
- WriteIntent 已有手动确认框架，但距离可扩展的 earned autonomy 还需要分级、权限、撤销和审计体验。
- 设备 source arbitration 已有后端能力，但多租户、个体化 source preference 和异常处理还需要加强。
- FHIR/SMART、报告导入、设备连接、IoT 和外部 agent 还没有统一 DataConnection、ConsentGrant、ProvenanceRecord 和 ConnectorPolicy。
- agent/ranker/prediction 评估还没有成为上线门槛，缺少 SyntheticUserTwin、EvaluationScenario 和 SafetyRegressionSuite 的持续体系。
- HealthProgram 已有对象，但 ProgramTemplate 尚未成为可审查、可版本化、可复用的产品资产。
- 文档中已有“不要继续堆功能”的方向，代码也显示目前更需要收敛、验证和上线质量，而不是再开新大模块。

## 10. Long-Term System Goal

### 10.1 1000 万用户目标定义

Reva 的长期目标不是让 1000 万人安装一个健康应用，而是让至少 1000 万用户能日常使用一个可信健康操作系统，持续改善自己的健康状态。

可验收的 1000 万用户目标应同时满足：

- 用户经常把 Reva 当作每日健康行动入口。
- Reva 每周帮助用户完成安全、个性化、可验证的健康行动。
- Reva 能沉淀用户长期健康 ledger，而不是一次性回答。
- Reva 在风险、隐私、成本、延迟和错误率上可规模化运营。
- Reva 能证明对一部分关键健康状态有真实趋势改善，而不是只证明 engagement。

### 10.2 Long-Term Product Thesis

未来十年，个人健康产品的核心资产会从“内容”和“设备数据展示”转向“可信健康托管 + 每日执行 + 个人证据账本”：

```text
Daily Artifact
  + Trust-Custodianship
  + Deterministic Safety
  + Evidence-Governed AI
  + Low-Friction Execution
  + N-of-1 Outcome Verification
  = Personal Health OS
```

Reva 的长期系统目标是成为：

- 用户个人健康状态的长期可信账本。
- 用户每日健康行动的执行层。
- 用户与医生、家庭、设备、agent 和外部服务之间的安全中介。
- 一个能随时间学习“什么对这个用户有效”的个人健康改善系统。

### 10.3 Competitive Benchmark Correction

竞品调研对长期目标给出四个硬修正：

1. **每日仪式是季度护城河的前门**。Whoop/Oura 的留存证明，用户不是为 90 天后的外环每天回来，而是为每天一个可理解的复合判断回来。Reva 必须把 `Daily Artifact` 做成长期主路径：今日状态、一个 top action、证据、完成/跳过、后续验证。
2. **护城河不是数据量，而是信任托管**。per-user 纵向数据会边际递减，且不能直接迁移给用户 #2。持久防御来自用户愿意托管更敏感数据、确定性安全脑约束 LLM/写入、以及多年执行/复测/解释形成的迁移成本。
3. **因果账本必须弱证据弱表达**。N-of-1 是开放空间，也是学术/商业风险区。CausalMemory 默认只能叫 observation 或 hypothesis；只有通过复测、样本数、噪声处理和安全边界后才能叫 validated effect。
4. **分发需要 5 分钟 on-ramp**。OpenHealth 证明“能跑、能看懂、能马上感觉到价值”先于深度。Reva 必须让新用户在 60-300 秒内看到安全脑、证据卡和一次可执行 top action。

## 11. Strategic Pillars For 10M Scale

### Pillar 1. Trustworthy Health Data Layer And Signal Contract

目标：让用户所有关键健康数据进入一个有来源、有新鲜度、有冲突处理、有权限控制的结构化层。

建设重点：

- 更强 onboarding：体检、Apple Health、Garmin/Oura、CGM、药物、补剂、症状、目标。
- 标准互操作：FHIR Bundle、SMART on FHIR、HealthKit、Garmin/Oura/Withings/CGM、Home Assistant 和后续 provider connectors。
- DataConnection、ConsentGrant、ProvenanceRecord 和 ConnectorPolicy 成为所有外部来源的统一治理对象。
- 建立 `SeriesType` 式 Signal Contract：每个指标固定单位、聚合语义、source priority、coverage matrix、freshness 和 privacy class。
- 建立 ClinicalRecordLibrarian：出院小结、门诊病历、体检 PDF 先 index，再按问题检索证据片段进入 Twin/Chat/Review。
- source quality score 和 per-user source preference。
- 数据缺口解释和最小补齐任务。
- 医生/家庭/导出场景的数据权限模型。

### Pillar 2. Health Trajectory And Prediction

目标：把健康从“状态解释”升级为“轨迹预测和运行时治理”。

建设重点：

- Health Twin 明确区分先天参数、当前状态、运行时输入、社会约束和可干预变量。
- `health_trajectory.py` 成为上游风险漂移和 next action 的统一入口。
- `personal_models` 只做小型统计预测器：人群先验 + 个人后验更新 + 不确定区间。
- 先从 Garmin/Apple Health 个人 baseline、异常偏离、8-12 周 InterventionCycle 和预测回测做起。
- 预测必须进入 Agenda、ActionRanker、Review 或补数据任务，不能变成孤立 dashboard。

### Pillar 3. Deterministic Safety And Evidence Governance

目标：让用户相信 Reva 不会为了 engagement 给出危险建议。

建设重点：

- SafetyGuardian 全链路接入。
- reviewed-first knowledge。
- DDI/DSI/PGx/训练/急症/红线持续扩展。
- 高风险场景升级医生或急救，而不是继续聊天。
- 建议证据等级、适用边界和不确定性可见。

### Pillar 4. Daily Artifact And Anti-Habituation OS

目标：让用户每天知道今天身体状态、为什么、现在做什么，并且真的做完，同时避免 JITAI 习惯化。

建设重点：

- Today/Watch/Chat 共用一个 Daily Artifact：状态判断、一个 top action、最多 3 个证据、confidence/freshness/safety boundary、完成/跳过/问 Reva。
- Watch/phone/ambient 低摩擦执行。
- Agenda 跨端统一。
- 跳过原因驱动调整。
- capped action count、dynamic availability、投递时机个性化和行动接受率周衰减监控。
- 通知预算和情境感知。
- 不追求提醒多，追求提醒准。

### Pillar 5. N-of-1 Verification And Honest Personal Evidence Ledger

目标：从“建议”进化为“对这个用户有效的证据”。

建设重点：

- 12 周 InterventionCycle 成为核心用户体验。
- 每个 program 都有 baseline、target、action、retest、review。
- 用噪声-aware 方法解释变化。
- 长期 CausalMemory 从后台能力变成用户可见资产，但必须用 `observation / hypothesis / validated_effect` 分级表达。
- Discoveries 体验把“你尝试了 X，指标 Y 出现了什么变化”做成 Chat/Review 卡片，弱证据弱表达。

### Pillar 6. Controlled Write And Earned Autonomy

目标：从只提醒用户，逐步走向低风险、可撤销、可审计的自动执行。

建设重点：

- WriteIntent 分级：display only、draft、manual confirm、trusted confirm、auto for reversible low-risk。
- 对日历、提醒、购物清单、预约、复查、家庭通知、医生摘要等外部动作提供可撤销执行。
- 每个自动化都有权限、审计、回滚和用户解释。

### Pillar 7. Ecosystem, Distribution And 5-Minute On-Ramp

目标：在不失控的前提下让 Reva 进入更多用户工作流。

建设重点：

- 5 分钟 on-ramp：合成数据、示例报告、真实 HealthKit 三入口，60-300 秒内展示安全脑、证据卡和 Daily Artifact。
- Agent/MCP skills 成为受控 extension layer。
- 医生、家人、企业健康和设备合作有不同权限边界。
- API contract 稳定，客户端只做 surface，不做独立健康裁决。

### Pillar 8. IoT Environment And Supply Chain Execution

目标：把健康行动从“提醒用户”升级为“环境默认 + 设备观察 + 受控供应链执行”。

建设重点：

- 先做高 ROI、低风险的环境闭环：卧室 CO2、PM2.5、湿度、温度、灯光、窗帘和睡眠保护窗口。
- 智能血压计、体重计、水杯、药盒、床垫和办公设备优先作为自动观察和低摩擦确认，不作为独立判断源。
- 补剂库存、补货和购买保持物流/财务边界；真实下单必须逐笔确认，不存支付凭据，不自动循环下单。
- 个性化补剂搭配或未来个性化生产只作为长期受控供应链能力，必须有 reviewed knowledge、相互作用检查、批次质量、法规和审计边界。
- IoT 设备接入以 Home Assistant / 厂商生态 / 标准协议为控制层，Reva 不做实时家居控制器。

### Pillar 9. Evaluation And Safety Regression Platform

目标：让 agent、ranker、prediction 和安全门的质量可持续验证，而不是依赖人工感觉或线上试错。

建设重点：

- 建立 SyntheticUserTwin，用非真实敏感数据覆盖缺失、冲突、红线、长期闭环和多设备场景。
- 建立 EvaluationScenario，评估对象落地率、行动排序、claim boundary、预测校准、执行率、复测率和用户纠正后的调整。
- 建立 SafetyRegressionSuite，覆盖急症红线、DDI/DSI/PGx、训练风险、IoT actuation、补剂供应链和 manual_confirm。
- 每次模型、工具、ranker、ProgramTemplate 或 connector 变化都保留评估结果和回滚依据。

## 12. Evolution Roadmap

### Phase 0. Consolidate Current Product

时间窗口：现在到 4 周。

目标：

- 让所有人对“Reva 当前是什么”达成一致。
- 停止新增并列 daily loop。
- 把 Mobile/Watch/Mac/Web/Agent/MCP 归位。

关键交付：

- 采用本 PRD 作为 code-derived baseline。
- 更新 surface ownership inventory。
- 标记和隐藏 admin/debug/stale daily pages。
- 明确 Today、Agenda、Capture、Programs、Review 五个主入口。
- 明确所有新需求必须落到 first-class object 和 verification loop。
- 明确 Health Runtime Governance 叙事：预测层只服务行动、验证和安全治理。
- 明确 DataConnection、ConsentGrant、ProvenanceRecord、ConnectorPolicy、ProgramTemplate、EvaluationScenario、SafetyRegressionSuite 进入一等对象清单。
- 定义 Daily Artifact contract：状态判断、一个 top action、最多 3 个证据、confidence/freshness/safety boundary、完成/跳过/问 Reva。
- 埋点 action impression、accepted、completed、skipped_reason、delivered_context、week_index，建立抗习惯化观测。

### Phase 1. Make One Wedge Work End To End

时间窗口：1-3 个月。

目标：

- 对第一类用户做到“每天打开就有价值”。
- 完成 12 周 metabolic/recovery/sleep/energy 闭环。
- 证明系统能离开创始人锚点，对第一批异质用户仍然给出可用 top action。

关键交付：

- 首次 onboarding 自动生成 HealthTwin、HealthProblem、Program、Protocol、Agenda。
- 首次 onboarding 同时生成或绑定 DataConnection、ConsentGrant、ProvenanceRecord 和最小 ConnectorPolicy。
- 首次 onboarding 区分先天参数、状态、运行时输入、社会约束和可干预变量。
- 5 分钟 on-ramp 支持示例报告、合成数据、真实 HealthKit 三入口，并在 60-300 秒内展示安全脑、证据卡和一次 Daily Artifact top action。
- 至少支持一个 FHIR Bundle/报告导入路径和一个 wearable/device DataConnection 的端到端授权、同步、撤权和 provenance 展示。
- Mobile Today、Watch 和 Chat 共用 Daily Artifact，而不是各自解释 top action。
- InterventionCycle review 在用户主路径可见。
- 行动完成、跳过、复测、结果变化形成可读 ledger。
- HealthTrajectory 风险和个人 baseline 偏离进入 ActionRanker，不再只做解释。
- 第一批 metabolic/recovery/sleep ProgramTemplate 可审查、可版本化，并声明适用人群、排除条件、安全门和复测窗口。
- 先服务 10-100 个高质量用户，追求真实改善而不是泛化规模；其中第一批必须含 5-10 个与创始人不同的用户，验证系统不把 N=1 假设误推给所有人。

### Phase 2. Toolized Agent And Evaluation

时间窗口：3-9 个月。

目标：

- 让 AI 能力从 prompt 编排进化到可工具调用、可评估、可审计。

关键交付：

- specialist 能力工具化。
- SafetyGuardian 强制前置和后置检查。
- 所有 agent 输出映射到对象。
- 小型个人预测器输出带不确定度的 forecast，LLM 只负责解释、提问和转化为对象。
- 建立建议质量、风险误判、执行率、结果复测、用户纠正的数据集。
- 建立 SyntheticUserTwin、EvaluationScenario 和 SafetyRegressionSuite，作为 agent/ranker/prediction/safety 变更的 release gate。
- 引入 prediction backtest 与 safety regression 的维护视图，防止模型或 prompt 改动破坏既有边界。
- 建立 discovery card 和 CausalMemory 证据语言 gate，默认 observation，满足复测/样本数/噪声处理后才可升级 hypothesis 或 validated_effect。
- 建立 Signal Contract / coverage matrix，使 LLM、trajectory 和 ActionRanker 只消费单位、聚合语义、来源和新鲜度明确的指标。
- 成本和延迟进入产品 SLO。

### Phase 3. Self-Serve Growth With Clinical-Grade Trust Boundaries

时间窗口：9-18 个月。

目标：

- 从高触达用户扩展到 10 万-100 万级自助用户，同时守住健康风险边界。

关键交付：

- 自助 onboarding、设备连接、报告导入和体检解读。
- ClinicalRecordLibrarian 支持出院小结、门诊病历、体检 PDF 的叙事证据检索，优先服务中国现实数据来源。
- 家庭/医生协作权限。
- DataConnection 和 ConsentGrant 支持自助管理、家庭/医生共享、撤权、导出、删除和 connector 故障解释。
- 多地区隐私、导出、删除、审计和合规机制。
- 可复用 program templates，但仍需个人化 safety 和 context。
- 付费、合作渠道和单位经济模型成型。

### Phase 4. 10M Personal Health OS Platform

时间窗口：18-36 个月以上。

目标：

- 成为千万级用户每日健康执行入口和个人健康 ledger。

关键交付：

- 多语言、多地区、多设备、多伙伴生态。
- 高可用、低成本、强审计的 health data infrastructure。
- 安全事件响应和医学/证据治理运营体系。
- 大规模 N-of-1 verification network。
- 受控 external agent/plugin ecosystem。

## 13. Milestone Metrics

| Stage | User Scale | Product Proof | Health Proof | System Proof |
|---|---:|---|---|---|
| Dogfood | 10-50 | Daily Artifact D7 使用、每周完成 top action、skip reason 可用 | 至少 1 个 12 周 cycle 有可读结果 | 安全门、agenda、review 可闭环 |
| Pilot | 100-1,000 | D7/D30 留存、行动接受率周衰减可观测、5 分钟 on-ramp 转化 | 代谢/睡眠/恢复指标有趋势改善 | agent 输出对象化，成本可控 |
| Paid Wedge | 1,000-10,000 | 付费和复购、异质用户 cohort 仍有可用 top action | program completion/retest 成熟 | 数据源、通知、审计稳定 |
| Self-Serve | 10 万-100 万 | onboarding 自动化 | 多人群 program 验证 | 多租户、权限、SLO 成熟 |
| Platform | 100 万-1000 万+ | 成为日常入口 | 大规模改善证据 | 合规、安全、成本、生态可扩展 |

## 14. Product Governance Rules Going Forward

所有后续需求必须回答：

```yaml
target_user:
health_problem_or_goal:
first_class_object:
surface_owner:
core_loop_step:
daily_artifact_impact:
habituation_guard:
onramp_impact:
state_variable_to_change:
prediction_or_trajectory_claim:
safety_gate:
data_source:
data_connection:
consent_scope:
execution_event:
verification_plan:
evidence_language:
evaluation_scenario:
rollback_or_archive_plan:
```

硬规则：

1. 新功能不能只新增页面，必须改进 core loop。
2. 新 agent 能力不能只输出文本，必须能落到对象或明确标记为 explain-only。
3. 高风险健康行为不能通过轻量入口绕过 SafetyGuardian。
4. 日常主路径优先 Mobile/Watch，复杂工作流优先 Mac，Web 退到 history/admin/doctor/family。
5. Outcome Review 和 CausalMemory 必须从后台能力变成用户可见资产。
6. 预测必须带不确定度、证据等级和声明边界；不能把基因或弱关联包装成个体命运。
7. 新外部数据源、设备、agent 或 IoT 能力必须先定义 DataConnection、ConsentGrant、ProvenanceRecord 和 ConnectorPolicy。
8. 新 agent、ranker、prediction、安全门或 ProgramTemplate 变化必须进入 EvaluationScenario / SafetyRegressionSuite。
9. 如果一个功能无法提高安全行动完成率、验证闭环、健康结果、轨迹治理或信任，它不应进入主路径。
10. 任何主路径功能都必须说明它如何增强 Daily Artifact、5 分钟 on-ramp 或 Discoveries，否则默认后置。
11. 任何因果语言都必须经过 evidence_language gate，弱证据只能叫 observation 或 hypothesis。

## 15. Immediate Next Product Decisions

建议下一阶段只做十四类工作：

1. 收敛 surface：Mobile 五入口、Watch 执行器、Mac 工作台、Web 历史/管理。
2. 做强 Daily Artifact：状态判断、一个 top action、why now、do now、verify by、证据、skip reason。
3. 做强 HealthTrajectory：让每个 top action 连接到状态变量、运行时输入和未来漂移风险。
4. 做强 12 周闭环：baseline、actions、retest、review、next cycle。
5. 做强 5 分钟 on-ramp：示例报告/合成数据/真实 HealthKit 三入口，让安全脑和 top action 立即可见。
6. 做强 onboarding：让新用户从报告/设备/目标自动进入 Program 和 Agenda。
7. 做强 safety/evidence：所有建议有 safety、evidence、uncertainty 和 escalation。
8. 做强 CausalMemory 诚实表达：observation/hypothesis/validated_effect 分级，弱证据不说因果。
9. 做强 eval：把 agent 建议质量、预测命中率、执行率、复测率和健康结果纳入持续评估。
10. 做强 data connection：把 FHIR/SMART、报告导入、wearable、CGM、Home Assistant 统一到 DataConnection/ConsentGrant/ProvenanceRecord。
11. 做强 signal contract：为 wearable/HealthKit/CGM/环境指标建立 SeriesType、单位、聚合、coverage matrix 和 provenance。
12. 做强 ProgramTemplate：先把 metabolic/recovery/sleep 三类 8-12 周计划做成可审查、可版本化模板。
13. 做强 connector policy：让每个外部连接都有 scope、rate limit、token refresh、失败降级和撤权后删除策略。
14. 做异质用户验证：招 5-10 个非创始人用户作为 Phase-1 blocker，防止 N=1 过拟合。

这比继续新增更多健康功能更重要。当前代码显示 Reva 已经有足够多能力，下一步产品胜负在于每日可感价值、收敛、信任、执行和验证。
