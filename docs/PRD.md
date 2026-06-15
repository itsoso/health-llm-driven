# 全局产品需求说明书(PRD)— LLM 驱动的多 Agent 个人健康管理平台

> **状态**: v1 基线(2026-06-15)。本文由对全仓库逐子系统、逐文件 review 反推而成,描述**当前产品实际做到什么、靠什么数据、守什么边界、缺什么**,作为后续**重新设计与产品演进**的事实基线。
> **方法**: 按 10 个产品域并行逆向工程代码(orchestrator / twin / safety / 专家团 / 用药 / 可穿戴 / 化验基因抗衰 / 行为闭环 / 心理慢病知识库 / 四端平台),每域抽取「能力 + 实体 + 不可变规则 + 缺口」。
> **读法**: §1–§3 是全景;§4 是分子系统需求(重设计时逐域读);§6 是**不可变约束**(重设计必须保留的医疗安全/隐私不变量);§7 是**缺口与技术债**(重设计要修/要补的清单);§8 是演进锚点。

---

## 1. 产品愿景与定位

**一句话**: 一个 LLM 驱动、多 Agent 编排的个人健康管理平台 —— 把分散在可穿戴设备、CGM、化验、基因、环境里的数据,沉淀成统一的「数字健康孪生」,由一支确定性专家团 + 安全闸门做结构化裁决,再由 LLM 合成可执行、可解释、有证据的健康行动,并通过四端 + 多渠道在「对的时刻」低摩擦触达用户。

**核心理念(贯穿全系统的设计哲学)**:
1. **确定性优先,LLM 只合成** — 所有评分/分级/判定(readiness、ACWR、PhenoAge、BP 分级、代谢综合征、DDI)都是纯函数;LLM 负责组织措辞与个性化,不参与「算事实」。
2. **不假装成功(Rule #1)** — 失败要让调用方感知;写库前对高确定性数据先复述确认;撞药方案不写库还报「记好了」是红线。
3. **医疗边界** — 不诊断、不开方、不调药量;分级措辞;高危引导就医;补剂/抗衰带 claim_boundary。
4. **行为闭环** — 不止给建议,而是「状态 → 少数可执行行动 → 提醒 → 完成/跳过反馈 → 用用户自己的复查数据验证(N-of-1)」。
5. **删码优先、复杂度预算** — 单文件 ≤500 行(约定);先复用再新建。

---

## 2. 目标用户与核心场景

**主用户画像(产品锚点)**: 中年、量化自我倾向、慢病风险管理 + 耐力训练。代表性真实画像:糖尿病前期(HbA1c 6.3)× 脂肪肝倾向 × 长期 PPI × 12 种在服药 × 同时佩戴 Apple Watch Ultra 3 + RingConn Gen3 + Garmin Enduro 2。

**核心场景**:
- 「今天我该不该练 / 怎么调?」— 多源恢复/训练决策。
- 「我这次加餐/这顿饭」— 抬手一句话记录,结构化估算。
- 「我体检异常了怎么办?」— 异常项 + 基因关联 + 趋势 + 复查窗口一次性聚合。
- 「这些药怎么吃才不出错?」— 复杂方案录入即排好时点 + 撞药拦截 + 到点复查。
- 「我做的事到底有没有用?」— N-of-1 个人实验 + 改善时间序列(outcome proof)。
- 「爸妈的健康」— 家庭代管(体检/用药/复查)。
- 主动:晨间恢复简报、饭后步行、睡前窗口、异常风险、复查到期 —— context-aware nudge,克制不刷屏。

---

## 3. 系统架构总览

### 3.1 分层(四层)
```
对话 / 客户端 (Web · iPhone/iPad · macOS · 微信小程序)
        ↓
L4 Orchestrator — 意图路由 + 专家调度 + cross-review/LLM 仲裁 + 合成 + 流式
        ↓
L3 13 Specialists(确定性)+ Safety Guardian(56 规则闸门)
        ↓
L2 Digital Health Twin(15 语义分区,Redis 缓存,多源融合 + 个人基线)
        ↓
L1 Collectors + Services(Garmin/Apple Health/RingConn/CGM/化验/基因/环境/补剂/药物)
```

### 3.2 四端定位
- **Web(Next.js 14)**: 功能最全;独占运营/内容创作(admin/review/onboarding/register/skills)。
- **iPhone/iPad(Expo RN,唯一原生 App)**: 日常驱动;独有 voice-chat / Apple Health import / live-run / 减药 / Siri。
- **macOS(Swift/SwiftUI)**: 桌面分析工作台(Core/UI 分层,纯逻辑可测)。
- **微信小程序(uni-app)**: 轻量入口。
> 真实跨端 = iOS + Web + Mac + 微信;**Android 是一等缺口**,**watchOS 仅有路线图无代码**。

### 3.3 数据源
Garmin(直连 Connect)= 训练/户外事实源;Apple Watch / RingConn / Oura / Withings 经 iOS HealthKit 汇入;CGM(批量幂等);化验(5 通道录入);基因(加密存储);环境(AQI/天气)。

---

## 4. 子系统需求

### 4.1 LLM Harness 与对话编排(`backend/app/orchestrator/`, `services/agent_executor.py`, `services/llm/`)

**定位**: 把「一句自然语言」稳定转成「可信、可解释、源感知的健康回答或一次写库动作」的中枢。

**能力**:
- **路由分流**: 正则 `_needs_skill`(记录/打卡/吃了…或带图片)→ OpenClaw skill(写库/多模态);否则 → Orchestrator(纯分析)。意图分类 `classify_intent`(9 类关键字,safety 优先)。
- **专家调度**: 静态注册表 + 每专家 `applies_to` 自决参与(非 LLM 自由 spawn);并行执行(池 max 4,墙钟 12s),Recovery→Movement 的 `readiness_zone` 经 context 显式传递。
- **cross-review + LLM 仲裁**: 确定性冲突规则(高蛋白×肾功能等)→ 仅 hard/≥2 冲突才调 LLM 裁决,fail-soft 回退。
- **合成 + persona**: 把结构化 finding 合成自然语言,语气按 `coach_persona`(strict/gentle/data_driven)。
- **流式 SSE** + 后台任务(客户端断开仍跑完 audit/cards/SOAP);**source-aware fast path**(`source=siri` 跳过专家/仲裁,3–5s)。
- **韧性**: provider 故障回退(主→openai);弱模型工具调用门控(`reliable_tool_calling=False` 的 glm/minimax 在要传 tools 时换可靠模型);内联工具调用恢复(把吐成文本的 `[tool_call:…]`/裸 JSON/弯引号解析回真调用)。
- **写库前确认**: weight/blood_pressure/illness 首次返回 `[NEEDS_CONFIRMATION]` 复述后才写。
- **记忆注入 4 stage**(conversation/case_timeline/directives/hybrid,各独立可观测,写 audit)。

**关键配置**: `ModelEntry`(8 条:5 tokenplan + 3 langbridge 商用 Claude/GPT/Gemini);`provider` 类型决定客户端路径;切换粒度 全局/per-user,`create_provider_for_user` 不缓存即时生效。

**缺口**: 意图分类纯关键字(MVP,多义/否定/错字漏判);无 LLM-as-judge eval 套件(prompt 改动无自动跑分);未启用 strict mode / force tool_choice;无运行中 compaction;cross-review 仅确定性 v1(覆盖 ~80%);`set_active_model_id` 重启失效。

### 4.2 Digital Health Twin(`backend/app/twin/`, `services/personal_baseline.py`)

**定位**: 用户当下健康状态的统一结构化快照,按「语义分区」而非数据源聚合,全字段 Optional、缺数据静默降级,是全部 agent/LLM 的唯一上下文入口。

**15 分区**: meta · physiological(HRV/睡眠/电量/SpO2/VO2max/夜间序列/多源 field_sources/个人基线)· body_composition(体重/腰围/BMI/TDEE)· labs(血脂糖肝肾 + PhenoAge 9 项)· cgm(TIR/GMI/CV)· medication · supplement · genetic(分类变异)· epigenetic(DNAm 时钟,experimental)· environment(AQI/UV,1h 缓存)· behavioral(饮食/饮水/ACWR/训练状态/鼻炎打卡)· acute(病程/症状/训练 guardrail)· mental(7日情绪均值)· chronic · goals · freshness。

**构建机制**: 三阶段(Phase A 同步先行依赖项 + 急性病用传入 db;Phase B 15 filler 并行各开独立 SessionLocal;Phase C collectors 补齐)。Redis 单 key `twin:v1:{uid}` TTL **60s**(注释仍写 5min,已漂移)。个人基线 = 90 天滚动 z-score(纯 statistics,<14 天不产出,冷启动护栏)。多源融合 `field_sources` 记录每字段获胜源,SpO2 跨源取最差值。`formatter.twin_to_prompt_blob` 每分区一行 + 新鲜度标签 + hedge 指令。

**不可变规则**: 数据写入后须 `invalidate_twin`;PhenoAge 全有或全无(缺一不猜算);**`build_twin` 自开 SessionLocal 看不到请求事务 —— 安全预检改用 `HealthTwin()` + 单独 `_fill_*`**。

**缺口**: 缓存粒度过粗(单 key 全量 60s,labs 与 physiological 同 TTL,分层 TTL 未做);`_collectors.py` 是过渡债(twin 层直查 model);PhenoAge 单位风险未治理(错单位静默失真);化验靠 ilike 模糊匹配(22 次串行查询);个人基线只覆盖 Garmin 9 指标;`fetch_latest_exam_meta` 死代码。

### 4.3 Safety Guardian(`backend/app/agents/safety_guardian/`)

**定位**: 确定性医疗安全闸门 —— 不依赖 LLM、纯规则,对 Twin 跑 56 条规则,输出结构化、可审计、带文献的告警。LLM 只事后做白话解读,从不参与「是否告警」。

**机制**: `@register` 自动注册纯函数规则;单条异常隔离;Severity 五档(INFO<LOW<MEDIUM<HIGH<CRITICAL);Alert 带 `rule_id`(支持忽略)/`data_citation`(审计快照)/`action`/`references`/`requires_medical_attention`。

**56 条分类**: vitals 12(BP/RHR/SpO2/stress/sleep 急性阈值)· labs 7(肝酶/血脂/血糖/肾/白细胞 + 陈旧 + catch-all)· ddi 7(药×药,GLP-1×磺脲、SSRI×MAOI CRITICAL)· dsi 7(药×补剂,维K×华法林、圣约翰草)· pgx 9(CPIC,CYP2D6/G6PD/HLA,位点+在服药双命中)· training_load 3(ACWR)· cgm 6(<54/>300 CRITICAL、TIR/CV)· symptoms 5(胸痛/卒中FAST/呼吸困难/急腹症,关键词兜底→120)。

**审计 + 升级**: 每次评估旁路写 `agent_audit_log`(失败静默不影响主响应);Celery 每小时 `escalate_critical_unresolved`(critical 24h 未决升级,最多 3 次,穿透/避让静默时段);`/safety/explain` LLM 个性化解读(两 provider 全挂降级返回规则原文)。

**不可变规则**: CRITICAL ⇒ requires_medical_attention;涉药一律「与处方医生确认」;默认只回 severity≥MEDIUM、去重、可 dismiss。

**缺口**: **无长期 PPI/NSAID/激素等慢性累积风险规则**;症状匹配脆弱(无否定检测、无 LLM 兜底);labs 肝酶 ULN=40 硬编码不分性别/方法;PGx 判型靠字符串启发式;clarification 模板只覆盖 5 个 AnomalyAlert 类型,与 56 条 rule_id 是两套独立体系(DDI/PGx/CGM/symptoms 无对话澄清)。

### 4.4 健康专家团(13 Specialists,`backend/app/agents/`)

**定位**: 从同一 Twin 读各自分区、产出结构化 `SpecialistFinding`(+ `ProposedCard` 信任循环),专家算事实+定边界,LLM 只组织措辞。

| 专家 | 触发 | 核心产出 |
|---|---|---|
| Recovery Coach | recovery / HRV+睡眠齐 | Readiness 0–100(5 维加权,HRV 用 MAD z-score,**Garmin 官方值覆写自算**)+ zone(rest/light/moderate/hard) |
| Fuel Strategist | fuel / 有饮食 | 热量缺口、蛋白目标(1.8/1.4 g/kg)、下一餐槽位、基因饮食 nudge(MTHFR/APOE/FTO…) |
| Movement Coach | movement / 有负荷 | ACWR × readiness_zone **决策矩阵** → 今日强度;急性病强制 rest;基因运动偏好 |
| Mental Health Companion | mental(Tier 5) | 情绪聚合 + **危机检测**(保守阈值→热线)+ 非药物行动 + 基因心理档案 |
| Hypertension | chronic / SBP≥130 或降压药 | ACC/AHA 分级 + 降压药识别 + 14 天降压实验;**无数据 short-circuit** |
| Metabolic | chronic/fuel / 有 HbA1c/CGM | 代谢综合征判定(5 项命中 3)+ LDL/HbA1c/TG 分窗 N-of-1 |
| Rhinitis | chronic / 有打卡 | 症状分级 + AQI/湿度环境关联 + 鼻喷依从 |
| Knowledge Librarian | 知识类/general | 系统知识库 v2(带 claim/证据等级)→ 回退得到 wiki RAG |
| Longitudinal Analyst | 趋势/general | 6 月趋势 + 干预事件×指标**因果叙事**(诚实标关联非因果) |
| Supplement Advisor | fuel/labs + 基因/异常 | SNP+化验补剂(**HFE 纯合硬阻断铁**、eGFR/华法林降级)+ 12 周 N-of-1 |
| Longevity | longevity | PhenoAge 解读 + 缺值清单 + **真实编排四件套**出 12 周协议 + 群体证据 |
| Cross-Source Validator | 有 garmin + 设备/质量 | 多源同指标差异过大→标可疑源 + 暂以谁为准(无异常产空,不制造噪声) |

**共享 context**: readiness_zone(Recovery→Movement)、db/user_id、query、knowledge_evidence、recent_cases。

**缺口**: 因果是关联归因非因果推断;Movement forecast 暂停(fetcher 不支持 ACWR);代谢综合征用 BMI≥28 替代腰围;**`fuel_strategist` 提前 return 致 GSTP1 分支 + `[:5]` 截断为死代码**;PhenoAge 门槛高大概率不可用。

### 4.5 多源可穿戴健康路由(`services/device_source_priority.py` 等)

**定位**: 同一指标多设备写入 → 逐指标来源仲裁 + 跨源一致性校验 + 安全指标取最差值,产出「该信哪台、数据是否可疑」的可解释视图。

**能力**: 多源接入(Garmin 直连 + 其余经 HealthKit 按 sourceName **每源各一条日记录**);per-metric 仲裁(睡眠/血氧/HRV→戒指、活动/心率→腕表、RHR/负荷/readiness→Garmin);agreement = 1−极差/均值;>30% 偏离→可疑检测;SpO2 跨源取最差值(防正常源掩盖危险低值);CGM TIR/GMI;睡眠/血氧/HRV 夜间分析;workout 同步 + 类型归一。

**关键实体**: `GarminData`(实为多源载体,`data_source` + `(user,date,source)` 唯一索引);`WorkoutRecord`(source manual/garmin/strava/apple_health + `(user,external_id)` 唯一去重锚)。

**不可变规则**: RingConn/Oura/Withings 无公开 API 只走 Apple Health(被动适配器 `raise NotImplementedError`,不主动拉);单源==旧行为;安全偏置仅 SpO2 取 min。

**缺口**: **置信度/agreement 是只读旁路,未回灌 Twin**(无 metric 级 confidence/freshness 字段,无 `DailyMetricArbitration`/`recovery_state_v2`/`training_gate` 落库);仲裁不看新鲜度;**ground-truth 校准未做**;Garmin Connect IQ / Silent Nudge Router / Personal Experiment 表未建;Android 整体缺位。

### 4.6 用药自动驾驶(`backend/app/...medication...`, `docs/MEDICATION_AUTOPILOT.md`)

**定位**: 把医生开的复杂方案一次录入成可执行带时点时间线,系统全程接管 —— **无脑的是执行不是决策**。

**能力**: 药品 CRUD + 误操作回滚;**相对吃饭时点**(`timing_relation`/`meal_anchor` → 中文「早餐前30分钟」);每分钟提醒扫描(文案带剂量+时点+一键打卡);依从追踪;**方案模板一键实例化**(铋剂四联 30 秒录全);**引入即 DDI 闸门**(delta 法,severity≥HIGH 或 requires_medical_attention 阻断不写库 + 422 + override 留审计);疗程多阶段(phases JSON);疗程→复查映射(PPI→胃镜,物化 ReviewSchedule);多药梳理减药候选(只产候选,不说停药)。

**关键实体**: Medication(+ regimen_id)· MedicationLog · MedicationRegimen(phases JSONB / current_phase / review_on_complete)。

**不可变规则**: 录入脚手架非开方,模板带强制 DISCLAIMER,用户必确认「这是医生开的」;DDI 闸门是写入前硬闸门;减药红线「请与医生讨论」;`_safety_twin` 绕 build_twin 用传入 db。

**缺口**: **阶段自动切换(P1b)未做**(current_phase 永停 0,愈合期药永不自动建);DDI 只覆盖药×药(PGx/DSI 引入校验未接,**长期 PPI 规则真空白**);移动端方案录入屏未做、相对吃饭智能提醒未做、注入 DailyOperatingPlan 0% 集成(提醒仍走固定时点);OCR 处方未实现;`spacing_min` 字段未加;依从率口径粗。

### 4.7 化验 / 基因 / 抗衰 / 长期(`api/medical_exams.py`, `services/phenoage.py`, 等)

**定位**: 把「一张体检 + 一次基因 + 可穿戴日志」沉淀为可追溯、可归一、可解读的纵向健康底座。

**能力**: 化验 5 通道录入(图片 OCR/PDF/JSON/CSV/文本)→ 指标统一(`normalize_item_name` + 13 套餐)→ 旁路 `BiomarkerObservation` 归一化;异常解释包(异常项 + 命中基因关联 + 趋势 + 复查窗口 + 找哪科医生);基因 8 类解读 + 交叉分析 + PGx 安全;**PhenoAge 表型年龄**(Levine 2018,9 项纯函数,缺值不猜算)+ Longevity 解读/拖累项/委托四件套出协议/偏老提 N-of-1;Epigenetic 第三方 DNAm 时钟(experimental);长期趋势 + 干预因果叙事;**个人改善时间序列 outcome proof**(事件锚点 + 前后 30 天对比 + AI 建议成绩单);TwinSnapshot 版本化快照(审计/复盘锚点)。

**关键实体**: MedicalExam/Item(OCR 原值轨迹)· MedicalIndicator(统一码)· BiomarkerObservation(标准单位/参考区间/is_risk/confidence)· GeneticVariant(genotype **列加密**)· EpigeneticReport · TwinSnapshot · PhenoAgeResult。

**不可变规则**: 医疗边界全程 claim_boundary + evidence_tier;缺值不猜算;OCR 不直接信任(需确认);PGx 双条件(位点+在服药);越权防护(强制绑当前用户)。

**缺口**: **个人预测模型未落地**(`personal_models/` 目录不存在,Twin 无 predictions 分区;Phase 0/1/2 停留设计稿,卡在数据采集量);因果非因果推断(无对照/混杂校正);ground-truth 校准缺位;趋势数据稀疏(化验靠 name_en 精确匹配,抽不出标准码进不了趋势);epigenetic 全程 experimental。

### 4.8 行为闭环执行层(饮食 / 训练 / 计划 / 干预 / 提醒)

**定位**: 把 Twin 状态转成「今天该做什么」的少数可操作行动,投递到手机/手腕,收反馈,并用 N-of-1 把效果用用户自己的复查数据验证成闭环 —— 连接「分析」与「行为改变」。

**能力**: 拍照识别入库饮食 + 营养缺口实时算;补剂 12 周 N-of-1(HFE 硬阻断 + UL 限制 + 自动评分);TRIMP/ACWR 训练负荷;**今日训练决策灯**(`recovery_decision.py`:readiness zone + 急性病兜底 + ACWR 封顶 → GREEN/YELLOW/RED + 置信度;**P0 已落地后端**);每日运营计划(确定性 planner v0:晨测→化验锚点→蛋白→运动分支→干预卡→睡眠,经 AdviceGuard 合规闸 + 急性休息仲裁 + top5 截断);干预周期/Episode(锁基线快照 + 停止条件 + delta 评分);可操作通知(top action「今天最重要一件事」镜像到 Apple Watch,完成/跳过回写事件);打扰预算限流(跨 watcher 全局周预算);Celery ~25 条定时节律。

**关键实体**: DailyOperatingPlan · InterventionCycle/OutcomeMetric · InterventionEvent(append-only)· HealthEpisode · SmartReminder · NotificationLog/UserNotificationSetting。

**不可变规则**: 提醒克制(每日 ≤1 行为闭环 + 必要周期/复查,空态不发);静默时段非 critical 延迟、critical 穿透;每条 action 带 claim_boundary;AdviceGuard 合规闸(无 advice contract 丢弃)。

**缺口**: **决策强度三套并行口径不统一**(ExerciseRecoveryService rest…peak / RecoveryCoach zone / MovementCoach intensity —— 注:本 PRD 已引入 `recovery_decision.py` 统一 GREEN/YELLOW/RED,但**尚无端消费者**,未接 Daily Plan);planner 仍 deterministic v0;周期生命周期半自动(无到期自动 complete;Episode 与 InterventionCycle 两套并存);**统一节律日历缺失**(Celery beat 时点 + mobile 本地通知时点两套硬编码无协调,有重复触达风险);behavior-loop Watch 镜像仅 iOS。

### 4.9 心理 / 慢病 / 知识库 / Skills / 家庭

**定位**: 在 Twin 之上用确定性专科 agent 做安全裁决,用 RAG 给结论背书,用两套发布模型的 OpenClaw skills 把「查/记/管」铺到任意对话渠道。

**能力**: 心理危机检测 + 热线 + 非药物行动(Tier 5,原始日记不出 specialist);慢病专科(高血压 ACC/AHA、代谢综合征、鼻炎环境关联,**无数据 short-circuit**);知识库双层 RAG(系统知识库 v2 → 得到 wiki ChromaDB);**22 个 OpenClaw skills**(health-query/record/data-summary、multi-source、analysis、spo2/sleep 分析、chronic-risk、exercise-recovery、genetic、medication-tracker、各 tracker、nutrition/supplement-advisor、environment、personal-plan/weekly-planner/reminder-setter/action-card-manager、family-health、workout-coach);家庭代管(体检 AI 提取/对比、用药、复查日历、proxy JWT);症状/过敏/按摩 tracker。

**不可变规则**: Tier 5 心理隐私(永不诊断、原始文本不上外部 LLM);Skill 两套鉴权(`backend/skills/*` 随后端部署、登录用户 JWT;`openclaw-skills/*` 独立分发、调用方自带 token);家庭代管须 `/family/switch` 换 proxy JWT。

**缺口**: 心理热线硬编码(仅大陆,且两条同号疑复制错);危机检测纯阈值(读不到文本自杀意念,被隐私挡外);知识库索引手动触发、ChromaDB 未装静默降空;代谢综合征用 BMI 替腰围;`family_health.py` 1110 行超预算;massage-tracker 不在仓库两套发布内。

### 4.10 四端与平台基建

**各端能力矩阵**(实际路由:Web ~50 顶级目录、Mobile ~60 路由、macOS 15 侧边栏、小程序 40 page):

| 功能域 | Web | Mobile | macOS | 小程序 |
|---|---|---|---|---|
| 首页/AI 对话/快速记录 | ✅ | ✅(含 voice-chat) | ✅ | ✅ |
| Safety 告警 | ✅ | ✅ | ⚠️合并 today | ❌ |
| 饮食/睡眠/运动恢复 | ✅ | ✅ | 部分(无饮食/睡眠) | 部分 |
| 用药/处方/减药 | ✅ | ✅(含 deprescribing/scan) | ✅ | ✅ |
| 化验/基因/数字孪生/长期 | ✅ 全 | ⚠️ 切片 | ✅ | ⚠️ 浅 |
| 家庭健康 | ✅ | ✅ | ❌ | ❌ |
| Admin/审核/Onboarding | ✅ 独占 | ❌ | 部分(jobs/trace) | ✅ |

**平台能力**: JWT 全端统一(localStorage / expo-secure-store / Keychain;Mobile `shared-keychain` App Group 给 Siri/Widget,iOS-only);推送 4 渠道(APNs/Telegram 双向/微信/Email);部署双通道(后端 systemd + managed migrations + 健康度<35 自动回滚 / 前端 PM2 / 移动 OTA + EAS);CI 四道闸(backend ruff+pytest+doc-drift+eval / frontend page-freeze+vitest+build / mobile tsc+jest / **mac swift build+test**);多 LLM provider 全局/per-user 切换。

**缺口**: **Android 一等缺口**(shared-keychain noop、OTA 只推 iOS、APNs/Siri iOS-only);**watchOS 仅路线图无代码**;Mobile 深度分析偏弱;小程序最浅;**CLAUDE.md feature-parity 表严重过时**(称 mobile ~15 路由,实况 ~60);复杂度预算 500 行无 CI 强制(20+ 文件超限)。

---

## 5. 跨域数据流(端到端)

```
设备/化验/基因/环境  ─ ingest(collectors / HealthKit 多源拆分 / Garmin 直连)
  → device_source_priority 逐指标仲裁(安全指标取最差) → GarminData 多源行
  → build_twin(15 分区并行 fill + 个人基线 + Redis 60s) → twin_to_prompt_blob
        ↓                              ↓                         ↓
   Safety Guardian(56 规则)      13 Specialists(applies_to)   Orchestrator 合成
        ↓                              ↓ (ProposedCard)          ↓ (流式/确认/记忆)
   Alert(审计 + 24h 升级)         ActionCard(信任循环)        回答 / 写库动作
        ↓
   DailyOperatingPlan(行动) → 可操作通知(镜像 Watch) → 完成/跳过 InterventionEvent
        ↓
   N-of-1 干预周期(锁基线快照 → 复查 delta) → PersonalOutcome(改善 proof)
```

---

## 6. 非功能需求与不可变约束(重设计必须保留)

> 这些是医疗安全/隐私/工程的**不变量**,任何重新设计都不能破坏。权威来源 `AGENTS.md` + `docs/governance/*`。

**医疗安全(产品级红线)**:
- 不诊断疾病、不开方、不调整药量;一切涉药措辞「与处方医生确认」。
- 确定性规则裁决安全,LLM 不参与「是否告警/能否吃」。
- 高危(BP≥180/120、CGM<54、症状红线、SSRI×MAOI 等)→ CRITICAL + requires_medical_attention + 引导就医/120。
- 引入新药写入前必过 DDI 闸门;撞药不静默放行(Rule #1)。
- 无事实数据时 short-circuit,不让 LLM 编结论。
- 补剂/抗衰/epigenetic 带 claim_boundary + evidence_tier;HFE 等硬阻断保留。

**隐私(分级)**: L3 健康+行为(加密 + 访问审计)/ L4 密钥(不可逆加密 + 最小权限);日志强制脱敏;所有查询强制 user_id 隔离;基因 genotype 列加密;Mental Health Tier 5(原始文本不出 specialist/不上外部 LLM);家庭代管须 proxy JWT。

**性能/韧性**: 专家并行 12s 墙钟;Siri 3–5s fast path;provider 故障回退;审计/记忆/KG 全旁路(失败不影响主流程);Twin 缺数据降级而非报错。

**工程**: 单文件 ≤500 行(约定);新依赖须证必要 + Snyk + pin exact;删码优先;移动端只走 RN;部署健康度<35 自动回滚;CI 四道闸 + doc-drift 数字一致。

---

## 7. 现状缺口与技术债(重设计输入清单)

**A. 能力缺口(产品演进点)**
1. 个人预测模型未落地(目录不存在,Twin 无 predictions 分区;卡在数据量)。
2. 多源置信度/agreement 未回灌 Twin(无 metric 级 confidence/freshness;决策灯无端消费者、未接 Daily Plan)。
3. ground-truth 校准缺位(CGM/血压/化验未用于校准可穿戴趋势)。
4. 统一健康节律/运营日历缺失(用药复查、训练、测量、体检各自调度;无年度体检跟踪;无病情驱动检查日历;Celery 与 mobile 本地通知两套时点无协调)。
5. 用药阶段自动切换(P1b)未做;长期 PPI 安全规则真空白;OCR 处方未实现。
6. watchOS 无代码;Android 一等缺口;Garmin Connect IQ 未做。
7. N-of-1 双闭环(Episode vs InterventionCycle)未收口;周期到期不自动 complete。

**B. 正确性/质量债**
8. 决策强度三套口径并行(rest…peak / zone / intensity / 新 GREEN-YELLOW-RED)未统一收口。
9. 无 LLM-as-judge eval 套件;意图分类/needs_skill 纯正则脆弱。
10. 症状安全匹配无否定检测;PGx/labs 判型靠字符串启发式 + 硬编码 ULN。
11. 因果叙事是关联归因(无对照/混杂校正)。

**C. 代码债(独立可清理)**
12. `fuel_strategist/strategist.py` 提前 return → GSTP1 分支 + `[:5]` 截断死代码。
13. Twin `_collectors.py` 过渡债 + `fetch_latest_exam_meta` 死代码;cache TTL 注释(5min)与实际(60s)漂移。
14. `family_health.py` 1110 行、20+ 文件超 500 行预算;`cross_source_validator` σ 检测死代码。
15. CLAUDE.md feature-parity 表严重过时(mobile ~15 → 实况 ~60),需同步。

---

## 8. 演进锚点(给重新设计)

- **保留的内核**: 四层架构 + 确定性专家 + 安全闸门 + Twin + 行为闭环 + N-of-1 + 多源仲裁 —— 这是已验证的骨架,且大部分「看似要造的」(路由/基线/事件流/实验平台/复查日历)**已建成**,重设计应**收口与贯通**而非重造。
- **最高 ROI 的下一层**: 把多源「置信度」做成一等信号回灌 Twin → 喂统一「决策灯 + 健康运营日历」(测/查/练/体检在时间轴上编排,状态驱动地前移/后延)→ 接 Daily Plan 和四端 surface(Apple Complication / Garmin Connect IQ)。
- **数据飞轮**: 腕上低摩擦「主观事件 + 时间戳」捕获(已有 `HealthEvent` 后端)补上被动数据唯一缺的标签,喂因果分析与个人预测模型。
- **演进纪律**: 任何重设计先过 §6 不可变约束;先清 §7-C 代码债再叠新抽象;每个新能力先问「§7-A 里它对应哪条,仓库是否已有 80%」。

---

*本 PRD 由全仓库逐子系统 review 反推,作为重设计基线。子系统细节(文件:行级)见各域 review 原始记录;架构数字以 `docs/ARCHITECTURE.md` + `scripts/check_doc_drift.py` 为准。*
