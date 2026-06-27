# Reva 竞品对标 + PRD/长期目标批判

> Status: research report
> Updated: 2026-06-27
> Owner: Reva / Personal Health OS
> 方法：GitHub + 网络检索 7 类同行（OSS 聚合器 / OSS 框架 / 合规基座 / SMART-on-FHIR / 商业产品 / 行为改变循证），对每个产品做结构化深读，再用一个对抗式 red-team agent 拿市场证据反推 Reva 的 PRD 与长期目标。
> 关联：[code-verified AS-IS PRD](../prd/2026-06-27-code-verified-asis-prd-and-10m-roadmap.md) · [愿景版 PRD](../prd/2026-06-27-code-derived-product-prd-and-10m-goal.md) · [Enter 键战略论纲](../prd/2026-06-16-enter-key-leverage-thesis.md)

> ⚠️ **重要核对声明**：本报告的研究输入读的是**当前工作分支**（`design/code-design-loop-scaffold`，落后 origin/main **44 commit**）。所有"代码现状/活 bug"类结论已**逐条对 `origin/main` 复核**（见 §6 校验表）。**两条已证伪并已在文中校正**：(1) Write 自治**已上线且默认开**（`services/write_autonomy.py`），不是"尚缺"；(2) 安全 fail-loud 已接到 medication/regimen/write_autonomy 多个面，不是"只接 watch"。**战略结论与分支无关，照常成立。**

---

## 0. 一句话结论

市场证据**同时验证了 Reva 的战略方向、又暴露了它的执行赌注**：

- ✅ **方向对**：所有规模化赢家（Whoop/Oura $10-11B、Function/Levels/Thrive）**全部停在"感知 + 推荐卡片"，把执行 100% 甩给用户意志力**。Reva 押的"验证 + 写入（Enter 键）"是**整个市场的无人区**——而且 Reva 已经上线了第一刀自治写（默认开），真在占这块高地。
- ⚠️ **赌注险**：Reva 的全部价值锁在**季度级外环**(per-user 因果收敛)，而它依赖的**每日 JITAI 前门 ~1 个月就习惯化失效**(HeartSteps 实证)。前门在后端账本复利成形之前就把用户churn掉。Reva **没有一个能与 Oura/Whoop"每早一个分数"抗衡的每日仪式**。
- 🔪 **最锋利的反方**：Reva 可能在为一个**学界已知、商业未validated、慢复利**的 N-of-1 账本过度投入，服务一个**最窄、最高摩擦、最难触达**的人群；而它两个**真正不可复制的资产**（62 条确定性安全脑 + 大平台因责任规避绝不敢碰的 trust-custody 立场）正被 158 router / 4 聊天入口 / 单锚点用户过拟合**埋没**。

---

## 1. Top 3 产品（最值得抄的对象）

从 ~10 个候选里，按"对 Reva 当前缺口的教学价值"选 Top 3：

### 🥇 #1 — Whoop / Oura（每日分数留存机制）

- **量级**：Whoop ~$1.1B 年化 bookings（+103% YoY）、2.5M+ 会员；Oura ~$11B 估值、**88% 年留存**；Whoop **83% DAU、18 个月后仍 50%+ 每日用**——对比健身 App 普遍 20-37% 30天churn。
- **它们解决了 Reva PRD 完全没答案的问题：消费健康的可持续留存**，而且是在 Reva **结构上最弱的轴**（每日可感价值 vs 季度结果）上解决的。
- **最大一课**：把 Reva 的 timeline-spine + "每日一个行动"收敛成**一个不可错过的复合每日工件**（一个 readiness / today-action 数字），并像 Oura Tags→Discoveries 那样让 N-of-1 实验**情绪可感**——"你试了 X，你的指标动了"。**用户感觉不到的、技术更深的因果账本，是一条用户不会付费的护城河。**

### 🥈 #2 — OpenHealth（3,907★ 的 AI 健康助手，直接竞品）

- **量级**：3,907★ / 418 fork，12 个月达成；做的远比 Reva 少（OCR 解析化验 → 结构化 → 多 LLM 聊天，Ollama 本地）。**无安全引擎、无 orchestrator、无 Twin、无每日行动环、无结果验证**；它的"specialists"只是存起来的 system prompt。
- **它是"分发靠可运行的工件、不靠智能"的最干净证明**：以 Reva 一个零头的临床深度，公开 traction 碾压 Reva 3900:0。它自己的 RFC #105 正是想补 Reva 早已 ship 的 validated-data-engine 层。
- **最大一课**：把 Reva 的深度藏到一个 **5 分钟 on-ramp** 后面——一条命令 + 合成数据，**60 秒内演示安全引擎抓住一个真实 DDI/相互作用**；首页大声打"隐私优先（本地/Ollama 选项 + 加密）+ 安全引擎"。**看不见的深度=不存在的深度。**

### 🥉 #3 — Medplum（FHIR 原生合规基座）

- **量级**：2,473★、Apache-2.0、SOC 2 Type II、HIPAA。FHIR 数据仓 + auth/RBAC + 多租户 + 审计 + bots 自动化。
- **它是 Reva 上多租户前必须先落地的"无聊但承重"基础设施的参考架构**：把**访问控制 + 审计 + 租户 + 短 token** 做成**单一 default-deny 数据层 chokepoint 的结构不变量**——正是 Reva opt-in 脆弱性的反面（RLS 仅 2 表、JWT 2 年、L3 PII 明文、审计只在安全决策不在 PII 读）。
- **最大一课**：把访问控制/审计/租户/短 token 收进**一个所有读写都过的 chokepoint**（Reva 的 Twin-builder/service 层可成为它），让第 N 张敏感表"默认合规"而不是"忘了加"；**现在就杀掉 2 年不可撤销 JWT**（Medplum 默认 1h access + 2 周 refresh）。

> **荣誉提名（各有一招专长）**：**open-wearables**（1,998★）= 直接抄它的 `SeriesType` 信号契约；**Spezi**（Stanford）= 抄它的 onboarding/consent + Standard/Constraint 架构纪律；**health-skillz / Fasten**（SMART-on-FHIR）= 抄它的**临床叙事病历管线**（对中国出院小结/门诊病历 PDF 今天就能用）。

---

## 2. 全景对标表

| 产品 | 量级 | 是什么 | Reva 领先 | Reva 落后 / 该抄 |
|---|---|---|---|---|
| **OpenHealth** | 3,907★ | OCR 化验→结构化→多 LLM 聊天（本地可跑） | 安全引擎、Twin、13 专家、每日环、N-of-1、审计——全面碾压深度 | **5 分钟 on-ramp + 隐私首页 + 顶级文档解析**；分发完败 |
| **open-wearables** | 1,998★ | 11 家穿戴归一成统一时序+事件 schema + MCP | 数据层之上全部（无推理/安全/Twin；"AI"是 vaporware） | **`SeriesType` 契约**（~80 指标、稳定不复用整数 ID、规范单位、per-metric SUM/AVG/MAX）+ **每行 data_source provenance** + Strategy/Factory/declarative-Coverage 适配器（解 Reva 的 `NotImplementedError` 适配器）|
| **Spezi** (Stanford) | ~254-290★/模块 | 模块化 Swift 数字健康框架（~40 包） | 临床安全 + 推理，且不接近（SpeziLLM 零 safety/guardrail 引用）| **onboarding/consent 管线**（Reva 完全没有）+ Standard/Constraint 接缝（解 158-router/god-file 散乱）+ **canonical schema/FHIR Standard 层** |
| **Medplum** | 2,473★ | FHIR 原生合规开发平台（SOC2/HIPAA）| 临床智能层（Medplum 故意不做）| **单 chokepoint 访问控制 + 审计 + 多租户 + 短 token**；合规基座完败 |
| **Fasten / health-skillz** | ~2,767★ | SMART-on-FHIR 患者授权拉结构化 FHIR + 临床叙事 | 中国场景 OCR/可穿戴 intake（美国 FHIR 在中国不可用）| **临床叙事病历管线**（index→关键词搜→全文读相关）+ FHIR 资源类型作 canonical schema（解 biomarker conflation）|
| **Whoop / Oura** | $10-11B / 83-88% 留存 | 每日 recovery/readiness 环 | **Write/Enter-key 层**（它们 100% 停在推荐卡片）| **单一每日分数仪式** + 实验 Tags→Discoveries 可视化 + **发表 efficacy 研究**（信任护城河）|
| **Levels / Function / Superpower** | Function $2.5B 估值 | CGM 代谢 / labs-first 纵向 100+ 生物标志物 | 闭环验证作护城河（它们只给关联+免责声明）| labs-first 纵向叙事 + 商业/定价模型（Function 正起诉 Superpower 灌水生物标志物数=市场在打"数据冒充洞察"这一仗）|
| **Thrive AI Health** | OpenAI + Huffington | 纯 AI 健康教练 | 数据飞轮 + 写入 + 安全（Thrive 无 write、无飞轮）| 提示"纯 AI 教练"的**薄产品风险**——验证 Reva 的飞轮路线但也警示别只做教练 |

---

## 3. PRD 的问题（market-grounded，按严重度）

| 严重 | 问题 | 市场证据 |
|---|---|---|
| 🔴 高 | **没有每日可感价值原语**。权威北极星是"L3 精力 30 日均线 + L4 生化 3-6 月改善"——结果落在 30-180 天外，而留存是靠"每早一个分数制造晨开仪式"赢的 | Oura 88% / Whoop 83% 留存全靠"每早一个复合数字"；行为改变文献：engagement 与 D30 留存"相关性极小"，只 track 不闭环的 App 30 天内churn |
| 🔴 高 | **目标用户是最难触达段，且 PRD 没画出能到 1M 的漏斗**。35-55 慢病早期数据素养男性需要 CGM+穿戴+化验+12 周坚持——最高摩擦、最高数据门槛、最小人群 | 高端市场二分为 performance(Whoop/Oura) 与富裕 biohacker(Function/Levels)；慢病中年男"无人服务"恰因它窄/高摩擦/高信任；中国 ≥3000 万 TAM 无任何转化率validated |
| 🔴 高 | **复杂度 vs 采用倒挂**。Reva 的差异化深度（62 规则/13 专家/16 分区 Twin/因果账本）首次接触**不可见、不可跑**，而 3900★ 聚合器靠"docker up→传 PDF→聊"赢分发；Reva 背 158 router/948 端点/4 聊天入口/6+ 每日计划面/2 Twin 的 accretion 债，买不来一个用户 | OpenHealth traction 来自 legibility+trivial on-ramp 不是深度；星标量premise-interest不等于留存，但教训成立：60 秒体验不到=深度白搭 |
| 🔴 高 | **PRD 对 JITAI 习惯化零答案**——这是"每天一个行动"产品最被记录的失败模式。静态每日行动必然衰减；无 capped-count、无 dynamic availability、无 RL 个性化调度，"行动接受率随周"不是被追踪指标 | HeartSteps 微随机试验：情境化建议的近端效应"~1 月后基本消失"，用户称"2-4 周后变无聊"；文献的解法是 RL 个性化**投递**(Oralytics)，不是更好的内容 |
| 🔴 高 | **causal_memory 过度归因**（`_MIN_PCT=0.05` 平 5% 前后窗均值、无控制、无显著性、无混杂处理）从回归均值里制造"X 改善了 Y"，且已展示给用户 | N-of-1 文献把时变混杂+洗脱不足列为对消费级 personal-science 的#1 学术攻击；Function 正起诉 Superpower——市场在打的正是这种"数据冒充洞察"。**已对 origin/main 复核：仍 live**（见 §6）|
| 🟠 中 | **FHIR 过度声称 + 错读**。PRD 把 SMART-on-FHIR 列"优先标准"，代码只有裸 allow-list 串 `fhir_bundle`（无 parser/OAuth）；而真正的标准化 intake 在美国已被法律商品化(任何 App 一个 OAuth 拉数千家)，在中国不存在 | Fasten/health-skillz 证明美国 FHIR 是 table-stakes 非护城河；中国无患者授权端点→Reva 的 OCR/叙事 intake **才是**护城河——PRD 把这点搞反了 |

---

## 4. 长期目标的问题

| 严重 | 问题 | 证据 |
|---|---|---|
| 🔴 高 | **"数据积累→CI 收敛"不是持久网络效应**。per-user 因果估计边际递减——一旦个体效应被识别，第 N 个数据点加噪声不加信号。可防御的是 trust+迁移成本，不是账本体量 | a16z《数据护城河的空洞承诺》：多数所谓数据网络效应只是 scale effect（增量数据成本↑价值↓）；唯一持久机制是"负责任数据托管赢得信任去接更敏感数据"——Reva 的基因/化验/CGM 托管+per-user 红线**正是**这个 trust 面，但论纲把"数据积累"当护城河，证据恰恰否定它 |
| 🔴 高 | **per-user N-of-1 学界已知、消费级商业未validated**——"散点式用了 40 年但未被广泛采用"。门槛(改善结局的证据薄、时变混杂、洗脱纪律、交叉依从)正是 Reva 还没解的 | 现存所有 N-of-1"产品"都是研究平台(StudyU/StudyMe/N1)，非商业爆款；incumbents 故意只 ship 关联洞察。**开放是因为难，不是因为没人想到** |
| 🔴 高 | **结构性慢（季度一圈外环）vs JITAI 前门 ~1 月习惯化**——时序错配可能致命：前门在后端账本复利够"被感觉到"之前就churn用户，护城河永远拿不到成熟的 runway | HeartSteps ~1 月效应消失；外环=一季度；付费转化需要 week 1-2 信号(incumbents 留存是每日)，而证明落在 30-180 天外 |
| 🔴 高 | **单锚点用户(创始人 N≈1，真实问题是反流非代谢)从根上动摇 10M 与护城河**：per-user 账本只在系统能跨用户泛化时可防御，但过拟合一个人的生理会在 ICP 变体上静默失败，且无法为任何别人 bootstrap per-user 先验。"时间×这个用户"按构造不可迁移→每个新用户从零起，系统从未在创始人之外validated | RL/JITAI 冷启动文献：个性化可靠前需数周-数月 per-user 数据，建议**跨用户迁移/pooling 冷启动**；而单租户/全局硬编码源仲裁/RLS-2-表系统做不到 |
| 🟠 中 | **Write 自治被季度 CI 封顶→按论纲自身逻辑"大多数动作永停在一键提议"**，所以公司押注的差异化按设计是渐近极小的——少数几个可逆低风险自治动作。护城河也许真但商业上薄 | 全部被调研产品停在推荐卡片(验证缺口)；但 Thrive(纯教练无写无飞轮)展示薄产品风险；论纲"安全带=自治速度上限"意味自治面保持小。**注：Write 自治第一刀已上线默认开（§6 校正），所以"高地无人占"已不成立——Reva 已在占** |

---

## 5. Reva 真正对的地方（含 origin/main 校正）

- ✅ **"感知+推荐是看板天花板，验证+写入是无人高地"——被整个市场实证**：Whoop/Oura/Levels/Function/Thrive/Ultrahuman 全停在推荐卡片把执行甩给意志力。**整个高端市场挤在"感知+推荐"本身就是"验证+写入"开放的证明**。
- ✅ **62 条确定性 Safety Guardian（DDI/DSI/PGx/急性阈值/个性化红线，KB-blind，fail-closed）是真不可复制的资产**：open-wearables、Spezi(SpeziLLM 零 safety 引用)、Medplum、OpenHealth、所有高端商业玩家**全都没有临床安全层**。这是 Reva **唯一对每个被调研产品都结构性领先**的地方。
- ✅ **【origin/main 校正】Write 自治第一刀已上线且默认开**（`services/write_autonomy.py`：双门 `kind∈runtime_allowlist ∧ ∉NEVER_AUTONOMY_KINDS`、原子 cap 槽、per-user graduation 接入点、后台 worker）。论纲称"唯一真缺=Write 自治层"——**它已经开始占这块高地**，不是还在画饼。这强化了"方向对"。
- ✅ **结果优于参与作增长指标（验证闭环轮次，非用户数）**——市场(Whoop/Oura 靠留存不靠数量值十亿)与学界(参与与临床结局实证脱钩)双重支持。Reva 在测对的东西。
- ✅ **闭合 within-person 复测环是真开放空间**：incumbents(Oura Discoveries/Levels)只给关联并免责，没人跑结构化外环(复测→CI 收敛)到硬终点。Reva 代码里已有统计原语(intervention_significance RCV 门、intervention_cycle、R16 clinician gate)。
- ✅ **R4 克制(defer 医生、不自治剂量/诊断、"筛查非诊断")是大平台因责任规避结构上学不来的差异化**，且兼作 a16z 认定的唯一持久数据护城河=trust/custodianship 面。
- ✅ **软件优先、骑在现有设备之上是对的反转**(更低 CAC、无硬件风险)——Reva 可成为"在 Oura/Garmin/Apple 数据上行动的 agent"，而非再卖一块表。

---

## 6. origin/main 代码核验表

> 遵循记忆 [`feedback_code_derived_review_against_origin_main`]：code-reality 结论落笔前必对 `origin/main` 复核（本分支落后 44 commit）。

| 红队/审计的代码声称 | origin/main 复核 | 落笔采纳 |
|---|---|---|
| causal_memory 平 5% 过度归因(无显著性/控制) | ✅ **仍 live**（`causal_memory.py` `_MIN_PCT=0.05`，`abs(pct)<阈值`才跳过）| 采纳为 P0 真缺陷，已 spawn 修复任务 |
| CGM Libre/Dexcom `NotImplementedError` | ✅ **仍 live**（`cgm/adapters.py:92,117`）| 采纳 |
| 源仲裁全局单租户 + Garmin SpO2 硬排除 + `TODO(多租户)` | ✅ **仍 live**（`device_source_priority.py:46`）| 采纳 |
| RLS 仅 2 表 | ✅ **仍 live**（仅 `genetic_raw_files` 一个迁移，2 处 ENABLE）| 采纳 |
| JWT access token TTL = 2 年 | ✅ **仍 live**（`services/auth.py:19` `60*24*365*2 # 2年`）| 采纳，Medplum 一课直接命中 |
| ~~安全 fail-loud 只接 watch.py:337~~ | ❌ **已证伪**：`evaluate_rules_with_status` 已接 `medication.py:442` / `medication_regimen_service.py` / `write_autonomy.py:234` / `watch.py:337`——**高风险写/用药路径已 fail-loud**；只剩 `guardian.py:31` 主入口(报告面/orchestrator 用)仍 lossy | **校正**：gap 更窄(报告面 under-alarm，低于写路径)，降级；已开始的修复任务应改瞄 `guardian.py:31` 非"只 watch" |
| ~~Write 自治 trust_tier 硬钉 manual_confirm / 不存在~~ | ❌ **已证伪**：`services/write_autonomy.py` **live 默认开**，双门+cap+per-user graduation+bg worker | **校正**：高地已开始占，强化"方向对" |

---

## 7. 该立即吸收的（ranked，区分战略 vs 代码修）

**战略层（决定生死）**
1. **落地一个不可错过的每日工件**（单一复合 today 数字/行动）作首页仪式，并把"行动接受率随周"列为一等指标——Whoop/Oura 留存原语 + JITAI 习惯化早警，今天都缺。
2. **对抗习惯化从 day 1 设计**：capped 行动数 + dynamic availability + 个性化投递(RL-lite/情境)，别只优化内容。
3. **把季度复测环当产品而非功能**：复测召回真推到腕上(论纲 P0 完全正确)，让外环转起来——否则护城河永不成熟。
4. **故意招募 5-10 个与创始人不同的用户**(过敏性非反流鼻炎/HP+ 溃疡/女性/非伏诺拉生)作 Phase-1 BLOCKER：拿纯过敏 twin 跑 RhinitisSpecialist，若仍提反流假说=系统过拟合。**不可迁移的护城河无法 bootstrap 用户 #2。**
5. **重定位护城河叙事**：别喊"数据积累"(a16z 否定)，喊**trust-custodianship + 不可复制的确定性安全脑**——这才是持久的，且 5 分钟可演示。

**代码层（已对 origin/main 核验）**
6. **修 causal_memory 过度归因**（加显著性/重复 floor + 匹配基线控制 + 回归均值收缩；1日vs1日纯噪声 kill-test）——信任论纲的承重诚实。*[已 spawn task_187003e7]*
7. **抄 open-wearables 的 `SeriesType` 契约** + 每行 data_source provenance + Strategy/Factory/Coverage 适配器——填"无统一 AI-ready 信号契约"缺口，把"CGM 未实现"从 runtime `NotImplementedError` 变成 declared matrix-cell，并用编码系统解 biomarker conflation。
8. **建临床叙事病历管线**(抄 health-skillz：index→关键词搜→全文读相关)作新 `ClinicalRecordLibrarian` specialist——对中国出院小结/门诊病历 PDF **今天就能用**，捕获结构化数字抓不到的医生推理信号。
9. **访问控制/审计/租户收进单 chokepoint**(抄 Medplum)，现在(数据集还小)就给每行 PHI 打 tenant/owner scope，**杀掉 2 年 JWT**(改 1h access + 轮换 refresh + 服务端撤销)，L3/L4 PII 用独立 KMS key 字段加密。
10. **抄 Spezi 的 append-only Task→Event→Outcome 调度** + Standard/Constraint 接缝：schedule 编辑绝不能重写过去依从(N-of-1 账本依赖的 provenance 保证)；每个 collector/specialist 只经窄类型契约碰共享状态(解 god-file + 158-router 散乱)。
11. **窄修 fail-loud**：把 `guardian.py:31` 主入口(报告面/orchestrator)也走 `evaluate_rules_with_status` + 崩规则注 HIGH fail-safe advisory。*(注：写/用药路径 origin/main 已 fail-loud，gap 比原判更窄)*

---

## 8. 最强反方观点（contrarian）

> **Reva 可能在精雕一个市场已用别的答案回答过的问题。** 押"验证+写入 > 感知+推荐"，但最强证据反向切：规模赢家(Whoop/Oura $11B/$10B、83-88% 留存)赢在 Reva 结构上学不来的**每日仪式**，因为 Reva 的全部价值锁在**季度外环**而它的 JITAI 前门 ~1 月习惯化(HeartSteps："2-4 周后变无聊")。前门在后端账本复利前churn用户；而公司同名的护城河——per-user 数据积累→CI 收敛——恰是 a16z 说**不持久**的 scale effect(识别后递减为噪声)，N-of-1 又"散点 40 年未被采用"(混杂/洗脱/依从/结局证据薄，而 Reva 的 causal_memory 正违反这些)。同时证据支持的**真护城河**——trust/custodianship + 不可复制的确定性安全脑——正被 158 router/4 聊天入口/2 Twin/单锚点过拟合**埋没**。
>
> **一句话风险**：Reva 在为一个**窄高摩擦人群**过度建一个**学术优雅、商业未validated、慢复利**的因果账本，而同一个团队两个**真不可复制的资产**(62 规则安全脑 + 大平台不敢碰的 trust 立场)本可以藏在 OpenHealth 级 5 分钟 on-ramp 后面、作为"在**你的**数据上的安全 + 诚实归因第二意见"产品——用户 week 1 就能感觉到、就能付费。**若 Function/Oura/Thrive 在 Reva 证明其环之前，给它们已有的分发栓上一个可信的安全+写入层，Reva 的结构性领先就变成功能差距。**

---

## 9. 我的综合判断

1. **战略骨架是对的，且 Reva 已经在执行而非画饼**（Write 自治第一刀上线、安全脑、N-of-1 原语都在 origin/main）。这点比红队的工作树视角更乐观。
2. **但 PRD 缺一个"前门"**：所有批判收敛到同一处——**季度护城河需要一个每日仪式来买时间**。这不是放弃 Enter-键论纲，是给它装一个能让用户活到外环成熟的前门(单一每日工件 + 抗习惯化投递)。**这是 §7 第 1-3 条，应是下一刀。**
3. **护城河叙事要换**：从"数据量"换到"trust-custodianship + 确定性安全脑"——前者 a16z 否定、后者市场无人能抄。
4. **单锚点过拟合是 10M 的隐形天花板**：招异质用户validate 应是 Phase-1 硬门，不是 Phase-3 任务。
5. **代码诚实债优先级最高的是 causal_memory**：它是整个信任论纲的承重墙，且 origin/main 仍 live——已 spawn 修复。

> 最值得记的一句：**OpenHealth 用 Reva 一个零头的深度赢了 3900:0 的分发，证明"看不见的深度=不存在的深度"。Reva 的胜负不在再加一个专家，而在让已有的安全脑与诚实归因在 60 秒内被感觉到。**

---

## 附：研究来源

GitHub: OpenHealthForAll/open-health · the-momentum/open-wearables · StanfordSpezi/Spezi(+SpeziLLM/Scheduler/FHIR/Onboarding) · medplum/medplum · fastenhealth/fasten-onprem · jmandel/health-skillz。
商业/循证: Whoop/Oura/Levels/Function/Superpower/Ultrahuman/Thrive AI Health 公开资料；HeartSteps/Oralytics 微随机试验(Klasnja/Murphy)；a16z《数据护城河的空洞承诺》；N-of-1/单受试试验文献(StudyU/StudyMe)。
