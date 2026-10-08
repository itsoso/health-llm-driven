# 跨机器接手：Prompt、Laya 与流式体验优化

| 字段 | 值 |
| --- | --- |
| 状态 | validating |
| 当前阶段 | 2026-10-08：优化修复已完成 Backend/Web 发布；餐食图片错误分类修复已部署，原用户照片验收待确认 |
| Controller | health-harness-orchestrator |
| Overlay | safety-gate |

## G1 范围准入

裁决：PASS。范围是用户授权的既有体验、路由和上下文传输优化及其分支交接，不新增产品入口、健康对象、用户数据权限或自动发布行为。权限、质量地板、写入回执和安全输出边界继续由原系统负责；失败候选不得进入运行路径。本文记录本地实现与证据，不代表全量 CI、生产效果或发布准入。

日期：2026-10-04。接手分支：`codex/reva-prompt-optimization`。本文件是各阶段 dossier 的最新索引；旧文档中的“未授权提交/推送”是当时状态，用户现已授权保存远端分支以便换机继续。用户随后明确要求“想办法解决之后部署”；现已授权按 Gate 完成 main 集成与生产部署，当前发布进度见本文末尾。

**10月4日交付（不包含本轮10月8日修复）**：后端与 Web 均已成功发布，精确 SHA、回执、健康检查和限制见[上线验收记录](../reviews/2026-10-04-prompt-deployment.md)。下文保留各阶段失败与检查点；历史“未部署 / BLOCK”不代表最终发布状态，真实用户体验及生产性能仍未完成验收。

## 10月4日交接时的代码

分支基于已 fetch 的 `origin/main`：`f201d85b4f0d726b09ff0f8b16acf403d70f3e57`。此前隔离工作树 HEAD `a8853dea1` 与该主干只差发布文档，运行时代码相同。不要以旧本地 checkout 替代 fetch 后的比较，也不要覆盖其他工作树修改。

已保留：

- Markdown 流式渲染稳定性及其测试。
- Laya 可信档位与 partial 能力建议分离、写意图否决、质量地板；未降低置信度阈值。
- provider 按服务端任务范围选择工具说明、公共任务工具选择、最终回答材料投影、工具 JSON 保真紧凑化。
- 历史中严格相同旧长答的引用与摘要窗口缺口补回；用户原话、待办与安全信息保留。
- 完整分析报告复用的进程内回执及公共输出护栏，默认 off。
- food recognition 用量调用方作用域修复。
- 固定合成质量评测与失败留证工具。

明确否决：health_record 写入示例精简。真实 API 上虽约减少 10.77% 输入，但 qwen3.8-flash 对 0.5升，以及收窄后的350毫升/250ml再次追问已知量。所有生产接线和触发 flag 已撤回；候选仅在 `backend/eval/experimental_record_projection.py`，由 benchmark 的独立实例注入。不能因 max 样本通过就重新启用，也不能把该收益算作已交付。应用未新增开关，已有优化开关默认值未改变。

## 先读的证据

1. [最终质量与撤回](2026-10-04-prompt-quality-preserving.md)：实验失败、回退和 387 项最终关联检查、独立33项检查。
2. [架构优化](2026-10-04-scoped-prompt-architecture.md)：读工具、历史与报告复用的边界；固定合成 API 的局部收益，不代表全量平均。
3. [Laya](2026-10-04-laya-routing-coverage.md)：本机真实适配器、部分建议和质量地板；无整体聊天提速结论。
4. [输入审计](../reviews/2026-10-04-prompt-token-audit.md) 与 [流式体验](../reviews/2026-10-04-web-streaming-ux-performance.md)。
5. [可携带 harness 轨迹](../reviews/2026-10-04-prompt-optimization-harness-traces.json)。原 `docs/_generated/harness-runs` 为本机忽略文件，已导出轨迹；旧文档的 `/tmp` 日志和本机服务地址不保证换机可用，仓库中的 JSON 证据可用。

证据全部是聚合指标或固定合成样本，不包含真实健康原文、运行凭证或 .env。另一台机器自行使用其已有私有环境；不要复制密钥进 Git。

## 下一步

先按 AGENTS.md 跑 router，根据最新远端比较本分支；继续在此分支优化。优先处理仍反复传输的大工具 schema、system 固定材料和多次模型调用，但先建立同批基线，分清 API 输入、缓存、输出、调用次数与耗时。不能用字符数代替 token，不能只跑强模型或只看静态测试。

`backend/eval/prompt_projection_quality.py` 冻结合成输入、日期及确定性契约；`scripts/benchmark_record_prompt_projection.py` 默认 dry-run，显式 `--include-live-llm` 才会调用 API。当前 candidate 是已否决实验，真实运行退出非零是可能且应保留的结果，不要为了绿色而放宽 oracle。完整临床/语义非劣、真实持久化及生产效果仍是 Unknown。

已知独立问题：原版“昨晚睡眠”在一条 API 提案中返回 days=1，不符合固定日期契约；两侧请求完全相同，不归因本次精简。若修复，应从服务端窗口解析与实际执行证据入手，不能只放宽评测。

## 可复现入口

使用仓库要求的 Python 3.12、后端开发依赖和 Node 依赖（含仓库 Pi runtime）；遵循现有安装入口。以下为离线测试环境，不使用生产数据库：

```bash
export SECRET_KEY=local-synthetic-test-key-only-000000
export DATABASE_URL=sqlite:///:memory:
export REDIS_URL=redis://127.0.0.1:1/15
python -m pytest backend/tests/test_agent_record_tool_prompt_projection.py backend/tests/test_agent_record_prompt_provider.py backend/tests/test_agent_tool_prompt_projection.py backend/tests/test_record_prompt_benchmark.py backend/tests/test_prompt_projection_quality.py backend/tests/test_scoped_prompt_provider.py backend/tests/test_agent_prompt_budget_execution.py backend/tests/test_agent_executor_fast_routing.py -q --no-cov
python scripts/benchmark_record_prompt_projection.py --output /tmp/record-prompt-dry-run.json
./scripts/system-map-check.sh
```

以上局部测试不是全量 CI 或 PostgreSQL 语义证明。提交已验证分支不等于发布验收；若继续产生改动，补相称测试及独立安全检查，更新 dossier。合并、部署与启用生产开关须单独授权及对应 Gate。

换机提交前补验：前端流式测试 5 passed、1 skipped；秘密扫描通过；仅格式收尾移除实验模块末尾空行，应用代码未改。

## 本机接续检查（2026-10-04）

已 fetch origin；分支 HEAD `7d934b3c6`，相对当前 `origin/main` 为 ahead 1 / behind 0。该分支无开放 PR。原共享 main 与远端分叉且有大量已修改/未跟踪文件，全部保留；在 `/Users/thomas/work/personal/health-prompt-optimization` 新工作树接续本分支，未合并、部署或推送。

Router 选择 implementation / health-harness-orchestrator + safety；命令行 overlay 的 canonical 参数是 `safety`，推荐 skill 为 `safety-gate`。本机使用已有 Python 3.12 创建工作树开发环境并安装后端依赖及 Pi Node lockfile 依赖。未加载已禁用的 superpowers skills。

新增 eval-only 候选 `backend/eval/experimental_argument_transport.py`：仅删除历史 assistant tool_calls.function.arguments 中合法 JSON 的字符串外空白。保留字符串及转义、重复键、数值字面量、工具名/ID、扩展字段、用户原话及工具结果；无效 JSON 原样返回。没有应用导入或生产开关；health_record 描述精简仍否决。

`scripts/benchmark_argument_transport.py` 默认 dry-run，默认同时覆盖 qwen3.8-flash 和 qwen3.8-max 的四个冻结 answer-stage 合成契约（睡眠缺血氧、血氧限制、写失败、写成功）。baseline 已应用现行工具结果紧凑化，candidate 只增加参数空白实验；不执行工具、不访问生产数据库。API 调用显式 `--include-live-llm`，记录真实 usage、缓存、输出、耗时、失败类型和原有质量 oracle；失败退出非零。

离线诊断：[dry-run JSON](../reviews/2026-10-04-argument-transport-dry-run.json)。cl100k_base 对 message JSON 的诊断计数依次为 449→446、420→419、376→371、397→392，降幅 0.24%–1.33%。这不是 Qwen API token 或全任务收益；本候选收益小，不能视为主要优化交付。

真实 API 尝试：[失败证据](../reviews/2026-10-04-argument-transport-live-attempt.json)。本机没有 .env 或继承的模型 API 凭据，首个 baseline 在创建 provider 时 OpenAIError，进程退出 2，无模型回归结果。已请求用户提供已有私有环境路径（不要提供密钥正文）。质量非劣、真实 token 节省与生产长尾仍 Unknown；候选不进入 runtime，不能用离线保真测试替代真实模型验证。

System Map 统一检查通过；离线 harness invariants 12 项、health_agent_core 50 项以及 trajectory contract / goldens 通过。首轮关联回归 131 passed / 3 failed，失败均在 Pi 初始化；安装工作树 Pi 依赖后的最终关联回归 **414 passed**（53.01s），含新增实验保真/隔离测试、stream/non-stream provider、Pi、被否决写描述保留、工具说明投影、预算、质量 oracle 与 fast routing。日志 `/tmp/reva-prompt-continuation-tests-final.log`，不代表全量 CI 或真实模型闸。

复现（工作树 .venv / 私有模型环境自行配置，禁止复制凭据入 Git）：

```bash
SECRET_KEY=local-synthetic-test-key-only-000000 APP_ENV=test DATABASE_URL=sqlite:///:memory: REDIS_URL=redis://127.0.0.1:1/15 .venv/bin/python scripts/benchmark_argument_transport.py --include-live-llm --output /tmp/argument-transport-live.json
```

继续方向仍为大工具 schema 与固定 system 材料：先取得同批真实 API 基线，覆盖 flash/max 及多轮工具执行，再决定候选。此次没有重新启用写工具说明精简，没有改变任何生产默认值。

## Token 与响应速度完整方案（2026-10-04 续）

用户要求继续优化并给出完整方案。已形成 [输入 Token 与响应速度优化方案](../plans/2026-10-04-prompt-token-latency-plan.md)，沿用本 Dossier：P0 同批基线 → P1 工具及阶段材料 → P2 扩展已有预规划/核验后直接交付 → P3 完整报告复用 → P4 请求内复用与独立 I/O → P5 缓存/路由预算 → P6 历史/流式。文档包括源码边界、目标、质量闸、真实 A/B、停止/回退条件与顺序；目标下降比例不是已交付收益。

本轮已完成 P0 的离线分项诊断器 `scripts/profile_prompt_inputs.py` 和 [合成测量](../reviews/2026-10-04-prompt-plan-profile.json)。使用现有真实 Pi 接线测试导出 payload，两个场景重新运行 **2 passed**；统一 System Map 检查通过。模型 provider 为 stub，输出仅 tokenizer 计数/工具名/源码摘要；不是 API usage、速度或质量非劣证据。现有优化开启后的答案轮 system 诊断仍为 5484 / 3880 tokens，支持优先调查固定材料；首轮工具输入也有收敛空间。

## 按方案实施 P0–P2（2026-10-04 续）

用户已明确“优化、执行，按照你的规划执行”。继续在 `/Users/thomas/work/personal/health-prompt-optimization` 的指定分支工作；保留原仓库及已有分支改动，未 commit/push/merge/deploy。此次范围仍由本 Dossier 和 harness run `b992d9b915cd` 负责，未新建完成状态。

- **P0**：`prompt_benchmark_metrics.py` 与成对 benchmark 支持有限重复、交替顺序、首正文/完成耗时、API usage、缓存未知值、失败样本和调用上限；小样本百分位仅诊断。错误即停批，缺失 usage 不估算成 API 值。
- **P1 默认重构**：`agent_prompt_sections.py` 提取基础规则列表；32 种条件组合与 `7d934b3c6` 预先冻结的摘要逐字相同，不改工具 schema、权限、安全地板或模型配置。
- **P1 候选**：`eval/experimental_read_synthesis.py` 只在既有只读答案阶段去掉固定规划文字；临床来源、R4、行为准则、证据、最终任务核对保留。删除段落哈希变化时返回完整原文；无 app 导入/开关。实际 Pi 回放的答案轮诊断 4441→3688（16.96%），整任务 16668→15915（4.52%）；首轮/工具结果/保存答案一致，但 provider 是 stub。
- **P2 候选**：`eval/experimental_owned_read_preplan.py` 对封闭且已由现有范围解析器绑定的本人睡眠+饮食请求提出已有批量读计划；从 Pi 到 Gateway 真实执行。合成 SQLite 回放 provider 2→1，日期、返回记录和流回答一致。负例与 owner/原话/附件/待确认/历史工具/重入边界保留模型路径。无 runtime 接线，非 PostgreSQL/质量/速度证明。

独立审查对 P1/P2 的默认等价性和实验隔离给 GO，分别复跑 130 / 25 项。P0 首审发现“自动兼容重试越调用预算、取消漏保存样本”并给 NO-GO；已修复，新增测试先 3 failed / 9 passed，后 **12 passed**，独立复审 **12 passed / GO**。评测时显式要求流 usage，关闭 SDK 重试与模型自动恢复，作用域退出恢复配置；取消保存状态后重抛。此前 NO-GO 保留在原轨迹。

最终关联验证 **707 passed**（86.42s），覆盖写入说明保持、stream/non-stream、实际 Pi、权限、日期、只读合成、历史、缓存布局、报告交付、usage 及新增候选；后续仅评测器修复，定向 12 项再次通过。离线 harness invariants 12、health_agent_core 50、trajectory contract 12 与 goldens 9 全过；统一 System Map 通过。[可携带验证摘要与源码摘要](../reviews/2026-10-04-prompt-implementation-verification.json) 已保存。临时日志 `/tmp/reva-prompt-implementation-regression.log`、`/tmp/reva-p0-review-green.log`。

**G3 仍 BLOCK：真实 LLM 证据缺失。** [路径敏感闸](../reviews/2026-10-04-prompt-implementation-live-gate.json) 为 failed/live required/unconfirmed；[API 尝试](../reviews/2026-10-04-read-synthesis-live-attempt.json) 在 provider 内客户端初始化时 OpenAIError，usage tracker 记录一次失败的包装层调用，没有 API usage 或回答。本机未配置模型凭据，已请求已有私有测试配置路径/服务；不得把初始化失败耗时当模型速度。独立 GO 不覆盖真实质量非劣、生产性能或发布资格。

P3 现有 Pi 测试确认 legacy passthrough flag 仍保留最终模型轮，因此不靠切旧开关宣称少一次调用。P4–P6 待真实同批分段数据和前置 Gate；当前未新开并发、共享健康数据缓存或降低模型档位。后续先跑四答案用例筛查，再补完整任务/holdout/PostgreSQL/盲评；详见[方案第八节](../plans/2026-10-04-prompt-token-latency-plan.md)。写说明精简继续 NO-GO，不重新启用。未合并、未部署，未声称全部方案完成。

## PostgreSQL 与组合验证接续（2026-10-04）

用户再次要求继续。本轮未改变应用或候选实现，补强 P2 的 1/7/31 天、实际读数、他人/未来记录排除、无数据语义、保存回答与健康行数不变的断言。一次性 PostgreSQL 17.11 首轮 **18 passed**，加入 P1/P2 组合回放后 **21 passed**；实例仅使用私有 Unix socket，均已停止并删除。[P2 PostgreSQL 证据](../reviews/2026-10-04-read-preplan-postgres-pi-evidence.json)、[组合数据库验证](../reviews/2026-10-04-composed-postgres-verification.json)。这补齐了所测读取路径的 PostgreSQL 证据，不代表迁移、并发或生产负载验证。

新组合回归在正常/空记录/读失败三种场景分别运行 baseline、P1、P2 和两者组合，经实际 provider 准备、Pi、Gateway、数据库及保存；provider 回答和无关上下文块仍为合成替身。正常场景整任务 cl100k_base 序列化诊断：基线 16825，P1 16072（4.48%），P2 6649（60.48%），组合 5896（64.96%），模型调用 2→1。证据、输出预算、终态与保存回答一致。[组合诊断](../reviews/2026-10-04-composed-optimization-pi-profile.json)。不代表 API、全量平均或真实提速。

独立首审 **20 passed / 1 failed / NO-GO**：失败测试错误假设只 dispatch 一次，stub 又在工具失败后重复提案导致 Pi 错误。按实际受限恢复策略修复 fixture，保留两次 dispatch、真实 Error 回执、完整失败 system，并直接断言无 Pi 错误；四臂终态一致。未改生产行为，未把失败视为成功。最后五文件 **77 passed**，独立 **21 passed / GO**；前次失败和修复均留在同一 run，GO 仍限离线。[完整验证摘要](../reviews/2026-10-04-composed-optimization-verification.json) 绑定当前源码哈希和测量口径。

真实模型配置仍缺失，未扩大读取私有配置的范围。默认运行行为保持前轮逐字等价重构，语义候选继续 eval-only，写说明精简继续 NO-GO。**真实模型非劣与速度闸仍 BLOCK**；下一步是私有模型配置与有限 A/B，详见[方案第九节](../plans/2026-10-04-prompt-token-latency-plan.md)。未合并、部署，未声称完整优化目标已完成。

## JSON 传输 CPU 等价优化（2026-10-04 接续）

再次 fetch origin，继续原指定分支并保留所有已有改动，无开放 PR。本轮将 `llm/prompt_transport.py` 的逐字符循环换成对合法 JSON 的字符串/非空白片段扫描。先执行相同 JSON 校验；完整保留字符串、转义、重复键、字段顺序、数值字面量和错误透传。仍只处理既有 `domain_prompt_optimization` 路径中的 tool 消息，不改变开关默认值、用户消息、调用参数、Pi transcript 或权限。

基线在改动前冻结自 `7d934b3c6` 的原模块，首轮目标未达成；直接正则替换的探索版本反而更慢，未采用。最终对相同合成输入做 101 组交替 A/B，每组 10 次，最后一次测量没有同时运行本任务测试。1000 条格式化记录的单次批均耗时 P50 **2.5→1.69 ms（减少 32.11%）**、P95 **2.55→1.76 ms（减少 31.05%）**；已紧凑记录 P50 **1.9→1.06 ms（减少 43.9%）**。17 组输入全都输出相同且不修改原数据；预设局部目标通过。记录完整样本、P50/P95/P99、环境和源码摘要：[最终微基准](../reviews/2026-10-04-transport-cpu-final.json)。基线与首轮结果也保留。

**这是本机合成 CPU 微基准，新增 token 节省为零，不是同批真实请求、API 延迟或全任务提速证据。** 当前组合 Pi 捕获只有 system/user 消息，该路径不进入 tool JSON 扫描，只作为透传对照；不得用其微秒级计时波动宣称收益。已有 P1/P2 的 64.96% 离线输入诊断与此次 CPU 收益不能相加。

先补保真测试；首版把 1500 层合法数组误判为必然超过解码器限制，出现 1 failed / 16 passed，已修正 fixture，并注入 decoder `RecursionError` 单独验证异常分支。改动前保真 **18 passed**；改动后关联 **48 passed**，包含 stream/non-stream provider 和实际 Pi 组合回放；独立审查 **31 passed / GO**。另外对 768 个确定性转义样本逐字比较冻结基线和 serializer 结果，覆盖长字符串、大整数及异常结果。离线 harness 与 System Map 通过。[验证摘要](../reviews/2026-10-04-transport-verification.json)。GO 仅限局部等价优化；[真实 LLM 闸](../reviews/2026-10-04-transport-live-gate.json) 仍 failed / required / unconfirmed。

此次应用差异保持在本地工作树，未 commit/push/merge/deploy；没有重新启用已否决写入说明精简。后续仍需已有私有测试模型环境，执行方案中的有限真实 A/B 和完整任务非劣验收。详细复现及回退见[方案第十节](../plans/2026-10-04-prompt-token-latency-plan.md)。

## 公共工具说明解析复用（2026-10-04 接续）

再次 fetch 并核对指定分支，无开放 PR；保留原工作树全部修改。本轮只给 `agent_tool_prompt_projection.py` 的两个纯文本解析函数增加各 64 项的进程内 LRU。缓存键为完整公共 registry 描述加维度集合，或完整批查询描述加当前查询说明；文本修改立即产生新键。有效期随进程，不依赖时钟 TTL；旧版本按 LRU 淘汰。缓存不保存用户、原话、日期、scope、健康结果、授权工具列表或可变 schema。当次身份检查、工具集合与参数 schema 比较、deepcopy 仍每次执行，缓存不能恢复被移除工具。

新增测试先 **4 failed / 4 passed**，包括原实现重复解析 5 次而非 1 次；加入缓存后关联 **135 passed**，独立 **32 passed / GO**。测试覆盖全部非空维度组合、冷热一致、说明更新/不识别格式、容量、修改返回对象、删除工具、封闭参数、stream/non-stream provider 完整载荷及身份重新检查。模块语句与分支合并覆盖率 **93%**；离线 harness、System Map 通过。[验证摘要](../reviews/2026-10-04-tool-projection-verification.json)。没有数据库业务语义修改。

同一冻结基线 `7d934b3c6` 的六组合成 CPU 测量，每臂 101 组、暖缓存每组 100 次；测量时本任务及独立 reviewer 均无测试并行。睡眠+饮食投影 P50 **59.25→25.48 μs（减少 56.99%）**，P95 **64.74→27.37 μs**；首次未命中单次 P50 **61.54 μs**，存在填充开销。暖缓存是批均值，冷缓存是单次计时，不将二者当作相同的请求延迟分布。预设局部目标通过；绝对节省约 **33.77 μs**，是很小的请求准备开销，不是整体响应速度。[改动前](../reviews/2026-10-04-tool-projection-cpu-before.json)、[改动后](../reviews/2026-10-04-tool-projection-cpu-after.json)。

发送说明与参数不变，新增 token 节省仍为零。P1/P2 语义候选继续 eval-only，写说明精简继续否决；[真实 LLM 闸](../reviews/2026-10-04-tool-projection-live-gate.json) 仍 failed / required / unconfirmed。已再次请求私有测试配置路径或已配置服务地址，没有读取 `.env-online` 或重试已知缺凭据的 API。未 commit/push/merge/deploy。下一步仍需真实模型环境，才能验收有明显输入/调用收益的 P1/P2；见[方案第十一节](../plans/2026-10-04-prompt-token-latency-plan.md)。

## 整任务评测入口（2026-10-04 接续）

本轮补齐 P1/P2 整任务 A/B：`scripts/benchmark_prompt_full_task.py` 默认计划模式，显式选择脚本或真实模型；经过实际 prompt、Pi、Gateway、查询及保存，使用合成用户和真实同意审计。仅允许 test 环境的内存 SQLite；不改变应用运行代码。模型、输入字节、输出 token、调用次数、工具范围和超时均有上限，失败即停批、取消留证、缺失 API usage 不估算成已知值。细节、复现及后续顺序见[方案第十二节](../plans/2026-10-04-prompt-token-latency-plan.md)。

独立审查指出旧 SDK 缓存可能保留重试，先 RED 复现后用显式客户端缓存键修复。随后日志核对发现懒加载上下文缺表；两份早期脚本报告已标为无效，补齐注册并增加数据库错误监听，防止上下文降级被计为通过。Twin 会话使用同一临时数据库；临床等未播种上下文为空、知识库未配置，不能代表复杂患者覆盖。

最终关联 **64 passed**；[最终脚本回放](../reviews/2026-10-04-full-task-scripted-final.json)共 **24 个任务通过**，数据库错误为零、36 次脚本 provider 调用，覆盖正常/空数据/读失败与四变体。baseline/P1 每任务 2 次，P2/组合 1 次；所有通过样本均核对读取范围、其他用户/未来数据隔离、健康行不变、保存与流一致。离线 harness 和 System Map 通过。验证摘要及独立审查见[本轮证据](../reviews/2026-10-04-full-task-verification.json)。

**真实质量与速度仍 BLOCK**：本轮没有真实模型请求、API token 或生产性能收益证据；[路径闸](../reviews/2026-10-04-full-task-live-gate.json)仍 required / unconfirmed。下一步用已授权的私有测试模型环境先跑最多 6 次调用的小筛查，再扩展矩阵和盲评。P1/P2 继续 eval-only，写入说明精简继续否决，全部已有改动保留，未 commit/push/merge/deploy。


## 部署授权与真实发布验证（2026-10-04 续）

用户最新明确要求“继续优化，部署到线上”，已覆盖此前不部署的限制；只有通过质量、安全与精确 SHA 发布闸的范围才可上线。已再次 fetch origin：main 仍为 `f201d85b4f0d726b09ff0f8b16acf403d70f3e57`，分支基线 `7d934b3c6`。生产只读核验为 `a8853dea1207163aaa412974dddfbc050ce3eeea`、backend/worker/beat active、health 200，旧后端回执 SUCCEEDED；未修改生产或轮换授权。生产 DOMAIN_PROMPT_OPTIMIZATION=true、报告复用 shadow、decision on、staged off。

### 已执行的真实模型验证

本机没有模型配置，已通过现有管理通道把服务器当前 TokenPlan 配置的两个必要字段传入临时测试进程内存，仅用于固定合成数据。配置值未输出、未入库、未写入 Git；未读取 `.env-online`，未访问生产健康数据。临时进程强制 APP_ENV=test、内存 SQLite、真实授权审计和调用预算。

- [首组 P1/P2 合成筛查](../reviews/2026-10-04-full-task-live-smoke.json)：Max 的整任务 API 输入 12270→4314，调用 2→1，42.09→18.86 秒，契约通过。只是单组诊断，不能作为上线收益或非劣证明。
- [扩大筛查](../reviews/2026-10-04-full-task-live-screen.json)：24 个计划样本只完成 5 个便按规则停止。Flash 有一组候选更慢；Max 基线提出范围外工具。该报告先于工具名诊断增强，不能推断其具体工具名。P1/P2 继续 eval-only。
- [真实主干严格读对照](../reviews/2026-10-04-release-main-full-task.json)：使用 origin/main 的完整 app 源码归档，eval-only overlay 不进入 baseline-only app 接线。首个样本选择 knowledge_search，被严格只读 oracle 拒绝。它表示测试范围不适配一般分析，不能当作主干质量失败或候选获胜。
- 新增独立 analysis 场景，允许通过真实 Gateway 调用本地 reviewed-KB 查询，空知识库必须如实未命中；不改变原严格读场景判据。仍禁止写入、超预算工具和任意外部分析调用。使用原句及未调参“复盘…”表达，记录读窗口、真实查询、知识来源、持久化和健康数据无变更。
- [主干分析对照](../reviews/2026-10-04-release-main-analysis.json)：原句 Flash/Max 均完成；holdout Flash 被 Gateway 拒绝后未完成，停止批次。
- [候选分析对照](../reviews/2026-10-04-release-candidate-analysis.json)：原句 Flash 被 Gateway 以 `health_query_dimension_conflict` 拒绝，未完成任务，发布质量闸失败。没有为了绿色重试整个矩阵或放宽边界。后续诊断增加脱敏的请求维度/日期及 Gateway 裁决留证；独立诊断不覆盖本次失败。

标准 live regression 的首次运行虽然返回通过，但测试库缺少 llm_usage_logs，用量/预算降级；[原报告作废](../reviews/2026-10-04-release-live-regression-degraded.json)。已补空库初始化回归（先失败后通过），保留真实 consent，同时创建用量审计表。[重跑及用量审计](../reviews/2026-10-04-release-live-regression-audited.json) 真实 5 个合成用例通过，10 次 MiniMax-M2.5 API 使用记录完整，无失败或模型恢复；offline invariants 12、health-agent rubric 50、trajectory 12/9 通过。该套件不是完整 AgentExecutor 质量验收，不能覆盖上述整任务失败。

### 修复与本地验证

1. OpenAI SDK 3.24 直接传播授权 hook 的 403；旧测试只接受包装后的 APIConnectionError。仅修测试兼容两种错误，并新增具体 403 code、一次发送的强断言，运行时鉴权不变。
2. PostgreSQL 的 ASC 默认把 NULL 排在最后，旧缺时间消息可能成为最后一个用户消息而失去历史来源边界。build_messages 显式 NULLS FIRST，仍以 ID 决胜；SQLite 原行为相同。失败已在 PostgreSQL 重现，修复后保证旧消息标记“时间未知/不是本轮指令”，当前用户原话仍为最后一条。
3. PostgreSQL 测试首次集群编码为 SQL_ASCII，无法建立含中文注释的表，该结果无效；重新建 UTF8 一次性集群。时间来源 fixture 改为明确的 naive UTC 列值，避免 aware fixture 经数据库 session timezone 隐式转换。UTC 环境 106 项通过，生产同款 Asia/Shanghai 时区的历史来源 3 项通过；这不证明所有时间写入路径，未迁移或回填已有记录。
4. CI-mode 关联集成 1030 passed、2 个 PostgreSQL-only skipped；最终 history/评测定向 75 passed、诊断增强 24 passed。前端 447 passed/1 skipped，build、lint（0 error/37 warning）、System Map 和阻断级 Ruff 通过。秘密扫描覆盖 tracked + task untracked，未发现高置信凭据。

[可携带验证摘要](../reviews/2026-10-04-release-optimization-verification.json) 记录源码摘要、测试范围与限制。当前 **G3 / 发布 BLOCK**：整任务非退化未通过；未通过目标 SHA 全量 CI、最终 G4 或生产发布事务。不得以标准 live gate、单组 token 收益、离线 CPU 微基准代替。写入说明精简继续否决，P1/P2/参数实验无 runtime 导入或开关，报告复用维持 shadow。下一步先根据 Gateway 诊断复现失败提案并定位归因，再固定候选、重新成对验证和独立审查；不得带红合并部署。

单次[新增 Gateway 诊断](../reviews/2026-10-04-release-candidate-diagnostic.json)后来完成了同一请求：日期和两个维度正确、原 Gateway 允许执行。这不是修复，不能抵消先前失败，也不重算为整批通过；原失败的完整参数未保存，根因仍待复现。新增测试明确覆盖错误维度被拒、仅保存窄诊断字段（不保存任意参数），最终 24 passed。


### 固定候选独立审查与摘要边界修复

本地保存 `3a92324b36a74ecb69493f2dce97a038d9874161`，未推送。独立 G4 对该固定提交给 **NO-GO**：读取已改 NULLS FIRST，但摘要 writer 仍使用原排序；且增量按 `id > prior_thru` 而非实际顺序判断。审查以真实 ORM 和两轮摘要复现顺序 `[3(NULL),1,2,4,5]` 时遗漏消息 1/2。这个代码阻断与真实模型 G3 失败分别记录。

补回归先重现两项失败，再修复：读写统一 `created_at ASC NULLS FIRST, id ASC`；cache key 升为 v3，TTL 仍为 24 小时，不删除旧 key；缓存保存有序前缀的单向摘要，绑定消息 ID、角色、正文与时间。reader、writer 和“切点相同”提前返回均校验来源前缀；按验证后的前缀位置取增量，顺序/内容/切点变化则拒绝旧摘要并完整重建。缓存只新增摘要值，不另存健康原文。

新增回归覆盖 NULL 位置与数值 ID 不同、v2 隔离、相同切点但前缀重排、正文修改、窗口桥接及收据保留。SQLite 52 项通过；PostgreSQL 复验使用 UTF8、Asia/Shanghai 和独立 worker session。最初测试替身把 `db.close()` 置空，导致 PostgreSQL teardown 自锁；已记录并终止本任务测试进程，临时集群正常停止和删除，随后改成真实独立 session 重跑。没有操作生产锁或发布进程。

`3a923` 的固定 CI-mode 关联集成为 1033 passed / 2 skipped（102.27 秒）；之后仅摘要边界修复，另以新鲜 SQLite/PostgreSQL 定向回归和独立复审覆盖，不把前次集成标为最后代码的全量 CI。整批发布继续 BLOCK，未修改 GitHub live-confirmation 变量或触发发布工作流。

摘要边界修复的最终 PostgreSQL 回归 **52 passed（38.29 秒，Asia/Shanghai）**，临时集群已停止并删除；SQLite 最终 52 passed（4.91 秒）。

### 最终检查点：代码复审 GO，发布仍 NO-GO

摘要修复已保存为 `eeb71eafde8554b1bb793c731b512cee13c537f0`。独立 reviewer 对该固定提交给出 **代码 G4 GO / 整批发布 NO-GO**：两项摘要阻断均已关闭，独立四文件 52 passed（4.01 秒），另核验两种 reader 拒绝顺序、正文、角色、时间、缺切点、插入六类前缀变化，合法旧切点与窗口间隙仍可衔接。受审源码摘要全部匹配；复审没有调用模型、重跑 PostgreSQL 或修改源码。此前 `3a923` 的 NO-GO 记录保留。

[有界诊断复测](../reviews/2026-10-04-release-candidate-diagnostic-repeat.json)预设 3 个原句 Flash 任务、最多 9 次调用，实际 6 次 API 调用，3 个任务契约通过。Gateway 均收到正确的睡眠/饮食与日期范围；没有复现原失败，因此不能确定原提案被拒的原因，也没有应用修复可以关闭该失败。每任务输入均为 12270 tokens，任务耗时 40.78 / 19.15 / 34.73 秒；缓存命中、输出量变化且无同期配对基线，这些仅为诊断记录，不构成提速或语义非劣结论。原失败报告继续有效，未重新计算为整批绿色。

**截至本检查点：优化与摘要修复已本地保存，G3 完整任务质量仍 BLOCK，未 push、merge 或 deploy。** 线上仍为 `a8853dea1207163aaa412974dddfbc050ce3eeea`，backend/worker/beat active、health 200；没有改生产开关、授权、锁或回执。P1/P2、参数压缩继续 eval-only，已否决的写工具说明精简没有启用。独立代码 GO 不替代真实模型质量、精确候选全量 CI 与发布验证。后续从原失败的脱敏 Gateway 提案诊断继续；需确认根因、先复现后修复，再执行同批基线/候选与未见样本验收，通过后才可进入已获用户授权的发布流程。

## 解决阻断后部署（2026-10-04 续）

用户要求“想办法解决之后部署”。沿用本分支与同一 run，fresh fetch 的 main 未变化。已不依赖随机重跑，分别复现以下问题：

1. [真实 holdout 诊断](../reviews/2026-10-04-release-blocker-holdout-diagnostic.json)中 Flash 正确提出 sleep/diet、days=7，但“复盘”请求仍被拒。`_request` 的 bounded-analysis 前级支持“复盘/总结”，逐域 owner-prefix 却漏掉这两个词。补齐同一语法，RED 4 failed / 34 passed，关联 393 passed；固定 `568d40263788b49a5975da22c25fcdc06f3cc0dc` 获独立 40 passed / safety GO。[真实复验](../reviews/2026-10-04-retrospective-live-verification.json)原句与复盘句、Flash/Max 四任务全部契约通过（8 次 API）；语义输出均限定于实际两条样本，没有据缺失作健康结论。该次源码绑定补充：受审 parser SHA-256 为 `65c9c42e6fbbd7139d5c2a98ce86e4321d36fa9c8a579bd2b3378492ddf620fd`；报告旧生成器未直接列出 parser，后续已补源文件清单。
2. 独立审查与离线 RED 确认 batch 在维度集合检查时归一化别名，逐项 scope 绑定却取原字段。因此 food、饮食、空白 diet、type=diet 被误拒。修复只统一维度归一化，所有者、天数、日期、时区和 period 继续检查原参数，防止投影丢失限制；四个正例先失败，十个负例保持通过。
3. 使用实际 `_call_llm_stream`→provider 包装复现首次维度错误后的 **tools→answer**，没有修参轮。原因是手选不可靠工具模型的答案交接仅看“已执行工具数”，而被 Gateway 拒绝的提案也增加该数。现有修参仍有预算且目标未核验时，推迟答案交接；不恢复被移除工具，不改变 Gateway 决策，维持两轮修参上限。完整管线现验证 **tools→tools→answer** 后完成；两次失败仍停止，他人 owner 拒绝只调用一次模型并终止。原失败未保存第一提案，不能声称它必由别名引起；已确认并修复的是该类拒绝后无法自我修正的执行缺陷。

上述新修复定向 134 passed；接下来执行 49 文件 CI-mode 关联集成、一次性 PostgreSQL、独立固定提交审查，再用 main/候选交替的 3 场景 × 2 模型整任务回归（正常、空记录、真实读取异常；最多 36 次 API），保留每个失败。新增 analysis 场景允许已有知识库查询，原严格读 oracle 和历史失败均保留。P1/P2 与写说明压缩不启用，当前没有上线行为。

### 配对回归发现的瞬态失败收尾

`85c244ed` 的 49 文件 CI-mode 集成为 3724 passed / 2 skipped，隔离 PostgreSQL 137 passed，独立代码复审 114 passed / GO。真实配对先后留下主干正常场景 Max 答案超时、主干失败场景 Flash 重复 sleep 后提前交接两个失败；只继续原计划未执行槽位，没有重跑覆盖。[首批](../reviews/2026-10-04-release-paired-validation.json)、[续批](../reviews/2026-10-04-release-paired-continuation.json)、[最后槽位](../reviews/2026-10-04-release-paired-final-slots.json)均保留。最后 Max 候选读取异常超出原三次工具派发上限，原矩阵停止，剩余最后一个主干槽位未执行。候选 5/6 契约及人工语义通过，1/6 失败，不能算矩阵通过或非劣证明。

新增失败根因已离线复现：底层 batch 瞬态读取失败自动重试一次，随后模型又选择 knowledge_search + single health_query，继续重复读取直到评测预算耗尽。RED 两例失败。窄修复在现有瞬态重试耗尽、Gateway allow 的完整 canonical queries 与当前纯组合读 scope 完全一致时，用 Pi terminate 直接结束本任务，停止同批剩余调用；保留所有既有核实结果，按原完成投影说明本轮未完成。batch 遇首个子查询错误即返回，因此不声称每个维度均实际失败。同步、写入、每日计划、运动计划、医生反馈、待确认、部分 batch、参数失败和重试成功均不触发。新状态与参数修复计数分开，下一用户回合重置。

当前继续固定候选测试与独立审查，再复验受影响真实场景；仍未 push/merge/deploy，不增加原评测上限。失败态可确定性如实结束，不需要再请求模型生成失败文案。正常场景 Flash 单样本输入 14614→12270，但耗时 26.62→38.83 秒，不能宣称端到端提速。写说明压缩及 P1/P2 仍不启用。

独立复审 `f1ce9b9` 虽复跑 31 passed，仍给 G4 NO-GO：新终止条件排除了同步命令，却遗漏“佳明同步完成了吗”这一独立只读目标及 server-bound 续问；健康维度查询范围完整不等于整个任务目标完整。新增四例（当前句、续问、普通 Pi 与 panel 同批 Garmin 状态）全部 RED 后，增加 `resolve_sync_status_query(snapshot)` 排除，最终六文件 **199 passed**。保留 G4 失败，不以纯 sleep/diet live 通过覆盖该边界。

纯读取异常的[真实复验](../reviews/2026-10-04-release-terminal-live-verification.json)在 `f1ce9b9` 上 Flash/Max 均通过：各一次模型调用、两次实际瞬态失败，真实保存 failed/error，没有虚构结果。[标准 live gate](../reviews/2026-10-04-release-final-live-regression.json) 5/5 通过，10 条 API usage 审计完整、零失败；离线 12/50、轨迹 12/9 通过。50 文件集成 3746 passed / 2 skipped，唯一旧实验断言仍要求失败合成轮，更新调用数预期后 55 passed；四臂的参数、真实回执、持久化、流文本与结果一致性断言继续保留。后续生产源码仅增加上述同步状态排除，不改模型提示词、参数修复预算或调用上限。

固定 `6e50d4cff0839342058e0c263ec00c043fe496e7` 获独立 30 passed / G4 GO；新边界 PostgreSQL 25 passed。其[最后复验](../reviews/2026-10-04-release-final-terminal-live.json)仍因工具预算失败，完整保留：模型从重复 batch 修成两个合法 single；每个 single 按原有协议瞬态重试一次，sleep×2 + diet×2 需要四次真实派发，而原评测只允许三次。此处没有第三轮模型重复读。独立审查抽取 main/候选原始 wrapper，无 API 复现两 single=4 次派发、加 KB=5 次，两端一致，确认是评测预算定义不兼容既有协议，不能再修改 runtime 迎合旧 cap。

评测 v2 将逻辑与物理口径分开：模型提案总数最多 3（含拒绝/缓存提案，在完整 provider usage 留证后、Pi 派发前检查）；逻辑工具执行事件最多 3（含 server preplan 与重放，来源单独标记）；每个逻辑执行最多 2 次底层派发，总派发最多 6；模型调用仍最多 3。原 API/字节/时限、日期/所有者/写入 oracle 均不变。新 RED 合法两单读失败；修后两单读加 KB、缓存重放、第四逻辑提案、第三单工具派发、第七总派发等负例与原回归共 39 passed。原 v1 失败不重评分为通过，也不拿作质量失败根因已修；新主干/候选须使用同一 v2 协议，单独留新证据。

## 最终控制流修复与发布候选（2026-10-04）

运行时代码冻结在 `35f7438f8`，executor SHA-256 `88f581141fe09e35a40bae2d6b03339f085166e69f1640bb197204037a0a4242`。独立审查实际复现“参数拒绝→两个正确 single 读取各失败两次→旧修参计数仍阻止回答交接”，先 RED 后修复。现在从最近一次拒绝后的真实 Gateway allow 执行记录核对完整 owned canonical scope；参数正确不等于数据 verified，累计修参上限不重置。同步状态及续问、写入、待确认、exercise、clinician、daily 等混合目标保留原保护。相同坏参数缓存重放在 normal/panel 都消耗第二次修参额度并收口。

最终定向 **165 passed / 44.31s**，PostgreSQL 17.11 临时数据库 **71 passed / 90.99s**，集群已清理；独立 **41 passed / 18s** 加真实 Pi/provider 包装合成重放通过。System Map、阻断级 Ruff 和离线 LLM gate 通过。新 helper 不改变模型提示、工具说明、生产开关或数据范围。

[v2 真实配对](../reviews/2026-10-04-release-v2-paired-validation.json) 的 12 个唯一槽位、24 次真实 API：候选 **6/6** 契约及独立语义审查通过，主干 **5/6**，Max 失败场景因再次提工具超过提案上限，原失败完整保留。标准 MiniMax **5/5** 及用量审计对应的 orchestrator 源未变化。窄控制判断后续差异由上述 RED/GREEN 与独立审查绑定，未重复真实矩阵求绿。G3 仅裁决合成质量筛查 GO，G4 仅裁决受审代码 GO。

正常两模型双调用输入由 14,614 降到 12,270（**16.04%**）；empty Max 由 14,217 降到 11,873（**16.49%**）；empty Flash 因多一次修参由 14,217 增到 19,711（**38.64%**）。失败候选各一次模型调用、两次真实失败读取即诚实收口。全部逐对耗时和用量见[发布证据](../reviews/2026-10-04-release-readiness.json)，不删慢样本，不声称统计非劣、整体提速或生产 p95。P1/P2、参数运输及已否决写工具描述实验均未进入生产。

接下来执行精确主干 CI、Trusted validate、canonical bootstrap 轮换、Trusted backend，再按 Web canonical operator 发布前端制品；任何步骤失败保留原回执，禁止重放或清锁。部署与上线复验尚未完成。

最终 CI-mode 关联集成：39 个测试文件，**1054 passed / 2 skipped**，138.57s，0 failure/error。它不替代接下来的精确主干 GitHub CI。

### 精确 CI 第一轮修复

`7985bef01` 的 GitHub CI `37203498721` 暴露两处本地关联集未覆盖的测试接线缺口：旧 r-other 分片目录缺少新增 `test_retrospective_read_scope.py`，以及 `test_health_record_amount_regression.py` 的旧 FakeAgentConversationService 未初始化 `provider_history_references`。两项均先本地复现 RED，补目录 pattern 和 fake 空引用后，发布分片合同、原记录回归及新增 retrospective 回归 **97 passed / 3.45s**。不改变运行时代码、不删除测试、不放宽 oracle；首轮失败原样保留。生产尚未轮换授权或部署。

同轮 balanced-14 的两个 advice 用例把公开 `run_stream` 直接换成 `_run_stream_impl`，跳过 `_report_dispatches` 初始化并在原安全断言前失败。临时合成异常探针确认后，测试仅让 local_advice_response 第一次路由调用返回 None 并立即恢复原函数，保留公开入口和真实最终答案 guard。原强制越界工具、拒绝原因和公开回答断言不变；相关 advice/query outcome **80 passed / 15.37s**，运行时哈希完全不变。

## 后端与 Web 发布完成（2026-10-04）

生产 revision 为 `a10e642cde189c9b414dc8d41346e22f088eaa0e`，运行时代码保持 `35f7438f8` 的已审摘要。精确主干 CI `37204244154` attempt 1、`37204525289` attempt 2 均成功；后者 attempt 1 曾因误读原 CI 进度而多触发并取消，按所有当前 attempt 必须绿色的发布规则完成重跑，历史未隐藏。Trusted validate `37205448925`、backend `37206256120` 成功。

原旧授权按 canonical revoke、验证后销毁旧 loopback 私钥、rotate 顺序退休。首次缺少前置步骤的 rotate 在 intent 前拒绝，检查后按既有协议补齐；没有修改发布器、手改授权、清锁或覆盖旧回执。新后端 `completed.json` 为 `SUCCEEDED`，部署日志三次 **60/60 PASS**。数据库备份、恢复演练和站外归档依权威部署规范默认跳过；不能声称已执行备份。

前端 operation `1302b9e763454e829e5c7f1e25e98a45` 从同 SHA canonical staging，经只读预检摘要绑定、隔离构建、制品切换及页面验证，得到 `FRONTEND_SUCCEEDED`。完整 frontend tree 为 `26b12bed72ee3aa7502d44dc4ef94ba66cc5b6d8`，制品摘要及旧制品摘要保存在[机器可读回执](../reviews/2026-10-04-prompt-deployment-verification.json)。原发布租约已释放，launcher inode 保留，后端/worker/beat 的进程与配置未被 Web 发布改变。

### G5 部署健康

裁决：GO。独立 reviewer 核验原回执和四份前端 proof 摘要、内外网 `/privacy` 与 `/connect/health` 的 200 及页面标识、后端进程/config 保持，以及前端跨稳定窗口无重启。最终四个服务均 active/running、`NRestarts=0`，本次启动以来无 ERROR/CRITICAL/Traceback 日志标记。生产 Git SHA、干净 tracked tree 和 executor 摘要匹配受审版本。

实际应用公开路径 `https://health.executor.life/api/health` 与 `/api/agent/stream` 分别为 **200/401**，TLS 校验通过。第一次复验沿用旧资料中的 `health-api.executor.life`，本机 TLS 失败、服务器 DNS 不可解析；源码确认实际客户端使用 `health.executor.life/api`，改正探测地址后通过。没有改生产 DNS、代理或 TLS 校验，没有重发发布。

### G6 用户体验与性能验收

仍待真实用户路径验收：生产聊天流式显示、完整回答及保存、失败状态如实呈现和实际响应体验。本次生产 smoke 未读取或写入真实健康数据，401 只证明路由与鉴权边界；不能替代上述功能验收。合成质量筛查通过不等于统计非劣，正常样本输入下降 **16.04%** 不等于所有场景下降，整体提速与生产 p95 尚未证实。

本轮交付为后端与 Web，不包含 Mobile OTA、原生包或 TestFlight。已否决写入工具说明精简、P1/P2 和参数传输实验均未启用；报告复用维持 shadow。完整方案中的进一步优化仍按同批基线、质量与长尾闸逐项推进。发布后的证据更新保存在接续分支，生产和 main 保持已验证的 a10e642c，后续不得把文档提交 SHA 当成已部署版本。


## 2026-10-07：下一批优化实验验证完成

用户“开干”后完成空结果结束、既有 P2 闭合本人读取预规划、重复字段缺口字典三项独立候选。代码提交 `415406202`、诊断留证提交 `679508d6f`；相对 `dba00171e` 的应用运行时差异为空，写工具说明精简仍 NO-GO。

32 个合成流程样本、50 次 Qwen API 调用已完整留证。P2 两模型有数据输入 12270→4724（减少 61.5%）、空数据 11873→4327（减少 63.56%），对应四组成功样本耗时均下降；失败状态仍 failed/error。独立语义检查通过有限三态筛查，允许单独进入后续生产接入评审。83 项关联测试、System Map、秘密扫描与项目 live regression gate 通过。

本批总体生产 NO-GO：空结果候选存在 Flash 规划修复成本；证据压缩收益在7天样本不足，Max样本变慢；先前两次营养护栏失败缺原答，另一条“查询”措辞样本未命中冻结日历范围，均原样保留。新诊断批成功不能覆盖这些失败。尚无可审生产接线、丰富档案/路由及精确生产 SHA 验证。本批未合并、推送或部署，不把实验收益报为线上收益。

详情及下一步：[本批结论](../reviews/2026-10-07-prompt-next-candidates.md)、[结构化汇总及六份原始报告哈希](../reviews/2026-10-07-prompt-next-candidates-summary.json)。独立 reviewer `prompt_p1_review` 对两个固定代码提交均裁决 eval GO、生产 NO-GO。新增 answer-stage 留证只作用于合成评测，有 16000 字符上限及截断标记，不捕获 reasoning。


## 2026-10-07 P2 runtime integration in progress

用户再次“开干”授权实际接入。候选仅覆盖首个新会话的闭合本人睡眠+饮食分析（1–31 天），无历史/引用/附件/待确认/同步/医疗证据流程。服务端只产生 OwnedReadScope 已绑定的工具提案，仍经 Pi/Gateway、原读取、完整性与回答护栏。独立 `owned_read_preplanning` 默认关闭且还要求 `domain_prompt_optimization`；关闭独立开关恢复当前生产行为。写工具说明精简仍否决，另外两个实验仍 eval-only。

先写失败测试再接入。85 项聚焦测试通过，早期 PostgreSQL 169 项通过（随后增加路由和独立开关测试，待刷新）。decision on/Laya 的 balanced 与 high_stakes 两臂都保持原质量模型，不放宽路由。perf 不把服务端规划计作模型调用。

真实 rich-profile 筛查保留在 `2026-10-07-runtime-preplan-rich-live.json`：已完成三对六条均契约通过；31 天 Max 候选触发 45 秒 provider TimeoutError，原批停止，缺少该 baseline。此失败不得删除或当成功耗时。新三态配对、独立安全审查和完整 CI-mode 正在执行。当前 production **NO-GO**，独立开关未在线开启；尚未推送、合并或部署本轮代码。激活必须另有足够质量与长尾证据，不能用小样本代替计划中的完整非劣验证。


### Runtime P2 final verification checkpoint (2026-10-07)

实现 `f5aff2062` 与 consent 测试 `f3f5fca1c` 已本地提交。CI-mode 1211 passed/2 skipped；最终 PostgreSQL 100 passed、临时实例停止清理；聚焦85+随后consent2，独立重跑87及取消/部分失败对抗2通过，集合重叠不相加。标准 live gate 12/50/5全部通过，10次MiniMax API usage完整；System Map、阻断Ruff和秘密扫描通过。

三份候选报告22流程/29次Qwen API尝试，包含2次超时（usage未知而非零）。最终源码匹配的三态12条全部契约通过，有记录12270→4724输入token、2→1API。丰富档案原批在独立开关之前，必须保留其源码差异，不能冒充最终提交验证。31天Max原批45.61秒超时，新预算限定诊断首对通过后第二候选45.36秒再超时，按规则停止。

独立安全裁决：代码GO、默认关闭部署代码准入GO、生产激活NO-GO。另缺真实生产Decision/Laya路径及完整统计非劣/长尾证据；不能用局部绿或减少token替代。**本轮未push、merge、deploy，也未开启线上独立开关。**继续点为回答阶段超时诊断和冻结回放，不是重新启用写工具说明精简。完整证据见 [运行时报告](../reviews/2026-10-07-runtime-preplan-review.md) 与 [结构化汇总](../reviews/2026-10-07-runtime-preplan-summary.json)。

## 2026-10-08：超时定位、真实路由与评分边界修复

接续指定分支，保留原主工作树。已修评测双时钟/记录身份，补真实resolver/Laya与生产参数路径，修复评测库入口和用量汇总缺口；真实语义审查发现无等级标准却称“评分尚可”，已补输出拦截与有界重写验证。组合布局去重同时恢复“可以没有下一步”。固定代码到 `f4cd470bd`，后续验证及精确证据统一在[本轮报告](../reviews/2026-10-08-prompt-timeout-resolution.md)。

真实路由输入下降35.24%，但首对耗时变慢且一条语义失败，不能据此关闭生产Gate。新的Max思考预算512仅为隔离实验，初次探针有明显提速，尚待同源扩大验证。默认预规划和预算均未在线开启，写工具说明精简仍否决。本批尚未push、merge、deploy；既有部署授权仍有效，满足Gate后再执行。


### 2026-10-08 最新断点：质量优先，撤回有损过滤

过滤撤回检查点为 `59387c25d`，最终睡眠事实保真修复为 `d201cdcc9`。512 三重复与扩大回放、8192 三场景均已完成并经独立审查，**语义 NO-GO**；出现新增采集要求、未知同步归因、日汇总误述为每晚/单次睡眠等问题。8192 对照的基线也存在单条日汇总误称单次睡眠，保留基线缺陷。不得启用预算或降低质量标准求绿。

新增积累记录正则过滤因跨行引用/否定可能误删已有信息，已全部撤回，保留 12 项上下文保真回归；`agent_composed_read_completion.py` 恢复到 ef85536f5（评分等级修复仍保留）。写工具描述精简继续否决。

Flash 不改思考控制的真实路由六场景12任务契约通过，但独立语义及性能仍NO-GO。最终代码d201cdcc9另修复了真实睡眠事实误删，180项相关测试、25项PostgreSQL边界和独立39项通过，固定源码标准真实闸10次API成功。结果、失败样本、固定源码和限制统一见 [10月8日修复记录](../reviews/2026-10-08-prompt-timeout-resolution.md)。本批未 push、merge、deploy，生产激活仍 NO-GO；10月4日的已部署结果不得混作本批验收。

### 2026-10-08 发布请求：本地就绪，主干红色 CI 阻断外部写入

用户明确要求合并 main 并上线。已在接续分支无冲突接入 main `8a7d85df0`，原工作树保留。发现 main CI `37721192561` 因依赖安全审计失败；固定本地修复 `246e697ea` 更新 Mobile compression/shell-quote/source-map-js，及 Web source-map-js/Next.js/sharp，未添加审计豁免。独立审查对完整代码/依赖范围 GO，三个后端运行时文件与已审 d201 完全一致；真实模型证据的 26 个摘要不变，未重新启用任何被否决实验。

新鲜 CI-mode 48 文件 **2468 passed / 2 skipped**，零失败；两项 SQLite skip 的 PostgreSQL 同源证据已在前轮保留。两端 npm ci/OSV 审计通过；Mobile tsc 与聊天头部6项通过；Web 447 passed / 1 skipped、build、lint通过（37 warnings）。Mobile 三次审计网络失败如实保留，第四次原闸完整通过。macOS sharp 实际 rsvg2.63.2，仍需最终 Linux 产物证据。System Map/秘密检查通过。

生产仍为 a10e642c，服务健康；只读核对预算0、staged off、parallel section thinking off，预规划未配置且候选默认false。AGENTS 第7节要求主干非绿停止外部写入，因此本轮尚未push、merge、部署或更新CI变量；需要明确允许推送受审修复以恢复CI，再等待精确主干全绿后按Trusted流程发布后端与Web。完整断点、修复版本、限制和下一步见[发布预检](../reviews/2026-10-08-prompt-release-preflight.md)及[结构化证据](../reviews/2026-10-08-prompt-release-preflight.json)。

### PR 277 真实 CI 与锁定环境补验

用户接续要求“发布之后解决”餐食图片识别和报错文案，按先发布再修复顺序继续。候选773经官方HTTPS推送到接续分支并创建PR277，原SSH连接失败与远端未更新检查保留。CI37726902417暴露multidict新漏洞和旧Next/sharp版本断言；已修为305ca6777，仅升级multidict锁块至6.9.1及更新三条期望版本。

本地发现venv版本漂移后已对齐134包完整生产锁；50项锁/版本测试、56项传输/API测试通过，完整库存漏洞审计通过（本地默认audit的ensurepip SIGABRT失败单独保留，未改CI命令）。锁定环境标准live重新运行10次真实API，0失败、用量完整、27份源码/锁摘要不变。证据与限制见[发布预检续节](../reviews/2026-10-08-prompt-release-preflight.md)及[锁定环境真实闸](../reviews/2026-10-08-release-locked-live-regression.json)。尚未main合并或部署；截图问题将在本批发布后接续，不能把泛化失败文案当作已定位根因。

### Main 合并后的 CI 断点：保留失败，补充诊断

候选8694a449的PR CI37727741607全部29项通过，经独立GO后快进合入main，PR277已合并。main同SHA的CI37728657086在balanced-02失败：`test_full_pi_task_preserves_read_contract_and_persistence[available]` 的empty_terminal返回failed_contracts。该回合仍有两次模型调用和complete终态，不能由此推断所有契约通过；原断言的字典repr截断隐藏了具体quality位。

本地锁定环境单文件66项、原f分片288项、30次六变体available重复均通过；这些不能替代失败的main CI。新增断言仅将既有质量位、工具契约、数据库错误类别和终态序列化为完整诊断，不改通过条件、不含原始用户数据、不改运行时。SQLite StaticPool与Twin多会话共享连接是待验证风险，尚未证明为本次根因。生产保持a10e642c，未执行bootstrap/Trusted部署；餐食图片识别和泛化错误文案仍待本批发布后接续。

### 评测数据库隔离缺陷已确定性复现并修复，待新候选闸

诊断CI37730165508在另一场景展开了InterfaceError，仅数据库上下文检查失败；同轮另一路由场景及最初main失败仍缺历史细项，不追认根因。新增RED证明StaticPool四线程和主会话共用一个连接、worker关闭会回滚主事务。现改为eval-only随机命名共享内存库和独立连接，保持并发、真实链路、所有oracle及生产配置。

319项CI-mode与补充4项负测通过；CLI18任务通过。所有状态断言补完整窄诊断。新鲜live、独立复审和Linux/main精确CI尚待完成；发布仍阻断。完整证据边界见[隔离修复记录](../reviews/2026-10-08-benchmark-database-isolation.md)。

隔离修复固定源码515531e96的真实闸5场景+5judge（10 API）通过，28份源码/锁摘要不变；复审补全剩余路由诊断和建表失败清理，13项通过。最终CLI18任务及25份源码摘要完全匹配，证据已持久化。System Map/秘密扫描/阻断Ruff通过，待最终复审与Linux/main CI；仍未部署。

### 精确 main CI 通过，Trusted 预检的事件类型阻断

独立审查对1c86269e4875a16ba27a9dabf763fa08a43175dd裁决代码及默认关闭发布准入GO，实验激活仍NO-GO。PR278的CI37731876684与快进合并后的main CI37732948052均29项成功；Linux balanced-02的f分片293项、agent-i-l分片7136项、twin-api分片4项零失败。它们与本地集合重叠，不合并计数。

Trusted validate 37733904268在凭据前失败：现有门禁核对同SHA的每条CI记录，PR事件不满足其main push/workflow_dispatch合同。因此即使同SHA两条CI均绿色，1c862仍不可发布。保留原失败，不重跑、不修改门禁；本次仅追加验证记录，形成独立main发布提交后重新等待完整精确CI。运行时、依赖、评测源码及28份live绑定摘要保持不变。

当前生产仍a10e642cde189c9b414dc8d41346e22f088eaa0e，原回执SUCCEEDED、业务lease不存在、launcher inode7777226。GitHub relay启用且active，隔离官方Git查询main身份一致。尚未撤权、销毁旧私钥、轮换授权或部署。餐食问题已完成只读定位，按用户指定顺序在本次发布后修复；未以截图或时间相近日志冒充完整用户路径验收。

## 2026-10-08 Backend/Web 已发布，接续餐食错误分类修复

第一批优化修复已合入 main 并部署 `0fe1122ad1f5fa3f36bf25607e10339e4b989609`：完整 CI 37734502146 全部29项成功；Trusted validate 37735680343、backend 37736434279 成功，后端回执 SUCCEEDED、健康评分60/60。Web operation `ad84dc77ca0b41a4a5a01a10168ca640` 为 FRONTEND_SUCCEEDED；实际 sharp0.35.5/rsvg2.63.2、公网页面、服务状态与原后端身份保持验证通过。独立 G5 GO，详见[精确发布证明](../reviews/2026-10-08-prompt-deployment-verification.json)。这不等于登录健康流程、Mobile 发布或用户 G6 验收；预规划及被否决预算/写工具说明实验保持关闭。

用户要求发布后修复“记录这餐”图片识别失败及泛化错误。本次沿用原 controller/run，范围为既有识别与终态错误语义，不新增写权限、健康对象或产品入口。已用合成 run_stream 复现 generic write_without_tool：有效 JSON 备注含拒绝词被整体拒绝、nofood 二次清洗丢分类、混合 timeout 被当 nofood、最终错误覆盖了补充提示。

修复先解析并验证模型 JSON，内部派生错误类别；当前用户/消息/图片绑定且封闭纯餐食记录意图下，缺少可记录食物返回 waiting_for_user 并明确未保存；服务或格式失败保持 failed/retryable 并给清楚重试说明。混合任务、部分成功、已有回执、待确认、其他工具失败、只读与来源不明仍走原流程。没有新增草稿/回执或额外写入。有效食物加普通不确定备注继续通过。

G3 本地：312关联回归、21 CI-mode集成、PostgreSQL196项及补充3项下一轮/重放用例通过；原Mobile恢复 waiting_for_user 1项通过；System Map通过。第一轮安全审查发现显式success=false及空food对象会误归nofood，补3项RED后收紧模型契约并复跑。真实模型首轮缺配置失败保留，授权测试配置仅进进程内存；修前10次API通过不替代修后新鲜证据。详见[餐食验证](../reviews/2026-10-08-meal-photo-validation.json)。修后标准live闸10次真实API通过、0失败、用量完整且源码摘要不变，见[修后真实闸](../reviews/2026-10-08-meal-photo-live-regression.json)。独立 G4 复审 GO，绑定 `ae6e99566a7bd3d24992e228bd8bb488d8c03d4c`；reviewer另跑244项与12个Base64/URL契约探针通过。餐食修复尚未push/部署，下一步精确main CI与Trusted后端发布。原截图是餐后残留，不据此声称能还原整餐；本地测试没有复用真实健康图片。

### 餐食修复正式发布与后验

已合入 main 并通过完整精确 CI `37741765620`（29项成功），push CI `37741692327` 成功。Trusted validate `37743406333`、backend `37744317239` 成功，生产精确版本 `1e3a19e58b075364ed6769f91a374cfc991d554b`，正式回执 SUCCEEDED。原授权按 canonical bootstrap 退休，新授权安装成功，原 launcher inode 与历史回执保留，无部署重跑。

上线后验：生产 tracked tree 干净、三个修改的运行时文件摘要与受审源码一致；三轮健康评分60/60；backend、worker、beat正常且restart count为0；实际前端服务 health-frontend 完整身份与上一批Web发布后相同；发布租约已释放。四项公开接口检查（健康200、未授权Agent401、隐私页200、健康连接页200）TLS验证通过；当前配置加载的四项实验/思考开关仍为原关闭值。探针首次误查不存在的 health-web，修正为实际unit后只读复验通过，没有修改生产或重跑部署。详见[餐食发布证明](../reviews/2026-10-08-meal-photo-deployment.json)。

独立 G5 后验复核 GO，确认精确CI、回执、运行时摘要、服务/租约与公开端点证据一致；后续稳定窗口四个服务PID保持且零重启。G6边界：合成流式路径、重放及下一轮测试已通过；未用用户原餐食图片进行真实线上识别，没有读取/写入生产健康记录，不能声称原图识别准确率或用户验收已通过。本次只发布后端，沿用现有Mobile waiting_for_user协议，不需要OTA/原生包，也未执行Mobile发布。

## 2026-10-08 截图问题后续：所选体检报告与手机端错误一致性

用户要求“全部解决并发布”，并追加体检报告截图：产品入口的报告解读原话被误判未授权，失败回复同时附有化验卡和回答依据。本轮延续原 Dossier/run，不复制截图中的个人指标。

- 补齐两个既有产品入口原话的封闭授权识别；30 天为建议时间范围，不扩展个人数据读取窗口。引用、他人、撤回等负例仍不授权。
- `medical-exam/{id}` 仅作为选择器；服务端按认证用户、报告 ID 和非未来日期核验，禁止回退其它报告。客户端摘要和控制提示不作医学证据。
- 所选报告回合不加载全量 Twin、其它报告、旧聊天摘要或可执行历史引用；历史聊天仍原样持久化。模型只获得所选报告读工具与公共知识工具，服务端另行检查范围和原有授权。
- 失败、阻断和中断的卡片、回答依据与引用在后端最终出口和 Mobile 实时/历史路径保持一致；保留真实写入回执以及正常部分成功结果。组合症状超出所选报告范围时明确未完成联合解读，保留原有紧急分流。
- Mobile 的“基于 基于……”标签去重；这部分按 Trusted OTA 发布，不涉及原生变化。

验证保留了失败过程：首轮安全评审发现旧会话泄漏到模型，补充真实历史对抗测试后修复；真实模型首次有效报告验收完成了报告读取但又尝试范围外工具，终态 blocked，未作为通过。后续收窄模型工具投影并补上下文规则。独立脚本曾缺少测试签名密钥，相关失败已标明测试环境无效，未修改生产密钥或绕过同意校验。最终上线状态以本节后续精确 SHA、CI、后端和 OTA 回执为准，当前仍在验证中。

餐食使用生产配置的真实视觉模型验证了空白、截图中的餐盘残渣及公开米饭图片；残渣端到端为待补充信息、无健康写入、流与持久化一致，同一请求重放不再次识别。截图裁剪仅在临时内存/目录处理，不提交原图；它不是原始全分辨率照片验收。首个端到端脚本缺失指标表导致上下文降级，已作废；补齐全部模型表并使用独立连接的临时内存库后通过且数据库错误为零。详见 `docs/reviews/2026-10-08-meal-photo-live-vision.json`。此前被否决的写入工具说明精简与未准入预规划继续关闭。

最终运行时 `2a9650fa35fd354a8c55b90f34fba750758a7836`：语义/授权 3260、执行 203、引用 20、Mobile 229、TypeScript、System Map、锁定依赖 134 与 CI-mode 集成 21 通过。PostgreSQL 原回归 375、最终所选报告 26 通过，临时集群已删除。最终真实报告验收 19 检查、4 次 API、source 不变，历史/档案/Twin 读取 spy 和 SQL 错误均为零；标准真实模型闸 10 次 API 通过。**最终报告耗时 155.35 秒，存在长尾，不宣称稳定提速**。中间源码变化导致一份标准闸 `failed_source_changed`，保持失败记录，不算发布证据。

餐食补证另保留一次断言失败：等待用户终态已成立，但该探针未完整保留“尚未保存”文案/流持久化失败的分项数据；后续带诊断的通过不能追认原失败或证明语义重复性。最终代码针对无食物与低置信确认的实际流契约 4 项通过，视觉解析及四个餐食关键函数相对已部署版本未变。此限制不包装成原图 G6 全通过，详见 `docs/reviews/2026-10-08-selected-report-validation.json`。发布仍待固定提交安全 GO、精确主干完整 CI、后端和 OTA 回执。

独立 G4 对 `2a9650fa3` 给出 GO：后端 115、原历史对抗 2、Mobile 201 通过，额外 schema 不变性/权限断言通过；最终两份真实模型证据共 36 份源码哈希匹配。GO 不替代上线或逐条临床正文验收。随后仅提交本轮脱敏证据，不改变受审运行时；用户已授权合并 main、后端及手机发布。

### 后端正式上线；Mobile OTA 未交付

发布版本 `5c1ef73518af8e49066cc9aab19c9558a084e05f` 已快进 main，完整 CI `37750199480` 29 项成功，Trusted validate `37751737519` 和 backend `37753182343` 成功。生产同 SHA 正式回执 SUCCEEDED，五个关键运行时文件摘要一致；三轮健康 60/60，四个公开 HTTP/TLS 检查通过，四个服务正常、零重启，旧前端身份保持。独立 G5 后端 GO。按发布治理默认跳过数据库备份/恢复演练/站外归档，不把跳过记为通过。预规划和被否决实验仍关闭。

Mobile validate `37754437344` 成功，但 publish `37755008534` 在启动阶段失败；服务器无该 SHA 的 OTA claim/目录或业务 lease，未进入供应商发布，未重发。泛化捕获没有保存细项，不能断言该次启动失败的具体根因。另用实际合约独立确认：固定原生 cad 基线相对本次源码有原生模块、配置和依赖变更，兼容性 BLOCK；仅换为历史 a885/275 也不能自动证明整个 production runtime cohort 相容。当前 validate 未调用发布器上下文和源码兼容性检查，是确定的预检覆盖缺口，正在修复；不扩大 allowlist、不改基线绕过，也不宣布手机已更新。

详见 [本批发布证据](../reviews/2026-10-08-selected-report-deployment.json)。后端已交付；手机新包渠道待用户选择及对应签名/发布 Gate。原图全分辨率验收、登录用户 G6 和稳定提速仍未验证。

新鲜 Expo 只读查询完整短页：production/runtime1.3.4 的四个 STORE 构建 272–275 存在三种不同原生 fingerprint，旧基线问题并非只换 latest 即可解决。channel mapping 查询超时，保持未验证；无供应商写入。证据见 [原生 cohort](../reviews/2026-10-08-native-cohort-readonly.json)。默认二维码原生交付准备精确已部署 5c / build276，独立 clean clone，使用已有签名/profile、rokid-production 独立 channel；不注册设备、不 submit TestFlight，IPA 核验和公开回读前不称已发布。

预检覆盖修复仅增加无凭据的真实上下文/原生源码检查，放在 validate/publish 的凭据阶段之前；正式发布仍保留全部原私钥、授权和单次 claim/vendor 检查。错误使用固定 phase/reason，未知异常不输出载荷。RED8、producer105、root含OTA/server/QR共150项通过；System Map、secret、diff检查通过，独立复审进行中。原始70ms启动失败根因仍未证明；不重发原失败，也不扩大原生准入。

### 同源码二维码原生包已发布

因完整 production/runtime1.3.4 cohort 不兼容，保留 OTA NO-GO，按仓库默认二维码方式交付。独立 canonical clean 5c 构建 **1.3.4（276）**，已有有效签名/profile，runtime1.3.4、rokid-production channel，未创建凭据/注册设备/操作手机。归档、ad-hoc 导出及独立签名/team/bundle/生产 entitlement/profile证书/嵌入生产API/源码和IPA回执绑定验证通过。IPA SHA256 `a5d928152d5f8d3977c10ed3475a63397e0e64326685ef386830ff84f84b5bb4`。

独立首次上传 GO 后复用原 IPA 和相邻回执，只执行一次发布。新固定目录 `20261008-qr276-release-5c1ef73518af`；使用 `--no-latest` 保留旧真实 latest 目录，其 inode 和清单/安装页摘要后验保持。脚本 exit0；公网 app.ipa、manifest、install.html、install-url 和 qr.png 五份文件均 HTTP200、逐字摘要一致，生产仍5c且无发布lease。新安装页：https://health.executor.life/mobile-install/ios/20261008-qr276-release-5c1ef73518af/install.html 。详见 [QR发布回读](../reviews/2026-10-08-selected-report-qr-publication.json) 与 [独立制品复核](../reviews/2026-10-08-selected-report-qr-artifact-review.json)。

这是二维码 ad-hoc 交付，不是 OTA/TestFlight/App Store；仅授权设备可安装，当前用户手机覆盖/实际安装与原图登录用户 G6 未验证。后台与新包已交付不能抹去155秒报告长尾或单次餐食探针未定位失败。发布预检修复固定 `1daaafd95594b889bd6942cc692ea9cc1bebbb03` 独立 G4 GO；不会重发失败OTA或放宽原生边界。
