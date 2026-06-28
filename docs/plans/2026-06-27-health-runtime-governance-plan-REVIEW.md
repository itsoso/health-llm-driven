# 评估:健康运行时治理产品规划

> Status: Review
> Date: 2026-06-27
> 评审: Claude (Opus 4.8)
> 被评文档: [`2026-06-27-health-runtime-governance-plan.md`](./2026-06-27-health-runtime-governance-plan.md)
> 关联: PRD [`2026-06-27-code-derived-product-prd-and-10m-goal.md`](../prd/2026-06-27-code-derived-product-prd-and-10m-goal.md) · 本评审 concierge 设计 [`2026-06-27-voice-concierge-loop-design.md`](./2026-06-27-voice-concierge-loop-design.md)

## TL;DR

这份 plan **比 PRD 更收敛、更落地**:它选定了楔子(trajectory-informed Today top action)、补齐了 PRD 缺的数据连接/授权/provenance 底座、加入了 eval + safety-regression release gate(真正高价值且当前缺失)。

但它和 PRD 犯了**同一个"code-derived"病**:**把已经建好的能力当成缺口在列**,会导致重建已有对象。修正 status 列后,阶段 1 从"建底座"变成"补契约 + 渲染已算好的东西",工作量和风险都小一截。

> 一句话:**保留它的楔子和评估闸,但把"未实现/缺少"重新核对——D0.1/D0.2/D0.4 和 G0.1/G0.2 的后端已存在,真缺口比 plan 写的窄。**

## 已核实的事实订正(关键)

| Plan 声称 | 代码实况(已核) | 影响 |
|---|---|---|
| D0.1 `DataConnection`「缺少统一对象管理 provider/scope/token/同步/撤权」 | **`models/data_connection.py` 已有 `DataConnection`**(provider, provider_type, scopes, token_status, last_success_at, sync_error, unique(user,provider))+ `api/data_connections.py` | 不是新建,是**补齐/接线** |
| D0.2 `ConsentGrant`「缺少产品化授权中心」 | **同文件已有 `ConsentGrant`**(scopes JSONB, revoked_at) | 对象已在;缺的是 scope 语义 + UX,不是建模 |
| D0.4 `ConnectorPolicy`「缺少统一 connector policy」 | **同文件已有 `ConnectorPolicy`**(scopes, rate_limit, token_status) | 同上 |
| G0.1「`ActionRanker` 尚未把 trajectory risk 作为一等评分输入」 | **`action_ranker.py` 已消费 `trajectory_context`**:`_TRAJECTORY_LEVEL_BOOST={high:45,attention:25}`,`trajectory_boost` 计入最终分(:190) | **过时**;trajectory 已是评分输入 |
| G0.2「top action 还没展示轨迹原因/状态变量」(后端语义) | **`agenda_service.py` 已有 `_attach_trajectory_context`/`_project_trajectory_context`(454-534)** 把 trajectory 贴到 item | 后端端到端**已通**;真缺口=契约字段补全 + **Mobile/Watch 渲染** |
| G1.3 CGM Libre/Dexcom adapter 仍 `NotImplementedError` | ✅ 属实(`cgm/adapters.py:92` LibreAdapter 抛 NotImplementedError) | 准确 |

> **订正(2026-06-27 复核)**:`ProvenanceRecord` 也**已存在**(`models/data_connection.py:83`,与 DataConnection/ConsentGrant/ConnectorPolicy 同文件)——我先前误标"真新建"。D0.3 同样是"已建+待接线"。**且本工作分支落后 origin/main 44 commit,status 列应对 origin/main 核**(如 Write 自治、effect_estimator R4 门控都已在 main)。

**真新建对象(已确认不存在)**:`ProgramTemplate`、`EvaluationScenario`、`SafetyRegressionSuite`、`SyntheticUserTwin`、`OrganSystemProgram`、`IoTActuationIntent`、`PersonalPrediction`(forecaster)。这些才是 plan 的真增量。

> 结论:trajectory→agenda→ranker 这条"阶段 1 主线"在**后端已经接通**(service→attach→boost score)。阶段 1 的真实工作 = ①补 trajectory risk 的完整契约字段(`state_variable`/`horizon`/`uncertainty`/`verification_window`)②**Mobile/Watch 把后端已算好的 top action 渲染出来** ③把已存在的 `ProvenanceRecord` 接进 top-action 解释。**比 plan 写的"让 trajectory 从概念变成行动依据"轻得多。**

## 跨文档一致性(必须收口)

1. **`ConsentGrant` 已存在 → 我的 concierge plan 要改**:[voice-concierge-loop-design](./2026-06-27-voice-concierge-loop-design.md) 里新建的 `consent_grants` 表应**复用已有 `ConsentGrant`**(声纹同意 = 它上面一个 `voice_clone_outbound` scope + `revoked_at`),不另起一张表。这正是本 plan「统一授权中心」该收的口。
2. **`ConciergeIntent` 属于本 plan 的受控执行族**:plan 已列 `IoTActuationIntent` / `SupplyIntent`;concierge 的 `ConciergeIntent` 是同族第三个,应直接进本 plan 的一等对象清单(§2 admission)和阶段 5(执行层),不是孤立设计。
3. **本 plan 与 PRD 的关系**:本 plan 实质是 PRD 的"实现缺口桥"。两者都需把"已建 vs 真缺"对齐(PRD 多维 review 完成后一并收口)。建议本 plan 的"当前证据/缺口"列以**实跑 grep 为准**,别照抄 PRD 的 AS-IS 叙述(PRD AS-IS 本身也有夸大,如 §9.2 说 trajectory 没进 ranker)。

## 保留(plan 的强项)

- **选定楔子**:trajectory-informed Today top action + 12 周闭环——和 PRD、和代码现状一致,是对的主线。
- **评估 + 安全回归 release gate**(阶段 2 的 `EvaluationScenario`/`SafetyRegressionSuite`/`SyntheticUserTwin`):**真缺、真高价值**,把"换模型/换 connector/改 ranker"从人工体验判断变成可回归的闸,契合项目"对抗验证 + system_health_score 自动回滚"的基因。**这是本 plan 最该先做的真增量。**
- **"预测必须服务行动/复盘,不做 vanity dashboard"** + **非目标清单**(不 fine-tune 个人 LLM / 不基因宿命 / 不自治临床改动 / 不静默下单):边界正确,和 R4、写自治阶梯、`project_genotype_effect_prior_verified_empty` 一致。
- **近期实现计划 A/B 双切片**够小;只是范围 B 还能再砍(见下)。

## 建议改动

| 优先 | 改动 | 理由 |
|---|---|---|
| P0 | **重核 §4 status 列**,把 D0.1/D0.2/D0.4 改"骨架→待接线/待产品化",G0.1 改"已实现",G0.2 后端改"已实现、缺端侧渲染" | 防止重建已有对象;`find/grep` 为准不照抄 PRD |
| P0 | **阶段 1 范围 B 再砍成"渲染已算好的 top action"**:后端 trajectory→ranker 已通,第一刀只做 ①trajectory risk 契约补字段 ②Mobile Today/Watch 渲染 state_variable/why/verify ③`ProvenanceRecord` 最小合同 | 比"让 trajectory 变成行动依据"小得多,1 个 PR |
| P1 | **把评估/安全回归闸(阶段 2)提前**为独立先行 PR | 它是纯增量、纯护栏、不依赖渲染;先有闸再改 ranker/predictor 更安全 |
| P1 | **收口 ConsentGrant / ConciergeIntent 跨文档**(见上) | 单一授权中心 + 受控执行族不分叉 |
| P2 | admission §2 的 **21 个一等对象**标注"已存在/骨架/新建" | 21 个里至少 8 个已存在;清单该反映实况,否则像新建 21 个对象 |
| P2 | 阶段 5(IoT/供应链)、器官系统地图(§11,12 个 program)明确标 **"not now / 远期"** | plan 自己说"不堆功能",但 §11 列了 12 个 program;避免被读成近期清单 |

## 一条没被 plan 覆盖的风险

plan 反复强调"trajectory 必须降级低置信为 watchlist/data-gap、不驱动 urgent action"——但 ranker 里 `_TRAJECTORY_LEVEL_BOOST` 给 `high` 直接 +45 分,是很大的权重。**需要一条对抗测试**:低 confidence 的 high-level trajectory risk **不能**靠 +45 boost 把一个本应 watchlist 的项顶成 Today top action(over-alarm)。这正是 plan 阶段 2 `SafetyRegressionSuite` 该覆盖的第一类用例,建议显式写进去。

## 与 PRD review 的合并

PRD 多维 review 仍在后台重跑(上一次被中断)。完成后两份一起收口:预计 PRD review 的"AS-IS 夸大/已建当缺口"结论会和本评估的事实订正高度重叠——**两份文档的 status/AS-IS 都应改成 grep 实测口径**,这是最大的共性修复。
