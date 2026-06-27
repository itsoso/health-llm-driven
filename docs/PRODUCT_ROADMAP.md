# 产品路线图(Product Roadmap)

> 战略级规划,非功能清单。2026-06 由对全产品 + 创始人真实健康画像的深度 review 得出。
> 配套哲学见 [HEALTH_WORLDVIEW.md](HEALTH_WORLDVIEW.md);本文件回答"接下来往哪走"。
> 2026-06-27 更新吸收 [`docs/reports/2026-06-27-competitive-benchmark-and-prd-critique.md`](reports/2026-06-27-competitive-benchmark-and-prd-critique.md):Whoop/Oura 的每日仪式、OpenHealth 的 5 分钟 on-ramp、Medplum 的 trust-custody、open-wearables 的 signal contract,以及 JITAI 习惯化风险。

## 核心判断

**功能已过剩,而非不足。** 13 specialist · 56 安全规则 · 15 Twin 分区 · 45 Web 路由。
再往"加功能"方向走边际价值在掉(CLAUDE.md 复杂度预算章节已警告)。

**下一阶段主线 = 收敛已有能力成"用户每天用的一条主线" + 让信任护城河在 5 分钟内被感知。**

护城河不再表述为单纯"数据越多越强",也不只是一条 `outcome_grader` 验证闭环。长期护城河是三件事叠加:

1. **trust-custodianship**:用户愿意把更敏感的基因、化验、药物、补剂、可穿戴和复查数据交给 Reva,因为它有权限、来源、撤权和审计。
2. **确定性安全脑**:DDI/DSI/PGx/急症/训练/红线规则约束 LLM 和写入,让 Reva 不为 engagement 牺牲安全。
3. **per-user 证据账本**:`outcome_grader`/InterventionCycle/CausalMemory 让"你做了什么,后来指标如何变"变成可复盘资产。

其中第 3 点必须诚实表达:弱证据只能叫 observation/hypothesis,不能把回归均值或短窗相关包装成因果。

**新的长期判断**:季度外环形成护城河,但每日入口买留存 runway。没有一个稳定的 `Daily Artifact`(今日状态 + 一个 top action + 证据 + 完成/跳过),用户会在验证闭环成熟前流失。

---

## 三个地平线

### H1(当下,数周)——Daily Artifact + 5 分钟 on-ramp

- **Daily Artifact**:把 13 specialist 输出 + 安全告警 + 数据新鲜度 + Agenda 收敛成一个每日工件:
  "今日身体状态 + 一个最重要 top action + 最多 3 个证据 + 完成/跳过/问 Reva"。
  不是新功能,是**编排已有能力成一个入口**。留存第一杀手是"打开后不知道看什么"。
- **抗习惯化埋点**:每个 top action 记录 impression / accepted / completed / skipped_reason / delivered_context / week_index。
  目标不是每天塞更多行动,而是监控行动接受率是否随周衰减。
- **5 分钟 on-ramp**:新用户可用 HealthKit、示例报告或合成数据在 60-300 秒内看到:
  安全脑拦截一次真实风险、证据卡解释一个建议、Daily Artifact 给出一次可完成行动。
- **新能力补三端 UI(进行中)**:多药梳理、社会连接、时滞观察、数据完整性等能力必须进入 Daily Artifact / Chat card / Review,不能成为并列入口。

### H2(1–2 月)——Discoveries + 诚实个人证据账本

- 用户可见的 **Discoveries / 预测 vs 实际** 时间线:每条 specialist 建议标
  "当时建议/预测 → 后来实际 → 观察/假设/已验证效果"。让信任**可见地复利**。
- CausalMemory 必须降级表达:默认是 observation,只有复测、样本数、噪声处理和安全边界足够时才升为 validated effect。
- 每条发现都要有下一步:继续、停止、复测、补数据或转医生。
  后端 outcome_grader / specialist_hit_rate / personal_outcome 已就绪,缺的是把它做成主叙事。

### H3(季度)——异质用户验证 + AI-ready signal contract

- **主动智能(预算化,不打扰)**:从"用户先问"转向"我注意到 X 在漂 → 一键自查"。
  强化已有 anomaly_check / proactive_coordinator,严格打扰预算。
- **跨病种编排**:单专家已强,**交互**才是 Twin 打败单点 App 处。创始人画像即活例:
  糖前期(HbA1c 6.3)× 脂肪肝倾向 × 长期 PPI × 12 种药 之间的相互作用
  (PPI 长期×B12/镁、代谢×肝、进食时间×血糖)。强化 orchestrator cross-review 的多病种合成。
- **异质用户验证**:Phase-1 不能只围绕创始人。必须招募 5-10 个不同性别、主诉、设备组合、药物/补剂背景的用户。
  如果系统在不同人群上仍输出单一反流/代谢假说,说明过拟合。
- **Signal Contract**:吸收 open-wearables 的 `SeriesType` 思路,给 HRV/HR/RHR/睡眠/血糖/血压/体重/SpO2 等固定单位、聚合方式、来源优先级、新鲜度和 coverage matrix。
  没有这个,LLM 和 trajectory 会在同名不同义数据上推理。

### H4(6–18 月)——信任基础设施 + 可控扩展

- **ClinicalRecordLibrarian**:中国场景先做出院小结/门诊病历/体检 PDF 的叙事管线(index → 关键词检索 → 证据片段 → Twin/Chat/Review),不要把美国 SMART-on-FHIR 误当近期护城河。
- **Medplum 式 chokepoint**:访问控制、审计、租户、短 token、字段级加密收进数据层默认路径。第 N 张敏感表不能靠"记得加 user_id"。
- **受控 Write 自治**:只对低风险、可撤销、可审计、对该用户已验证有效的动作升级;处方、剂量、财务、供应链永远逐笔确认。
- **10M 平台化**:只有当每日工件、异质用户验证、信任托管、合规数据层和自助 onboarding 成熟后,才谈家庭/朋友圈/B 端平台。

---

## 贯穿纪律:删 ≥ 加,日价值 ≥ 慢账本

下一阶段每加一个,先问"能不能先合并/删两个重复的"。45 Web 路由有多少死路?13 专家有无该合并?
**收敛本身就是产品工作**,且是此阶段性价比最高的。

新增长期纪律:

- 任何主路径功能必须增强 Daily Artifact、5 分钟 on-ramp 或 Discoveries,否则默认后置。
- 任何"因果"措辞必须有证据等级;弱相关只叫 observation/hypothesis。
- 任何全局写死的 N=1 规则都是过拟合气味,必须 per-user 化或明确 TODO。
- 任何新数据源必须有 DataConnection / ConsentGrant / ProvenanceRecord / Signal Contract。

## 创始人 dogfood 闭环

创始人真实画像(12 药 / 糖前期 / 胃炎 / 脂肪肝倾向 / 鼻炎 / 睡眠)是完美的多病种测试用例。
个体化能力**先在创始人身上证明**,但不能只在创始人身上证明。创始人是最深 dogfood,不是泛化证据。
Phase-1 必须加入 5-10 个异质用户作为 blocker:验证 Reva 能否从一个人的生理和生活方式迁移到不同主诉、不同设备、不同药物/补剂组合的人。

---

## 已完成(2026-06 这一批,作为 H1 起点)

原研药识别+对话推荐 · 肝脏趋势 · 归一层同步(修复 biomarker 断连)· 用药疗程→复查闭环 ·
健康世界观注入 · 症状级急症红线 · 时滞因果引擎 · L4 社会连接自评 · **系统自我监控** ·
多药梳理。其中后 4 项待补三端 UI(H1 进行中)。

---

## 2026-06-27 长期规划修订摘要

从今天起,长期规划的排序改为:

1. **Daily Artifact** 先于更多 specialist。
2. **5 分钟 on-ramp** 先于复杂 onboarding。
3. **trust-custodianship + 安全脑** 先于"数据量护城河"叙事。
4. **CausalMemory 诚实表达** 先于用户可见因果故事。
5. **异质用户验证** 先于家庭/朋友圈/B 端扩展。
6. **Signal Contract + provenance** 先于更多 wearable connector。

*改本文件时,与实际进度对齐;过期的规划比没有规划更误导。*
