# LLM Token 消耗与性能优化方案(实测版)

> 2026-07-08 · 方法:4 区并行审计,在 backend venv 内真渲染 prompt 量长度(实测与推导分开标注)。
> 原则:效果第一 —— 先做「不减内容的省」(缓存/去重复支付/路由分层),再做「减内容的省」(裁剪/摘要);每条带 eval 质量闸,基线先行。

## 一、每回合 Token 解剖(实测)

| 组件 | 实测大小 | 重发/占比说明 |
|---|---|---|
| 工具 schema JSON(get_health_tools,14 个) | 实测 18,064 chars ≈ 5,200–6,400 tokens;big-3(health_record 4,375/health_query 3,074/health_manage 2,372)=54% | 每个工具决策轮全量重发;可靠模型的合成轮也再发一次;fast/lite 回合零裁剪(占 lite 输入 ~70%) |
| orchestrator tool result(深分析回合) | 实测 15,755 chars,其中 findings[]=14,675(93%),synthesis 仅 420 | 每个深分析回合 1 次,_api_post 无截断,原样喂 agent 二次合成强模型(双合成=37-75s 根因) |
| 对话历史(build_messages limit=15 原文) | 实测满窗 ~10,290 chars ≈ 6,800 tokens(真实回复 p50=1,332/p90=2,077 chars,n=110) | 每轮重发,无摘要;第 8 个来回起早期上下文被硬切丢弃 |
| full system prompt | 实测空用户 5,461 chars(静态骨架 4,233);真实用户推导 8–12K(叠 liver/blood/gene/memory/effect blob) | 每轮 messages[0] 重发;turn-scoped KB 证据块拼在 system 尾部→每轮字节变化,破坏前缀缓存 |
| 分析 blob 栈(liver/blood/gene/worldview/干预/效应/记忆) | 静态部分实测 worldview 579+基因 356+gene安全 359;真实用户推导 1,500–3,500 chars/轮 | 非 fast 回合无条件全量注入,无 query 维度门控(问血压也背肝酶趋势) |
| menu_share + 基因解读规则块 | 实测 739+356=1,095 chars ≈ 730 tokens | 意图专属(问吃啥/问基因才有用)却硬编码每轮全发,占空用户 full prompt 20% |
| orchestrator 合成 prompt(管道内部) | 实测 5,463 chars(system 2,482+user 2,981;findings_text 1,838/twin_blob 887) | 每深分析回合 1 次;twin blob 已高度优化(453–887),非浪费点 |
| prompt caching / usage 观测 | 实测 0 处 cache_control;provider 丢弃 response.usage;tiktoken 未装→永远 len/4 估算兜底 | 所有前缀全价重 prefill;百炼隐式缓存(命中价 40%)是否生效完全不可见 |

## 二、优化计划(按 节省×置信度÷effort 排序)

### 1. [S] provider 层透传 usage + cached_tokens 落库(一切验收的前置)

- **做**:openai_provider.py chat()/chat_stream(stream_options.include_usage) 读 response.usage,把 prompt/completion/cached_tokens 透传 usage_tracker,llm_usage_logs 加 cached_tokens 列;API 真值优先、估算只作兜底。上线拉一周 caller×model 分布,核实 TokenPlan 套餐口径下百炼隐式缓存是否折抵配额
- **省**:直接 0;解锁 rank 5/6/8 的实测验收 + 总账占比测算(不做它,所有缓存优化都无法证明命中)
- **质量闸**:纯旁路观测零输出风险;既有 usage_tracker pytest 全绿 + 部署后 journalctl 抽一条真实请求确认 cached_tokens 非空

### 2. [S] fast/lite 回合工具 schema 白名单子集(最高频路径 -60%)

- **做**:get_health_tools 加 subset 参数;agent_executor.py:3691 在 _fast_route_simple_turn=True 时固定发 {health_record, health_query, health_manage}(子集固定不随消息变,保前缀字节稳定);fast 模型吐子集外工具名→走既有丢弃重合成兜底升级全集
- **省**:实测 fast 轮工具 prefill 18,064→~6,700 chars,省 ~11,300 chars ≈ 3,200 tokens/轮;fast 是最高频路径,且缩短 qwen3.6-flash prefill 再压 1–2s 时延
- **质量闸**:smoke_fast_tool_model.py 真网跑记录/查询/删改/提醒四类带数值参数,断言工具名+参数无损;tests/test_agent_executor_fast_routing.py 全绿;加『记录+分析复合意图』对抗样例断言正确升级全集

### 3. [S] orchestrator tool result 投影:只回 synthesis + 4 字段精简 findings

- **做**:_exec_health_analysis(agent_executor.py:6795)解析 orchestrator JSON 后重组:{synthesis, used_specialists, 每 specialist 的 severity_label/title/action/evidence_refs},彻底丢 finding.raw/intent/富字段(审计/前端另走 reasoning-trace 端点,不进 LLM 上下文)
- **省**:实测 15,755→~2,400 chars,省 ~13,300 chars ≈ 3,800–5,500 tokens/深分析回合;同时降弱模型 JSON 回显风险
- **质量闸**:evals/comparative judge 对比裁剪前后答案证据完整度不降;KB 引用率(record_kb_citation_usage)不降;既有防回显测试(_leaks_tool_result_json)继续绿

### 4. [S] 合成轮不再重发 18KB 工具 schema(可靠模型也置空)

- **做**:agent_executor.py:3747-3751 round_tools 逻辑改为『上一轮已无 tool_calls / 进入最终合成』时对所有模型置 round_tools=[](现只对不可靠工具模型生效)
- **省**:每个带二次合成的回合省 18,064 chars ≈ 5,000 tokens 输入(推导;若 rank 7 透传落地则此项自动消失)
- **质量闸**:run_xiaoba 深分析+复合意图回合,验证无因缺 tools 漏调(如 orchestrator 后还想 knowledge_search 的场景用保守条件『上一轮无 tool_calls 才置空』规避)

### 5. [S] menu_share + 基因解读块按意图门控

- **做**:agent_executor.py:4736-4770 两个硬编码块加关键词门控:menu_share 按餐食/菜单词注入;基因解读按基因/SNP 词或 twin 有基因数据注入;均不涉安全可放心裁
- **省**:非匹配回合每轮省实测 1,095 chars ≈ 730 tokens(空用户 full prompt 的 20%)
- **质量闸**:evals 菜单/基因案例回归确认门控命中(漏注入最坏=该回合不出菜单卡,无安全影响)

### 6. [M] 前缀缓存排布:turn-scoped 内容移出 system + provider 缓存探针

- **做**:KB 证据块/opener note/入口上下文从 system 尾(agent_executor.py:3599-3632)移到最后一条 user message;system 只留慢变内容,保证跨轮字节稳定前缀=system+tools+history;同时对 LangBridge→Claude 路径探针 anthropic cache_control ephemeral,qwen 直连以 usage.cached_tokens 核实百炼隐式缓存命中
- **省**:推导:多轮回合每轮多命中 5–10K tokens,按百炼命中价 40% 计输入成本 -20~35%/轮 + TTFT 同步降;以 rank 1 落库的 cached_tokens 真值验收,不以假设宣告
- **质量闸**:KB 依据从 system 移 user 可能改引用行为:system_knowledge_eval KB 引用 eval + run_xiaoba --only 生产 eval + judge 新旧排布 A/B,引用率与裁决不劣化才合

### 7. [M] 深分析短路二次合成:orchestrator synthesis 直接透传(影子先行)

- **做**:orchestrator 是本回合唯一工具且 synthesis 非空时,跳过 agent 第 2 次强模型合成,把 synthesis(已过 advice_guard/R4)直接流式下发;多工具/需对话融合的回合保留二次合成作降级分支;先 DISABLED 影子对比再灰度
- **省**:省 1 整次强模型调用:输入 ~11–13K tokens+输出,深分析回合时延实测量级 -5~15s(强模型生成+LangBridge 非流式 buffer),该类回合合成侧成本约 -50%
- **质量闸**:evals/comparative judge 对 20-30 条深分析 query 做 passthrough-vs-双合成 pairwise,win-rate≥平手;invariant_judge 跑 R4 不变量;run_xiaoba user3 真账号核实答案不降级;不达标不切

### 8. [M] 30 个内部辅助调用点从默认强模型降档 flash(分两批)

- **做**:批1(零 R4 风险纯抽取):memory 抽取×2/dialog extractor/directive_parser/kb_reconciliation_judge/action_card_extractor 照抄 starter_polish 模式显式 create_provider_for_model_id(默认 deepseek-v4-flash,settings 可配可回滚);批2(用户可见非医疗)走 task_tier=casual;orchestrator 合成/safety explain 正文不动
- **省**:这些调用点单价 -80~90%(flash vs reasoning 档 5–10×);占总账比例待 rank 1 落库后按 caller 拉分布核实;clarification 类同步路径时延 10s+→1–3s
- **质量闸**:每个改点按 smoke_fast_tool_model.py 模式写真网 smoke(10 条真实样例断言 JSON 可解析字段齐);kb judge 另跑 system_knowledge_eval;逐点灰度

### 9. [S] 去掉两处短窗重复计算:advice 轮 build_twin no-cache + /safety/explain 无缓存

- **做**:agent_executor.py:4975 use_cache=False→True,新鲜度改由写路径落库后调 twin invalidate(补齐缺口);api/safety.py:358-410 加结果缓存键 (user_id, rule_id, sha256(data_citation)) TTL 1h,照抄同文件 :73 既有 RedisCache 模式
- **省**:advice 轮 pre-first-token 省一次全量 14 分区 Twin 重建(推导数百 ms–2s,生产 kb_ms 可前后对比);safety 解读重复点击 LLM 调用命中时 -100%
- **质量闸**:补『导入化验→invalidate→立即提问,断言 KB 证据卡含新指标』集成测试打到 consumer;safety 缓存两例:同键二次命中 + data_citation 变更必 miss

### 10. [L] 减内容的省(最后做,强闸):分析 blob 意图门控 + 历史滚动摘要

- **做**:① agent_executor.py:4809-4895 的 liver/blood/gene 等 blob 用 health_query_dimensions.py 做白名单门控(worldview/R4/安全恒发,只裁明确无关的趋势 blob);② 历史改『最近 2-3 轮 verbatim + 更早轮结构化摘要』,摘要失败 fail-open 退回原文
- **省**:blob 门控真实用户推导 1,000–2,300 tokens/轮;历史摘要长对话推导 2,000–3,000 tokens/轮(且以摘要保住第 8 轮前被硬切的上下文)
- **质量闸**:风险最高:evals/comparative 按血压/睡眠/化验分维度前后对比 judge 不降;run_xiaoba 加多轮跟进用例(第 N 轮引用第 1 轮结论);safety eval 零回归;最近 2-3 轮永不进摘要(fast path 丢跟进上下文的历史教训)

### 11. [S] 合成轮思考封顶(qwen `thinking_budget` / `enable_thinking`)——**最大单杠杆,已接线 ships-flag-off**
- **背景**:prod qwen3.7-max 合成轮 in-call TTFT p50 ~20-24s,是首个可见 token 前那段**沉默的思考阶段**;最终答案却只 ~373 real completion tokens。假说=隐藏思考吃掉墙钟。
- **探针实证**(2026-07-12,真网络 `backend/scripts/probe_qwen_thinking_budget.py`,单样本决定性,Δ 达 20s+):

  | variant | placement | ttft_content | total | completion | reasoning |
  |---|---|---|---|---|---|
  | qwen default(思考开) | n-a | **35.82s** | 52.64s | 2802 | 1898 |
  | qwen `enable_thinking=false` | extra_body 顶层 | **1.61s** (↓95%) | 20.03s | 1024 | — |
  | qwen `thinking_budget=512` | extra_body 顶层 | **10.99s** (↓69%) | 29.55s | 1541 | 512 |

  - **Lever 1(封顶/关思考)= SUPPORTED**:`extra_body` **顶层**放置生效(`parameters` 嵌套不需要);TTFT 从 ~36s 塌到 1.6s(关)/ 11s(封顶 512)。
  - **Lever 2(思考流可视化)= SUPPORTED**:流式**暴露** `reasoning_content` delta——首个 reasoning delta @ 1.67s,首个可见 content @ 35.82s → 那 ~34s 死气可用**真实思考流**填进现有「思考过程」UI(非破坏性,保留思考)。本 rank 只接了 Lever 1;Lever 2 是独立的未来 UI 项。
- **已接线**(默认关,`SYNTHESIS_THINKING_BUDGET=0`):
  - `ModelEntry.supports_thinking_budget`(fail-closed 白名单,仅探针验证过的 `qwen3.7-max` 置 True);`OpenAIProvider._apply_thinking_controls`(参数折进 extra_body);`config.synthesis_thinking_budget`(int,0=关);`agent_executor._maybe_apply_synthesis_thinking_budget`(只在**无 tools 的合成/答案轮**注入,`_turn_invoked_deep_analysis`=True 即 health_analysis 深分析轮**fail-closed 跳过**保留完整思考,绝不碰工具决策轮)。
- **enable-runbook(评测闸,过了才可翻 flag)**:
  1. `pytest tests/test_openai_provider_thinking_budget.py tests/test_agent_executor_thinking_budget.py tests/test_synthesis_invariant_eval.py`(离线,已绿);
  2. 铸基线:`SYNTHESIS_THINKING_BUDGET=0` 跑 `python -m evals.comparative.cadence --run-id <sha>-base --judge-model <非参赛模型>`(需 eval token/出网)+ `run_xiaoba --only`(user3 真账号)存快照;
  3. 候选:`SYNTHESIS_THINKING_BUDGET=512`(先取封顶而非全关——保留部分思考更契合医疗 fail-closed)重跑同集;`eval/scorers/invariant_judge.py` deterministic 层**零新增违规**、cadence 家族漂移 exit 0(`--drift-threshold 0.5` 默认,**safety_refusal 家族 overall 掉幅 ≤0.5**)、KB 引用率不降,三条全过;
  4. 三条全绿再把 prod `.env` 的 `SYNTHESIS_THINKING_BUDGET` 置 512(走根 `.env` → `deploy.sh -e`);任一不过维持 0。
- **省**:合成轮 TTFT ~20s→~11s(封顶)乃至 ~2s(全关);纯延迟杠杆,不改 token 账,但深分析轮不受影响(gated)。**风险**:面向用户医疗正文的思考深度下降 → 故 ships-disabled + 上述闸。

## 三、整体质量护栏

- 基线先行:任何改动合入前,先用当前 main 铸基线——run_xiaoba --only(user3 真账号)记录/查询/深分析三类 + evals/comparative judge 快照 + baselines/safety_main.json;改后同集对照,win-rate≥平手且安全零回归才合
- 工具路由类改动(rank 2/4)一律 smoke_fast_tool_model.py 真网 eval 闸:断言工具名正确 + 数值参数无损(饮水 ml/体重/血压——历史 2000→250 静默错值教训),白名单 fail-open,拿不准回退全集
- 任何 prompt 内容裁剪(rank 5/10)必过 invariant_judge R4 不变量 + safety eval:worldview/R4 边界/安全免责块永不进门控,只裁明确无关块
- 缓存/成本类(rank 1/6)只认 provider 返回的 usage.cached_tokens 实测数字验收,禁止以『理论上会命中』宣告胜利;tiktoken 估算仅作缺失兜底
- 深分析短路(rank 7)必须影子模式先行:DISABLED 开关 + passthrough-vs-双合成 pairwise judge ≥平手 + KB 引用率不降,三条全过才灰度
- 合成轮思考封顶(rank 11)ships-disabled(`SYNTHESIS_THINKING_BUDGET=0`):翻 flag 前必过 invariant_judge deterministic 零新增违规 + cadence safety_refusal 掉幅 ≤0.5 + KB 引用率不降;深分析/health_analysis 轮恒 fail-closed 跳过(保留完整思考);只对探针验证过的 qwen 模型注入(fail-closed 白名单,免端点 400)

## 四、明确不做

- 别压缩 big-3 工具的 worked-example(health_record 逐 type 示例 JSON)——它们是弱模型(glm/minimax)防丢量参的护栏,历史已烧过饮水 2000→250 默认值和 float→int 422 整批失败;要动必须先过参数完整率硬闸,收益(~1K tokens)配不上风险
- 别裁 worldview / R4 边界 / 安全免责 / gene 安全块——安全底座恒发,任何意图门控都不许碰;漏注入的代价是不安全建议,不是多花几百 token
- 别动已优化的点:IQS 证据块(已有 2200 char 硬预算)、twin_to_prompt_blob(实测仅 453–887 chars)、starter_polish(已 flash+sig_hash 缓存)、conversation_opener(纯规则零 LLM)、跨轮工具结果(本就不重发)
- 别对最近 2-3 轮对话历史做摘要或剔除——fast path 曾因剔上轮 assistant 丢跟进上下文(MEMORY 教训);摘要只碰更早轮次且生成失败 fail-open 回原文
- 别做动态 per-message 工具挑选或 denylist 式裁剪——逐消息变化的工具集会拆掉前缀缓存(与 rank 6 收益互斥),denylist 漏裁即静默数据丢失;一律固定白名单子集 + 拿不准回退全集

---
*来源:token-perf-optimization-audit workflow(wf_5971e7a9-073),4 审计区 + 综合;实测环境 = backend venv + in-memory SQLite。*
