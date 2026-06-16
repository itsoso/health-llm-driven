# 基因解读第一性原理最优方案(复元 / Reva 个人健康 OS)

> 来源: 多视角工作流(6 巨匠/学科透镜 + 41 条断言 3 票对抗式核实)综合
> 日期: 2026-06-16 · 状态: 战略稿(已对抗式核实, 炒作/不安全断言已降级)
> 实现: 见 §6 分阶段; Phase 0 先行

All key claims are now verified against the actual code:
- `compute_prs`/PRS_WEIGHTS only consumed at `genetic_data.py:1740-1750` (a display endpoint) — **not** wired into Twin/specialists. The "放大人群偏差" risk is potential, not current.
- `effect_estimator.py` has explicit `prior_mean`/`prior_var` params and `estimate_from_deltas` uses `_population_deltas` only — no genotype stratification exists yet.
- `gene_config.py:154/203/222` confirms the strong imperatives ("需严格控制LDL", "下午后避免咖啡", "COMT Met/Met...需正念和低咖啡因").
- `intervention_significance.py:29` `_GENERIC_CVI_PCT = 10.0` un-sourced; RCV formula drops the CVA term.
- `gene_knowledge_audit.py` confirms tier0/1/2/X with `requires_authority` gate on tier0 only; tierX lumps BRCA1/2 with CFTR/ATP7B.

Now I have what I need. Here is the strategy document.

---

# 第一性原理基因解读最优方案 — 复元 / Reva 个人健康 OS

> 战略定位:这不是"再做一份更准的基因报告",而是把基因型从**产品终点**降级为**系统先验参数**,接进已有的纵向真值与 N-of-1 验证回路。差异化护城河不在"我比别家更懂某个 SNP",而在"我有一本 per-user 因果账本,记录这个变异对**你本人**到底有没有用,且每季复测都在收敛"。

---

## 1. 一句话第一性原理

**基因组不是蓝图,是一组终身恒定的概率先验 + 一张"环境→表型"的反应规范函数表;它告诉你地形,不告诉你走哪条路——路由可改层(表观/行为/药物/暴露)的干预与你自己的复测数据共同决定。**

展开三句:
- 中心法则是**信息流方向,不是因果强度保证**。DNA→RNA→蛋白→表型之间有转录、剪接、翻译、修饰、定位、降解七道独立可调闸门,每一道都被表观/环境/年龄/剂量改写。
- 进化结构决定信号在**多位点上而非单点**:能在人群里保持常见(>5%)的变异,几乎都是近中性/微效(纯化选择会迅速清除"常见+大效应+纯有害"的组合)。所以单 SNP 对个体的预测力天然极低。
- 因此基因型在贝叶斯意义上是 **prior**;只有叠加表型(化验/CGM/可穿戴/N-of-1)这些 likelihood,才能得到对这个个体可行动的 **posterior**。没有下游数据,基因解读停在先验,先验本身不可执行。

---

## 2. 为什么"抄 skill / 堆 SNP / 静态报告"必然没突破(从第一性原理推)

| 失败路径 | 第一性原理上的死因 |
|---|---|
| **静态报告(23andMe 式)** | 把 prior 当 posterior 卖。报告是一次性、看完即弃的低杠杆物(Meadows 谱系最底端:参数/常量)。它呈现的是不可逆的边界条件,却伪装成可行动结论。这块早已商品化、零差异。 |
| **堆 SNP(测更多位点)** | 信噪比不随位点数提升。复杂性状的遗传方差被成百上千位点稀释(omnigenic 假说的极端版),单点可解释方差天然极低。多测 100 个近中性 SNP = 多 100 条噪声。瓶颈从来不是"测得不够",而是"缺下游闭环把先验收敛成后验"。 |
| **抄 skill / 通用文案** | 把"群体平均 OR≈1.2 的关联"翻译成"对你的确定性指令",是 calibration 失败。同一变异在不同祖源、不同环境下效应量不同(效应量是环境的函数,不是常数);把它当常数输出,对东亚用户系统性失真。 |
| **用单一 risk_level 摊平展示** | 把因果强度完全不同的三类(单基因致病 / 药物基因组 / 复杂性状弱关联)用同一 UI 权重渲染,制造伪确定性。这正是消费级基因"看着炫但没用"的根因。 |

**结论**:突破不在"读更多",而在**改解读语法**——从"你有没有这个变异",转向"在你当下的环境与生理状态下,你这套等位基因把概率分布往哪个方向移了多少,以及这一步能否反向移动它"。

---

## 3. 最优解读范式:按因果可行动性的三级分诊

定义:**因果可行动性 = 干预能改变结局的程度 × 证据等级 × 结局可逆性。** 三者任一为弱 → 只能解释,不能驱动行动。

> ⚠️ **被降级断言的显式纠正(分诊框架本身)**:`act / risk-stratify / de-emphasize` 是**本方案提出的新命名**,而仓库现状是 `gene_knowledge_audit.py` 的 `tier0_pharmacogenomics / tier1_lab_anchored / tier2_lifestyle / tierx_confirmation_only`(已核实,见 `TIER_DEFINITIONS`)。**不要再造第三套命名**——下面的三级直接映射到既有 tier,把"可行动性"这个**正交新维度**叠加上去,而非替换。另外:ACMG/AMP(评单变异致病性)、CPIC/PharmGKB(评药物-基因对用药证据,输入是 star-allele 表型而非单 SNP)、ClinGen actionability(评基因-疾病可干预性)**作用域不同、互不覆盖**,**不能逐条"过三关"**;应按位点类型选对应权威。

### 🟢 Tier ACT(对应 tier0 + 部分 tierx)— 唯一进"行动卡片"层

| 类别 | 具体基因 | 证据来源 | 出口动作 |
|---|---|---|---|
| **药物基因组(PGx)** | CYP2C19/CYP2D6/CYP2C9/VKORC1/SLCO1B1/G6PD/DPYD/TPMT/NUDT15/HLA-B\*5701/HLA-B\*15:02/HLA-B\*58:01/HLA-A\*31:01 | **CPIC Level A / PharmGKB 1A / FDA label**(`requires_authority=True`,只认 `cpic:/pharmgkb:/fda:` 前缀来源 ID) | 生成"就医时出示给医生/药师"的 PGx 卡;**即使当前未服该药也预生成**(价值在处方那一刻兑现,而处方发生在 App 之外) |
| **高外显单基因/孟德尔** | HFE(血色病)、FH 信号(LDLR/APOB/PCSK9)、BRCA1/2、Lynch、肥厚型心肌病基因、携带者状态 | **ClinVar Pathogenic + 多星专家共识 / ClinGen actionability / ACMG SF** | 唯一动作 = "**转诊遗传咨询 / 对应专科 + 做临床级测序确认**",绝不下结论 |

> ⚠️ **消费级芯片硬护栏**:23andMe 类是 **genotyping 不是 sequencing**,只查预设位点,对 BRCA 常只覆盖少数创始变异(如三个德系犹太位点),对 indel/CNV/HLA 只能 proxy 近似。**任何"阴性"都不能解读为"没有该病风险"**;ACT 级发现一律强制"诊断级测序复核"前置。仓库 `genetic_registry.py` 的 `_VARIANT_TYPES`(indel_proxy/hla_proxy_marker)已诚实标注,UI 与 prompt 都要透传。

### 🟡 Tier RISK-STRATIFY(对应 tier1_lab_anchored)— 只做"背景解读 + 调可改层阈值"

- **APOE / MTHFR / FADS1 / ALDH2 / LCT / 9p21** — 不输出风险数,而是**调谐可改层的阈值/默认值**:如 APOE4 → 上调降脂/运动权重(不预测痴呆);MTHFR → 盯 Hcy、定叶酸形式;FADS1 → 直接补 EPA/DHA 而非亚麻籽。
- 强制附带 **GxE 情境化**:效应量是环境的函数,基因型只给"反应规范方向",要叠加 Twin 的环境/行为/化验分区。
- 每条建议挂一个**可测 endpoint + 复查窗口**,进 N-of-1 闭环(见 §6/§7)。

### 🔴 Tier DE-EMPHASIZE(对应 tier2_lifestyle + PRS 弱关联)— 默认折叠,只在追问时展示

- **FTO / ACTN3 / ADORA2A / VDR / COMT / CYP1A2 / 各类 GWAS 单 SNP / PRS_WEIGHTS 里的位点**。
- 强制前缀:**"群体弱关联(OR 通常 1.05–1.3),个体无预测力,非诊断"**。
- **绝不进首页行动卡**;COMT/CYP1A2 这类行为基因学关联效应量小、重复性争议大,最多做"概率性科普先验",**不做祈使指令**。

---

### 被降级断言的逐条纠正(分诊层相关)

| 原断言 | 裁决 | 纠正(已对代码/文献核实) |
|---|---|---|
| "APOE4 不改诊断只改生活方式权重;生活方式获益证据有限" | overstated | 方向对,但**把证据说弱了**。FINGER 是 RCT,2025 三 RCT(FINGER/J-MINT/MAPT)meta 显示多域干预在 ε4 携带者获益**反而更大**(交互 p≈0.035)。但结局是 2 年认知测验复合分,**不是痴呆发病率下降**。措辞:**"有 RCT 支持的合理手段、可能获益更大",而非"能抵消/消除 AD 风险"**。另:**杂合 ε3/ε4 外显不完全,但纯合 ε4/ε4(约 2% 人群)病理外显接近完全**(Fortea 2024 NatMed),需遗传咨询解读。 |
| "ALDH2 仅靠单篇 2014 Cell Metabolism 支撑、需软化戒酒建议" | overstated(部分 refuted) | **把修正对象搞反了**。结论(戒酒最安全)证据**充分**:IARC 列乙醛为 1 类致癌物,ALDH2 是孟德尔随机化经典模型,杂合饮酒者食管癌 OR≈3.19、重度>10 倍。真正缺陷是**引用卫生**:`pgx.py:386-414` 只挂一篇机制类期刊文献去支撑流行病学量级 → 应替换为 IARC + 食管癌 meta + 精准预防指南。ALDH2×心血管关联比×食管癌更存争议,应降级并列。 |
| 分诊"逐条核对 ACMG+CPIC+ClinGen 三套" | overstated | 范畴混淆(见上)。按位点类型选对应权威;仓库现状是**人工策展 + 来源 ID 闸门**(tier0 `requires_authority`),**不自行做 star-allele 定型**(`pgx_cpic_table.py` 明确声明)——这是对的,保持。 |
| "CYP1A2 慢代谢→限咖啡因 / COMT warrior-worrier→压力策略" | overstated(主张降级=supported) | 两例**证据强度不对等**:CYP1A2 对咖啡因清除的**药代层**可重复(medium-high),但**临床结局层**(心梗/血压)重复性差;COMT 单 SNP 对认知/焦虑接近"候选基因时代未复现"的反面教材(解释方差<1%)。代码 `gene_config.py:203/222` 用了"避免/需"祈使句 → **降级为概率性科普**(如"慢代谢者可把咖啡前移,以睡眠反馈为准";COMT 单 SNP 强结论剔除)。干预本身良性,非 unsafe,但祈使口吻会侵蚀用户对高证据告警的信任。 |

---

## 4. 杠杆点(系统论):为什么 DNA 本身是最低杠杆

借 Meadows 杠杆点谱系 × 多组学层级。**越靠"参数/常量"越低杠杆,越靠"信息流/反馈回路/范式"越高杠杆。**

| 杠杆排序 | 层 | 可改性/带宽 | 角色 |
|---|---|---|---|
| **L4 最高(元杠杆)** | **闭环验证回路**:personal_baseline(90 天滚动 z-score)、baseline_deviation_sentinel、outcome_grader、effect_estimator、intervention_cycle | — | 决定上面所有层是否可信。把"先验"变成"对你成立的后验"的机制 = Meadows 的"信息流/反馈回路"层,比任何单层干预都高 |
| **L1 高** | 暴露组(PM2.5/AQI/花粉/光照昼夜/噪声/久坐/饮食模式) | 近端、几乎完全可改、效应快且大 | 基因无关就能即时产生价值;基因型在此只做阈值调谐(特应性变异→花粉/AQI 更保守) |
| **L2 高** | 行为/表观可塑层(睡眠/运动/进食时机/压力) | 每日可反复施加并测量 | 表观基因组与代谢组最强上游驱动 |
| **L3 高** | 代谢组/可改化验(CGM/血脂/Hcy/HbA1c/hs-CRP) | 数周可动 | N-of-1 验证的金标准 endpoint |
| **L5 中** | 微生物组 | 可改但检测信度弱 | **占位不仓促上**(避免重蹈"解读多但不可行动") |
| **L6 中低** | 蛋白组/转录组 | 消费级不可及 | 暂不落点 |
| **L7 低(仅作长程代理)** | 表观年龄时钟(甲基化) | 重测噪声大 | 长期轨迹参考,**绝不作 N-of-1 主 endpoint** |
| **L8 最低** | **基因组本身** | 终身恒定、不可逆、单独不可行动 | 唯一价值 = 上面所有层的**个性化先验输入** |

**论证 DNA 为何最低杠杆**:① 可逆性 = 杠杆,germline 在消费级语境不可逆(编辑不安全不合规),不可逆的东西是边界条件不是干预靶点;② 效应沿因果链衰减,落到个体建议上,单 SNP 的 OR=1.2 信噪比往往**低于**"你自己 90 天 HRV 偏离 2σ"这种近端个体信号;③ 把它当产品终点 = 用最低杠杆点定义产品 = 没突破的根因。

> ⚠️ **被降级断言纠正**:"基因组是最低杠杆点"是**基于 Meadows + 消费级可逆性的论证立场,不是普适真理**。在单基因病 / PGx 场景(HLA-B\*5701、DPYD、G6PD),基因型其实是**高杠杆决策点**(直接改药/停药)——**这类高外显场景必须排除在"低杠杆"论断之外**(它们正是 Tier ACT)。另:"暴露组/行为 > 单 SNP"方向有共识但**无统一倍数**,高度依赖性状(身高几乎全遗传 vs 血脂环境占比大),不给未加限定的普适比较。

---

## 5. 前沿(CRISPR / 表观编辑 / MSC)的诚实定位

**平台角色 = 追踪 + 科普 + 转诊。绝不推动用户行动。** 已获批/在研的基因编辑**全部是体外或体内临床级医疗干预**,起点是专科诊断 + 临床级测序,**不是芯片风险评分**。消费级 SNP 与前沿疗法之间是**范畴断层,不是连续光谱**。

### 三档证据标签(基于被降级断言的逐条核实)

| 疗法 | 真实状态(已核实纠正) | 平台呈现 |
|---|---|---|
| **Casgevy / exa-cel(镰刀贫血/β地贫)** | ✅ 已获 FDA 批准(2023-12/2024-01)。但**成本约 220 万美元、需清髓预处理、仅少数授权中心**,可及性极低 | 仅对**已确诊**患者,科普 + ClinicalTrials.gov 转诊 |
| **VERVE-102(体内 base editing×PCSK9)** | ⚠️ 早期 phase 1b。**数字需大幅收紧**:88% PCSK9 上限对(2026 期中,n=35,随访最长~18 月),但"68%"下限对不上任何报告值(0.6mg/kg 队列实为 60%);LDL"53-69%"是把 **4 人小队列均值(53%)与单人极值(69%)并列**,各剂量队列均值跨度 9%–62%。无临床结局、无对照、未获批 | "早期信号、单臂、未获批",**绝不作可选疗法** |
| **Tune TUNE-401(表观沉默 HBV)** | ⚠️ phase 1b/2a 极早期 PoC。"cure"是高度前瞻措辞 | 同上,绝不作 HBV 患者现实选项 |
| **Prime PM359(prime editor×CGD)** | ⚠️ **n=2**。**纠正**:已于 **2025-12 NEJM 同行评议发表**(不再是"待同行评议");"effectively cured"出自 CEO **带 "may have" 限定词**的口语表态,非论文结论(论文用"NADPH 氧化酶活性持久恢复 + 早期获益");随访仅 4-6 月**且项目已因商业原因关停**——长期数据可能永远不补齐,这反而是更需警惕的不确定性 | 科普 + 标注"研究阶段、n=2" |
| **MSC 免疫调节** | ⚠️ **证据分裂且关键论据已过时**。**纠正**:获批级证据集中在**急性 GvHD**(日本 Temcell 2015、美国 **Ryoncil/remestemcel-L 2024-12**,首个 FDA 批准 MSC);**"慢性 GvHD III 期 STAR 失败"查无此试验**(真正失败的是 remestemcel-L 在**成人急性** GvHD 的 III 期);**Alofisel 确证性 ADMIRE-CD II 失败(p=0.571)、2024-12 退出欧盟**——早期 56-66% 数据已被推翻。这恰恰**强化**"不可外推"论点 | 主动**警示**:静脉输注"万能干细胞"/外泌体抗衰缺可信疗效证据,FDA 已确立对未注册诊所监管权 |
| **表观编辑"可逆更安全"** | ⚠️ 机制成立(无双链断裂),但"更安全"是**未经长期临床验证的预期**;表观标记本身可能脱靶,耐久性逐病不同(NHP 中 PCSK9 沉默约 9 月) | 标"机制合理 ≠ 已证有效" |

### 安全边界(硬红线)

- **绝不**基于消费级 SNP 向用户推荐、暗示或"让用户去问要不要做"任何基因编辑/干细胞干预。
- 前沿信息**只对已确诊单基因病用户**呈现,且仅作转诊/科普;临床试验链接**只导向 ClinicalTrials.gov / 有资质医院**,绝不导向未注册诊所或医疗旅游。
- "已获批 ≠ 可及":批准不等于随时能做的选择。
- 平台最高保护价值 = **打假**(静脉 MSC 抗衰、外泌体美容、未注册诊所的感染/栓塞/肿瘤/经济风险),而非中立呈现。

---

## 6. 落地到现有系统的具体改造(分阶段)

> 原则(项目 CLAUDE.md):删代码 > 写代码;不为假想未来设计;凡个性化干预标"需专科/医生"。下面优先**接线既有零件**,而非新写抽象。

### Phase 0 — 止血(高 ROI,改 ≤3 个文件,先做)

| 改造 | 改哪个服务 | 动作 |
|---|---|---|
| **PRS 降级/正名** | `backend/app/services/genetic_prs.py` + `backend/app/api/genetic_data.py:1740-1750` | `PRS_WEIGHTS`(L9-39)是**无引用、无祖源校准的手写序数权重**(同 FTO 在 diabetes=0.8、obesity=1.2,纯人为缩放),`percentile = raw_score/max_score*100`(L93)**凭空构造、误导为人群百分位**。对外**不再叫 PRS、不再展示 percentile**,改为"相关位点计数 + 方向",formatter 注明"非人群校准多基因评分"。**好消息(核实)**:它目前**只被一个展示端点消费**(`/profile/me/comprehensive`),未接入 Twin/specialist——所以"放大人群偏差"是**潜在风险非现状**;**在接入任何 agent 先验前必须先替换为带溯源效应量**。子串匹配 `pattern.upper() in geno.upper()`(L81)还会让 ε2/ε4 误匹配,顺手修。 |
| **gene_config 强指令降级** | `backend/app/twin/gene_config.py:154/203/222` | "需严格控制LDL"→"饱和脂肪敏感,建议盯 LDL/ApoB 并验证(需医生评估目标值)";"下午后避免咖啡"→"慢代谢者可前移咖啡时间,以睡眠反馈为准";COMT"需正念和低咖啡因"单 SNP 强结论→**剔除或降为低置信科普**。 |
| **ALDH2 引用替换** | `backend/app/agents/safety_guardian/rules/pgx.py:386-414` | 单篇机制类文献 → IARC 乙醛 1 类 + 食管癌 meta + 精准预防指南;心血管关联降级并列。 |

### Phase 1 — 证据分级 + 去噪贯通

| 改造 | 改哪个服务 | 动作 |
|---|---|---|
| **正交两维落地** | `backend/app/twin/schema.py`(genetic 分区) + `genetic_registry.py` | 每条 variant 加 `actionability ∈ {act, risk_stratify, de_emphasize}` 与 `evidence_grade ∈ {cpic_a, pharmgkb_1a, clinvar_path_confirm, clinvar_likely, gwas_association, proxy_uncertain}`,**由静态映射驱动,不靠 LLM 判断**(沿用 `gene_knowledge_audit` 的 `requires_authority` 闸)。 |
| **evidence-aware formatter** | `backend/app/twin/formatter.py`(`twin_to_prompt_blob`) | 基因块每条附 `(actionability, evidence_grade, effect_size_if_known)`,de_emphasize 级强制前缀"群体弱关联,个体无预测力",防 LLM 渲染成确定结论(HARNESS.md source-aware 原则)。 |
| **CVi 兜底标占位 + 补 CVA** | `backend/app/services/intervention_significance.py:29` | `_GENERIC_CVI_PCT = 10.0` **无公认来源**,标"需查 EFLM/Westgard 占位";完整 Harris RCV=√2·Z·√(CVA²+CVi²),代码丢了 **CVA 项**会低估 RCV(噪声带偏窄),补上。**术语纠正**:CVi 在 PhenoAge 计算里**不存在**(`phenoage.py` 是确定性 Levine 线性模型),它在**N-of-1 干预去噪层**——别写成"PhenoAge 的 CVi"。 |

### Phase 2 — 先验注入 + 多组学总线 + 抗衰闭环

| 改造 | 改哪个服务 | 动作 |
|---|---|---|
| **基因型→effect_estimator 先验(最高 ROI 一根线)** | `backend/app/services/effect_estimator.py`(`conjugate_posterior` 已是纯函数,`prior_mean/prior_var` 是显式入参 L109) + 新增 `services/genetic_effect_prior.py`(~80 行) | 当前 `estimate_from_deltas` 只用 `_population_deltas` 算先验(L169)。新函数输入(基因型 + metric_code + cycle_type)输出 `(prior_mean, prior_var, stratum_label, evidence_tier)`:(a) 同基因型人群子池 ≥ 阈值 → 信息先验;(b) 不足 → PRS 方向给**弱先验**(小幅偏 mean、保大 var,个人数据照常主导)。**`estimate_effect` 加可选 `genotype_prior` 入参,缺省回退现有路径,零破坏。** ⚠️ **纠正**:当前任一基因型分层的人群周期数据**几乎为零**(design doc 标 0 周期),冷启动会立即退化到弱先验;且"同基因型子池"目前**仅设计构想未实现**,弱先验源头 PRS_WEIGHTS **未经祖源校准**——必须先做 Phase 0 的权重替换,否则放大人群偏差。 |
| **多组学投影到 domain 总线** | `backend/app/services/personal_evidence_matrix.py` | 不建宽表,所有组学投影到 domains(metabolic/cardiovascular/recovery...)对齐。加 `signal_type='verified_effect'`(reliability=high,**唯一能 raise 基因 domain 个人响应置信度的信号**),PRS 结果标 `genetic`(强制 lower)。新组学接入 = 加一个 `_add_xxx_signals`,自动获得分级+去噪+gap 检测。 ⚠️ **纠正**:verified_effect 只能上调"**个人响应置信度**",**不能上调"基因→表型"的群体生物学因果置信度**(后者由文献/CPIC 定档,N-of-1 不可上调)。建议把两条置信度拆成不同字段(`genetic_causal_confidence` vs `personal_response_confidence`),否则会把个人 n=1 结果错误回灌到生物学判断——在用药/基因 domain 是安全隐患。 |
| **PhenoAge 作可改读数闭环** | `backend/app/services/phenoage.py`(读 Labs 纯函数) + `intervention_cycle_service`(加 `start_longevity_cycle`) + `longevity_specialist/specialist.py` | 把 `phenotypic_age`(direction=down)注册为合法 `OutcomeMetric`,目标含拖累最重的 2-3 个血检项。 ⚠️ **多处纠正**:① PhenoAge 短期(8-12 周)变化大半来自 CRP/血糖/WBC 急性炎症波动,**不反映衰老速度**——保留现有 claim_boundary"非诊断、非真实衰老速度";② `_propose_phenoage_episode` 用 **Fitzgerald 2021** 背书是**跨时钟张冠李戴**(那测的是唾液 DNAm Horvath 时钟、n=18 pilot,与血检 PhenoAge 不同底物)→ 改引同类血检纵向证据或显式标注"仅作方向参考";③ 单次抽血无 CV 护栏 → 要求复检在无急性炎症期 + 加最小可信变化阈值;④ "变年轻了"庆祝文案补单次抽血波动免责。**好消息(核实)**:现有措辞已克制(卡片标题是疑问句"验证身体年龄是否真的下降",非定论),"已验证降 X 岁"在代码里**不存在**——保持。 |
| **采集优先级接基因** | `data_acquisition_guidance.next_best_data` | 用户有基因型但某 domain 无验证信号(genetic_only_policy 命中)→ 把"开针对该 domain 的 N-of-1 周期 / 补锚定血检"排高优先级,形成"基因→采集→验证→收敛"飞轮。 |

### Phase 3 — 诚实边界 / 转诊层

| 改造 | 改哪个服务 | 动作 |
|---|---|---|
| **边界路由器** | 新增 `services/claim_boundary_router.py`,复用 `genetic_registry._CLAIM_BOUNDARIES`(不另造) | 统一 `route_finding(category, evidence_tier, requires_clinician, has_personal_validation) → {mode: explain｜downgrade｜refer}`。orchestrator 合成前每个 finding 过一遍。前沿疗法 / PGx / 高风险疾病 → **refer 态**("不替代诊断 + 去 X 科 + 带上这些数据")。 |
| **PGx 处方措辞收口** | `pgx.py` 各条 action | 多条写了"换用 X 药" → 统一收敛为"**与处方医生讨论**换用",绝不越处方权(`_CLAIM_BOUNDARIES.drug_sensitivity` 已 requires_clinician,守住)。 |
| **前沿"追踪+科普+试验地图"模块(只读)** | 新增,挂已登记 HealthProblem | 对已确诊单基因病用户展示:已获批疗法 / 在研试验(链 ClinicalTrials.gov)/ 三档证据标签 + "基因炒作过滤器"打假卡。 |

---

## 7. 真正改善健康的闭环

```
                        ┌─────────────────────────────────────────────────┐
                        │  基因型(PRIOR,L8 最低杠杆 · 终身恒定 · 不可逆)   │
                        │  genetic_registry / gene_config                  │
                        │  Tier ACT→行动卡  RISK→调阈值  DE-EMPH→折叠科普  │
                        └───────────────────────┬─────────────────────────┘
                                                 │ 注入先验(prior_mean/var)
                                                 │ ⚠不下结论·OR<1.3 标"群体平均不可外推"
                                                 ▼
   ┌──────────────────────────────────────────────────────────────────────────┐
   │  可改层干预(高杠杆 · 反复可施加可测量)                                     │
   │  L1 暴露组(AQI/花粉/光照) · L2 行为(睡眠/运动/进食时机) · L3 代谢       │
   │  (CGM/血脂/Hcy/HbA1c) · 药物(PGx 只提示·处方权在医生)                   │
   │  基因型在此只调"阈值/默认值/盯哪个指标",GxE 情境化                        │
   └───────────────────────┬──────────────────────────────────────────────────┘
                            │ 每条建议挂 baseline_value/target/check_back_date
                            ▼
   ┌──────────────────────────────────────────────────────────────────────────┐
   │  纵向测量(高带宽 · 随干预流动 = LIKELIHOOD)                                │
   │  biomarker · CGM · 可穿戴 · PhenoAge(可改读数,非衰老速度)                 │
   │  personal_baseline 90 天滚动 z-score                                       │
   └───────────────────────┬──────────────────────────────────────────────────┘
                            │ ① RCV 去噪(单次复查·intervention_significance)
                            │    防把测量噪声当见效  ⚠补 CVA 项
                            ▼
   ┌──────────────────────────────────────────────────────────────────────────┐
   │  N-of-1 效应验证(L4 元杠杆 = POSTERIOR)                                    │
   │  effect_estimator 层级贝叶斯:先验(基因/人群) + 个人 delta → 后验+CI       │
   │  ② 跨周期贝叶斯 CI 去噪  防把单次波动当因果                                 │
   │  intervention_cycle 12 周 episode                                          │
   └───────────────────────┬──────────────────────────────────────────────────┘
                            │ CI 跨 0 → "未在你身上确认"(哪怕基因强烈提示)
                            │ confidence→措辞自信度(effect_estimate_prompt_blob)
                            ▼
   ┌──────────────────────────────────────────────────────────────────────────┐
   │  调整 → per-user 先验校准账本(护城河)                                      │
   │  记录"基因先验预测 X" vs "你实测 Y"的系统性偏差,收缩/外推个性化系数        │
   │  (例:APOE4 说该限饱和脂肪,但 12 周你 LDL 几乎不响应 → 下调这条先验权重)   │
   └───────────────────────┬──────────────────────────────────────────────────┘
                            │ 群体先验 → 个体后验,每季复测收敛
                            └──────────────► 回灌上方"可改层干预"(新一轮)
```

### 闭环的硬约束(被降级断言纠正 + 安全红线)

1. **基因先验只改起点,不改终点**:CI 跨 0 时必须输出"未在你身上确认",**严禁因"基因说该有效"就建议继续**——这正是两段去噪要挡的确认偏误。
2. **三级证据天梯**:群体 OR = "先验/相关";personal_baseline 偏离 = "相关非因果"(sentinel 已做);**只有 effect_estimator 闭环命中才升格为"对你成立的个体证据"**。UI 与 prompt 双侧透传。
3. **N-of-1 是"自我实验级"证据,n=1**:⚠️ 纠正——它能(在带对照/随机化/多周期时)提升"**对你本人该干预是否有效**"的后验,但**几乎不能**提升"基因→表型"的**群体因果**置信(那需 GWAS/MR/RCT)。当前 `_propose_phenoage_episode` 给 12 周**单臂无对照无随机单点复检**却标 `evidence_level="high"` → **应降为 low/anecdotal**;要升级必须加内部对照(交叉/洗脱/AB 重复)。证据等级绑**设计质量**,不绑样本量标签。
4. **不假装闭环成功**:数据缺失/陈旧时 outcome_grader 必须标 `inconclusive` 顺延,不为"好看"硬评分——否则个体后验被污染,比没验证更危险。
5. **不绕过急症红线**:baseline_deviation_sentinel 已把 RHR≥100/<40 让位 SafetyGuardian;**任何个性化/闭环逻辑不能吃掉确定性急症阈值**,基因个性化只调慢性/优化层。
6. **PGx 永远 requires_clinician**;**前沿抗衰(senolytics/雷帕霉素/NAD+ 静脉/表观重编程/干细胞)一律 refer 态**,不开方、不背书、不暗示自行尝试。
7. **群体外推有祖源偏差**:多数 GWAS/PGx 证据以欧裔为主,用于中国/东亚用户时等位频率与效应量可能不同,先验权重对应下调并标注。

---

## 一句话收尾

把基因从"内容(报告)"降级为"先验参数",把验证权交给用户自己的纵向 delta —— 别家给的是"你是什么",你给的是"对你这类基因型,改什么最划算,且这是我们在你身上验证过的"。这就是会持续运营的真实健康平台唯一可防御的护城河:**一本每季都在收敛的 per-user 因果账本。**

---

**关键源文件锚点(供执行参考,均绝对路径)**:
- `/Users/liqiuhua/work/personal/health-llm-driven/backend/app/services/genetic_prs.py`(PRS_WEIGHTS 手写权重 L9-47,percentile 凭空构造 L93,子串误配 L81)
- `/Users/liqiuhua/work/personal/health-llm-driven/backend/app/api/genetic_data.py:1740-1750`(PRS 唯一消费处,仅展示端点)
- `/Users/liqiuhua/work/personal/health-llm-driven/backend/app/twin/gene_config.py:154/203/222`(强指令文案)
- `/Users/liqiuhua/work/personal/health-llm-driven/backend/app/services/gene_knowledge_audit.py`(tier0/1/2/X + requires_authority 闸)
- `/Users/liqiuhua/work/personal/health-llm-driven/backend/app/services/effect_estimator.py:106-203`(conjugate_posterior 显式 prior 入参,estimate_from_deltas 仅用人群先验)
- `/Users/liqiuhua/work/personal/health-llm-driven/backend/app/services/intervention_significance.py:16-50`(CVi 兜底 10.0 无来源,RCV 缺 CVA 项)
- `/Users/liqiuhua/work/personal/health-llm-driven/backend/app/services/phenoage.py`(确定性 Levine,无 CVi)
- `/Users/liqiuhua/work/personal/health-llm-driven/backend/app/agents/longevity_specialist/specialist.py:165-175`(_propose_phenoage_episode,Fitzgerald 跨时钟引用 + evidence_level 偏高)
- `/Users/liqiuhua/work/personal/health-llm-driven/backend/app/agents/safety_guardian/rules/pgx.py:386-414`(ALDH2 单文献引用)