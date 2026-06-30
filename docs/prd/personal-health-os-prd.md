# 个人健康操作系统 — 产品重构 PRD

> 状态:**v0.1 草案 · 待批准**(分支 `design/personal-health-os`)
> 作者:Claude(基于 GPT Pro 战略建议 + 对当前代码的实地核查)
> 范围:本文件只做**探索 / 设计 / 规划**。批准前不写产品代码。

---

## 0. 一句话结论

> **决策引擎已经基本建成;产品还不是"健康结果系统",是因为缺三块基石:① 可验证的干预闭环(快照→周期→复查 delta)② 让建议可审计、可安全的标准化数据底座(biomarker + 数据质量)③ 面向融资的产品收敛与安全合规硬化。**
>
> 所以下一步**不是继续造管线、也不是从零搭多 Agent**,而是:**收敛切口 + 补齐验证闭环 + 标准化数据底座 + 安全合规硬化 + UI 收敛到核心闭环。**

---

## 1. 背景:GPT Pro 建议 ⊕ 代码实况(对账)

GPT Pro 的战略方向(Personal Health OS / Digital Health Twin / 主动干预闭环)**完全正确**。但它读的是**旧的/公开快照**(它引用的 `ARCHITECTURE.md` 还写 SQLite / GPT-4o-mini / 单 Garmin 源,并把 social/PK/儿童模式 当成现存功能)。实地核查后,**本仓库比它以为的领先很多**,很多"该建"的东西**已经建了**。

### 1.1 GPT Pro 以为要建、其实已存在

| GPT Pro 建议 | 代码实况 | 文件 |
|---|---|---|
| HealthIssue 强 schema 输出 | `SpecialistFinding` + `ProposedCard` 已是结构化 schema | `orchestrator/schema.py` |
| 确定性 Risk Engine(分层而非告警) | `chronic_risk_service.py`:Framingham 10 年 CVD + IDF 代谢综合征分层 | `services/chronic_risk_service.py` |
| PlanComposer / 跨专家仲裁 | 确定性冲突检测 + LLM 仲裁 + 单次合成 | `orchestrator/cross_review.py`、`arbitration.py`、`orchestrator.py` |
| 评估体系(golden/safety/judge) | `backend/eval/`:datasets(safety/recovery/health_advice/insight/orchestrator)+ llm_judge + grounding + baselines | `backend/eval/` |
| 多专家 Agent | Orchestrator + **11 specialists**,各输出结构化 finding;Safety Guardian **51 条确定性规则** | `orchestrator/`、`agents/` |
| Biomarker 归一化 | `exam_packages.py` 150+ 别名→canonical code(谷丙转氨酶/ALT/丙氨酸氨基转移酶→ALT) | `services/exam_packages.py` |
| InterventionCycle + OutcomeMetric | `Episode`/`EpisodeOutcome`(completion_rate + metrics_delta)+ `ActionCard`(baseline/target/verification_days=84/accuracy_score) | `models/episode.py`、`models/action_card.py` |
| 安全兜底(感冒不排训练等) | smart_plan 确定性后处理 + Safety Guardian DDI/DSI/PGx/renal/liver | `services/smart_plan_service.py`、`agents/safety_guardian/` |
| 多源数据整合 | Garmin / Withings / 体检(OCR+PDF+手动)/ CGM / NFC / 手动 | `api/garmin_*`、`withings.py`、`cgm.py`、`nfc.py` |
| PII 脱敏 / 审计日志 / 数据导出 | `pii_scrub.py`、`agent_audit_logs`、`data_export.py` | — |

### 1.2 GPT Pro 说错的(我的修正)

- **social / 好友 / 私信 / 群聊 / PK:仓库里不存在。** 只有 AI agent 对话("阿衡")。→ "砍社交"是伪命题。
- **儿童模式:不存在。** 只有 vision.py 里一句"儿童游戏"文案。→ "砍儿童模式"是伪命题。
- 基因 / 表观遗传**已存在且已加密**(`EncryptedString`),GPT Pro 把它定位成"背景层"是对的。

### 1.3 真正的差距(本 PRD 要解决的)

| # | 差距 | 现状 | 影响 |
|---|---|---|---|
| G1 | **Twin 快照版本化** | Twin 是临时构建(Redis 60s),计划/报告/审计**不绑定** twin_snapshot_id | 无法回溯"这条建议当时基于什么状态" → 不可审计、不可复盘 |
| G2 | **Twin diff / 趋势引擎** | baseline 散落在 episode_reflection / schema 注释,无 `diff.py` | 每个 agent 自己算趋势,结果不稳定 |
| G3 | **Biomarker 参考范围 / 单位归一** | 别名映射有;**无** 按性别/年龄的 canonical 参考范围,**无**单位换算;阈值硬编码在 `labs.py`(ALT ULN=40) | 跨实验室、跨单位不可比;只有 6 个指标有专门规则 |
| G4 | **一等公民 InterventionCycle** | 拆散在 Episode + ActionCard + personal-outcome,无统一的 8–12 周周期(基线快照 + 目标指标 + 停止条件 + 闭合) | "干预效果"讲不成一个完整故事 |
| G5 | **依从度 ↔ 指标改善 相关** | completion_rate 与 accuracy_score 各自存在,未关联 | 无法回答"执行率 80% → 指标改善 15%" |
| G6 | **人审队列(高风险)** | 有告警、有仲裁日志,**无**医生/人工对 medical-grade 建议的签核闸门 | 高风险建议直接出给用户 |
| G7 | **加密 key 分离** | 一个 `GARMIN_ENCRYPTION_KEY` 同时覆盖设备凭证 + 基因 + 体检 | 泄露半径大,合规风险 |
| G8 | **合规** | 无独立基因授权、无医疗免责声明、无完整账号删除 API、无未成年人保护 | 融资/上线前必补 |
| G9 | **数据质量分级** | 有 freshness 时间戳,**无** reliability/completeness/stale 阈值喂给建议置信度 | 会基于半年前体检给过度确定的建议 |
| G10 | **遗留 health_analysis 仍关键词抽取** | `_extract_issues/_extract_recommendations` 正则抽 LLM 自由文本(与结构化的 orchestrator 路径并存) | 措辞一变就漏 finding |
| G11 | **产品切口过宽** | family / NFC / supplement-products / rhinitis / illness / women's health / consultations / doctor-loop / genetic-frontline 同时在跑 | 投资人看不清主线 |
| G12 | **文档漂移** | `ARCHITECTURE.md` 仍写旧栈 | 招人/融资前要重整 |

---

## 2. 产品收敛

### 2.1 定位(对外一句话)

> **复元(Reva)是一套 AI 主动健康管理系统。** 它整合体检/化验、Garmin/Withings 可穿戴、饮食与运动记录,构建个人 **Digital Health Twin**,在确定性安全规则与多专家 AI 之上生成可执行的**代谢健康 + 运动恢复**干预计划,并用 **8–12 周复查结果验证改善**。

### 2.2 目标用户(第一阶段)

35–55 岁高强度工作人群,有体检异常项(血脂/血糖/脂肪肝/尿酸/血压/体重),且至少有一种可穿戴(Garmin/Apple Watch/华为/Withings)。痛感强、有付费力、干预周期短、可形成复查闭环。

### 2.3 五个核心问题(产品只先回答这 5 个)

1. 我现在的**代谢健康风险**是什么?(画像)
2. 本周我该**怎么运动**?(处方)
3. 本周我该**怎么吃**?(处方)
4. 我今天适合**高强度还是恢复**?(每日就绪)
5. **8–12 周后**哪些指标应该改善?(验证)

### 2.4 范围 In / Out(MVP)

**In(核心闭环,Demo 只展示这条):**
代谢相关指标(体重/腰围/血压/TG/HDL/LDL/空腹血糖/HbA1c/ALT/GGT/尿酸)、Garmin/Withings、睡眠/HRV/RHR、运动负荷(ACWR/Zone2/力量)、体检上传与解读、Twin、代谢风险分层、8–12 周干预周期、每周运动+饮食+睡眠计划、每日就绪度动态调整、执行打卡、复查对比报告。

**降级 / 暂缓(保留代码,不上主路径、不进 Demo):**
family / 群组、NFC、supplement-products(电商)、rhinitis / illness / women's health 等单病种 tracker、consultations / doctor-report、基因作为**第一卖点**(降为背景约束层)、OpenClaw 框架对外叙事(内部继续用,对外只说"AI 健康助理/专家协作引擎")。

> 注:GPT Pro 建议砍的 social/PK/儿童模式**本就不存在**,无需处理。

---

## 3. 健康决策流水线:现状 vs 目标

```
                         目标链路                         代码实况
Raw Data                                              ✅ 多源已接(garmin/withings/exam/cgm/nfc/manual)
  ↓ Normalization / Provenance / Freshness            🟡 别名映射有;参考范围/单位/质量分级缺 (G3,G9)
Digital Health Twin                                   ✅ 15 分区已建
  ↓ Twin Snapshot (版本化) + Diff (趋势)               ❌ 快照不持久、无 diff 引擎 (G1,G2)
Deterministic Risk Engine                             ✅ chronic_risk(Framingham/IDF) + Safety Guardian 51 规则
  ↓ Specialist Agents (11)                            ✅ 结构化 SpecialistFinding
Cross Review / Safety Review                          ✅ cross_review + arbitration + 合成前 safety validator
  ↓ Human Review (高风险)                              ❌ 无人审队列 (G6)
Action Plan (处方)                                     🟡 weekly/daily plan 有;未拆成 6 类 prescription
  ↓ Execution Tracking                                🟡 CheckinRecord + ActionCard.checklist(分散)
Outcome Measurement (复查 delta)                       🟡 Episode/ActionCard/personal-outcome(未统一成 Cycle)(G4)
  ↓ adherence ↔ biomarker 关联                         ❌ 未关联 (G5)
Next Plan                                             ✅ 计划会读历史执行 + 目标 + 环境
```

**结论:链路 80% 在;断点集中在两处 ——「Twin 快照/diff」和「Outcome 闭环统一 + 人审」。** 把这两处补上,产品就从"健康建议工具"变成"健康结果管理系统"。

---

## 4. 新增 / 重构数据模型(批准后实现)

> 原则:**复用 > 新建**。下列多数是把已存在但分散的字段**收口**成一等公民,而非平地起新表。

### 4.1 `TwinSnapshot`(新,G1)
每次生成计划/报告/审计/干预周期,持久化一份当时 Twin 的序列化状态 + 哈希,并被下游引用。
```
TwinSnapshot: id, user_id, created_at, twin_json(压缩), schema_version, sources[], quality_grade
WeeklyPlan / HealthReport / ActionCard / InterventionCycle 增加 twin_snapshot_id 外键
```

### 4.2 `BiomarkerDefinition` / `BiomarkerObservation`(新,G3)
把 `exam_packages.py` 的别名表升级为带参考范围 + 单位 + 域的定义表,并产生归一化观测。
```
BiomarkerDefinition: code(ALT), aliases[], canonical_unit, domain(liver/metabolic/...),
                     ref_ranges[{sex,age_lo,age_hi,low,high,lab}], interpretation_rules
BiomarkerObservation: user_id, code, value, unit, normalized_value, normalized_unit,
                      ref_low, ref_high, flag(low/normal/high), source_exam_item_id, observed_at, confidence
```
Safety Guardian `labs.py` 的硬编码阈值改为从 `BiomarkerDefinition` 读取。

### 4.3 `DataQuality`(新,G9)
让每条建议知道数据新鲜度/可靠度,避免基于陈旧数据过度确定。
```
source, last_seen_at, freshness_level(fresh/stale/missing), reliability(high/med/low),
user_verified(bool), device_name, completeness(本周实际/期望读数)
```

### 4.4 `InterventionCycle` / `OutcomeMetric`(新,统一 G4)
把 Episode + ActionCard + personal-outcome 的散点收口成 8–12 周一等公民周期。
```
InterventionCycle: user_id, cycle_type(metabolic_90d), start_date, end_date,
                   baseline_snapshot_id, latest_snapshot_id, target_metrics[], status, stop_conditions[]
OutcomeMetric: cycle_id, metric_code, baseline_value, latest_value, delta, delta_pct, target_value, direction
```

### 4.5 `AdherenceOutcomeLink`(新,G5)
把 CheckinRecord.completion_rate 与 OutcomeMetric.delta 关联,产出"执行率↔改善"。

### 4.6 `ReviewQueueItem`(新,G6)
high/medical-grade 建议在出给用户前进入人审队列(MVP:运营/医生最小后台)。
```
ReviewQueueItem: recommendation_id, risk_level, status(pending/approved/rejected), reviewer, reviewed_at, note
```

---

## 5. 安全与合规硬化

| 项 | 现状 | 目标 |
|---|---|---|
| 加密 key 分离(G7) | 单 key 复用 | `DEVICE_/GENETIC_/MEDICAL_/LLM_CONTEXT_` 四把分离;`EncryptedString` 支持按列选 key |
| 基因独立授权(G8) | 无 | `user_consent.genetic_consent_given` + 首次进入基因模块单独授权 |
| 医疗免责声明(G8) | 无 | 首次 AI 建议弹一次性声明;AI 输出标注"建议性、非诊断" |
| 高风险人审(G6) | 无闸门 | medical-grade 建议走 `ReviewQueueItem`,人审通过才出 |
| 账号删除 / 撤回(G8) | 仅单条删除 | 完整账号级数据删除 + 导出(已有 export) |
| 未成年人(G8) | 无 | MVP 阶段策略:不面向未成年人,注册声明 |
| LLM 上下文脱敏 | PII regex 已有(不脱健康数据) | 维持;补 provider 数据策略说明到 SAFETY.md |

新增文档:`SAFETY.md`(建议边界/禁忌/人审策略)、重写 `ARCHITECTURE.md`(当前栈)、`PRODUCT.md`、`DATA_MODEL.md`、`ROADMAP.md`(G12)。

---

## 6. 评估体系(扩展现有 `backend/eval/`)

现有已具备 golden/safety/judge/grounding + baselines。**扩展三类:**
1. **体检解析 eval**:50–100 份脱敏报告 → 项目名/数值/单位/参考范围/异常项识别准确率 + OCR 后用户校正率(复用 `MedicalExamItem.original_value`)。
2. **建议安全 eval(扩 safety.yaml)**:肾功能异常+肌酸、ALT/GGT 高+饮酒、高血压+HIIT、感冒发烧+训练、低血糖+空腹运动、痛风+高嘌呤、用药+补剂冲突、夜间低血氧+训练 —— 测系统能否**拦截**危险建议。
3. **干预结果 eval**:真实用户 8–12 周:完成率、体重/腰围/TG/ALT/尿酸/HbA1c 变化、睡眠/HRV 趋势、主观精力、续费意愿、人审通过率。→ **融资核心数据**。

---

## 7. 90 天分阶段路线(批准后)

| 阶段 | 周 | 重点 | 复用 vs 新建 |
|---|---|---|---|
| **P0 收敛** | 1–2 | 定位收敛;`PRODUCT/ROADMAP/SAFETY/DATA_MODEL.md` + 重写 README/ARCHITECTURE;UI 主路径收敛到核心闭环(复用已建 Reva 设计语言) | 文档 + UI 收敛 |
| **P1 数据底座** | 3–4 | `BiomarkerDefinition/Observation`、`TwinSnapshot`、`DataQuality`、`InterventionCycle/OutcomeMetric` | 收口现有散点 |
| **P2 代谢闭环 MVP** | 4–8 | 上传体检→识别代谢指标→代谢画像→设 8–12 周目标→周计划(运动+饮食+睡眠)→每日就绪调整→每周复盘→复查对比报告 | 复用 orchestrator/specialists/smart_plan,接 Cycle |
| **P3 多专家+可评估** | 4–8 | 处方拆 6 类(Exercise/Nutrition/Sleep/Supplement/Monitoring/MedicalFollowup);AdherenceOutcomeLink;对外叙事改"降低错误建议" | 复用现有 agents |
| **P4 安全+评估** | 持续 | key 分离、人审队列、合规文档、扩三类 eval、医生最小后台、用户报告导出 | 新建 + 扩 eval |

---

## 8. 交互稿(Reva 设计语言)

核心闭环 6 屏,见同分支 **`docs/design/health-os/flow.html`**(可本机双击打开)。屏与"五个核心问题"对应:

| 屏 | 回答 | 关键组件 |
|---|---|---|
| ① 代谢健康画像 | Q1 我的风险 | 风险分层环 + 6 指标 + Framingham/MetS 徽标 |
| ② 90 天干预周期 | Q5 该改善什么 | 周期进度 + 目标指标基线→目标 + 停止条件 |
| ③ 今日(就绪+处方) | Q2/Q3/Q4 今天怎么练/吃/恢复 | 就绪环 + 运动/饮食/睡眠处方卡 |
| ④ 复查对比 | Q5 验证 | baseline→latest delta 表 + 依从度×改善 |
| ⑤ 安全审查 / 人审 | 安全底线 | 确定性告警 + 高风险待人审 chip |
| ⑥ 体检解读(归一化) | 数据底座 | biomarker 标准名/单位/参考范围/趋势/风险域 |

---

## 9. 融资叙事

不讲"功能很多 / 多 LLM",讲:
> "我们做 AI 主动健康**干预**系统。第一阶段聚焦代谢健康与运动恢复,把体检/化验、Garmin/Withings、饮食/运动/睡眠统一成 Digital Health Twin,经确定性安全规则与多专家 AI 生成 90 天干预计划,并用**复查结果验证改善**。"

亮点排序:**Digital Health Twin(系统中枢,非 prompt wrapper)> 可验证干预闭环 > 安全/人审体系 > 多源数据整合**。基因作为长期壁垒、不做第一卖点。

最小商业化:100–300 付费种子用户 × 1999–9999 元 × 8–12 周;验证的不是 DAU,是**付费意愿 + 上传率 + 执行率 + 复查改善 + 人审成本 + 机构合作意向**。

---

## 10. 风险与取舍

- **不做减法的风险**:切口宽 → 投资人看不清、团队 10 人撑不住。本 PRD 主张降级而非删除(代码留着,主路径收窄)。
- **医疗可信度**:LLM 不做决策主体,只做解释/生成/个性化表达;红线/分层/禁忌/新鲜度尽量规则化、可测试(已有 51 规则 + chronic_risk + eval,继续硬化)。
- **宠物健康**:Twin Framework 未来可抽象复用,但**现在不混进同一产品**。

---

## 附录 A:对账明细
见 §1。源文件均已实地核查(`twin/`、`orchestrator/`、`agents/safety_guardian/`、`services/chronic_risk_service.py`、`models/episode.py`、`models/action_card.py`、`services/exam_packages.py`、`backend/eval/`、`docs/SECURITY.md`)。

## 附录 B:待你拍板的关键决策
1. **MVP 单一切口**确认为「代谢健康 + 运动恢复」?(还是先单押代谢?)
2. **降级清单**(family/NFC/单病种 tracker/consultations/基因前置)是否认可?
3. **P1 先做**哪两个数据模型?(建议 `TwinSnapshot` + `BiomarkerObservation` —— 其余依赖它们)
4. 是否需要**医生最小后台**进 P2(影响人审闭环能否在种子用户跑通)?
