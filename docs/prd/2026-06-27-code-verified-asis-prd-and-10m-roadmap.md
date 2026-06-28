# Reva 代码核验版：当前产品 PRD · 长期目标反推 · 1000 万用户演进路线

> Status: code-verified baseline（证据级）
> Updated: 2026-06-27
> Owner: Reva / Personal Health OS
> 方法：对全仓库 15 个子系统做只读取证盘点 + 对抗式复核（31 个 agent、~3.3M token、894 次工具读取、读真实 `file:line` 与测试），逐条把"声称实现"降级到 `real / partial / scaffold_inert / placeholder / aspirational`。
> 关系：本文是 [`2026-06-27-code-derived-product-prd-and-10m-goal.md`](2026-06-27-code-derived-product-prd-and-10m-goal.md)（愿景版 PRD）与 [`../plans/2026-06-27-health-runtime-governance-plan.md`](../plans/2026-06-27-health-runtime-governance-plan.md)（治理计划）的**证据底座**。前两份是"我们想成为什么"；本文是"代码现在到底是什么"，并据此修正 10M 路线的优先级。产品方向权威仍是 [`reva-personal-health-os-prd.md`](reva-personal-health-os-prd.md)；长期战略锚点是 [`2026-06-16-enter-key-leverage-thesis.md`](2026-06-16-enter-key-leverage-thesis.md)；竞品与红队修正来源见 [`../reports/2026-06-27-competitive-benchmark-and-prd-critique.md`](../reports/2026-06-27-competitive-benchmark-and-prd-critique.md)。

---

## 0. 一句话核验结论

> **Reva 今天（代码核验）是一个跑通了的、单锚点用户的"每日健康闭环"——不是文档暗示的多租户预测式 Health OS。**

真正端到端跑通的脊柱是：

```
多源采集 → 16 分区 Digital Health Twin → 62 条确定性安全规则 + 13 专家 Orchestrator
        → 统一 Agenda/Timeline（完成即原子写真实领域记录）→ ActionCard/InterventionCycle 结果评分
```

这条**向内闭环（inward loop）成熟且测试充分**。但三件被文档当成"已有"的能力，核验后是另一回事：

1. **预测/轨迹** 基本是回顾性的——**全仓库没有任何"向前预测"**；唯一叫 `backtest` 的是诚实的 `not_ready` 占位；主动轨迹推送需要 ≥2 个 Twin 快照，而**没有任何周期任务去写第二个快照**，对未进入 cycle 的绝大多数用户是静默 no-op。
2. **自主执行 / 供应链 / IoT 边缘**是**有意 inert** 的脚手架：下单一律 `HTTP 501 by design`，对外设备执行**一条都没发**。
3. 系统**普遍单租户**：源仲裁是全局硬编码、RLS 只覆盖 N 张表里的 2 张、JWT 2 年不可撤销，且背着很重的**收敛债**（4 个聊天入口、6+ 个每日计划面、2 个 Twin、158 个 router）。

这与战略论纲完全吻合：[`enter-key-leverage-thesis`](2026-06-16-enter-key-leverage-thesis.md) 早判断"框架 ~70% 已落地，唯一真缺 = Write 自治层"。本文用代码逐条证实了这句话，并补出它没点名的另外两块真缺口（**冷启动/多租户**、**前向预测**）。

### 0.1 竞品调研吸收结论

Claude 的竞品调研有两类价值：

- **战略结论高置信**：Whoop/Oura、OpenHealth、Medplum、open-wearables、Spezi、Fasten/health-skillz 给出的共同信号足够明确：Reva 的深度方向是对的，但用户留存、分发、合规底座和可见价值原语都弱。
- **代码事实需要分支校正**：该报告明确用 `origin/main` 校正了部分活代码事实；本工作分支仍可能落后。例如本分支没有 `services/write_autonomy.py`，而报告指出 `origin/main` 已有 write autonomy 第一刀。因此本 PRD 接收其战略修正，同时把代码事实按"当前分支 / origin/main 差异"标注，避免把未合并能力当作本分支现实。

本次正式吸收 8 条修正：

1. **每日可感价值原语升为 P0**：Reva 不能只把价值押在 30-180 天外的复测和 N-of-1 账本上；必须有一个类似 Whoop/Oura 的每日工件，让用户每天打开就知道"今天身体状态、最值得做的一件事、为什么"。
2. **抗习惯化是产品要求，不是运营优化**：每日行动必须有 capped-count、dynamic availability、skip reason、投递时机个性化，并追踪"行动接受率随周衰减"。
3. **5 分钟 on-ramp 是分发要求**：OpenHealth 证明"可运行、可演示、可理解"比深度更先决定传播；Reva 的安全脑、知识库和诚实归因必须能在 60-300 秒内被新用户看见。
4. **护城河叙事改为 trust-custodianship + 确定性安全脑**：per-user 因果账本是产品学习资产，不应被表述成单纯"数据量网络效应"；持久护城河来自用户愿意把更敏感数据托管给 Reva，以及 Reva 能用确定性安全规则约束 LLM/写入。
5. **异质用户验证前置**：Phase 1 必须招募 5-10 个与创始人不同的用户，覆盖不同性别、不同主诉、不同设备组合、不同药物/补剂背景，作为 10M 泛化的硬门。
6. **CausalMemory 诚实性升为信任承重墙**：任何"X 改善了 Y"都必须带证据级、样本数、回归均值/混杂 caveat；弱相关只能叫 observation，不能叫因果。
7. **统一 signal contract 与 provenance**：吸收 open-wearables 的 `SeriesType` 思路，为每个时序指标固定单位、聚合方式、来源、新鲜度和 coverage matrix，避免 AI-ready 信号层继续散在各 adapter。
8. **临床叙事病历管线进入路线图**：在中国场景，出院小结、门诊病历、体检 PDF 的叙事信息比美国 SMART-on-FHIR 更现实；应新增 ClinicalRecordLibrarian，把 index→关键词检索→全文证据片段接入 Twin/Chat/Review。

---

## 1. 当前产品是什么（Code-Verified AS-IS）

### 1.1 核心闭环逐步现状

| 闭环步骤 | 核验状态 | 证据（file:line / 测试） | 关键缺口 |
|---|---|---|---|
| **Intake 采集** | ✅ real | HealthKit push `/devices/healthkit/import`（按源幂等）、Garmin Celery 2h 自动同步、biomarker 归一、ambient/Rokid 语音视觉、device-observation | 源仲裁全局单租户；CGM Libre/Dexcom `NotImplementedError`；Apple/RingConn 新鲜度依赖 App 被打开 |
| **Twin 状态镜像** | ✅ real | `twin/schema.py:463` 16 分区；`build_twin` 三阶段并行 filler；~45 消费者；60s Redis 缓存；`twin_to_prompt_blob` 带分区新鲜度；69 测试 | TwinSnapshot 仅 cycle 路径写，无周期快照；`quality_grade` 算了没人读；并存 legacy `DigitalTwinService` |
| **Trajectory / 预测** | 🟡 partial | `health_trajectory.py` 当前态风险快照（state_variable/horizon/uncertainty 合同，3 消费者含 agenda top-action）；personal baseline z-score；RHR 偏离哨兵 | **无任何前向预测**——全是回顾性；`_prediction_backtest_placeholder` 硬返回 `not_ready`；`trajectory_watch` 因缺快照饿死 |
| **Safety 安全门** | ✅ real | 62 条 `@register` 规则、registry 引擎、7+ 消费面；watch 症状路径 fail-loud→fail-safe HIGH advisory；R4 guidance 校验 + AdviceGuard | **当前分支** fail-loud `failed_rule_count` 只有 `watch.py:337` 一个消费者；竞品报告复核 `origin/main` 后指出用药/自治写等路径已扩接，剩余重点应窄到 `guardian.py`/报告面/orchestrator under-alarm；LLM 合成层仍需对抗门 |
| **LLM/工具综合** | ✅ real | Orchestrator 合成带 safety wrap + memory + system-KB 注入；AgentExecutor 统一 tool-calling + 弱模型门控；provider failover；SSE 流式 | 4 个聊天入口并存；OpenClaw skill 分支在默认 tokenplan provider 下走不到；IQS grounding 失败返回 `''` 永不阻断 |
| **Action Ranker 排序** | ✅ real | `action_ranker` 读 `item['trajectory_context']` 套 `_TRAJECTORY_LEVEL_BOOST {high:45, attention:25}`；trajectory_context 在 agenda_service 构建并端到端测试 | 两套未统一排序公式：`action_ranker`（watch）vs `agenda_service._rank_score`（smart_today），两端排序数学不同 |
| **Agenda 执行合同** | ✅ real | 后端单一合同 `health_agenda_contract_v1` + smart_today top-N + 时序 today-spine；mobile 共用完成路径；HealthProtocol `today_status` 喂脊柱 | 6:00 Celery "daily plan" 建的是 **legacy AIScheduler 晨报，不是 DailyOperatingPlan**；DOP 只在读时惰性生成；三套规划面并存 |
| **Surface 执行** | ✅ real | `complete_by_ref/complete_agenda_event` 物化 HealthEvent 并双写真实源（MedicationLog/SupplementRecord/WaterIntake/DietRecord/ExerciseRecord）；**原子 DB 认领防虚高依从**；mobile Hero 内联完成 + watch 一键 + timeline 全汇于此 | 已接通路径无大缺口；voice_actionable 安全正确地从 `source_model` 派生 |
| **Execution Event** | ✅ real | HealthEvent + HealthProtocolEvent（唯一约束）一等；device-observation COMPLETION 走 `complete_by_ref` 带幂等 + 跨用户隔离测试 | device-observation COMPLETION 严格测试但**无活产者**；Rokid 俯卧撑 session→ExerciseRecord 自动写接缝未闭 |
| **Outcome Review 复盘** | 🟡 partial | ActionCard 结果评分（`outcome_grader` Celery → accuracy_score）；InterventionCycle/OutcomeMetric（baseline→recheck→delta，RCV 显著性）；health_operating_review 带归因 caveat | InterventionCycle recheck **无定时自动复测**，只在用户/LLM 显式调用时闭；预测 backtest 是 inert 占位；结果评分只覆盖 ActionCard，不覆盖自由文本 agent 输出 |
| **Causal Memory 因果记忆** | 🟡 partial | `causal_memory.derive_causal_notes`（事件×指标，\|pct\|≥5%）；AgentAuditLog→推理轨迹/eval/审计；TwinSnapshot dedupe；intervention_significance RCV 门 | **有意做弱**（时序关联、硬编码"相关非因果"、小白名单）；crystallize 入库环刻意 inert（只产草稿）；`protocol_learning_watch` 写 `notified=False` 审计行**无人读**（开环） |
| **Knowledge 知识库** | 🟡 beta | System-KB v2 reviewed-first DB 支撑（**419 claims / 219 entities / 3171 relations，100% reviewed**）；hybrid search + twin-match + prompt 注入；导入/服务/eval 三处 reviewed 门；**34/34 eval slice 通过**；confidence 衰减按 beat 运行 | KB eval 仅测试期跑，无生产/定时 eval 信号；legacy ChromaDB RAG 已默认关闭，仅显式 `LEGACY_KNOWLEDGE_RUNTIME_ENABLED=true` 时可作为旧路径启用；vector 流是同义词扩展不是真 embedding |
| **External Agent 外部** | 🟡 partial | OpenClaw SSE 代理上线带 per-user `HEALTH_API_TOKEN` 注入（真多租户 skill 鉴权）；22 个 SKILL.md；可分发 skills 部署校验；assistant-openclaw BYO 绑定测试 | `_needs_skill` OpenClaw 分支在默认 provider 下死；MCP server（18 工具）未挂载无生产消费；Telegram inbound 单硬编码用户；kuaishou/food_order/skills-hub 是 `NotImplementedError`/不存在仓库的桩 |

### 1.2 一等对象账本（是否真接进每日闭环）

| 对象 | 状态 | 进每日闭环？ | 证据 / 备注 |
|---|---|:---:|---|
| **HealthTwin** | ✅ real | ✅ | `twin/schema.py:463` 16 分区、`/twin/me`、~45 消费者、60s 缓存。**键石**。并存 legacy `/digital-twin/*` 竞争 |
| **SafetyGuardian** | ✅ real | ✅ | 62 规则、`/safety/me`、7+ 面。确定性 fail-loud——但**该信号只有 watch 一个消费者**，其余面崩规则静默变绿 |
| **HealthProblem** | ✅ real | ✅ | `models/health_problem.py`、agenda 脊柱 followup、`problem_red_lines` 规则、`/health-problems/due`。喂随访 + 红线匹配 |
| **HealthProtocol** | ✅ real | ✅ | `models/health_protocol.py`(+Event)、`build_today_spine`、watch `/summary`、完成写真实领域记录。**执行键石** |
| **HealthAgendaItem** | ✅ real | ✅ | `agenda_contract.py`（`health_agenda_contract_v1`）；两投影（flat + 时序）共用完成路径但**排序公式不同** |
| **InterventionCycle** | ✅ real | ✅ | `models/intervention_cycle.py`(+OutcomeMetric)、N-of-1 baseline→recheck→delta + RCV；但 recheck **仅手动**，且是 TwinSnapshot **唯一**产者 |
| **ExecutionEvent** | ✅ real | ✅ | HealthEvent + HealthProtocolEvent、`complete_by_ref` 物化、原子认领 + 幂等 |
| **WriteIntent** | ✅ real | ✅ | propose→一键确认→执行 syscall ledger 真；**当前分支** `write_intent.py:39` `trust_tier` 硬钉 manual_confirm；竞品报告复核 `origin/main` 后指出 `measurement_prompt` write autonomy 第一刀已上线，但语音记录/卡片 action/医疗写仍必须 `manual_confirm`；生成器 GET 时惰性运行 |
| **HealthTrajectory** | ✅ real | ✅ | `health_trajectory.py`、`/trajectory/me`、agenda top-action。但是**当前态风险快照，不是 forecast**；非 cycle 用户主动环饿死 |
| **PersonalPrediction** | 🔴 placeholder | ❌ | `health_operating_review.py:126` `_prediction_backtest_placeholder` 硬返回 `not_ready`、`ready_candidate_count=0`、"without pretending a model exists"。**前向预测在代码里不存在** |
| **CausalMemory** | 🟡 partial | ✅ | `causal_memory.py`、`/personal-outcome/me/causal-notes`。真但**有意弱**；crystallize 入库刻意 inert |
| **DomainKnowledge** | ✅ real | ✅ | system-KB v2、`lookup_for_twin`、orchestrator+agent prompt 注入、防御纵深 reviewed 门。legacy ChromaDB 仍竞争 diet/supplement |
| **RealtimeHealthSignal** | 🟡 partial | ✅ | ambient/Rokid 采集真且接通；bedroom 快照仅采集带隐私门；SIGNAL device-observation 无确认活产者 |
| **IoTActuationIntent** | ⬜ aspirational | ❌ | `home_assistant.py` 只入站；`command_entity_id` 存了**从不下发**。**对外执行零**。`bedroom_outcome_analyzer` 建好测好**无消费者** |
| **SupplyIntent** | ⚪ scaffold_inert | ❌ | ReorderIntent 检测（缺货 nudge）真且推送；下单**确证 inert**：`place_order` raise `NotImplementedError`→`501 by design`，`_monthly_spent_cents` 硬编码 0 |
| **HealthProgram** | ⚪ scaffold_inert | ❌ | 文档称"第 4 个一等对象"但**零下游消费者**——无 agenda/spine/task/LLM 工具用它。**孤儿容器** |
| **ActionCard** | ✅ real | ✅ | `models/action_card.py`、orchestrator `_persist_proposed_cards`、`/action-cards/me`、`outcome_grader`。**7 个专家产 ProposedCard 持久化为 ActionCard 并按周评准确率——最接近自我准确度信号的东西** |

### 1.3 今天真正端到端可用的能力（用户能拿到价值的）

- 穿戴 + 化验 + 手工数据流进 16 分区 Twin（真新鲜度标签），被 orchestrator/safety/agenda 消费（~45 消费者、69 测试）。
- 确定性安全：62 规则评估 Twin，在 `/safety/me`、mobile 安全 tab、Apple Watch 症状语音路径（真 fail-loud + fail-safe advisory）出分级告警。
- mobile 首页一个**时序感知 top action**，一键完成即**原子写真实依从/业务记录**并翻转 agenda（原子认领防虚高依从）。
- 多源仲裁：HealthKit（Apple Watch/RingConn/Oura）与 Garmin 按指标优先表合并，跨源分歧暴露为 agenda 数据质量项（单租户策略但真）。
- N-of-1 干预周期：开 90 天代谢 cycle、复测、得到贝叶斯前后效应裁决（RCV 显著性门），在 mobile cycle 页渲成 chip。
- ActionCard 信任环：7 专家产 ProposedCard→ActionCard，按周 `outcome_grader` 评 accuracy_score——真（虽窄）的自我准确度信号。
- reviewed-first 知识注入：419-claim DB 语料按 twin 匹配注入 orchestrator 合成与聊天证据卡，34/34 eval 门 + 每周 confidence 衰减。
- 主动每日环：~45 个错峰 Celery 任务（晨报、用药/事件提醒、异常+安全评估、周/月报、结果评分）触达真 iOS APNs 推送，受真打断预算门控。
- 四个真实端（mobile、web、Mac 工作台、Apple Watch）都消费**同一** `agenda/today` + `agenda/complete` 环；Mac 与 Watch 真测（245 + 55 Core 测试）。

### 1.4 子系统成熟度矩阵

| 子系统 | 成熟度 | real/partial/inert/placeholder |
|---|---|---|
| twin | production | 13 / 2 / 1 / 0 |
| safety_guardian | production | 11 / 2 / 0 / 0 |
| orchestrator_agents | production | 13 / 2 / 0 / 1 |
| action_loop | production | 12 / 3 / 0 / 0 |
| trajectory_prediction | production* | 13 / 2 / 0 / 1（*结构成熟但语义是回顾性，非预测） |
| data_intake_wearables | production | 15 / 3 / 1 / 2 |
| tasks_scheduler | production | 24 / 4 / 0 / 0 |
| platform_security_ops | production | 11 / 4 / 1 / 1 |
| mobile_surface | production | 10 / 5 / 3 / 0 |
| knowledge | beta | 9 / 7 / 1 / 0 |
| first_class_objects | partial | 7 / 4 / 2 / 0 |
| other_surfaces | partial | 9 / 3 / 1 / 1 |
| external_agent_skills | partial | 5 / 6 / 1 / 2 |
| iot_environment_supply | partial | 9 / 5 / 2 / 0（+1 aspirational） |
| api_census | production | 158 router / ~948 endpoint，accretion-heavy |

---

## 2. 当前产品 PRD（基于现实抽取，非愿景）

愿景版 PRD 的世界观/五层基座/一等对象表已在 [`2026-06-27-code-derived-product-prd-and-10m-goal.md`](2026-06-27-code-derived-product-prd-and-10m-goal.md) 完整给出，本文不重述。这里只给**与代码现实一致的精炼版**。

- **一句话定义**：Reva 是一个个人健康运行时治理系统——持续把多源数据组装成 Digital Twin，用确定性安全门 + 专家舰队把干预提议成一等对象，把单条最高杠杆行动推进每日 Agenda，用户完成即落真实执行事件，再用 InterventionCycle 把每次干预对**这个人自己基线**的实测效应打分。
- **第一目标用户**：35–55 高知中年男性，慢病早期 + 多指标异常 + 有数据素养（锚点 = 创始人本人）。**不是高净值人群**（那是"管家"需求）。中国此人群 ≥3000 万（见 [`enter-key-leverage-thesis`](2026-06-16-enter-key-leverage-thesis.md) §6）。
- **核心问题**：感知精度指数增长，但"测准 ≠ 做到"——执行仍卡在人类意志力。锚点用户本人 24 补剂 / 12.6% 依从 / 胃溃疡即最有力反例。
- **产品承诺**：每天生成一个不可错过的 **Reva Daily Artifact**：一个复合身体状态判断 + 最值得做的**一件**安全、个性化、可验证健康行动 + 数据依据/信心/风险边界；在对的设备上提醒执行，把结果写回长期账本。
- **双层北极星**（沿用权威 PRD）：
  - 行为北极星（过程，= WSCLA）：每周完成的**安全 + 证据可追溯 + 被安排 + 已执行 + 可验证**的闭环数。
  - 结果北极星（裁决）：L3 主观精力 0–10 的 30 日均线 + L4 抗衰生化（ApoB/hs-CRP/HbA1c）3–6 月同时改善。
- **每日前门指标**（本次竞品调研新增）：D1/D7/D30 晨间打开率、Daily Artifact 理解率、top action 接受率、skip reason 覆盖率、行动接受率按周衰减、数据新鲜度达标率。季度外环买来护城河，每日前门买来 runway。
- **真实主循环**（§1.1 核验过的脊柱）：
  ```
  Intake → Twin → [Trajectory(当前态) + Safety] → Orchestrator/LLM 综合
        → ActionRanker → Agenda top action → Surface 一键完成 → ExecutionEvent（双写真实记录）
        → ActionCard/InterventionCycle 结果评分 → CausalMemory
  ```

> 与愿景 PRD 的关键差异（诚实标注）：愿景 PRD 把 `HealthTrajectory / PersonalPrediction` 列为已成型一等线，把 IoT/供应链列为"受控执行层"。**代码现实**：trajectory 是当前态快照非预测、prediction 是占位、IoT/供应链对外执行为零。这些应在 PRD 标为 **TO-BE**，不是 AS-IS。

---

## 3. 反推的长期系统目标

> **从对象模型反推（不是从市场话术）**：`HealthTwin → SafetyGuardian → HealthProblem/Protocol/Program → InterventionCycle/OutcomeMetric → ActionCard → CausalMemory` 这条链，加上 `outcome_grader` 的准确度评分机制，泄露了系统真正想成为的东西——

**一个 per-user 因果健康账本（per-user causal health ledger），闭合完整回路：**

1. 从每个可得来源持续组装结构化 Digital Twin；
2. 确定性安全层 + agent 舰队把干预**提议成一等对象**；
3. 把单条最高杠杆行动推进每日 Agenda；
4. 用户完成时**捕获真实执行事件**；
5. 用 InterventionCycle 把每次干预的实测效应对**该用户自己的基线**打分；

→ 于是系统**逐季度积累一份 N-of-1 个人健康证据账本，让它的推荐对这个特定的人可证地越来越好**。

这与 [`enter-key-leverage-thesis`](2026-06-16-enter-key-leverage-thesis.md) 的公式一字不差：

```
Enter键 = Write权限 × 个体化先验 × 闭环验证
护城河 = trust-custodianship + 确定性安全脑 + 外环（每季复测）的 per-user 纵向证据账本
增长指标 = 单用户验证过的闭环轮次，不是用户数
```

> 竞品调研修正：不要把"数据积累"本身写成持久网络效应。单个用户的纵向数据会边际递减，且不可直接迁移给用户 #2。真正能长期防御的是用户愿意把更敏感的数据交给 Reva 的信任托管关系、确定性安全脑对 LLM/写入的约束能力、以及多年执行/复测/解释沉淀出的迁移成本。per-user 账本仍是产品核心，但它是信任与个体改善的证据资产，不是单纯数据规模护城河。

**对象脚手架还泄露了第二层（更高）的志向**：把这条环**向外延伸到自主执行**——前向轨迹预测 + backtest 验证（PersonalPrediction）、IoT 执行（IoTActuationIntent）、供应/商务执行（SupplyIntent），把"推荐引擎"变成"可测地改变用户环境与健康轨迹、无需手动步骤的 agent"。

> **当前**：向内环（twin→safety→agenda→execution→outcome）是真的；**向外的预测/执行环被建模但尚未承重**。
>
> **战略含义**：护城河不在"再多接一个传感器"或"再训一个大模型"，而在把向内环跑出 per-user 因果收敛、并在**安全带封顶下**逐级解锁向外的 Write 自治。安全带（Safety Guardian / R4）不是补丁，是 Write 自治的**速度上限**。

---

## 4. 现实 vs 文档的偏差（诚实清单）

这些是文档与代码不一致、会误导后续 agent 的地方，应优先订正（多数是一行文档/常量改动）：

| # | 文档/常量说 | 代码真相 | 处置 |
|---|---|---|---|
| 1 | CLAUDE.md/PRD："14 语义分区" | `schema.py:463` 实为 **16 分区**（+gene_config +epigenetic） | 改文档 + doc-drift |
| 2 | 6:00 "daily plan" 任务建 DailyOperatingPlan | 实际建 **legacy AIScheduler 晨报**；DOP 只读时惰性生成，无任务预生成 | 接通或明确 DOP 生成时机 |
| 3 | fail-loud 安全是"全系统保证" | `failed_rule_count` **只有 `watch.py:337`** 一个消费者；其余面崩规则静默变绿 | **P0 安全修复**（见 §5） |
| 4 | ChromaDB 得到-wiki RAG 是"**the** 知识库" | 承重的是 reviewed-first DB-backed **system-KB v2**；ChromaDB 是 legacy，仅 OpenAI+vectorstore 存在时激活 | 改 CLAUDE.md 知识库段 |
| 5 | safety_eval.py："51 条规则" | 注册数 **62**（CLAUDE.md 与 check_doc_drift 都 62） | 改 in-code 注释 |
| 6 | CLAUDE.md：Capacitor `frontend/ios` "残留未维护" | 目录**已完全删除**，零 capacitor 依赖 | 删 CLAUDE.md 过期段 |
| 7 | PRD："用户隔离已强制执行" | DB 层 RLS **只覆盖 2 张表**（genetic_raw_files/audit）；其余全靠应用层 `WHERE user_id` | 标注真相 + 多租户路线 |
| 8 | HealthProgram 是连接 Problem→Protocol→outcome 的一等对象 | **零下游消费者**——完全建好的孤儿 | 接通或降级标注 |
| 9 | protocol_learning_watch 学习环"已闭"（建议进 /corrections + agenda） | 实际**开环**：只写 `notified=False` 审计行，`/corrections` 读的是另一套 detector | 闭环或标 TODO |
| 10 | Mac 假定很薄 | 真工作台，245 Core 测试 + Mac 独占面（desktop 导入 job/推理轨迹/命令面板） | 文档升级 Mac 定位 |
| 11 | WeChat 小程序在产品矩阵内 | 冻结在改版前 ai-scheduler 环，**从未到 agenda/timeline 脊柱** | 明确降级/归档 |

**有意为之的诚实占位（不是 bug，是纪律）**：`reorder_intents 501 by design`、`place_order NotImplementedError`、`_prediction_backtest_placeholder not_ready`、`crystallize 只产草稿`。`WriteIntent.trust_tier 硬钉 manual_confirm` 是当前分支事实；若以 `origin/main` 为基线，`measurement_prompt` 自治已解冻第一刀，但敏感写仍应保持 manual_confirm。这些体现了仓库"不假装成功"的规矩，应**保留为门，按路线分阶段解冻**。

---

## 5. 通往 1000 万用户的关键缺口（代码核验、按 P 排序）

> "1000 万用户"不是 1000 万次安装，而是 **≥1000 万人日常用一个可信健康操作系统、持续改善健康状态**。验收同时满足：常把 Reva 当每日入口、每周完成安全可验证行动、沉淀 per-user 账本、风险/隐私/成本可规模化、能证明对一部分关键状态真有趋势改善（不只是 engagement）。

下面每条都是**代码里实打实挡路**的，不是想象需求。

### P0 — 不修就到不了规模

| 缺口 | 为什么挡 10M | 证据 |
|---|---|---|
| **没有每日可感价值原语 + 抗习惯化机制** | 外环价值落在 30-180 天后，但消费级留存靠 week 1-4 的每日仪式。没有 Daily Artifact、行动接受率衰减监控、skip reason、dynamic availability，用户会在 per-user 账本成熟前流失 | Whoop/Oura 竞品留存机制；JITAI/HeartSteps 习惯化证据；当前 PRD 只有 WSCLA 与 3-6 月结果，没有每日留存原语 |
| **没有 onboarding/冷启动管线 + 系统是单锚点用户调参的** | 源仲裁 `device_source_priority.py` 全局单租户，硬编码 Garmin-SpO2 排除（源自一个用户），注释自承 `TODO(多租户): 上线前必须改 per-user override, 否则无差别误伤所有用户`。RLS 只 2 张表。**没有任何把新账号变成可用 Twin 的路径**，也无 per-user 源信任 | `device_source_priority.py:46-47` |
| **Twin 快照只有 cycle 路径写，无周期快照任务** | `trajectory_watch.py` / `longevity_watch.py` 在 `len(snaps)<2` 时返回 `[]`，主动轨迹/抗衰环对**未开 cycle 的绝大多数用户结构性饿死**——头部"主动漂移检测"对 10M 中绝大多数是静默 no-op | `trajectory_watch.py` 快照门 |
| **fail-loud 安全在当前分支仍只接了一个面** | 本分支 `evaluate_rules_with_status`（返回 `failed_rule_count`）只被 `watch.py:337` 消费；orchestrator、`/safety/me`、daily_recommendation、notifications、medication_regimen 仍走 lossy `evaluate_rules()`。调研报告指出 `origin/main` 已扩到用药/自治写等路径，因此该项应按目标分支复核后窄修：至少 `guardian.py` / 报告面 / orchestrator 不能 under-alarm | 本分支 grep 仅 `watch.py` import fail-loud 版；竞品报告 §6 对 `origin/main` 做了校正 |
| **任何地方都没有前向预测** | "个人预测模型"全是回顾性（前后 delta、你 vs 你的基线、跨快照漂移）；唯一叫 prediction/backtest 的 `_prediction_backtest_placeholder` 硬返回 `not_ready`。**没有任何随规模准确度提升的模型**——"预测你的轨迹并验证"的核心护城河在代码里尚不存在 | `health_operating_review.py:126` |
| **CausalMemory 过度归因风险** | 如果系统把 1 日/短窗前后均值差异包装成"X 改善了 Y"，会直接摧毁 trust-custodianship。N-of-1 的最大攻击面是回归均值、时变混杂、洗脱不足和依从偏差；健康产品不能用弱相关冒充因果 | `causal_memory.py` 当前按阈值派生 notes；竞品报告 §3/§7 将其列为信任承重墙缺陷 |

### P1 — 决定护城河能否成立 / 能否运营

| 缺口 | 为什么挡 10M | 证据 |
|---|---|---|
| **看不见的深度无法分发** | OpenHealth 用更少临床深度获得明显开源 traction，说明用户/开发者首先购买"能跑、能看懂、能在 5 分钟内感到价值"。Reva 的 62 规则安全脑、reviewed KB、Twin 和闭环若藏在复杂入口后，等同不存在 | 竞品报告：OpenHealth 5 分钟 on-ramp 与 Reva 深度对比 |
| **agent 输出默认路径不被强制成对象** | 13 专家是 prompt 注入非工具化（`agent_specialist_tools=False`）；仅 7 专家产 ActionCard，其余出自由文本；crystallize 刻意 inert。**不强制每个裁决过一等对象，per-user 因果账本就不积累**——而那正是护城河 | `config.py:205` |
| **严重收敛债** | 4 个聊天入口、6+ 个每日计划/评分面、2 个 Twin、2 个 N-of-1 估计器、2 个 agenda 投影、2 套排序公式、`/checkin` v1+v2、2 套 RAG、2 个 daily-insight 任务。158 router / ~948 endpoint。**6 个互相不一致的规划面下无法为 10M 跑一条连贯可调试的每日环** | 见 §6 |
| **CGM 自动采集不存在** | Libre/Dexcom adapter `NotImplementedError`，ManualAdapter 返 `[]`，全手工。Apple/RingConn/Oura 依赖 App 被打开；只有 Garmin 真自动。**最富的实时信号被手工劳动门控，规模下崩** | `cgm/adapters.py:92,100,117,124` |
| **缺统一 AI-ready 信号契约与来源覆盖矩阵** | 每个 wearable/HealthKit/CGM 指标若没有固定单位、聚合语义、来源优先级、coverage 和 provenance，LLM/Trajectory/ActionRanker 会在"同名不同义"的数据上推理 | open-wearables `SeriesType` 调研启发；当前源仲裁和 adapter 覆盖散落 |

### P2 — 重要但非核心健康改善阻塞

| 缺口 | 为什么 | 证据 |
|---|---|---|
| **IoT/供应链执行边缘全入站/或确证 inert** | 对外设备执行零；ReorderIntent/kuaishou/food_order 全 `NotImplementedError→501 by design`；`bedroom_outcome_analyzer` 建好测好**零消费者**。"agent 在世界里行动"目前是无执行的脚手架 | `home_assistant.py`、`reorder_intents.py:85` |
| **L3 医疗数据明文 + token 2 年** | L3 化验/medical_exam（含 patient_name）**明文存储**（只 L4 基因加密）；JWT access token TTL **2 年**（弱撤销）；Sentry 默认关。10M 规模处理受监管 PII 时这是合规/泄露爆炸半径问题 | `tenant_crypto.py:5-6`、config |

---

## 6. 收敛债清单（最大可维护性阻塞）

> 愿景 PRD 自己也点名"surface 太多"。核验给出**确切的重复实体**——这是 Phase 0 必须收口的：

- **4 个聊天入口**：`/agent/stream`（canonical tool-calling）、`/orchestrator/chat[/stream]`（只读专家综合）、`/openclaw/stream`（legacy，前端注释已迁走砍一半 LLM 成本却仍接着）、`/assistant-openclaw/stream`（BYO）。mobile 只用 `/agent/stream`，web 接三个。
- **6+ 个 today plan/score/coach 面**同时被不同屏消费：`/daily-plan`、`/smart-plan`（WeeklyPlan）、`/movement/plan`、`/diet-plan`、`/daily-recommendation`、`/health-score`——一个不死，比死了更糟。
- **2 个 Twin**：canonical `/twin/me`（16 分区、~45 消费者）vs legacy `/digital-twin/*`（8 端点、自带 BMR/TDEE/health-score/report）。mobile 读 `/twin/me`，web 首页仍读 `/digital-twin/report`。
- **2 个 N-of-1 估计器**：`personal_models/treatment_effect.py`（端点，`verdict=improved_in_cycle`）vs `services/effect_estimator.py`（prompt-blob，`is_effective`），仅共用 clinician-gate 关键词表。
- **2 个 agenda 投影**：flat `agenda.today/smart_today`（mobile agenda 屏 + Rokid）vs 时序 today-spine（mobile 首页 hero），共用合同与完成路径但分开装配。
- **2 套排序公式**：`action_ranker`（杠杆分，仅 watch）vs `agenda_service._rank_score`（status/priority/source/trajectory，smart_today）——watch 与 mobile 排序数学不同。
- **重复 `/checkin/*`**：`health_checkin.py`(v1) 与 `checkin.py`(v2) 并挂。
- **3 套规划面**：HealthProtocol→`build_today_spine`（新）、DailyOperatingPlan（脊柱明确拒绝调它）、WeeklyPlan/PeriodGoal（legacy）。
- **2 个 daily-insight 任务**：`insights.py`（09:20）vs `notifications.py`（20:30），不同引擎都排程。
- **2 套 RAG**：新 reviewed-first DB system-KB v2（承重）vs legacy ChromaDB 得到-wiki（默认关闭，仅显式开关启用）。
- **158 router / ~948 endpoint**；`genetic_data.py` 2410 行 / 23 端点（远超 500 行预算）。

---

## 7. 演进路线（锚定 §5 核验缺口）

> 原则：**先收敛、先安全、先冷启动；预测与自治后置**。每阶段交付都钉到具体 `file:line` 缺口。沿用愿景 PRD 的阶段编号，但用核验结果**重排优先级**——把"让 trajectory 影响 Today"从 Phase 1 降级，把"安全 under-alarm 修复 + 冷启动 + 收敛"提到最前，因为代码证明前者已部分接通而后者是真空。

### Phase 0 — 安全正确性 + 收敛 + 每日工件契约（现在–4 周，最高优先）

不扩展预测/自治，只修"会在规模下伤人/失控"的承重问题，并把每日入口的产品契约定死：

1. **安全 fail-loud 全面接通（P0 安全）**：把 `evaluate_rules_with_status` 的 `failed_rule_count` 接到**所有**安全消费面（orchestrator、`/safety/me`、daily_recommendation、notifications、medication_regimen），崩规则注入 HIGH fail-safe advisory，绝不静默变绿。每个吞异常点配对抗测试。
2. **收敛 §6**：选定 canonical 聊天入口（`/agent/stream`）+ 单一 Twin（`/twin/me`）+ 单一排序公式 + 单一 today 投影，其余 `Converge/Archive`，按 [`surface-ownership-inventory`](../specs/active/2026-06-26-surface-ownership-inventory.md) 处置。每删一个重复面写迁移 + 回滚。
3. **订正 §4 文档偏差**（多数一行）+ doc-drift 守护更新（16 分区、62 规则、知识库段、删 Capacitor 段）。
4. **定义 Reva Daily Artifact 合同**：一个复合状态判断、一个 top action、3 个以内证据来源、confidence/freshness/safety boundary、skip reason、完成入口；禁止把它做成新页面，必须接入 Today/Watch/Chat 三个主入口。
5. **建立抗习惯化指标**：记录 action impression、accepted、completed、skipped_reason、delivered_context、week_index，能看行动接受率是否随周衰减。

验收：安全面无静默绿灯；每个每日概念只有一个权威实现；CLAUDE.md/PRD 与代码零漂移；Daily Artifact schema 能被 Mobile/Watch/Chat 共用。

### Phase 1 — 冷启动 + 多租户去锚点化（1–3 月，让"第 2 个用户"成为可能）

这是 [`enter-key-leverage-thesis`](2026-06-16-enter-key-leverage-thesis.md) 说的"先验积累机"的前提：

1. **统一 onboarding 管线**：把报告/设备/目标自动转成 `HealthTwin + HealthProblem + HealthProgram + Protocol + 首个 Agenda`（愿景 PRD G0.6）。
2. **5 分钟 on-ramp**：支持合成数据/示例报告/真实 HealthKit 三种入口；60-300 秒内演示一次安全脑拦截、一次证据卡、一次 top action，而不是让用户先配置完整系统。
3. **per-user 源仲裁**：拆掉 `device_source_priority.py:46` 的全局硬编码 Garmin-SpO2 排除，改 per-user override + per-user 源信任分；凡写死成全局规则的 N=1 过拟合点（血氧剔 Garmin、HP- 胃溃疡路由）留多租户 TODO 并 per-user 化。
4. **周期 Twin 快照任务**：补一个定时 snapshot（不只 cycle 路径），让 `trajectory_watch`/`longevity_watch` 对所有用户有 ≥2 快照可比——这是"主动漂移"对多数用户从 no-op 变可用的**唯一**前提。
5. **DB 层隔离补齐**：把 RLS 从 2 张表扩到全部敏感表，或确立应用层 `WHERE user_id` 的强制审计门。
6. **异质用户验证门**：先服务 10–100 个高质量用户，其中第一批必须包含 5–10 个与创始人不同的用户；如果不同主诉/性别/设备组合下系统仍输出单一反流/代谢假说，判定为过拟合。

验收：一个全新账号能从零数据走到有 top action 的可用 Twin；源偏好可 per-user 覆盖；新用户也能拿到轨迹漂移信号。

### Phase 2 — 强制对象化 + 让闭环对用户可见（3–9 月，护城河开始积累）

1. **agent 输出强制落对象**：把 13 专家逐步工具化（解冻 `agent_specialist_tools`），让每个裁决落 ActionCard/WriteIntent/InterventionCycle 或显式 explain-only；结果评分从 ATSC 扩到覆盖更多 agent 输出。
2. **复测召回真推到腕上**（论纲 P0）：HealthProblem `follow_up.next_due` 与 InterventionCycle recheck 自动排程 + watch 推送，让外环"每季复测"真转起来。
3. **InterventionCycle 自动复测**：补定时 recheck，闭合 baseline→recheck→delta，无需用户手动触发。
4. **CausalMemory 变用户可见但不过度归因的资产**：在 Review 主入口呈现"你的个人健康观察"；区分 `signal` / `hypothesis` / `validated_effect`，展示样本数、时间窗、混杂 caveat、retest plan，未验证前不说"因果"。
5. **预测回测 = 诚实 backtest**：把 `_prediction_backtest_placeholder` 换成真"预测→实际→met/not_met/inconclusive"时间线，**观察性措辞**，不做 vanity score。
6. **Discoveries 体验**：吸收 Oura Tags→Discoveries 的可感反馈，把"你尝试了 X，指标 Y 出现了什么变化"做成 Chat/Review 卡片，弱证据必须弱表达。
7. 建建议质量/预测命中/执行率/复测率/健康结果的持续 eval；成本与延迟进 SLO。

验收：用户能看到至少一个完整闭环（预测/行动/实际/解释/下一步）；维护者能看 specialist hit-rate。

### Phase 3 — 小型个人预测器（数据够了再做，不微调 LLM）

只在数据支撑处引入小型可审计预测器，优先级：① 穿戴/化验时序的个人基线 + 异常检测 ② 攒够 cycle 后估 N-of-1 干预效应 ③ 仅当同时有 CGM + 饮食记录才做餐后血糖响应。规则：不在个人健康事实上微调 LLM；模型参数留服务端按用户隔离；只把摘要预测/不确定度/边界给 LLM；每个模型能优雅降级到 baseline/data gap/人审；每个输出围绕 confidence/边界/不安全升级建测试。

验收：`personal_models` 至少产一个带 uncertainty + version 的前向预测，进 Twin/trajectory 结构化区块并被 ActionRanker 用（不靠 LLM-only 推理）。

### Phase 4 — 规模化治理 + 受控向外执行（验证 retention/outcome 后）

1. **隐私/合规补齐（解 §5 P2）**：L3 数据加密存储、token TTL 收紧 + 可撤销、key rotation 落地、多区域删除/导出/审计。
2. **成本/延迟/安全事件仪表盘**：每次 Today/Agenda/Trajectory 调用记成本延迟；trajectory-driven action 与 prediction-driven nudge 的安全审计与误报追踪。
3. **用户隐私控制中心**：暂停/删除特定预测类别与派生 CausalMemory。
4. **受控向外执行**（按门解冻，论纲安全带封顶）：先卧室环境窄 pilot（CO2/PM2.5/湿度/灯光/睡眠保护窗）→ 测量设备 ground-truth → 低风险依从设备 → 补剂物流（先提醒后手动购买，永不静默循环下单）。LLM 不直接控设备；每条 actuation 有 manual override/audit/降级/通知预算；金融与处方动作永久 manual_confirm。
5. **Write 自治分级**（论纲核心，最后一刀）：`display_only → draft → manual_confirm → trusted_confirm → auto(可逆低风险)`，只对 CI 证明对该用户有效、可撤销、可审计的少数升级到自治。若以 `origin/main` 为基线，先盘点已上线 `write_autonomy` 的 allowlist/cap/worker，把路线从"新建"改成"收敛、审计、graduation"。

验收：系统能解释为何向用户展示某 trajectory action；用户能纠正/暂停/删派生预测记忆；运营者能审计 prediction-driven action 而不查不必要敏感原始数据。

---

## 8. 演进治理规则（每个后续需求必须答）

```yaml
target_user:                    # 默认 35-55 慢病早期男性，偏离要给理由
health_problem_or_goal:
first_class_object:             # 必须落 Twin/Problem/Program/Protocol/Agenda/WriteIntent/InterventionCycle/ActionCard 之一，否则不做
surface_owner:                  # Mobile/Watch/Rokid/Mac/Web/OpenClaw/Backend（按 surface-ownership-inventory）
core_loop_step:                 # 必须改进核心环，不是新增并列页
daily_artifact_impact:          # 是否改善每日工件：状态判断/top action/证据/完成/skip reason
habituation_guard:              # 是否限制行动数、动态投递、记录跳过原因、监控周衰减
onramp_impact:                  # 新用户是否能在 5 分钟内看到可运行价值
state_variable_to_change:
prediction_or_trajectory_claim: # 必须带 horizon/uncertainty/evidence_tier/claim_boundary
safety_gate:                    # 高风险路径 fail-closed，且接 fail-loud（不是只 watch 一个面）
data_source:                    # 带 source/freshness/confidence，per-user 仲裁
execution_event:
verification_plan:              # 1d/7d/4w/8-12w/retest
evidence_language:              # observation/hypothesis/validated_effect，禁止弱证据强因果措辞
rollback_or_archive_plan:
```

**硬规则**：① 新功能必须改进 core loop，不能只新增页；② agent 输出必须落对象或显式标 explain-only；③ 高风险行为不能经轻量入口绕过 SafetyGuardian，且安全必须 fail-loud 全面接通；④ 每日主路径 Mobile/Watch，复杂工作流 Mac，Web 退到 history/admin/doctor/family；⑤ 预测必须带不确定度/证据级/声明边界，绝不把基因或弱关联包装成个体命运；⑥ **凡写死成全局的 N=1 规则都是过拟合气味，必须 per-user 化或留多租户 TODO**；⑦ 若一个功能无法提高"安全行动完成率/验证闭环/健康结果/轨迹治理/信任"，不进主路径；⑧ 任何主路径功能都必须说明它如何增强 Daily Artifact 或 5 分钟 on-ramp，否则默认后置。

---

## 9. 里程碑度量

> 核心增长指标是 **per-user 验证过的闭环轮次**，不是用户数（论纲 §3）。

| 阶段 | 用户规模 | 产品证明 | 健康证明 | 系统证明 |
|---|---:|---|---|---|
| Dogfood | 10–50 | Daily Artifact D7 使用、每周完成 top action、skip reason 可用 | ≥1 个 12 周 cycle 有可读结果 | 安全 fail-loud 全接通、agenda/review 闭环 |
| Pilot | 100–1,000 | D7/D30 留存、行动接受率周衰减可观测、5 分钟 on-ramp 转化 | 代谢/睡眠/恢复趋势改善 | 收敛债清零、agent 输出对象化、成本可控 |
| Paid Wedge | 1k–10k | 付费/复购 | program completion + 复测成熟 | per-user 源仲裁、冷启动自动化、隐私合规补齐 |
| Self-Serve | 10 万–100 万 | onboarding 全自动 | 多人群 program 验证 + 前向预测命中 | 多租户/RLS/SLO 成熟、Write 自治分级上线 |
| Platform | 100 万–1000 万+ | 成为日常入口 | 大规模 N-of-1 改善证据 | 合规/安全/成本/受控向外执行生态可扩展 |

---

## 10. 立即下一步（只做 10 件，全在 Phase 0–1）

1. **安全 fail-loud 全面接通**（P0 安全，§5）——这是唯一"不修会规模化伤人"的项。
2. **定义并实现 Reva Daily Artifact 合同**：状态判断 + top action + 证据 + 信心 + 风险边界 + skip/complete。
3. **收敛聊天入口/Twin/排序/today 投影**到各一份（§6）。
4. **订正 §4 的 11 处文档偏差** + doc-drift 守护，并标出当前分支与 `origin/main` 的能力差异。
5. **统一 onboarding 管线**：报告/设备/目标 → Twin+Problem+Program+Protocol+首个 Agenda。
6. **做 5 分钟 on-ramp**：合成数据/示例报告/真实 HealthKit 三入口，60-300 秒看到安全脑和 top action。
7. **per-user 源仲裁 + 周期 Twin 快照任务**：让第 2 个用户与"主动轨迹"成为可能。
8. **CausalMemory 诚实化**：弱相关只叫 observation，validated effect 必须有复测/显著性/样本数/混杂说明。
9. **招募 5-10 个异质用户作为 Phase-1 blocker**：验证系统能离开创始人锚点。
10. **复测召回真推到腕上** + InterventionCycle 自动复测：让外环（护城河）真转一圈。

> 这比继续新增健康功能重要得多。核验证明 Reva 已有足够能力；下一步胜负在**每日可感价值、收敛、安全、冷启动、验证**——把跑通的单用户向内环，变成可信、多租户、按季度积累 per-user 证据账本的系统。
