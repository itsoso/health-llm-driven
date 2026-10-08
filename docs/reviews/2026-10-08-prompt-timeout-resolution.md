# 回答阶段延迟与质量缺口修复

日期：2026-10-08。归属：[交接 Dossier](../dossiers/2026-10-04-prompt-optimization-handoff.md)。当前为本地验证，尚未发布。旧超时和语义失败保留；本报告不将小样本通过等同于生产非劣。


**最终代码：d201cdcc9866f7315286fdfa52e5e0bf143eaaf0；独立代码审查 GO，候选生产激活 NO-GO。** 修复无量表评分评级、评测时钟/路由口径及睡眠事实误删；撤回会误删引用的积累记录过滤。写工具说明精简未恢复，预规划默认关闭，512/8192思考预算仅留评测且已否决。本批未推送、合并或部署。

最终提交180项相关测试、25项PostgreSQL边界、独立39项通过；独立另用原Flash模型完整原答重放，确认原句保留，并通过10项反例。固定源码的标准LLM闸10次真实API全部成功，26项源码hash前后未变，完整用量已记录。完整证据见[验证摘要](2026-10-08-prompt-fix-validation.json)与[固定源码真实闸](2026-10-08-fixed-source-live-regression.json)。这些检查不等同于完整120例非劣集或全量发布CI。

六场景Flash实测输入下降31.65%，但语义和耗时仍有失败；这个数值属于实验，未成为线上收益。尚未解决的模型输出包括把日汇总当睡眠事件、读取溯源误述及完成后的多余改查邀请。继续保持候选关闭，不用后处理或少量通过样本消除失败裁决。

## 定位与修复

1. `0e2e6fa16` 为 provider 增加首 reasoning/content、事件计数和最后事件的诊断；不保存推理正文。31 天 Max 诊断的等待主要在答案正文前，不能由此追溯证明旧两次超时的唯一原因。
2. 同一提交修复评测的双时钟冲突：ExecutionContext 已冻结到 23:30，profile 时段原来仍来自主机上午；现在两者均冻结。每对变体共用合成 owner 和源记录 ID，分别建立独立 conversation，避免日期/row ID 及历史污染。
3. 通用组合回答同时携带 200 字/一条下一步与 800 字/三条下一步的布局要求，删除重复的通用布局。这个改动作用于所有组合回答，关闭预规划不会关闭它。展开邻近回归后发现旧布局还含有“可以没有下一步”，`c3133aabd` 已在简短布局中恢复，避免把可选建议变成强制建议。
4. `d056b5e92` / `99a1a6a20` 补足真实 resolver、tier picker、Laya 及应用 `.3/8000` 参数路径。独立审查发现并修复库入口 non-live 绕过与决策未知 usage 漏算；CLI/scripted 和库入口均需显式 live 才能出网。决策消耗共享调用预算，低置信 abstained 与网络失败分别记录，失败仍停止批次。
5. 真实路由回放出现“评分尚可”，但返回数据只有评分数值，没有量表等级。`c3133aabd` 增加明确提示及组合回答输出拦截，复用现有有界纠正路径；数值事实、比较和不能判断的表述保留。修复未增加读取权限或写入操作。

## 已留存的真实证据

| 报告 | 结果与限制 |
| --- | --- |
| [分段诊断](2026-10-08-max-stage-diagnostic.json) | 改时钟/布局前的定位证据，不当作最终源码回归。 |
| [旧/新布局三对](2026-10-08-layout-max-paired.json) | 六条契约及人工语义通过，无本批超时；三对中两对更慢，不能宣称提速。 |
| [初次真实路由](2026-10-08-production-route-max.json) | 本地默认 Laya 2 秒超时，契约失败；后核对线上实际配置为 5 秒，该批不代表线上配置。原失败保留。 |
| [配置对齐的真实路由](2026-10-08-production-route-max-aligned.json) | 六条契约通过，独立语义五条通过、一条失败（行 2“评分尚可”）；未归因于预规划，因为同对答案 payload hash 相同。 |
| [隔离预算探针](2026-10-08-max-budget-probe.json) | Max 接受 thinking_budget=512，26.7→7.81 秒；仅两条合成任务的探索，未证明非劣，不修改 registry 或生产开关。 |

配置对齐批包含真实 Laya 每次 99 输入 tokens，实际规划模型为 qwen3.6-flash，答案模型为 qwen3.8-max。整任务输入 **7451→4825（下降35.24%）**，API 调用 **3→2**；不能继续沿用固定模型实验的61.5%作为这条实际路由的收益。三对墙钟为30.43→34.73、21.81→18.28、32.22→24.16秒。全部 Laya 为 abstained，只验证真实适配器与低置信处理；accepted/partial 本批只有单元验证。私有连接用独立 loopback SSH 转发，测试结束已停止；仅发送固定合成数据，未访问生产健康数据库。

该批 app/eval hash 与99a1一致，CLI只有后补的summary完整性修复不同；独立审查已重建旧CLI哈希。不能把它写成完整绑定99a1的回归。

## 思考预算实验与边界（后续已否决）

[阿里云官方参数说明](https://help.aliyun.com/zh/model-studio/qwen-api-via-openai-chat-completions)说明 Qwen3.8 Max 支持 thinking_budget；默认思考力度为xhigh，预算与reasoning_effort不能同时设置。官方能力说明只是探针依据，不能替代实际端点与质量回归。

`f4cd470bd` 将探针收敛为 `backend/eval/experimental_read_thinking_budget.py` 和 `preplan_budget512` 变体。只允许显式live、真实路由、Max、当前新会话预规划确实命中、非质量地板且未深度分析的答案阶段。首个预规划命中保留到答案轮，不改变工具规划；原输出、调用、工具、45秒provider/90秒任务界限保留。应用没有导入该实验，registry、临床质量地板和生产默认值未变。

可复现入口（通过已有私有测试环境配置 TokenPlan 与 Laya，不复制凭据）：

```bash
.venv/bin/python scripts/benchmark_prompt_full_task.py --include-live-llm --production-routing \
  --reference-variant runtime_preplan --variant preplan_budget512 --case analysis_31d_rich \
  --model qwen3.8-max --repetitions 3 --max-api-calls 24 --output /tmp/max-budget-paired.json
```

## 验证检查点

- 固定99a1评测代码：独立98项通过，代码GO；生产激活NO-GO。
- 评分边界先真实复现；新增评分/实验边界25项通过，实际Pi保存与流式路径验证。
- 新真实路由/实验接线15项通过；数据库232项通过（含runtime、coherence、决策与组合完成），临时集群已停止并删除。
- System Map、Ruff F821/F822/E9、秘密扫描通过。CI-mode 1251项通过/2项跳过，组合回答相邻回归1116项通过；这两批在评分审查增量前已导入源码，不能声称最终SHA全量通过。
- 默认关闭预规划，预算仍eval-only；写工具说明精简继续否决。尚未push、merge或deploy本批。

下文继续追加各固定代码检查点、全部新报告、独立语义裁决和Gate状态；旧失败不覆盖。计划中的完整冻结回放与统计非劣仍须另有证据。

### 独立审查增量 ef85536f5

审查复现数值比较“评分差2分/差值/差异”及“评分尚可与否无法判断”的误伤，也复现“达到80分”“（80分）”“算是良好”的漏判。新增七条RED后修复有限评分语法，保留其他质量检查。CLI整批预检现会在任何baseline调用前拒绝错误模型或缺失production-routing的预算探针，三组RED→GREEN。上述最终增量与评测/实验边界合计92项通过。固定源码的三重复配对和扩大回放均已完成，语义结果见后文；报告保留此前失败样本。


### 512 预算淘汰，继续保留默认质量控制

`ef85536f5` 的 [31 天三对比较](2026-10-08-budget-max-paired.json)与[六场景扩大回放](2026-10-08-budget-max-expanded.json)分别完成 6 / 12 个合成任务；独立审查确认两份报告全部 24 项源码哈希与该提交匹配，契约通过但语义 **NO-GO**。

三对比较隔离预算本身：墙钟 19.85→9.07、19.44→8.92、20.07→8.82 秒；包含 Laya 的输入 4849→4837。第 2 行候选要求用户“积累一段时间的连续记录”，已超出当前封闭读取分析任务。

扩大回放比较 baseline 与预规划＋512，全部输入（含 Laya）49769→33958，API 17→11，不能把组合收益都归给思考预算。候选第 2/3/7 行新增记录采集要求；第 7/10 行将每日汇总当成每晚记录并猜测同步/重复写入；第 11 行把缺值归因为未同步，实际 `sync_status=unknown`。这些内容进入最终回答；12 条原答均无截断，确定性契约不能覆盖这些语义失败。读取失败样本明确 failed/error、无聊天调用，但仍消耗一次 Laya API。后处理修复不得追溯改判旧样本。

`7ca808ff7` 单独修复明确“建议/请/你可以积累记录”的新任务布置，保留既有事实、否定语句、医生背景和跨句记录词；原完整医疗检查先于投影，含医疗违规的答案不能靠删除此句变成成功。11 个针对性测试 RED→GREEN，相关评分/评测回归 98 项通过。它不解决 512 的其余语义问题，不构成重新启用理由。

`d04752f27` 仅为评测增加 `preplan_budget8192`。预算只允许显式 512 或 8192；实测仍需 production-routing、Max 和既有预规划命中，非答案阶段/质量地板/深分析不应用。非法整批配置在任何 baseline API 前停止；应用与 registry 没有新增预算能力或默认开关。新预算边界 RED 10 项失败后完成实现，相关 120 项通过（32.84 秒）。当前 8192 只处于筛查，不能替代完整冻结回放、独立质量裁决或发布 Gate。


### 独立审查后的过滤收窄 64063cfa1

审查指出前版会误删“医生此前说，建议…”、“并不是说，建议…”及同句事实。补四例 RED（4 失败/11 通过）后，把新分支拆为整句 `fullmatch`，仅接受有限修饰语、明确指派和特定“如需有效分析”前缀，不再从任意逗号后开始；未知表达原样保留。相邻组合完成、评分和采集投影合计 **156 项通过**（3.92 秒）。此前 7ca808ff7 不是最终可合入版本。

[8192 六任务](2026-10-08-budget8192-max-screen.json)基于 d04752f27，包含同对同 owner 的 runtime_preplan 与 8192，6 条契约通过、全部 API usage 已知。31 天密集：29.72→22.91 秒；单日丰富：17.98→18.2 秒；31 天丰富：25.47→15.11 秒。两组均为每任务一条 Laya＋一条答案 API，预算没有节省调用。独立语义裁决为 NO-GO：候选第 2 行把日汇总称作“每晚”，且在热量仍有缺值时笼统说两维度“零方差”；基线第 5 行也把单条日汇总称作单次睡眠，按同一标准记录缺陷，不能豁免。其余四行事实安全可接受；第 6 行是对未来已有记录的条件性回顾邀请，不算明确新增采集任务。该批计时不包含后来 64063cfa1 过滤修复，也不能用小样本长尾证明生产收益。


### 最终撤回风险过滤 59387c25d

64063cfa1 仍会丢失跨行引用/否定的来源关系。审查提出两条多段输入，复现 **2 失败/15 通过** 后，彻底撤回本轮新增的积累记录过滤，而非继续扩大正则或掩盖失败候选。最终 `agent_composed_read_completion.py` 与已审 ef85536f5 逐字一致；评分等级边界修复保留。新增 `test_composed_record_context_preservation.py` 12 项通过，包含跨行引用实际 Pi 流式/保存路径。以上撤回不改变 512/8192 的原始失败裁决。

最终本地验证固定到 59387c25d（除文档外）。47 文件的关联 CI-mode 回归、一次性 PostgreSQL 6 文件、标准真实 LLM gate 正在执行；通过数量、完整命令和可携带摘要将在完成后补入。它们不等同于尚未执行的项目全量 CI、120 用例冻结非劣集或线上验收。

[Flash 真实路由扩大回放](2026-10-08-production-route-flash-expanded.json)固定到 64063cfa1，baseline 与 runtime_preplan 未改变思考控制，12 个任务契约通过。第 12 行采样与本机一个 4.32 秒的小测试重叠，最后一对时延不用于性能结论；其 API usage 和输出仍保留。前十行也有快慢混合，不据此宣称稳定提速。完整独立语义裁决与汇总待追加。


### Flash 回放裁决及真实代码缺陷

独立确认 Flash 的 24 项源码哈希与64063cfa1一致。输入包含 Laya：49769→34018（下降31.65%），API 17→11。每对回答请求 hash 相同，收益来自跳过规划调用；不能称为答案提示压缩。Laya实际均abstained。空数据10.87→11.96秒、31天密集13.59→26.99秒，未证明稳定提速。

语义裁决NO-GO：baseline第4行邀请改查其他时间范围，违反当前完成边界；baseline第9行的已验证睡眠事实被后处理误删；candidate第11行说“本轮未新增读取”，与实际health_query_batch执行矛盾。其他健康事实未发现新增评级、诊断或治疗越界。末对第12行计时受本机测试干扰，不作性能结论。

第9行定位到 `_record_description_flags`：即使日期全覆盖，`_EXERCISE_QUANTITY`也把睡眠“420分钟”当成未经核验运动数量删除。115ae3d14的初版数值例外仍可被前后文借用，独立审查复现深睡/REM、建议、错误评分和完整区间的误放，六例RED留证后在952d9d685收窄：只匹配完整有限事实句，每条日记录的时长、可选评分、可选天数及Garmin来源都必须验证；阶段、建议、任意前后文继续使用旧拦截。没有删除或放宽运动数量规则。

最终新增测试含来源错误、天数错误、缺评分、缺日、缺时长、重复日期、错误量、阶段、建议、完整区间；加相邻完成/评分/上下文共178项通过，实际Pi/Gateway/持久化的baseline与preplan均验证真实密集数据中的合法句子得以保留，模型调用数不增加。

[31天双模型质量回放](2026-10-08-daily-sleep-quality-replay.json)基于c6d34338d（收窄前版本），4条契约通过；仅用于诊断/语义审查，不当作952d9d685的精确代码验证。它与本机回归并行，整批墙钟不用于性能结论。旧NO-GO样本不覆盖、不改判。

### 验证选择纠正

首次对睡眠增量跑PostgreSQL时误把只允许内存SQLite的benchmark接线两例纳入，数据库隔离保护如实拒绝，结果62通过/2失败，日志保留。随后使用明确node id选择PostgreSQL兼容的62例重新验证；两条内存benchmark接线已有SQLite实际Pi/Gateway证据，不借此宣称它们在PostgreSQL上执行过。


### 原句精确回放 d201cdcc9

952d9d685 的安全边界通过独立审查（37项＋15个额外控制），但原真实句式仍被保守删除，因此没有把它称为原问题修复。d201cdcc9进一步把原第9行文本原样加入测试：`睡眠：31天均为Garmin来源、按醒来日期记录，每日总睡眠420分钟、评分80；`。新增 wake-date 子句只有服务器证据的 `date_attribution=wake_date` 时才允许；日期数、来源、时长和评分仍逐项核验，任意前后文不进入例外。原句及实际Pi的baseline/preplan两臂先RED（3失败/24通过）再GREEN，最终相邻180项通过（4.14秒）。它解决这个已复现误删，不代表所有自然语言表述都已得到完整事实验证。

代码修复验证与生产激活继续分开：完整120例冻结集、质量非劣和稳定长尾改善尚无证据；基线/候选的其他已知执行溯源与收尾措辞问题仍保留。预算候选不启用，预规划默认关闭。

本轮重新fetch后远端main推进到8a7d85df0，当前分支与main已存在不同提交历史，停止外部写入；未把此状态当作可直接发布。保留所有本地提交与原共享工作树改动，后续集成须重新核对基线、真实CI和发布准入。


## 固定代码最终验证

| 来源 | 新鲜检查 | 结果与范围 |
| --- | --- | --- |
| 59387c25d | 本地关联CI-mode，47文件 | 2441通过、2跳过；不是全项目CI。跳过的两个授权事务测试已另用PostgreSQL补验，2项均通过。 |
| 59387c25d | PostgreSQL，6文件 | 253通过，临时集群已清理。 |
| 睡眠例外初版 | 邻近组合投影 | 1128通过；导入早于最终收窄，不能冒充d201精确验证。 |
| 952d9d685 | PostgreSQL兼容节点 | 62通过；先前误纳内存专用benchmark的2条失败留存。 |
| d201cdcc9 | 最终相关回归 | 180通过，含真实原句的Pi/Gateway两臂回放；模型由测试桩替代。 |
| d201cdcc9 | PostgreSQL睡眠边界 | 25通过，临时集群已清理。 |
| d201cdcc9 | 独立安全复审 | 39通过＋原真实模型完整原答重放＋10项反例，代码GO。 |
| d201cdcc9 | 标准真实LLM闸 | 10次API全部成功、usage完整；26项源码运行前后hash一致。此闸不是睡眠数量新例外或完整语义非劣证明。 |
| d201cdcc9 | 本地live-change gate | 精确SHA确认通过；没有更新GitHub变量、push或发布。 |

中途的 `prompt-fix-final-live-regression.json` 使用旧临时包装器，仅在结束读取hash，期间源码曾变化，**不得作精确源码闸**。以 `fixed-source-live-regression.json` 的运行前snapshot和结束一致性校验为准；旧结果保留，失败与口径问题不覆盖。

最终复现入口（私有模型配置仅通过现有安全环境提供；不复制密钥）：

```bash
CI=true APP_ENV=test TZ=Asia/Shanghai SECRET_KEY=local-synthetic-test-key-only-000000 DATABASE_URL=sqlite:///:memory: REDIS_URL=redis://127.0.0.1:1/15 .venv/bin/python -m pytest backend/tests/test_composed_daily_sleep_evidence.py backend/tests/test_composed_score_interpretation.py backend/tests/test_composed_record_context_preservation.py backend/tests/test_agent_composed_read_completion.py -q --no-cov
.venv/bin/python scripts/harness_llm_regression_gate.py --include-live-llm --json
PATH="$PWD/.venv/bin:$PATH" ./scripts/system-map-check.sh
.venv/bin/python scripts/check_secret_leaks.py
```

PostgreSQL使用一次性本地集群与 `TEST_DATABASE_URL`，睡眠文件只选择两个纯证据test node，内存专用`test_actual_pi_keeps_verified_daily_sleep_text`仍由SQLite harness执行；认证并发需PostgreSQL。下一步必须先解决剩余语义/稳定性能问题，再做完整冻结回放、主干集成及精确CI，不直接重开任何否决实验。
