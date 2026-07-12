# Agent 对话时延优化 Phase 2 路线图(2026-07-13)

> 产出方式:业界/GitHub 最佳实践检索 + DashScope 厂商特性调研 + 内部代码勘探,逐条对 prod 实测解剖数据(7d n=231 回合)做可行性核算后排序。
> Phase 1 已落地:工具轮 fast 路由三级跳(34s→1.5s)、合成轮停发 schema、重试流式化、KB 去重、思考流直播、前缀布局。
> 已被闸门否决(勿重提):thinking_budget=512(双基线证伪)、deepseek-v3.2(founder 否决)、深分析直通(shadow 证伪前提)。

## 路线图(按 预期秒数×回合占比 / 风险×工时 排序)

### rank 1 · GenUI-first 数据回答:确定性 metric_table 卡片 + ≤300字叙事契约  `prose-quality` `M`

强模型以 12-13 tok/s 把工具结果重新打成大 markdown 表是剩余 decode 税的主因,且 mac 客户端指令在以'最高优先级格式要求'主动强制表格(自伤)。改为后端从已在 messages 里的工具结果确定性生成 metric_table reva-ui 块(零 LLM token,R4 构造性合规),正文只写 2-3 条结论+行动(≤300字);caps 协商、客户端组件注册表、R4 strip 守卫、genui 确定性短路先例全部已就绪。并吸收 industry 条目的显式输出预算行('结论先行, ≤N字, 数据引用卡片')。

- **预期**:数据密集的 chat-advice(28%)与 query(25%)回答省 15-40s(450-1000+ 解码 token → ~150-300);全清单最大单一 founder 可见收益
- **上线闸**:双基线质量 eval(叙事契约重塑 founder 可见医疗文本)+ 三端卡片渲染验证(mobile/mac/web caps 差异)+ strip_reva_ui_blocks 防 LLM 伪造块回归
- **出处**:apps/mac/Sources/HealthAgentMacCore/AgentChatViewModel.swift:1837; backend/app/services/genui/chart_builder.py:39-44; backend/app/api/agent.py:283-399; mobile/utils/revaUiBlocks.ts:4-12

### rank 2 · 确定性查询直出:把 fast-record 的'跳过合成轮 break'扩展到 top-5 高频查询形状  `pure-perf` `M`

record 路径已证明该模式(写工具执行后确定性回复 + break,合成轮不跑),查询侧没有对应物,_natural_language_from_tool_results 只是泄漏兜底。补每维度确定性格式化器(水/体重/睡眠/步数/血压,各约50行)+ 对 fast-route 只读回合同样 break;二期对正则无歧义形状('今天喝了多少水')直接 message→dimension 短路,零 LLM 调用。纯数据读数无医疗文本,R4 干净。

- **预期**:query(25%)中每日读数子集从 ~10-30s → ~2s(一期);二期亚秒;是查询类的整段成本清零
- **上线闸**:每维度格式化器正确性测试(算错饮水总量=信任 bug)+ '查询回合绝不谎报/执行写操作'硬门保持 + 读数只允许渲染自真实 tool result
- **出处**:backend/app/services/agent_executor.py:4270-4289, 694-717, 2229-2232; backend/app/services/health_read.py:51-75

### rank 3 · DashScope 显式上下文缓存(cache_control ephemeral)钉死 14.4k prefill  `pure-perf` `M`

tokenplan 就是官方 cn-beijing compatible-mode 端点,无第三方代理,支持 Anthropic 式显式缓存(4 标记/块≥1024 token/5min TTL 命中续期/命中 10% 价)。把 29% 的概率性隐式命中变成多轮会话内近确定命中;同时是并行分段合成与 chip 预生成的 fan-out 成本使能器。标记布局映射到已核实的 prompt 结构:静态跨用户块+基因注册表 → 用户档案 → 历史前缀。

- **预期**:所有回合类的合成轮 TTFT 省 1-3s(跳过 ~10-14k token prefill,间隔<5min 的轮次);缓存前缀输入成本降 ~90%
- **上线闸**:第0步:在 3593-3598 旁记一行 per-call prefix hash 量测跨轮前缀分歧;真网单发验证 usage.prompt_tokens_details.cached_tokens 透传;与历史摘要联动约束(摘要必须 append-only 否则互杀);flash/max 各自标记(缓存 per-model 不共享)
- **出处**:https://help.aliyun.com/zh/model-studio/explicit-cache-guide; backend/app/services/agent_executor.py:4694-4781, 3593-3598; backend/app/config.py:62

### rank 4 · LLM 连接复用:消灭 per-round TLS 握手税  `pure-perf` `S`

create_provider_for_user 文档自认'每次都新建 (不缓存)',每轮新 provider → 新 OpenAI client → 新 httpx 连接池;prod 的 task_tiered_routing + per-user 偏好让多数真实轮次走重建路径,每轮付一次 TCP+TLS 握手。修法:module 级按 (base_url, api_key) memoize 原始 client/连接池,wrapper 仍 per-call,'用户切换立即生效'契约不动(路由在请求参数不在连接)。

- **预期**:每回合稳省 0.1-0.6s(~50-300ms 握手 × 2-3 轮)+ 消除握手尾部方差;对 ~2s 快路径 record 回合(40%)相对收益最大
- **上线闸**:用户切模型立即生效回归 + 并发下共享池无 key 串号;注意 5549 直调路径已 per-turn 复用,别重复修
- **出处**:backend/app/services/llm/factory.py:228-233; backend/app/services/llm/providers/openai_provider.py:33-48; backend/app/services/agent_executor.py:5032-5095

### rank 5 · parallel_tool_calls=true:多轮工具回合折叠成一轮  `pure-perf` `S`

DashScope 默认每响应只回一个 tool call,而我们的 fast-record prompt 在主动要求'一次性发起多个 tool_call'——在用 prompt 索要被 API 旗标压制的行为,所以这大概率是真收益。客户端多 index tool_calls 累积已就绪,改动=传旗标+eval;只动工具决策轮,合成文本不受影响,R4 不碰。

- **预期**:多条目 record/query 回合(record 40% + query 25% 子集)每折叠一轮省 1.5-3s;与并行读工具执行复利
- **上线闸**:smoke_fast_tool_model.py 式真网 eval 验 qwen3.6-flash 多 call 可靠性后才开;丢弃重合成兜底网保持
- **出处**:https://www.alibabacloud.com/help/en/model-studio/qwen-function-calling; backend/app/services/agent_executor.py:1072-1076; backend/app/services/llm/providers/openai_provider.py:176-215

### rank 6 · 修 chat_stream 事件循环阻塞(async generator 里同步迭代流)  `pure-perf` `S`

流用 asyncio.to_thread 创建但随后 `for chunk in response:` 同步迭代,每个 inter-chunk 网络等待(~80ms @ 12-13 tok/s)阻塞整个 event loop——一条在飞合成流拖住所有其他回合的 SSE flush、工具执行、TTFT。换 AsyncOpenAI(同 SDK drop-in)或 worker 线程泵入 asyncio.Queue。与历史 IncompleteRead 并发事故签名一致,正确性级修复。

- **预期**:当前 n=231/7d 单用户主导流量下 p50≈0;≥2 回合重叠时彻底消除跨用户 p95 饥饿/延迟耦合
- **上线闸**:tool_call chunk 按 index 累积的回归测试;流式中断/取消行为保持
- **出处**:backend/app/services/llm/providers/openai_provider.py:172-217; backend/app/services/llm/factory.py:64-71

### rank 7 · Starter chip 答案预生成(signals_hash 新鲜度门,polish cache 模式上移一层)  `safety-adjacent` `M`

默认 chips('分析我最近的代谢健康')路由到最慢的 deep-analysis 类。全部基建已 shipped:signals_hash 内容摘要(任何卡片数据变化即翻转)、BackgroundTasks 响应路径外预热模式、确定性答案 SSE 回放+持久化先例。tap 时重算 hash,任何不匹配或间隔写入 → fail-closed 落回 live turn;答案是完整强模型输出,R4 完好。

- **预期**:chip 入口回合(不成比例地是那批 ~40s 的)感知延迟 ~30-40s → ~0(命中时);命中率=CTR×same-hash 率,先测再扩
- **上线闸**:tap 时新鲜度检查必须 fail-closed(预生成医疗答案绝不对已变化数据出示)+ 投机 token 成本上限(限 served chips,先 top-1/2)+ 命中率量测决定是否扩
- **出处**:backend/app/services/starter_polish.py:461-472; backend/app/api/agent.py:357-399, 1219-1237; backend/app/services/conversation_starters.py:33-38

### rank 8 · 进程内工具执行:扩展 canonical read 层 + 替换 orchestrator 内层 localhost HTTP  `pure-perf` `M`

每个工具调用经 loopback HTTP + 全 FastAPI 中间件重入,orchestrator 工具仍 POST /orchestrator/chat 非流式——正是 60s 中间件击杀那类故障的老路。迁移缝已证明(health_read.canonical_read 已进程内服务 exam+wearable 维度),run_orchestrator 直接收 (db, user_id, req)。逐维度增量、低爆炸半径;还解锁 stream_orchestrator 分段流式(rank 11 前置)。

- **预期**:有工具回合每回合省 0.1-0.5s + 根除深分析路径的 60s 中间件击杀故障类;是深报告分段流式的前置
- **上线闸**:开工前先查并行 session 是否已修内层 60s 击杀(memory 有记);进程内调用必须保留 HTTP 层原有的 per-user 鉴权作用域(canonical_read 的 user_id-scoped 是模板)
- **出处**:backend/app/services/agent_executor.py:5917, 6795-6800, 6123-6171; backend/app/orchestrator/orchestrator.py:1403, 1337

### rank 9 · [MARGINAL·先量测] 预合成流水线并行化:twin ∥ KB ∥ inspect ∥ history  `pure-perf` `S`

KB 上下文和 twin blob 要进合成 prompt,无法与 prefill 重叠——但它们彼此之间目前是串行的,可以互相并行。per-stage 计时(pre_stages 的 system_prompt_ms/kb_ms/inspect_ms/history_ms)已在 prod 日志里,第一步是免费的:先读日志确认串行成本,再决定动不动手。

- **预期**:非快路径回合(chat-advice 28% + deep 7%)估省 0.5-2s p50;以 prod pre_stages 实测为准,若实测<1s 直接放弃
- **上线闸**:先读 prod pre_stages 日志确认串行成本 ≥1s 才实现;fail-closed 门语义不变(输出在门绿前不出示);输出侧 advice_guard 已是流后校验,不动
- **出处**:backend/app/services/agent_executor.py:3626-3632(pre_stages 计时已存在)

### rank 10 · 并行只读工具执行(读集 gather,写保持串行)  `safety-adjacent` `M`

工具执行严格串行且注释自认'串行执行的墙钟',而 prompt 在鼓励一轮多 call——多工具轮是设计常态。按固定工具名枚举确定性切读/写:读集(health_query/query_lab_indicators/knowledge_search 等)asyncio.gather 保序回填 messages;写集保持串行,post-write 安全检查、写回执指纹、加层不减层的顺序依赖全部不动。

- **预期**:多工具轮每多一个读工具省 0.3-1.5s(record 40% / query 25% 子集);进程内读(rank 8)落地后此项覆盖残余
- **上线闸**:读/写边界是评审点:工具日后改类(读→写)必须 fail-loud 而非静默并行;SSE tool_call 事件顺序变化过三端客户端 sanity
- **出处**:backend/app/services/agent_executor.py:3971-4055(串行注释), 1072-1076, 5917

### rank 11 · 深报告并行分专家段落合成 + 确定性拼接  `prose-quality` `L`

深分析合成是一次串行强模型大 decode(单 _call_llm 吃掉全部 findings);findings 天然 per-specialist,确定性专家层早已并行,只有 LLM 叙事被串行化。改为 asyncio.gather N 个小强模型调用(每段一个专家 finding + twin blob + 该段仲裁判词),严重度排序确定性拼接;每段仍是 qwen3.7-max 文本(R4 成立),_safety_wrap 套在拼接整体上。

- **预期**:deep-analysis(7% 回合但最差尾部)合成 decode ~40s+ → ~10-15s 墙钟(max-of-sections 取代 sum);配合 rank 8 可再叠加分段流式
- **上线闸**:全清单最重 eval 项:双基线质量 eval 验跨段连贯性;只对报告形输出启用(SoT-R 教训,对话形回答会劣化);先落显式缓存(rank 3)否则 N× prefill 贵;先落进程内 orchestrator(rank 8)
- **出处**:backend/app/orchestrator/orchestrator.py:1440-1483, 609-630, 286-338, 1449; https://arxiv.org/abs/2307.15337

### rank 12 · [MARGINAL·缓存后做] rank10 历史摘要:append-only 冻结 checkpoint  `prose-quality` `M`

15 条 verbatim 消息(含多条 1800-4000 字助手表格)≈ 6-10k / 14.4k 输入 token 每轮重发。设计已钉死:checkpoint append-only(绝不逐轮重摘——否则杀前缀缓存,与 rank 3 直接冲突)、最后 ~4 条 verbatim、'已记录'回执逐字保留(fast-path followup bug 前科)。诚实定位:延迟收益小,真价值是输入成本 + 上下文 headroom。

- **预期**:长线程 prefill 估省 1-2s p50;输入 token 砍 40-60%(主要是成本/headroom 而非延迟)
- **上线闸**:严格排在显式缓存(rank 3)落地之后、围绕缓存边界设计;摘要有损性对医疗上下文的质量 eval;回执保留回归测试
- **出处**:backend/app/services/agent_executor.py:3644-3655; backend/app/services/agent_conversation_service.py:579-587

## Quick Wins(本周)

- 连接复用 memoize(rank 4):module 级按 (base_url, api_key) 缓存原始 OpenAI client,wrapper 照旧 per-call——S 级改动,每回合稳省 0.1-0.6s,全回合类受益
- parallel_tool_calls=true(rank 5):传旗标 + 跑一遍 smoke_fast_tool_model.py 式真网 eval;客户端累积逻辑已就绪,prompt 早在索要这个行为
- AsyncOpenAI 换掉 chat_stream 的同步迭代(rank 6):S 级、行为保持的正确性修复,顺手补 tool_call 分片累积回归测试
- prefix hash 日志一行(rank 3 第 0 步):在 agent_executor.py:3593-3598 现有 prompt-size 日志旁加 per-call 前缀哈希,量测跨轮前缀分歧,为显式缓存定 marker 布局
- 读 prod pre_stages 日志(rank 9 第 0 步):instrumentation 已存在,零代码先拿到 twin/KB/inspect/history 各自串行成本,决定并行化值不值
- mobile 端补'先给 2-3 条关键结论'的结论先行 prompt 行:mac 已有该契约,mobile 缺;作为 rank 1 prompt swap 的 rider 顺手带上,感知 time-to-actionable ~30s → ~5-8s

## Moonshots(值得但要立项)

- 深报告并行分段合成 + 分段流式(rank 11 + rank 8 联动):把 40s+ 深分析尾部打到 ~10-15s 且首段 ~8s 可读——但要立项:进程内 orchestrator 迁移前置、显式缓存前置、跨段连贯性双基线 eval、只对报告形输出门控
- 确定性查询二期(rank 2 的 stage 2):正则无歧义形状直接 message→dimension 映射,零 LLM 调用亚秒答案,复制 genui chart 短路先例(agent.py:311-335);一期落地并量测覆盖率后立项
- preserve_thinking=true 评估:vendor 侧唯一未探索的 thinking 旋钮(勿与已否决的 thinking_budget=512 混淆),可能缩短 follow-up 回合的重推理;输入变长需显式缓存先落地对冲,且触碰推理行为必须过双基线质量 eval 才谈上线
- GenUI 组件体系扩展到深报告整卡化:rank 1 落地 metric_table 后,把深报告的每专家段落也卡片化(severity 排序卡片流),与分段合成天然拼合——叙事进一步压缩到每段 ≤150 token

## 已毙(决策记录,防重提)

- Output-token diet(industry 版)——与内部 GenUI-first 完全重复,后者已核实全部接线;其'结论先行, ≤N字, 数据引用卡片'输出预算行已并入 rank 1,勿另开工作流
- DashScope 显式缓存(industry 版)——与 vendor 版同机制同定价事实,只保 vendor 条目(rank 3)一条工作流
- Skeleton-of-Thought——与内部并行分专家合成重复,且我们凭 SpecialistFinding 结构可直接跳过骨架阶段;SoT-R 的'只对报告形启用'教训已作为 rank 11 的 gate 保留
- record 确定性确认模板——已经上线:fast-route 写回合的 _fast_record_reply_from_tool_results + break(agent_executor.py:4270-4289)含写工具硬门和安全后缀携带;残余空间只是 fast-route 分类器覆盖率,不是新机制
- RLM-Cascade 草稿-验证级联——R4 下可用面太小(仅非医疗短答案 ~10-20% 且本就短);需要新建 fail-closed 医疗内容分类器=新安全面,一次假阴=弱模型医疗文本出街;确定性方案(rank 1/2)支配其全部收益。勿重提
- 语义答案缓存——论文 60%+ 命中率是跨用户共享(隐私不可行),单用户预期 10-20% × query 25% ≈ 3-5% 回合;陈旧的个人医疗答案是真危害;n=231/7d 流量撑不起 ANN+embedding+失效体系。唯一重开条件:先从 agent_messages 实测重复问句率且显著高于预期
- Starter chips 预取(industry 版)——与内部 signals_hash 版重复,后者基建全部核实在案,只保 rank 7
- 历史摘要(industry 版)——与内部 rank10 重复;其两条设计约束(每 K 轮刷新+稳定块位、显式缓存标记置于可变尾之前)已并入 rank 12,勿另开
- 更快强模型变体——确认负结果:max 层无 turbo、快照无延迟差、TokenPlan 多租户隔离即 QoS 层且我们已在;12-13 tok/s 是模型层级地板,唯一出路=少吐 token(rank 1/2)。这是决策记录,勿重新议价
- LLM 连接复用(internal 版)——与 vendor 的握手税条目重复(同文件同修法),并入 rank 4;核验时的修正要记住:agent_executor.py:5549 直调路径其实已 per-turn 复用连接,真正的 per-round 重建在 SDK provider 路径
- 静态指令块显式缓存(internal 版)——只是 vendor 显式缓存布局里的 marker #1,并入 rank 3;其独有贡献(prefix-hash 日志作为第 0 步)已收进 quick wins
- PrivateLink / 区域端点(降为不做)——tokenplan_base_url 已经是 cn-beijing maas 区域端点(config.py:62),剩余 VPC 腿对 31.9s p50 只是几十 ms 噪音,且其主要价值(握手成本∝RTT)在 rank 4 连接复用落地后基本蒸发;prod ECS 39.98.x 区域大概率非 cn-beijing。除非量测出残余网络时间显著,否则不做

## 增补裁决(2026-07-13 实测)

- **rank 9(预合成流水线并行化)按其自身闸门毙掉**:prod 实测 pre_llm 串行成本 p50=217ms(system_prompt 60.5 / kb 0 / history 1 / conv 11),远低于 1s 门槛;p90 3.0s 由图片回合 vision 主导,属独立议题(路线图外,见 anatomy 报告 vision 并行化条目)。
