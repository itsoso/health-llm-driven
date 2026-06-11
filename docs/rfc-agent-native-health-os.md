# RFC:Agent Native LLM 时代的个人健康产品演进规划

> 状态:草案 (Draft) · 2026-06 · 作者:产品/技术
> 范围:HealthPilot 从「精心编排的多专家系统」演进为「Agent 自主驱动的健康操作系统」的 12-18 个月技术与产品路线
> 一句话:**给 Agent 工具 + 长期因果记忆 + 主动出手能力,跑在确定性安全护栏之上,以独家健康数据为护城河。**

---

## 0. 为什么现在要重写架构假设

HealthPilot 当前架构(L4 Orchestrator 关键字意图路由 → 调度 11 个 specialist → Digital Twin → Collectors)是 **2023-2024 的最佳实践**:用确定性编排把不可靠的 LLM 框在可控流程里。

但在 Opus 4.7 / GPT-5.5 这代模型上,几个底层假设正在反转:

| 旧假设(编排时代) | 新现实(Agent Native) |
|---|---|
| 模型不可靠,需硬编码意图路由 | 模型比正则更懂意图;手写路由成为包袱 |
| 编排逻辑写在 Python if-else | 编排逻辑应在 context(工具描述)里,模型自己决定 |
| 功能越多越强 | 模型能力在涨,**功能边际价值下降**;数据深度/闭环验证边际价值上升 |
| Agent 等用户开口 | Agent 应主动出手(Ambient Agent) |
| 记忆 = 最近对话 | 记忆 = 持续演进的因果史(护城河) |

**护城河迁移**:从「编排得多精巧」→「工具设计 + 长期记忆 + 独家数据 + 闭环验证」。代码精巧性谁都能抄,3 年的个人健康因果史不能抄。

**已有的有利基础(2026-06 复核代码确认):**
- ✅ **动作类已是 tool-calling**:`tool_schema_registry` 注册了 **11 个动作工具**(health_query / health_record / health_manage / health_analysis / environment_check / supplement_guide / upload_genetic_txt / query_genetic_profile / upload_medical_exam_text / query_lab_indicators / manage_plan),`agent_executor` 多轮工具循环已成熟(含 tool_round_limit、finish_reason 完成度判定、fallback provider)
- ⚠️ **但分析类 specialist 仍是「被编排」**:11 个 specialist(Recovery/Fuel/Movement/Mental/Hypertension/Metabolic/Rhinitis/Knowledge/Longitudinal/Supplement + SafetyGuardian)由 `orchestrator` 按 `classify_intent` 关键字路由调度,**尚未工具化**。这是方向一的核心改造对象
- ✅ Digital Twin 14 语义分区 + conversation_memory 已落地
- ✅ Safety Guardian 51 条确定性规则 + 审计日志(`agent_audit_log`)
- ✅ Episode N-of-1 闭环(在 supplement_advisor)
- ✅ 51 个 Celery 定时任务(主动推送雏形)
- ✅ **多模型 panel 已落地**:`_run_multi_model_stream`(Claude Opus 4.7 lead + GPT-5.5 + Gemini 3.1 Pro 并发综合);per-user / per-request 模型切换(`create_provider_for_user` / `create_provider_for_model_id`),已接 DeepSeek V4 / GLM-5 / MiniMax M2.5 / qwen 等多 provider
- ✅ **近期已修的 Agent 健壮性 bug**(2026-06):长回复 max_tokens 截断(→8000)、`_api_get` 字符截断损坏 JSON(→ `_api_get_json` 干净解析)、补剂/用药记录原始错误泄漏。这些是 Agent Native 化的前置债务,已清

**关键区分(本次复核新增)**:系统其实是**双层**——「动作层」已 Agent 化(tool-calling),「分析层」(11 specialist)仍编排化。方向一不是「从零工具化」,而是**把分析层也并入已成熟的 tool-calling 循环**,改造成本因此更低。

零件齐全,缺的是**重组**:把分析层 specialist 从「被编排」改为「Agent 自主调用的工具」,把闭环验证从配角提为主角。

---

## 1. 十大演进方向(总览)

| # | 方向 | 从 → 到 | 优先级 |
|---|---|---|---|
| 1 | 编排范式 | 分析层硬编码调度 → 并入 Agent 工具循环 | P0 |
| 2 | 记忆 | 对话记忆 → 持续因果记忆(护城河) | P0 |
| 3 | 主动性 | 定时模板推送 → 事件驱动主动 Agent | P1 |
| 4 | 多模态 | 拍照识别 → 语音优先 + 持续被动感知 | P1 |
| 5 | 闭环 | Outcome 是配角 → N-of-1 验证为产品中枢 | P0 |
| 6 | 信任 | 有审计日志 → 用户可见的可解释性 | P2 |
| 7 | 聚焦 | 广铺功能 → 深做一个垂直闭环 | P0(战略) |
| 8 | 多模型 panel | 固定三强全开 → Agent 按价值路由 | P1 |
| 9 | 评估可观测 | 有 audit 雏形 → 黄金评估集 + 看板 | **P0(方向一前置)** |
| 10 | 成本延迟 | 不可控 → 预算感知 + 模型分层 + 缓存 | P1 |

> ⚠️ **不可动摇的边界**:Safety Guardian 的 51 条安全裁决**永远确定性**,绝不交给 Agent 自主判断。Agent Native 改造只针对「创造性分析与编排」,安全裁决留在规则引擎。这是健康产品的生死线。
>
> 🔑 **依赖关系**:方向九(评估可观测)是方向一(Agent 自主编排)的**前置**——没有回归基线就让 Agent 自主,等于盲飞。**先建评估集,再全量推自主化。**

---

## 2. 方向一(P0):编排范式 — 从「调度」到「Agent 自主工具调用」

### 现状(双层:动作已 Agent 化,分析仍编排化)
- **动作层 ✅**:`tool_schema_registry` 的 11 个动作工具 + `agent_executor` 多轮 tool-calling 已成熟
- **分析层 ⚠️**:`intent.py::classify_intent` 关键字路由 → `specialists.py::_build_registry` 注册 11 个 specialist 按依赖顺序执行;**不在 agent 工具循环里**
- 每加一个分析能力 = 改 intent 关键字 + 改 registry + 改调度依赖

### 目标态
把 11 个 specialist 并入**已存在的** tool-calling 循环,变成 **Agent 可调用的分析工具**;主 Agent 自己决定调哪个、调几次、怎么组合。Orchestrator 退化成「工具注册表 + 安全护栏 + 结果合成」。

### 落地路径(复用现成 tool-calling 链路,改造成本低)
1. **Phase A**:每个 specialist 包一层 tool schema 注册进 `tool_schema_registry`(`analyze_recovery` / `analyze_fuel` / `analyze_movement` ...),内部逻辑不动,只加工具入口 + 在 `agent_executor._execute_tool` 加 dispatch 分支。**先并 2-3 个高频的(recovery/fuel/movement)灰度验证**,不一次全迁。
2. **Phase B**:主 Agent 一次对话内**自主多轮调用** specialist 工具。共享 context(如 recovery 的 readiness_zone 传给 movement)从「Python 传参」改为「Agent 看到上一个工具结果再决定下一步」。
3. **Phase C**:`classify_intent` 降级为**给 Agent 的 hint**(注入 system prompt 的「可能相关方向」),不再硬路由;trivial query 仍走 lite path 省 token(已有)。
4. **保留**:Safety Guardian **不进 Agent 自主调**——它在每次 Agent 产出**之后**做确定性兜底审查(旁路 + `agent_audit_log`),不依赖 Agent 主动调。
5. **回归基线**:迁移前先抓一组「典型 query → 当前编排输出」快照作为黄金集,Phase A/B 每步用它对比,确保 Agent 自主版本不退化(见方向八「评估」)。

### 收益
- 加新专家 = 加一个 tool,不改路由代码(符合「删代码 > 写代码」)
- 模型自主组合远比手写依赖图灵活(如「这个用户问睡眠,但我看到他 HRV 异常,自动也调 recovery」)
- 护城河从「编排代码」转移到「工具设计质量」

### 风险与缓解
- ⚠️ Agent 乱调工具 / 调用爆炸 → 加 tool 调用轮次上限(已有 `tool_round_limit` 雏形)+ 每工具幂等
- ⚠️ 失去确定性可复现 → 关键医疗结论仍走 Safety Guardian 复核;审计日志记录每次工具调用链

---

## 3. 方向二(P0):记忆 — 持续因果记忆 = 真护城河

### 现状
- Digital Twin = 当前状态快照(14 分区)
- conversation_memory = 最近对话注入 prompt
- LongitudinalAnalyst = 被调用的 specialist,做 6 个月趋势

### 目标态:三层记忆
1. **状态记忆**(已有):Twin 当前快照
2. **情景记忆**(新):关键健康事件的时间线(「3 周前连续熬夜后血糖高」「上月换粮后软便」)
3. **因果记忆**(新):干预 × 结果的因果链(「建议 X → 你做了 Y → 两周后指标 Z 改善」)

### 落地路径
1. 把 LongitudinalAnalyst 从「被调用的 specialist」升级为 **Agent 每次对话默认携带的记忆底座**(注入 system context),而非按需调用
2. 新增 `causal_memory` 表:记录 (干预事件, 时间, 关联指标, 前值, 后值, 评分) —— 复用 Episode 的结构
3. Agent 每次给建议前,默认先看「这个用户历史上类似情况做过什么、有没有用」

### 收益
- **这是对阿福/巨头的结构性护城河**:模型谁都能调,「你这个人 3 年的健康因果史」只有持续陪伴的产品有
- 数据沉淀越深 → Agent 越懂你 → 迁移成本越高 → 续费率越高(直接拉 LTV)

---

## 4. 方向三(P1):主动性 — 事件驱动的 Ambient Agent

### 现状
- 51 个 Celery 定时任务推送**固定模板**(晨报 7:30、异常检测 23:00...)
- Safety Guardian 告警 → 直接弹固定文案

### 目标态
事件驱动的**会思考的主动 Agent**:数据异常 → Agent 自己判断「该不该打扰、用什么语气、给什么行动」,而非触发模板。

### 落地路径
1. Safety Guardian 检出异常 → 不直接推模板,而是触发一个 **主动 Agent 回合**:它读 Twin + 因果记忆,决定「现在该不该说、怎么说、给什么可执行行动」
2. 加「打扰预算」:critical 穿透(已有 quiet-hours bypass),其余按用户疲劳度/历史响应率调频次,避免变成骚扰
3. 主动消息也进闭环:用户响应了吗?行动做了吗?进 causal_memory

### 收益
- 把「被动健康管理」变「主动健康守护」——这是 Health OS 定位的灵魂
- 解决用户最大痛点:「我不知道我不知道什么」

### 风险
- ⚠️ 主动 = 双刃,推多了卸载。必须有疲劳度模型 + 用户可调频次。**宁可少推、推得准**。

---

## 5. 方向四(P1):多模态 — 语音优先 + 持续被动感知

### 现状:拍照记录(食物/补剂/体检)+ voice-chat(备选入口)

### 目标态
1. **语音成为第一入口**(不是备选):健康场景天然适合语音(开车/做饭/躺床)。「今天感觉累」一句话 → Agent 自动关联 HRV/睡眠/训练负荷给判断
2. **拍照进 Twin 做纵向对比**:这次体检 vs 上次;伤口 7 天愈合趋势;不止识别,要进时间线

### 落地路径
1. voice-chat 提到首页主入口级别;优化「一句话 → 多源关联判断」的 prompt
2. 图片识别结果默认写入 Twin 对应分区 + 与历史对比

---

## 6. 方向五(P0):闭环 — N-of-1 验证提为产品中枢 ⭐

> 这是最该重投的方向。Episode N-of-1 闭环是**最独特、却还没做成主线**的资产。

### 现状:闭环在 supplement_advisor 里,是一个能力

### 目标态
把「建议 → 接受 → 执行 → 设备/用户验证 → 结果评分 → 下次调整」提升为**操作系统级循环**,所有 specialist 的建议都进这个闭环。

### Agent Native 的升华:Agent 自己设计实验
> 「要验证镁对你睡眠有没有用,我们做个 2 周对照:单周补、单周不补,我盯着你的深睡数据告诉你结论。」

Agent 从「建议者」变「**研究者**」——这是任何竞品(尤其阿福这种导流平台)结构上做不了的。

### 落地路径
1. 把 Episode 闭环从 supplement_advisor 抽到**通用层**,所有建议(运动/饮食/补剂/睡眠)都能挂 Episode
2. Agent 能**主动发起 N-of-1 实验**:设计对照、设置追踪指标、到期自动出结论
3. 首页做一个「**进行中的健康实验**」模块,展示「第 X 天 / 已观察到 Y」

### 收益
- 阿福结构上做不了(它要导流变现,不要留客追踪)——见竞品分析
- 巨头最难抄(改的是商业模式不是功能)
- 直接产出「可展示的真实改善案例」——融资 + 留存双杀

---

## 7. 方向六(P2):信任 — 可解释性做成用户可见

### 现状:evidence/confidence/claim boundary + 审计日志(后端已有,前瞻)

### 目标态:每条建议可展开看「**为什么 Agent 这么说**」——基于哪些数据、置信度多少、哪条规则触发

### 收益:健康场景信任 = 复购;比「黑盒大模型问答」的结构性优势

---

## 8. 方向七(P0 战略):聚焦 — 深做一个垂直闭环

### 判断
Agent Native 时代,**功能边际价值下降**(模型能力在涨),**数据深度/闭环验证边际价值上升**。继续铺功能(已有 11 specialist + 多端)是上一代打法。

### 建议
挑**一个**能跑通完整闭环的垂直场景 —— **推荐代谢/血糖 或 睡眠**(数据密、可穿戴可测、干预可验证、付费意愿强):
```
基因/可穿戴 → AI 建议 → N-of-1 验证 → 真实指标改善 → 可展示案例
```
做到能产出 **3 个可展示的真实改善案例**。这比 11 个浅功能,对融资和留存都更值钱。

---

## 8b. 方向八(P1):多模型 panel — 从「固定三强综合」到「按需路由」

> 本次复核新增。代码已有 `_run_multi_model_stream`(Opus 4.7 lead + GPT-5.5 + Gemini 3.1 Pro 并发综合),这是真资产,但当前是「固定三强、全量跑」。

### 现状
- 多模型综合 = 三个旗舰并发跑同一上下文再由 lead 综合。质量高,但**贵 + 慢**(3× token,延迟叠加)
- per-user / per-request 已能切模型(`create_provider_for_user` / `create_provider_for_model_id`)

### 目标态:Agent 自己决定「这个问题值不值得开 panel」
- **分诊**:trivial / 记录类 → 单个快模型(GLM-5 / DeepSeek V4,便宜);高风险 / 高分歧 / 用户明确要「多专家会诊」→ 才开三强 panel
- **分歧即信号**:三强结论分歧大 = 这是个真不确定的健康问题,主动告诉用户「这事专家也没共识,建议就医」——比假装确定更可信
- Safety 相关永远走最强模型 + 确定性规则双保险

### 收益:把 panel 从「默认全开」变「按价值开」,省 50%+ 成本,延迟可控,且分歧本身成为诚实信号

---

## 8c. 方向九(P0):评估与可观测 — Agent 自主化的安全网

> 本次复核新增。**这是方向一能否安全落地的前置条件,优先级 P0。** 一旦 Agent 自主编排,行为不再确定可复现,没有评估集就是盲飞。

### 现状
- 有 `agent_audit_log`(每次决策旁路记录)、`tests/eval_runner.py` 雏形
- 但缺「Agent 行为回归基线」——改了 prompt / 换了模型 / specialist 工具化后,**怎么知道没变笨**?

### 目标态
1. **黄金评估集**:50-100 条「典型 query → 期望行为(调了哪些工具 / 关键结论 / 安全是否触发)」,每次 Agent 改动 CI 里跑,对比是否退化
2. **LLM-as-judge**:对开放回答用一个裁判模型打分(有用性 / 安全性 / 是否幻觉),纳入 CI
3. **线上可观测**:audit_log 聚合成看板——工具调用分布、失败率、finish_reason=length 比例、人均轮次(防 Agent 自主后调用爆炸)

### 收益:让「Agent 自主编排」从「不敢上」变「敢上、出问题能发现」。**没有这层,方向一不该全量推。**

---

## 8d. 方向十(P1):成本与延迟 — Agent 自主的隐性账单

> 本次复核新增。Agent 自主多轮调用工具 = token 消耗和延迟比固定编排更难预测。

### 风险
- Agent 自主决定调几次工具 → 最坏情况调用爆炸(已有 `tool_round_limit` 兜底,但要监控实际分布)
- 多模型 panel + 自主编排叠加 → 单次对话成本可能 10×
- 健康 query 常需长回复(已踩过 max_tokens 截断坑)→ token 成本天然高

### 目标态
- **预算感知编排**:给 Agent 一个「本次对话 token 预算」,trivial 省着用,复杂才放开
- **缓存**:Twin → prompt blob 已有 Redis 5min 缓存;扩展到「相同 query + 相同 Twin 状态」的回答缓存
- **模型分层**:便宜模型做 80% 的轻活,旗舰只做高价值 20%(呼应方向八)
- 成本/延迟进方向九的看板,作为一等指标

### 收益:Agent Native 不等于「无脑烧最贵的模型」;单位经济(呼应 BP 财务模型的 CAC/毛利)直接受此影响

---

## 9. 优先级与排期(12-18 个月)

### 本周可做的最小起点(把抽象规划落地的第一步)
1. **抓黄金集**(方向九):跑 30-50 条典型 query,把当前 orchestrator 编排的输出存为快照基线
2. **工具化 1 个 specialist**(方向一 Phase A 试点):选 RecoveryCoach,包 tool schema + 加 `_execute_tool` dispatch 分支,灰度对比新旧输出
3. 这两步合起来就是一个可独立 review/部署的 PR,且不碰 Safety——风险最小、验证 Agent 自主化是否可行

### Phase 1(0-3 月):奠基 + 选垂直 + 评估网
- [P0] **方向九(前置)**:建黄金评估集(50-100 条)+ CI 跑回归 + audit_log 看板雏形 —— **先于方向一全量推**
- [P0] 方向七:选定垂直场景(代谢 or 睡眠),定义「闭环跑通」的成功指标
- [P0] 方向五:Episode 闭环从 supplement_advisor 抽到通用层
- [P0] 方向一 Phase A:specialist 包 tool schema(先 2-3 个高频的,不改内部逻辑,用评估集对比)
- 目标:垂直场景能跑通 1 个完整闭环 + 3 个种子用户改善案例雏形 + 评估集进 CI

### Phase 2(3-9 月):Agent 自主化 + 记忆 + 成本
- [P0] 方向一 Phase B/C:Agent 自主调用 specialist 工具,intent 降级为 hint(每步过评估集)
- [P0] 方向二:三层记忆,LongitudinalAnalyst 升为默认记忆底座 + causal_memory 表
- [P1] 方向八:多模型 panel 改按需路由(分诊 + 分歧信号)
- [P1] 方向十:预算感知编排 + 模型分层 + 回答缓存
- [P1] 方向四:语音提为首页主入口
- 目标:Agent 自主编排(评估不退化)+ 携带因果记忆;单次成本可控;3 个可展示改善案例达成

### Phase 3(9-18 月):主动 + 信任 + 规模
- [P1] 方向三:Safety 告警接主动 Agent + 打扰预算
- [P1] 方向五升华:Agent 自主设计 N-of-1 实验 + 首页「进行中实验」
- [P2] 方向六:可解释性做成用户可见
- 目标:从「被动问答」全面转为「主动守护 + 自主验证」

---

## 10. 衡量指标(对齐 BP 的 Agent 产品指标,非 DAU)

**产品/留存指标**
- **WSCLA**:每周安全闭环行动数(核心)
- **Plan Adherence**:每日计划完成率
- **Outcome Delta**:体重/血压/睡眠/HRV/血脂 真实改善
- **因果记忆深度**:人均累计 Episode 数 / 验证过的干预数
- **主动命中率**:主动消息的用户响应率(防骚扰)
- **Trust Score**:建议可信比例

**Agent 工程指标(方向九/十,Agent Native 必看)**
- **评估集通过率**:每次改动 vs 黄金集的回归得分(防变笨)
- **幻觉率 / 安全触发准确率**:LLM-as-judge 抽检
- **人均工具调用轮次**:监控 Agent 自主后是否调用爆炸
- **单次对话成本 / P95 延迟**:Agent 自主 + panel 的隐性账单(直接影响 BP 毛利)
- **finish_reason=length 比例**:回复被截断率(已修 max_tokens,需持续盯)

---

## 11. 一句话总结

> **Agent Native 时代的个人健康产品 = 一个有长期因果记忆、能主动出手、自己设计验证实验的 Agent,跑在确定性安全护栏与可观测评估网之上,以独家健康数据为护城河。** HealthPilot 的**动作层已 Agent 化**(11 工具 tool-calling + 多模型 panel 已落地),缺的是:① 把**分析层** 11 个 specialist 也并入这个循环;② 把对话记忆升级为**因果记忆**;③ 把 N-of-1 闭环从配角提为**产品中枢**;④ 在自主化之前先建**评估网**(方向九),别盲飞。

---

## 12. 本次优化变更记录(2026-06,基于最新代码复核)
- 校正:系统是**双层**——动作层已 tool-calling(11 工具),分析层(11 specialist)仍编排化。方向一从「从零工具化」修正为「并入现有循环」,成本更低
- 新增方向八(多模型 panel 按需路由)、九(评估可观测,定为方向一的 P0 前置)、十(成本延迟)——均来自最新代码已有 `_run_multi_model_stream` / 多 provider / audit_log 的现实
- 新增「本周可做的最小起点」:抓黄金集 + 工具化 1 个 specialist = 一个可独立部署的低风险 PR
- 补充 Agent 工程指标(评估通过率/幻觉率/调用轮次/单次成本/截断率)
- 纳入近期已修的 Agent 健壮性债务(max_tokens 截断、_api_get_json),作为 Agent Native 化的前置清理证据

---

## 附:诚实声明
本 RFC 是**战略判断 + 对本仓库代码的实际了解**,不是已验证的市场调研。Agent Native 趋势判断、各方向收益是基于当前模型能力的推断;架构数字(11 specialist / 11 工具 / 51 规则 / 14 分区 / 51 Celery 任务)为 2026-06 复核值,会随代码演进漂移——以 `scripts/check_doc_drift.py` 和现场为准。落地前每个 P0 方向建议先跑 feature-plan(四问 + ASCII 数据流 + 边界确认)再开工。Safety Guardian 确定性边界是唯一不可妥协项。
