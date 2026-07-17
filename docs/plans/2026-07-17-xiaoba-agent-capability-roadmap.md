# 小巴 Agent 能力方向优化规划(对标业界 agent 设计)

日期:2026-07-17
状态:待 founder 批准
输入:①外部对标(Pi/pi-mono、Claude Code/Codex、OpenClaw 类个人助理 agent,3 路并行研究);②小巴现状盘点(HARNESS.md §10/§11 + 代码锚点逐一核实);③本仓已知痛点(生产实测)。
姊妹文档:`docs/HARNESS.md`(方法论权威,本规划落地后 §11 须同步更新)。

---

## 0. 一句话结论

**要参考,但只搬"治真实痛点"的模式**:小巴在安全/写入诚实/确定性专家层已领先业界编程 agent,
不该为"看齐"而改;真正的缺口集中在**上下文管理、eval 例行化、工具调用强制、主动性治理、
深分析交互契约(异步 job)、临床跟进闭环(commitments)**,每处都有业界成熟模式可抄,
且都过得了 R4/fail-loud/加层不减层/复杂度预算四道滤网。两波执行:Wave 1 基建治痛
(全 flag 默认关 + battery 回归),Wave 2 产品级新能力(需 founder 产品决策/观测期)。

## 1. 为什么现在做

生产实测的四个痛点,全部指向 agent 基建而非单点 bug:

| 痛点 | 实测证据 | 对应缺口 |
|---|---|---|
| 深分析慢 | 90–150s(dogfood 2026-07-14);合成换 flash 后仍是最大黑洞 | 上下文肥大 + 无 compaction |
| prefill 肥 | 14k tokens/分析轮(thinking-budget A/B 时定位的瓶颈) | 同上 |
| 长对话 token | 15 条历史 ≈ 10,290 chars,轮数↑线性涨 | HARNESS §11.3 自知缺口(❌) |
| 弱模型工具调用不稳 | 吐文本/弯引号 JSON/漏参数(三层防御 memory) | 全 AUTO tool_choice,无 strict(§11.2/§11.4 ❌/⚠️) |

另一个结构性观察:主动性(什么时候主动找用户)散落在 **54 个 celery 定时任务** + push_scheduler
+ starter 里,没有统一的"该不该现在打扰"决策层 —— OpenClaw 类个人助理 agent 的 heartbeat/
gatekeeper 模式正是解这个的。

## 2. 现状诚实盘点

### 2.1 已领先业界、绝不动的(加层不减层)

| 能力 | 实现 | 对比业界 |
|---|---|---|
| 写入安全 | 确认档位(auto/typed_only/never_auto)+ 写入回执诚实闸 + `_UNVERIFIED_WRITE_USER_MESSAGE` | 比 Claude Code permission tiers 更严:医疗域逼出来的 per-kind 档位 + id-based 回执验证 |
| 确定性安全脑 | 64 条 safety 规则(不依赖 LLM)+ 服务端硬闸范式(如 remember 的医疗 redirect) | 业界多数还在软 prompt 约束;本仓裁决"LLM 自动动作闸=服务端硬闸" |
| 专家编排 | orchestrator-workers,specialist 注册表静态、`applies_to` 确定性门控,非 LLM 自由 spawn | 正面绕开 Anthropic 报告的 coordination 爆炸/duplicate work 失败模式(HARNESS §10) |
| 记忆治理 | 4-stage 可观测注入 + memory_facts 三元组(reinforce/supersede/dismiss/decay)+ 用户管理面(mobile/app/memory.tsx「小巴对你的了解」:dismiss/矛盾裁决) | 结构化程度高于 Claude Code 的 CLAUDE.md 文件记忆;业界力推的"记忆 legibility 用户管理面"小巴已有——对标合成曾拟推荐此项,对抗自查后删除 |
| Provider 层 | model registry + failover + per-user 切换 + 显式缓存(实测 33% 命中) | 与 Pi 的 unified LLM API 同级,多了 failover 与缓存实测 |
| GenUI | 确定性取数结构化卡(metric_table/line_chart/sleep_summary),三层闸 | 业界消费级 app 有,编程 agent 无;已是差异化资产 |

### 2.2 已有一半、缺口在"例行化"的

| 能力 | 已有 | 缺口 |
|---|---|---|
| Eval | `backend/evals/comparative/`(battery/blind_pack/aggregate/cadence)+ 合成层不变量 eval(invariant_judge) | 无标注代表查询集常跑;"改 prompt 必过 eval"未成流程强制 —— HARNESS §11.1 的 todo 只完成了框架半截 |
| 工具渐进加载 | fast 子集(简单轮只发 3 工具,769 tokens 实测)+ 意图门控 prompt 块(gene/menu) | 分析轮仍全量 18k schema;Pi 的"按需进上下文"哲学只落了一半 |
| 主动性 | 54 个 celery cron + push_scheduler + quiet_hours + starter 预生成 | 无统一决策层:各 cron 自行判断,打扰预算/频控分散 |

### 2.3 确认缺失的(HARNESS §11 自知 + 代码核实)

- **运行中 compaction**:§11.3 ❌。`memory_extractor` 只在对话结束抽事实;单次长对话内无压缩。
- **强制 tool_choice**:§11.4 ⚠️。全仓只有 telegram 用 `tool_choice="auto"`,主执行器无 force。
- **strict mode**:§11.2 ❌。`tool_schema_registry` 未启用 `"strict": true`。

## 3. 不采纳清单(看着酷但不搬)

| 模式 | 来源 | 为什么不搬 |
|---|---|---|
| bash 万能工具 + 4 工具极简内核 | Pi | 通用执行器逃逸口正是 R4 明令禁止的;面向患者的写入必须是窄类型 allowlist fail-closed 领域 API。**15 个加厚工具是安全特性不是臃肿** |
| LLM 自由 spawn 子代理 | Claude Code subagents | 违反 §10 决策规则:specialist 注册表静态是刻意设计,防 coordination 爆炸;医疗域不能让 LLM 决定"起几个分析器" |
| 深报告分段/并行合成 | 多 agent 并行 | **已被 rank11 战役证伪**(0-9 否决,分段摧毁跨维度整合;flag 恒 shadow)——不重蹈 |
| Heartbeat 的 LLM 裁决"要不要打扰用户" | OpenClaw | 与"规则铸事实/LLM 只复述"的已验证路线相反;HEARTBEAT_OK 靠 prompt 约定+网关剥离=fail-open(伪标签泄漏教训:剥离式防御是死路);R4 的确定性预算已覆盖同一需求 |
| Prompt 层审批门(Standing Orders) | OpenClaw | 审批门必须留在服务端(R4 铁律);write_receipts + 双门 allowlist 机制上已强于它 |
| 隐式不可审计推断记忆层 | ChatGPT 式 | 对患者做不可审计画像风险>收益;小巴只保留显式可审计层(mobile/app/memory.tsx 已有管理面)是正确形态 |
| Mid-flight steering | Anthropic 报告 | §11.5 已明确降优先:specialist 少(单次 3-5 个),成本可控 |
| Session 树/分支 | Pi session tree | 编程场景需求(试错回滚);健康对话是线性叙事,患者不需要"回到上一分支" |
| Cross-provider 中途接力 | Pi unified LLM API | failover + per-user 选模已覆盖真实需求;接力序列化上下文有丢 R4 状态的风险面 |
| TUI/终端形态 | Pi/Claude Code | 形态无关,小巴是移动/Web/Mac 三端 |

## 4. 采纳路线图(按 价值÷成本 排序)

> 每个增量独立上线独立验证;增量间无部署依赖;全部过四道滤网
> (R4 / fail-loud / 加层不减层 / 复杂度预算)。

### R1 · 运行中上下文 compaction(治:长对话 token + 14k prefill)

**借自**:Claude Code compaction(recall-first)+ Pi 结构化压缩 + OpenClaw write-before-forget
(HARNESS §11.3 原生 todo)。**现状锚点**:`backend/app/services/agent_conversation_service.py:624`
`build_messages(limit=20)` —— 历史固定 20 条窗口硬截断,超窗静默丢,既费 token 又丢上下文。
患者顺口说的"我对青霉素过敏"被截掉是真实安全损失;**安全承重状态(过敏/现用药/red_lines)
永远走 Twin/memory 结构化注入,绝不依赖摘要携带**——这是本增量的红线测试。
**方案**:`agent_executor` 装配历史时,超过阈值(estimated_chars>8k)将**更早的轮次**
折叠成一条确定性格式的摘要消息(LLM 生成,flash 档,失败 fail-open 保留原文截断),
保留:最近 4 轮原文 + 摘要块 + 写入回执行(写诚实依赖它,**绝不摘要掉**)。
三条业界实现纪律直接抄:
① **切点规则**(Pi):永不拆散 tool call/result 对,摘要边界只落在完整轮之间;
② **write-before-forget**(OpenClaw):被折叠的轮次先过 memory_extractor 抽事实,
   抽完才允许折叠——压缩绝不造成记忆丢失;
③ **结构化优先**(Pi):健康数值/记录 ID 等领域状态进摘要的**结构化字段**,不靠 LLM 散文
   (LLM 摘要只管叙事线)。
**锚点**:`backend/app/services/agent_executor.py` 历史装配处;摘要生成走
`create_provider_for_extraction`(已有 fail-soft 工厂);摘要缓存挂 conversation id + 已折叠轮数
(增量折叠,不重复摘要)。
**第一刀**:只对超 20 条窗口(现状会被硬截断的部分)先做"截断→摘要"替换——纯增益,
不动窗口内行为;`LLM_HISTORY_COMPACTION=false` 默认关,灰度开。
**验收**:①单测:12+ 轮对话装配后 prompt 含摘要块 + 最近 4 轮原文;写回执行仍在;
②生产 telemetry:长对话(>12 轮)平均 prompt_tokens 降 ≥25%;③eval battery 上摘要开/关
对答案质量无回退(R3 的 battery 先行,故 R1 排 R3 后上线)。
**风险滤网**:R4 无关(只读优化);fail-open 摘要失败回退原文(诚实降级);
不动写回执 = 加层不减层;复杂度 ≈ +1 服务函数 + 1 flag。

### R2 · 记录意图强制 tool_choice + strict 试点(治:弱模型工具调用不稳)

**借自**:OpenAI/Gemini force tool_choice + strict schema(HARNESS §11.4/§11.2 原生 todo)。
**方案**:fast-route 已有确定性意图分类器(`intake_intent_classifier`);当分类器高置信命中
记录意图(water/weight/bp…)时,对该轮首个 LLM 调用设
`tool_choice={"type":"function","function":{"name":"health_record"}}`;同 PR 给 `health_record`
单个工具开 `"strict": true` 试点(先跑 probe 脚本验证 TokenPlan/DashScope 兼容,**探针不过不开**,
镜像 explicit-cache 的探针纪律)。
**锚点**:`agent_executor` 首轮工具调用装配处;`tool_schema_registry.get_health_tools`;
新 probe:`backend/scripts/probe_tool_choice_strict.py`(双 provider 各跑 force+strict)。
**第一刀**:只 force 分类器 confidence≥0.88 的记录轮;其余全部维持 AUTO。
**验收**:①probe 双 provider 通过;②单测:高置信记录意图 → 请求体含 tool_choice;
③生产:记录意图轮"0 工具调用落兜底话术"的比率下降(现有 usage/audit 可查)。
**风险滤网**:R4 增强(更确定地走受控写路径而非自由文本);fail-loud(probe 不过不开;
strict 拒绝 → 报错不静默);复杂度 ≈ +1 分支 + 1 probe 脚本。

### R3 · Eval 例行化(治:"改 prompt 靠手感"——一次性成功的底座)

**借自**:Anthropic LLM-as-judge + ~20 代表查询(HARNESS §11.1 原生 todo);
框架已有(`backend/evals/comparative/`),缺的是标注集 + 流程强制。
**方案**:①建 `backend/evals/battery/xiaoba_core.yaml`:20-24 条代表 query
(记录 5/查询 4/分析 4/安全告警 3/痊愈-修改 2/档案属性 2/多轮跟进 2),每条标 expected_behaviors
(须引用数据源/须调某工具/须不含剂量/…);②rubric judge 复用 invariant_judge 硬闸词表;
③接 CI 非阻断报告(阻断留给既有不变量 eval),周跑 cadence 已有。
**锚点**:`backend/evals/comparative/battery.yaml`(扩展)、`aggregate.py`、`cadence.py`。
**验收**:battery 全量跑通出分;对最近两次已知 regression(卡片误发/兜底话术偏见)做回溯
——battery 能抓到才算合格(用真实历史 bug 校准 eval 灵敏度)。
**风险滤网**:纯观测,无产品行为变更;复杂度全在 evals/ 目录内。

### R4 · 主动性统一决策层 Gatekeeper(治:54 cron 各自为政)

**借自**:OpenClaw heartbeat/gatekeeper(个人助理 agent 的核心模式,与小巴产品形态同类)。
**方案**:新 `notification_gatekeeper` 单一决策函数:所有主动触达(push/提醒/晨报/趋势/…)
发出前过它——输入(用户 quiet_hours、当日已触达次数、消息优先级、上次互动时间),
输出 allow/defer/drop + 原因(审计)。**不改任何 cron 的生成逻辑,只收口发送出口**(加层)。
**锚点**:`backend/app/services/notification/push_service.py`(单一发送出口已存在,收口成本低);
每日触达预算进 user_profile 或 settings。
**第一刀**:观测模式先行(只记 would_defer/would_drop 决策日志两周,不实际拦),
founder 看日志后再翻执行——镜像"LLM 自动动作闸 ships DISABLED"的三层纵深纪律。
**每通道硬预算**(OpenClaw 模式):每类主动触达通道各设数量上限(如 洞察类 ≤2/天),
上限是确定性 clamp 不是 LLM 判断;用户"关推送/负反馈"回灌预算调参。
**验收**:观测期日志显示决策合理率(founder 抽查);翻开后打扰投诉/关推送率不升,
关键安全告警(CRITICAL)**永远 bypass gatekeeper**(加层不减层的硬约束,进对抗测试)。
**风险滤网**:安全告警 bypass 是红线测试;fail-open(gatekeeper 异常 → 放行 + 告警,
绝不静默吞通知);复杂度 +1 服务 + 观测日志。

### R5 · 分析轮工具子集(治:分析轮 18k schema 白载)

**借自**:Pi 渐进式加载哲学(fast 子集的对称补全)。
**方案**:意图分类为纯分析/知识轮(不含记录/管理动作)时,首轮只发只读工具子集
(health_query/health_analysis/knowledge_search/query_lab_indicators…),写工具经"升级护栏"
按需补发(镜像 fast 子集已验证的 withheld-upgrade 机制,agent_executor 里已有同款代码路径)。
**第一刀**:复用 `FAST_TURN_TOOL_NAMES` 同款机制加 `ANALYSIS_TURN_TOOL_NAMES`;flag 默认关。
**验收**:分析轮 prompt_tokens 降(telemetry);升级护栏单测(分析轮中途要写 → 全量补发);
eval battery 无质量回退。
**风险滤网**:已验证机制的对称复用;升级护栏保证不阉割能力(加层)。

### R6 · 会话推断跟进承诺 Inferred Commitments(补:多步任务 partial 的最大缺口)

**借自**:OpenClaw Inferred Commitments——从会话推断的**短命跟进对象**,独立于持久记忆
(memory_facts)和精确提醒(reminder)的第三类:用户说"我明天去做胃镜""下周复查血脂",
agent 应在事后**主动问结果**,闭环后对象消亡。
**小巴现状**:agenda/timeline 有确定性事件完成回路;memory 有持久事实;reminder 有精确时间
——但"对话里顺口提到的临床跟进点"三者都接不住(不到 reminder 的精确度,不该进永久记忆,
agenda 只收结构化事件)。这正是健康 agent 比通用助理**更需要**的模式(临床跟进=核心价值)。
**方案**:对话结束的既有抽取管线(memory_dialog_extractor)加一类 `commitment` 输出
(what/expected_when/source_quote/建议问句),落 `agent_commitments` 表
(status: open/asked/closed/expired);到期承诺注入**既有晨报**(7:30 Celery,不新增推送通道)
产一条**关怀问句**("胃镜做了吗?结果如何?"),输出仅允许问句、过 guidance_red_lines 同款闸
(禁建议/禁剂量);用户答"好了"→ 触发 symptom/illness resolve 建议——**顺手治 active 堆积**
(36 条烂账的病根之一就是缺轻量跟进+resolve 触发)。**LLM 只推断承诺草稿,投递过 R4 预算,
写入走既有确认档位——全程无新的不可逆动作面**。
**第一刀**:只抽取+落表+到期列表(观测,不发问);founder 看两周抽取质量再翻晨报注入。
**防过度抽取三件套**(briefing 记忆自强化事故的教训,一件不许砍):maxPerDay=3 硬限、
到期 clamp(过期自动 expired,**上线即带 TTL**)、抽取 pass 禁工具;
commitment 文本进推送须过 push_privacy 药名 backstop,投递回合禁工具(注入防御)。
**验收**:抽取精确率 founder 抽查 ≥80%;误抽有 dismiss 通路;expired 不堆积。
**风险滤网**:R4(只推断+询问,不代做);fail-loud(抽取失败不静默);
复杂度 +1 表 +1 抽取类别 + 复用晨报/记录管线。

### R7 · 异步深分析任务对象(治:90-150s 最大黑洞——交互契约侧正解)

> 对标合成排 **#1 价值**。rank11(分段合成)已证伪、保活流式是硬扛(还遗留内层 60s 连杀),
> job 化是**唯一没试过的正解方向**,且不碰合成质量——整链照跑,只是不再让用户盯着等。

**借自**:OpenAI Deep Research background mode + ChatGPT Pulse(提交即返回 → 后台跑 →
完成推送 → 带引用的可回看报告)。
**方案(第一刀严格限定一条路径)**:只做**体检深报告(mega)**:新 `analysis_jobs` 表
(status: queued/running/done/failed)+ POST 返回 job_id;Celery 跑既有 orchestrator 链;
**产物入库前过全套既有闸**(guidance_red_lines + 写后安全筛查——异步绝不成为绕闸新出口,
对齐"降级/兜底路径逃逸 R4"教训);完成走 expo-notifications 推送(内容过 push_privacy
药名 backstop);结果落成可回看报告页。**聊天保活流式路径原样保留**,零冲突。
**验收**:①fail-loud 状态机:超时/失败必推"分析失败",绝不无声(job 静默失败=最大风险);
②job 产物与同 query 流式产物过 battery 对比无质量差;③founder 实测"提交→离开→收通知→回看"。
**风险滤网**:R4(产物只读报告,无写动作);fail-loud 状态机是验收第一条;
复杂度 +1 表 +1 Celery 任务,链路全复用。
**留给 founder 的产品决策**:mega 报告默认走 job 化(通知型)还是给用户"等着看/跑完叫我"
二选一?——建议后者起步,数据说话。

### R8 · Plan-grant:一次审批一份多步干预计划(排最后,纯体验增量)

**借自**:Claude Code plan mode + approve-for-scope 语义。**现状**:R4 逐条写入确认 ×
12 周 Episode 的 N 步 = 摩擦乘 N;founder 已确认偏好"非医疗可逆记录低摩擦"。
**方案(第一刀限一个对象)**:`intervention_cycle`(Episode)开启时渲染 GenUI 计划卡
(每步何时/做什么/为何/风险),一次确认后服务端存 `plan_grant`(scope=该 episode_id,
expiry=周期结束);计划内 **AUTO 档位**步骤免逐条确认;**处方类/NEVER 集恒 clinician_review,
grant 压不掉**(对齐 admin-bypass 三重护栏教训,配隔离测试);计划外动作回逐条档位。
**风险滤网**:grant 必须服务端强制 scope+expiry(绝不 prompt 层);新 GenUI 卡型走三端契约
(fence→parser→卡片,漏一环即静默丢弃的历史坑);不治 known pain,故排最后。

### 执行顺序与依赖(两波)

```
Wave 1 · 基建治痛(全部 flag 默认关 + battery 回归)
  R3(eval 底座)──先行,1 个迭代
     ├─ R0:prompt 分解测量脚本(14k prefill 按 block 构成——R1/R5 的靶子)
     ├─ R2(force tool_choice + strict probe)──独立,S
     ├─ R1(compaction)──依赖 R3 battery
     ├─ R5(渐进披露/分析轮子集)──依赖 R3;注意:动 prompt prefix 会破显式缓存命中,
     │    先测缓存构成再动(与 token 战役的缓存资产不打架)
     └─ R4(触达硬预算:Redis 计数器收单一出口,来源管道判 bypass)──独立,S

Wave 2 · 产品级新能力(需 founder 产品决策 / 两周观测期)
     ├─ R7(异步深分析 job,mega 报告一条路径)──合成排 #1,独立
     ├─ R6(commitments:抽取观测两周 → 晨报注入关怀问句,maxPerDay=3)
     └─ R8(plan_grant)──排最后
```

### 候选池(本批不做,记录理由)

- **Extensions 事件总线**(Pi):统一可拦截点工程上优雅,但小巴的拦截点(确认档位/安全筛查/
  写回执)刚修到覆盖全部写工具(adad3b756),现在付 L 级重构换已覆盖的收益,不过复杂度预算
  ——降级为"下次新增写路径时的架构方向"。
- **授权状态对患者可见**(Standing Orders 的可取部分):挂 R8 的 plan_grant 页面顺手做,
  不独立立项。

## 5. "一次性成功"的保障结构

1. **每增量一个独立 flag,默认关**,灰度开;失败 = 关 flag 即回滚,零耦合。
2. **R3 先行**:所有会影响答案质量的增量(R1/R5)必须过 battery 无回退才翻 flag
   ——"确保一次性成功"的机械保障,不靠手感。
3. **探针纪律**:涉 provider 行为的(R2 strict/tool_choice)先跑真网 probe,不过不开
   (镜像 explicit-cache 探针先行的既有纪律)。
4. **安全评审**:R4(触达用户)与 R2(改写路径行为)各过一次 safety-privacy review;
   R4 的 CRITICAL-bypass 做对抗测试。
5. **部署前集成闸**:多增量合流时,CI 模式合跑全量测试(单增量绿 ≠ 批量绿的既有教训)。
6. **HARNESS.md 同步**:每增量落地同 PR 更新 §11 对应条目(❌→✅),文档不漂移。

## 5.5 对标合成交叉校验记录(provenance)

本规划由两条独立线收敛:①我(主 agent)基于 HARNESS §10/§11 + 代码锚点 + 生产痛点的
独立初稿;②5-agent workflow(3 路外部研究 + 1 路现状盘点 + 1 路对抗合成,51 万 token)。
分歧及裁决:
- **异步深分析 job**:初稿放候选池(担心与保活流式冲突),合成排 #1——裁决:**采纳合成**,
  因第一刀限定 mega 报告一条路径,不碰聊天流式,冲突论据不成立;升为 R7。
- **截断锚点**:初稿写 agent_executor,合成核实为 `agent_conversation_service.py:624`
  ——已修正(本机复核过)。
- **force tool_choice/strict**(R2):合成 top6 未含,但它是 HARNESS §11.4/11.2 原生 todo、
  S 成本、治弱模型痛点——裁决:**保留**,作为 Wave 1 快赢项。
- **plan_grant**:合成新增——采纳为 R8(排最后,纯体验)。
- 合成的对抗自查曾自删一条推荐(记忆管理面——发现 memory.tsx 已存在),该自查行为
  提高了整体可信度。

## 6. 明确不在本规划范围

- 深报告延迟的进一步压缩(rank11 已 park,等架构级新思路)
- LangBridge/Claude 侧优化(探针已证伪显式缓存,唯一杠杆是换默认模型 = 需 eval 闸的产品决策)
- 移动端 UI/交互(另行规划)
- 研发侧 harness(已单独对标过:hooks→judge→Workflow→plugin,别混)
