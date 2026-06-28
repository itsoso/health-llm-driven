# Rulebook → Deterministic Governed Runtime —— 一个可复用研发范式(量化交易实例)

> Status: Design draft
> Date: 2026-06-27
> 方法: 5 视角对抗式 workflow(harness 考古 / 量化落地 / 规则抽取法 / SDLC-CICD / 对抗反类比)+ 4 条承重声称对真实代码验证(全 holds=high)+ 综合。
> 一句话: **复用本健康仓库已被代码验证的机器——权威源 → owner-reviewed 带 regime 守卫的结构化规则 → 确定性 fail-closed `@register` 引擎 → 治理化验证闭环 → 6-Gate SDLC + 自动回滚——去造一个趋势量化系统;LLM 只离线产规则、永不下单;成功从"挖书里 alpha"重定义为"证伪工厂 + 风控兜底"。**

---

## ⚠️ REALITY CHECK(2026-06-27 复核 —— 本文档是 greenfield 写的,夸大了缺口)

> 本文档写时**没读用户的真实量化代码** `~/work/personal/macd-analysis-claude/`。5 视角映射 + 对抗验证后(16 缺口里 **2 个被驳回为"其实已有"**,其余多数降级为"形式而非能力")结论:**那套仓库已经 ~80% 是本文档说的"证伪工厂 + 风控治理",且常常比本文档/脚手架更严谨。** 它甚至**凭实证走到了本文档的核心立场**(CLAUDE.md §战略方向:单锚点 book-alpha 扫参已穷尽 R45-R52 全 NO-GO → 转多 alpha sleeve)。

**它已有(别重建)**:两套独立 Deflated Sharpe + PSR + PBO/CSCV(`stat_validation.py`/`cpcv_validator.py`)、CPCV 含 purge+embargo(Lopez de Prado)、walk-forward 带 IS→OOS 衰减比、ablation + 10 维 alpha 归因、ex-ante 成本/滑点闸(回测+实盘共用 `execution_cost.py`)、next-bar-open 防前视(`test_backtest_realism.py` 钉死)、kill-switch + 熔断(三套 `risk_manager`/`portfolio_risk`/`kill_switch`)、paper→shadow→live 毕业阶梯(`lifecycle_manager.py` R91 + `paper_readiness.py`)、sleeve 加层不减层风控、regime 守卫(`regime_classifier.py` = applies_when 真身)、回测↔实盘 bit-wise parity CI(`test_backtest_live_parity.py` atol=1e-9)、**R4 de facto**(ML shadow_mode 默认、实盘引擎零 LLM import,grep 确认)。

**真缺口(窄,形式/强制执行,非能力)**:① 没有把这些已存在的 rung 串成**一道 fail-closed 的验证阶梯 orchestrator**(现在人工 ad hoc 调,过拟合配置能跳过 DSR/parity 还摸到 paper);② **DSR 算了但没当硬闸**(`reverse_dsr_check.py` 写好却零调用方!);③ 没有机器可读的 S1 reviewed-rule registry(规则是命令式 Python+config dict,溯源是 R 号散文注释);④ **整个仓库没有 CI**(`.github` 不存在;R4/防前视只靠约定+零散测试,没东西会因违反而变红);⑤ 交易所 key 无 withdraw/IP 断言;⑥ kill-switch 三套阈值分歧 + hotcoin-v1 下单 tick 不查组合级 kill。

**本文档的 S1/S2/S5 应重读为"命名/合并/强制执行已存在的东西",不是"去建"。** greenfield 脚手架 `~/work/personal/quant-rule-factory/` 相对真仓库是玩具,**已废弃**(见其 README),不要长它。详见对账 workflow w2to0gv0x。

---

## 0. 最重要的一句:范式迁移时,价值重心反转

健康域里**价值在规则内容**:CYP2C19→氯吡格雷替代(claims.jsonl 实证,evidence_level A,CPIC 源)对所有人永远为真,确定性引擎只是正确地应用它。

市场里**规则内容是最弱一环**:生理平稳且有因果;市场非平稳、对抗、自反。书里任何 edge 都不成比例地**已被套利**(印出来就公开)、**幸存者偏差**(爆仓的人不写书)、或一被使用就衰减——拥挤的 edge 还会变负(清算瀑布你站错边)。

> 本仓库其实已经知道这个形状:`基因型→效应先验核实为空 0/12` 就是一次回测挖掘——只不过市场给的是**相反的失败模式**:不是诚实的空,而是多重检验噪声递给你一堆"看起来很棒"的假阳性。

**所以:KB→确定性规则管线——健康仓库的字面心脏——迁移过去是最不值钱的组件。** 价值在健康域当配角的那些部件:`applies_when` regime 守卫(没有 regime 守卫的规则是地雷)、裁决抑制门(改名 `requires_live_confirmation`)、deflated/样本外验证闭环、确定性风控引擎、回撤自动平仓 kill-switch。**用系统"多狠地拒绝假赢家、多可靠地破限平仓"来衡量它,而不是它"挖出多少 alpha"。**

---

## 1. 通用范式:8 阶段工厂(从仓库抽象,域无关)

剥掉"健康",本仓库是一台把权威知识变成**治理化、确定性、可验证软件、且 LLM 被挡在每个不可逆决策之外**的工厂。八个可组合 STAGE,每个产一个 ARTIFACT、配一道 GATE:

| Stage | 做什么 | 仓库实证(verified) | GATE |
|---|---|---|---|
| **S1 INGEST→reviewed claim** | 权威散文→机器可评估记录:`applies_when`(闭合文法 regime 守卫)+`evidence_level`+`claim_boundary`+`sources` 溯源 | `claims.jsonl` + `system_knowledge_importer` | importer 只收 `review_status=='reviewed'`,其余主动降级;未评审知识进不了服务表 |
| **S2 COMPILE→确定性引擎** | 每条阈值→纯 `@register` 函数 `(state)->alert`,KB-blind,正负单测 | `safety_guardian/` 62 规则 | `evaluate_rules_with_status` 隔离每条但回 `failed_rule_count`;`make_fail_safe_advisory` 把 HIGH 注入主渲染 `alerts[0]`——空告警永不冒充绿。fail-closed+fail-loud 是**结构性**的 |
| **S3 SNAPSHOT→带时效的类型化状态** | 单一校验过的分区视图(Twin),规则与 LLM 都读它而非原始行,陈旧度被显式说出 | `twin/`(14 分区+builder+cache) | 陈旧值不被当当前 |
| **S4 ORCHESTRATE→路由→确定性专家→LLM 只综合** | 正则意图分类→静态 `applies_to` 门控专家注册表(非 LLM 自由生成)→结构化 finding→LLM 只写 rationale | `orchestrator/` | LLM 不做裁决 |
| **S5 VERIFY-BEFORE-WRITE + N-of-1** | 高风险动作需 restate-confirm 或确定性执行;"有效"裁决须过样本外 CI-excludes-zero + 混杂门 | `effect_estimator`(`is_clinician_gated_metric` 强制 `is_effective=False`) | 混杂指标降级 inconclusive |
| **S6 SDLC** | 四问+ASCII→6-Gate 双环+Dossier→CI(pytest+`check_doc_drift` 计数 PIN)→`deploy.sh` 低于阈值自动回滚 | feature-plan / product-pipeline / ci.yml / deploy.sh | 各 Gate |

**跨域不变量(原样carry)**:R4(LLM 永不发出不可逆动作)、earned-autonomy 阶梯(display→draft→manual_confirm→trusted→auto,含 `NEVER_AUTONOMY_KINDS` 永不毕业集)、加层不减层、fail-closed+fail-loud(每个吞掉的异常=静默绿=bug)、verification-before-write、每条晋级规则带证据溯源、确定性规则 > LLM 自由发挥。

## 2. 可复用 skill:`domain-rule-factory`

落在 `.claude/skills/domain-rule-factory/SKILL.md`,是现有 `extend-safety-or-specialist` / `system-map` / `product-pipeline` 的**抽象父**。

- **INPUTS**:① 可引用 ID 的权威源(书/指南/论文);② 域状态 schema(Twin 分区);③ 要围栏的不可逆动作(健康 write / 交易 order);④ 每项目 gate 绑定(测试命令/评审 agent/deploy+health+rollback)。
- **STAGES** = 上面八阶段。
- **如何与现有生态组合**:被 `product-pipeline`(双环+6-Gate)调用为 S5 实现模式;把团队 fan-out 委托给 `health-harness-orchestrator` 拓扑重皮;把计数注册进 `system-map` 让 `check_doc_drift` PIN 住。
- **量化实例** = 子 skill `quant-rule-factory`(在量化 sibling 仓库的 `.claude/skills/`):源=交易书,不可逆动作=券商 order,状态=MarketTwin+PortfolioTwin,S2 引擎=RiskGuardian+StrategySignals,S5=walk-forward 回测 + 纸面 soak + 伪 edge 门。

> 新域达到 build-ready = 填四个 INPUT + gate 绑定;其余(reviewed-gate / 闭合文法 / fail-safe 注入 / 自治阶梯 / doc-drift PIN / 自动回滚)从上述 artifact **逐字搬**。

## 3. 量化架构(对象一一对应健康 artifact)

1. **StrategyClaim store** — `data/strategy_kb_seed/rules.jsonl`(claims.jsonl 逐字段类比):
   `{rule_id, version, supersedes, book_citation:{isbn,author,chapter,page,worked_example_ref}, signal_spec:{entry,exit,sizing,filters}(结构化非散文), parameters:[{name,value,search_range,source:'book'|'inferred'}], applies_when:[regime 守卫,同一闭合文法], evidence_tier, rule_boundary:'历史回测非保证;过去≠未来;非投资建议', review_status, leakage_attestation, oos_report_ref}`。`strategy_kb_importer` 只收 reviewed;`lint_strategy_kb` 拒收缺引用/OOS/泄漏证明的规则;`decay_rate` 变成**实时滚动 OOS** 估计(非手填复审日),低于 Sharpe 地板自动归档。
2. **RiskGuardian** — `app/agents/risk_guardian/`(safety_guardian 逐字移植):`@register` + `evaluate_rules_with_status(state)->(breaches, failed_rule_count)` + `make_fail_safe_halt`(failed>0 注入 HIGH "风控评估不全→平仓,别假设安全")。规则:max_position / max_gross_net_exposure / per_instrument_concentration / max_leverage / max_daily_loss / max_order_rate / fat_finger_price_band / correlation_cluster_cap / stale_quote_halt。崩溃的风控规则**平仓**,绝不当"无违规"。加层不减层:风控只 TIGHTEN。
3. **StrategySignals** — `app/agents/strategy_signals/`:每条 reviewed StrategyClaim 编译成纯 `@register` `(MarketTwin,t)->Signal|None`,用书的 worked example 做 golden 测试。
4. **MarketTwin + PortfolioTwin** — `app/twin/`:prices/regime(ADX/已实现+隐含波动)、positions、exposures、open_orders、liquidity(adv_usd)、session、**freshness 分区**(tick 龄/末次成交龄)。**point-in-time builder 只能服务 timestamp ≤ t 的数据(结构性防前视)**。
5. **signal_orchestrator** — `app/orchestrator/`:live tick→快确定性趋势专家 vs 夜间研究→全专家+LLM 评论;LLM 只写 rationale,**永不发 order**。
6. **EffectEstimator→BacktestVerdict** — live PnL=个人 delta,回测分布=群体先验;"这条规则在我的实盘成交上 OOS 有效"须过 CI-excludes-zero,**替换为 deflated Sharpe(惩罚尝试过的试验次数)**——唯一净新统计量;`requires_human_review` 对 regime/前视/过拟合混杂强制 inconclusive。
7. **SlippageModel** — `app/services/slippage/`(**净新,无健康类比**):保守、确定性、可测的交易成本+滑点模块,**每次回测必过**,不可绕(像 `_load_rule_modules`)。

**ASCII 数据流**:
```
交易书(带引用)
   │ S1 LLM 离线抽取 → rules.jsonl{signal_spec, applies_when, parameters, book_citation}
   ▼
[reviewed-gate] ── 未评审 → DEMOTE(永不交易)
   │ 仅 reviewed
   ▼
StrategyClaim store ──(S2 编译)──► StrategySignals @register(书 worked example golden 测试)
   ▲                                      │
   │                                      ▼
MarketTwin/PortfolioTwin(point-in-time, 带时效) ─► signal_orchestrator ─► Signal(LLM 只写 rationale)
   │                                      │
   │                                      ▼
   │                            RiskGuardian.evaluate_rules_with_status ──failed>0──► 平仓(fail-safe halt)
   │                                      │ 无违规
   │                                      ▼
   │                            SlippageModel(不可绕) ──► 确定性执行器 ──► ORDER
   │                                      │                  (LLM 绝不在此 = R4)
   │                                      ▼
   └────────── 实盘成交 ──► EffectEstimator(deflated Sharpe + requires_human_review) ──► edge 崩溃自动降级
```

**范围(诚实切分)**:**趋势/中频系统化策略是真适配**(规则形、regime 依赖、书可派生:Turtle/Donchian、Clenow、Carver 波动目标;effect_estimator 的慢 N≥3 节奏正好匹配数月验证)。**HFT alpha 出局**(edge=延迟/托管/微结构,非可抽取的书规则;R4"LLM 离线、确定性代码后执行"**结构性禁止**微秒级快路径)。**HFT 唯一进来的是确定性盘前风控**(交易所限频/fat-finger 带/max-order-rate/自成交防护)——RiskGuardian 完美适配。

## 4. 确定性 vs LLM 边界(R4 比健康更严一档)

健康里 LLM 可"先说再被 sanitize"(`guidance_validator` 在 LLM 说完后剥离命令式饮食 token)。**交易没有 inline 校验的时间,所以 LLM 完全离线**。

- **LLM 侧(离线、只产规则)**:S1 抽取 `{signal_spec, applies_when, parameters, book_citation}` 为结构化 JSON(假设记录,review_status:draft,evidence_tier:C——**不是代码**);S4 写 rationale/夜间研究评论。**LLM proposes, never disposes。**
- **确定性侧(所有承重)**:编译的 `@register` 信号函数、RiskGuardian 裁决、SlippageModel、下单执行器、point-in-time builder、EffectEstimator 裁决、kill-switch/自动平仓。
- **关键纠正(尊重反类比)**:书派生规则**不是 evidence-tier-B 的 reviewed claim**,而是**比健康最低档还低的未验证假设种子**(书幸存者选择、印出即被套利、真正的耐用 edge=执行/滑点/sizing/微结构不是任何书陈述的"规则")。所以 LLM 产的规则永远拿不到 reviewed CPIC claim 那种信任;它必须靠证伪关卡一路挣上来,而 LLM 的角色相应降级为"廉价假设生成器"——和参数扫描、结构先验**可互换**,这恰恰证明了书从来不是资产。

## 5. 验证阶梯(5 rung,最便宜确定性 kill 在前)

| Rung | 内容 | 健康类比 |
|---|---|---|
| **R1 书 worked-example 单测** | 喂书的成交 bar→断言编译出的规则发出书里那条精确信号;书无 worked example→规则欠定义,退回 S1(四问"数据从哪/写到哪") | test_safety_guardian 正负例 |
| **R2 无泄漏/point-in-time lint(硬 CI,无人工豁免;净新)** | 静态扫禁用模式(`.shift(-n)`、测试窗全序列 `.mean()/.fit()`、回填 fillna、偷看 resample)+ 运行时 canary:未来 bar 全 NaN 时信号若变=泄漏→BLOCK。泄漏是交易版"静默 under-alarm":回测绿、实盘死 | (无,净新) |
| **R3 风控回归** | 每条风控规则带反例测试;加层不减层去重绝不让两条违规路径同时静默(RHR clean[-1] vs twin.resting_hr 教训) | safety 规则对抗测试 |
| **R4 回测回归+walk-forward+参数稳定+deflated Sharpe** | 冻结数据集{data_version hash, seed, slippage 版本}上:位级可复现 / OOS 留出 / walk-forward 滚动重拟合 / 参数 ±N% 扫描须**优雅退化不悬崖**(MA(50) 才行=曲线拟合=拒)/ **deflated Sharpe 惩罚试验次数**;退市纳入宇宙(幸存者守卫);单 CI 不够,**强制 family-wise 校正** | effect_estimator CI-excludes-zero,硬化 |
| **R5 纸面 soak→canary-live→放量** | 回测"有效"非实盘裁决;纸面 N 场看实盘成交 vs 模型滑点、纸面 PnL vs 回测预测在容差内、零风控违规、延迟达标;**重跑回测不是新证据,只有未见的前向 bar 是**;canary 微额(1-5%)人工批首笔实盘;放量逐 tranche 上阶梯,绝不 0→满;live 后验持续过 deflated-Sharpe 地板否则自动降级 | staging + InterventionCycle 前瞻确认 |

**贯穿的反过拟合守卫**:在受控变量上取不同值让回归的泄漏/过拟合 bug 真变红(幂等测试教训);跨家族对抗 capstone(第二模型在晋级前专挑前视/过拟合/相关书风险,像 Codex capstone);**回测/测试闸绝不 `| tail`**(tail 永远 exit 0,带红上线)。

## 6. 完整 SDLC + 量化专属闸 + deploy/kill-switch + 团队

**双环 6-Gate(product-pipeline-contract,Dossier 作可恢复脊柱)**:
- DEFINE 环(便宜、可逆、纯文档):S0 四问(谁的 edge?哪些 regime/品种**不做**——HFT alpha 明确出局;最小路径先 grep 复用;风险)+ 强制 ASCII 数据流 → **G1 准入**(≥1 一等对象?命中交易核心环?新策略默认 paper_only 永不 live?)→ S2 PRD(策略论 + 哪本书 by claim id)→ S3 Plan(Sharpe/maxDD 验收带 + 反馈环路由)→ **G2 可行性+对抗压测**(我们的延迟/成本能执行吗?别承诺托管打不到的 HFT edge;R4/资金上限/NEVER-graduating 合规焊死;**跨家族**第二模型攻击论点找前视/过拟合)。
- DELIVER 环(贵、严闸):S4 分解(信号 schema↔sizing↔执行器跨层契约=OpenAPI 类型生成类比防漂移)→ S5 实现(**从干净 origin/main worktree 切分支**;`quant-rule-factory` 写确定性代码)→ **G3 = R1-R4**(替代 pytest+doc-drift 的五闸)→ **G4 = risk-reviewer 强制评审**(任何碰 sizing/杠杆/新品种/路由的)→ **G5 = LIVE PROMOTE**(deploy+kill-switch+自动平仓+canary;人工批首笔实盘资金)→ **G6 = 上线验证**(live health-score 看 R5 canary)。

**量化专属 CI/CD 闸(ci.yml 类比,每 PR、全硬、绝不 `| tail`)**:① 策略单测+风控回归对抗例;② 无泄漏/point-in-time lint(硬,无豁免);③ 冻结数据回测回归+位级可复现;④ `check_strategy_drift.py`(check_doc_drift 双胞胎)PIN 住 `baselines.json` Sharpe/maxDD+注册风控规则数,漂移→红、同 PR 修 baseline;⑤ determinism lint:禁信号路径裸用 wall-clock/RNG。

**deploy/kill-switch/rollback(deploy.sh 形状)**:`save_rollback_point()` 快照先前 live 配置+持仓;promote canary tranche;`strategy_health_score.py --json`(live-Sharpe-vs-回测背离/已实现-vs-模型滑点/滚动回撤/成交率/拒单率/延迟,加权同 system_health_score 桶)低于阈值→**自动平仓**(确定性代码平,LLM 绝不发平仓单=R4);手动 kill-switch=人拉**同一条确定性平仓例程**(单一真源)。**只从干净 origin/main worktree 晋级**(mobile-OTA 教训)。可观测=回测预期权益锥,live PnL 逃出锥→throttle→平仓。

**团队(.claude/agents 一一移植,均 opus,`quant-harness-orchestrator` 编排)**:strategy-engineer(=backend-engineer)、backtest-verifier(=qa-verifier,真红假红/跨层 shape 比对)、risk-reviewer(=safety-privacy-reviewer,**碰风控/下单路径强制**,每个吞异常点=P0 静默裸仓)、execution-release(=release-engineer,纸面 soak+canary+kill-switch,从干净 main,先基建后策略)。**长回测/soak 异步不串行阻塞;先查 main+开着的 PR;最便宜确定性闸在贵 soak 前。**

## 7. 仓库集成:~70% 复用 / ~30% 净新(净新即护城河)

**逐字复用(搬模式非内容)**:reviewed-gate(`_is_reviewed_payload`+降级)→strategy_kb_importer;闭合 `applies_when` 文法(六正则+`is_supported_condition`)→MarketTwin regime 守卫(`twin.regime.trend_strength >= 25` ↔ `twin.genetics.9p21 in [...]`);fail-safe 注入(`evaluate_rules_with_status`+`make_fail_safe_advisory`)→RiskGuardian halt;裁决抑制(`is_clinician_gated_metric` 强制 is_effective=False)→`requires_human_review`;自治阶梯(`NEVER_AUTONOMY_KINDS`+双门)→"发实盘单"永不毕业;doc-drift PIN→`check_strategy_drift.py`;deploy 自动回滚→canary+自动平仓;6-Gate 双环+Dossier+四问+agent 拓扑。

**净新(无健康类比,且这才是护城河)**:① point-in-time 数据 builder(物理上不能服务未来 bar);② 无泄漏静态+运行时 lint;③ **deflated Sharpe/多重检验校正**(仓库编码了**纪律**——0/12 空+RCV 噪声带+washout fail-closed——但验证裁定明确:代码里**没有**Bonferroni/FDR/deflated-Sharpe/PBO 统计量,这是净新);④ SlippageModel(回测"盈利"是虚构的 #1 原因);⑤ 仓位/风险 sizing 作首要生存机制(Kelly/波动目标/仓位上限,**被证错时的生存才是真护城河**);⑥ live decay(`decay_rate`/`last_confirmed` 字段在但语义错=引用新鲜度,须变成持续重算的滚动 OOS+Sharpe 地板自动归档);⑦ 合规边界戳+人工合规闸+免费数据源进评审门隔离(免费数据=交易版未评审 KB claim)。

## 8. 诚实风险 + 重定义 + HFT 边界 + 监管

- **反类比**(见 §0):必须明说否则项目自欺。
- **重定义成功**:不是挖书 alpha,是**证伪工厂+风控治理**;书派生规则是假设种子,喂同一工厂廉价自产假设(参数扫描/结构先验)几乎无损——证明书从不是资产。
- **存在性守卫(健康里 nice-to-have,这里承重)**:多重检验校正/deflated Sharpe 卡 live 晋级;regime 条件化 `applies_when`(书策略最常见的爆法是 regime-blind 开火);强制 OOS+前向纸面 soak;不可绕保守滑点;sizing 作真护城河(生存>信号);确定性、快、不可覆盖 kill-switch;**到处 fail-loud——下单/sizing 路径每个 `except: pass` 都是 P0**(静默裸仓=无界亏损,不止 under-alarm)。
- **HFT 范围诚实**:砍掉 HFT alpha 并明说——其 edge 是延迟/托管/队列位/微结构,无一是可抽取书规则,且 R4"LLM 离线、确定性代码后执行"**结构性禁止**微秒快路径(范式自身不变量禁止 HFT 需要的东西)。趋势/中频才是真适配。HFT 唯一属于这里的是确定性盘前风控。**假装 book→rule 管线产 HFT alpha 是最大自欺风险。**
- **监管(净新、同等严重度无健康类比)**:算法交易有审计轨迹义务(agent-audit 模式可迁)、市场操纵/spoofing 禁令、注册阈值。每条晋级策略带合规边界戳("backtest only, not investment advice" ↔ "guidance only, not diagnosis");live 部署需人工合规闸(G2/G6 human STOP);**交易所 API key=本域的基因/化验数据**——静态加密、仅生产、永不入库、**只交易权限(关提现)**、每账户交易授权门(PIPL 同意类比)后才下单。
- **复杂度预算**:别投机建空假设先验通道(0/12 空通道刻意没建的 YAGNI 教训);删>加;第一刀是一条线程不是平台。

## 9. 分期 MVP + 第一刀

| Phase | 范围 | 交付 |
|---|---|---|
| **P0 脊柱+首条 reviewed 规则** | rules.jsonl+strategy_kb_importer(reviewed-gate 逐字移植);MarketTwin schema+point-in-time builder;一条 StrategyClaim(Donchian 55/20 突破,带 book_citation+worked_example_ref+regime 守卫)。无执行无 LLM | 注册表里一条 reviewed StrategyClaim + 物理不能服务未来 bar 的 MarketTwin;`check_strategy_drift.py` CI PIN 计数 |
| **P1 确定性引擎+RiskGuardian+golden** | StrategyClaim 编译成 `@register` 信号;书 worked example golden 测(R1);移植 RiskGuardian(3 条种子:max_position/max_daily_loss/stale_quote_halt)+对抗测(R3);无泄漏 lint(R2)硬 CI | KB-blind 确定性信号+风控引擎,fail-closed/fail-loud,R1-R3 CI 全绿 |
| **P2 回测关卡+裁决门** | SlippageModel(不可绕)+冻结数据回测回归(位级可复现)+walk-forward+参数稳定+**deflated Sharpe**(R4);EffectEstimator 移植 requires_live_confirmation 抑制;退市纳入宇宙 | 证伪工厂拒掉假赢家:证 Donchian 过 OOS deflated-Sharpe,**或被诚实拒绝(两种都算成功)** |
| **P3 纸面 soak→canary→kill-switch** | 纸面 soak(R5a);deploy 类比 save_rollback_point+canary tranche+低于 strategy_health_score 自动平仓+手动 kill-switch(单一确定性平仓例程);人工合规闸+加密只交易 key;LLM 只离线接入,绝不在下单路径 | 一条策略跑微额 canary,带确定性不可覆盖回撤 kill-switch + live-PnL-vs-回测锥告警;首笔实盘资金人工批 |

**第一刀(一条端到端线程)**:**Turtle 的 Donchian 55 进/20 出通道突破**(有显式 worked example、明确 regime 守卫=仅流动期货、几十年 OOS 历史)。线程:S1 LLM 离线抽成一行 rules.jsonl → 引用+owner 评审门(人确认书里真有→reviewed,否则降级不前进)→ S2 编译 `@register` → R1 golden(书 bar 上精确进出)→ R2 无泄漏 lint+NaN-future canary → R4 冻结退市纳入宇宙过 SlippageModel + deflated Sharpe + walk-forward + 参数稳定 → **定义完成 = EffectEstimator 输出"tier-A:OOS deflated-Sharpe CI 排除零、参数稳定"(晋级纸面)或"inconclusive/拒绝"——两种都是成功的第一刀,因为交付物是证伪机器在工作,不是规则盈利**。

> 全程不碰实盘资金、下单路径无 LLM(R4 第一天就成立),且把每个复用 exemplar(reviewed-gate/闭合文法/`@register` fail-closed 引擎/point-in-time Twin/裁决门)+净新面(point-in-time builder/无泄漏 lint/滑点模型/deflated Sharpe)都在一条线程上跑通。一条规则、一条引擎路径、一道门,无投机平台。
