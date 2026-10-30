# 发布耗时优化

| 字段 | 值 |
| --- | --- |
| 状态 | complete |
| 当前阶段 | 第十一阶段 G4 PASS；近期六轮 placement 校准待 G5/G6 |

## G1 范围

裁决：PASS。用户要求尽可能缩短发布耗时。工程优化，不新增用户行为、健康对象或权限。Router implementation / health-harness-orchestrator + safety-gate；superpowers 禁用。沿用既有干净 main 发布目录，原工作区其他改动不动。

run_path：`docs/_generated/harness-runs/9e372629e4f4.jsonl`（本地）。

保留完整精确 SHA CI、独立安全审查、来源、授权、锁、无备份事务、schema 和线上健康闸。无应用行为、模型、数据库或 Mobile 改动。不得以候选工具本地测试冒充生产安装。

## G2 基线与方案

PASS。基线 f1b0d12421b0a0eb573d3b0280e7aa16306683f0。最近两轮完整 CI 40358356587 / 40431390771 分别约 12 分 16 秒 / 13 分，后者至独立线上核验总共约 28 分 03 秒。样本不足以建立 P95/P99。

1. 修复现有计时刷新器对 process_groups 的支持，要求每个子进程恰好一次、首轮成功，汇总回原分片。CLI 保留 deadline_calibration 等非调度元数据。以最近两轮成功日志的逐分片最大值更新 placement；测试选择、worker 数、超时和重试不变。
2. 优化 deploy.sh 中受跟踪文件的权限规范化：先完整校验 index 路径和实际类型；父目录去重，按固定类型以最多 128 路径 / 32768 字节的 argv 批次运行。保留 .git 权限处理，符号链接仅 lchown、不 chmod，不递归触碰忽略数据。异常命令失败向上传播。
3. 拆分停写后 runtime prepare、fetch、checkout 和权限处理时间戳，保留原远端时钟和失败条件链，拒绝从混合时钟推算耗时。
4. 本轮发布使用既有 canonical 授权与可信工作流连续执行，在前置通过后及时推进；不新建自动授权/失败重放协议。自动轮换事务需独立设计，不能仅为减少交接而绕过原操作状态。

验收目标：完整 CI 争取 9～10 分钟、整体发布争取 18～22 分钟；是目标而非保证。保持验证集合和安全语义，记录实测与回放区别。错误率增加、遗漏测试、权限目标扩张或 Gate 弱化均 NO-GO；不自动恢复旧配置或创建回退副本。

## G3 证据

- RED：分组计时刷新 unknown shard；权限规范化 66 个 tracked 文件执行 266 次权限命令，违反批量上限。新增分段计时两项在旧实现失败。
- 定向首轮：53 passed；完整部署/无备份/CI 合约回归 322 passed。独立审查发现 AND-list 下 errexit 失效可能掩盖 Python 权限失败，第一版 NO-GO。已为每个 prerequisite/mutation 添加显式失败传播，测试同时覆盖独立 subshell 与实际 AND-list 上下文；修复后 69 项定向通过。第二轮独立审查 268 passed，但发现 stat 先输出再非零退出时被 test 命令替换吞掉错误；已拆开赋值与结果判断。旧实现独立/AND-list 两项 RED，第三轮独立复审 270 passed，失败注入通过；对重接主干后的 4f8fffed375006b783cb8ccc586552f1114d8fd5 逐字节等价复核后 G4 GO。
- 同源 CI 日志离线回放：最长测试进程组 554.761 → 439.374 秒、542.367 → 431.308 秒。总测试进程耗时不变，不包含 runner 排队或环境准备，不是新 CI 实测。来源和非调度策略摘要见 `docs/reviews/2026-10-27-release-latency-replay.json`。
- 本机同批 1000 个合成文件权限处理对照：旧 8004 次权限命令 / 83.996 秒，新 22 次 / 0.416 秒。chown/chmod 使用记录目标的桩隔离进程启动开销，不能宣称真实所有权已变更或生产同幅加速。真实 chmod、路径拒绝、忽略数据不变和失败传播另有回归。见 `docs/reviews/2026-10-27-permission-batch-benchmark.json`。

## G4–G6

- G4 PASS：候选 `4f8fffed375006b783cb8ccc586552f1114d8fd5` 独立 GO；保留完整测试集合、执行期限与失败传播。
- G5 PASS：[完整 CI 40438974052](https://github.com/itsoso/health-llm-driven/actions/runs/40438974052) 首轮成功，11 分 42 秒。紧邻前一轮 40436764319 为 10 分 59 秒，故不能宣称整轮 CI 已稳定加快。最慢后端测试步骤 547 → 484 秒；本轮关键 job 在 CI 创建后 140 秒启动，存在调度等待。
- G6 PASS：[后端发布 40440607024](https://github.com/itsoso/health-llm-driven/actions/runs/40440607024) 由并行任务完成；本任务未重复部署。生产 SHA 与 SUCCEEDED 回执均绑定候选，runtime 终态 COMMITTED / code-only-no-backup，lease 不存在。health-backend、celery-worker、celery-beat 为 active；公网 `/api/v1/health` 200、匿名 `/api/v1/auth/me` 401。
- 同版本 [OTA 40441500904](https://github.com/itsoso/health-llm-driven/actions/runs/40441500904) 由并行任务发布，服务器 SUCCEEDED、intent/verified 摘要独立核对；本任务改动本身不需要 OTA，不声明设备已接收。

## 生产耗时实测

| 环节 | 紧邻上一轮 2fed3eaa | 本轮 4f8fffed | 说明 |
| --- | ---: | ---: | --- |
| 完整 CI | 659 秒 | 702 秒 | 总时长增加 43 秒，不能用离线回放冒充实际收益 |
| 最慢后端测试步骤 | 547 秒 | 484 秒 | 不含 runner 排队、安装和收尾 |
| 后端发布工作流 | 364 秒 | 264 秒 | 减少 100 秒，约 27% |
| 停写后至源码准备完成 | 90 秒 | 6 秒 | 同一远端 shell 时钟差值；包含 runtime prepare、fetch、checkout、权限 |
| 权限规范化 | 旧版无独立计时 | 小于 1 秒计时分辨率 | 新版 checkout 与 permissions 均落在 elapsed=20 的秒桶，不表示零成本 |

新版远端 checkpoint：writers_stopped=14、runtime_prepare=15、git_fetch=20、git_checkout=20、permissions=20、dependencies=65、schema=68、services_restarted=68。外层 finalized 从 303 秒降为 207 秒。保留所有健康与终态闸，不新增备份。

并发记录：本任务 stage 在发现其他流程已建立同候选 canonical 目录后，于 intent 之前拒绝；未重试、覆盖或轮换授权。用户随后要求等待另一任务完成再接管。本任务独立读回成功回执及健康状态完成核验，不重放已成功发布。后续 Web 发布也已完成：独立读回 operation `a9aa1cc0e069434d9040dc012df96ce8` 为 FRONTEND_SUCCEEDED，publisher 为 2ce44daedc3bb80386fea7dd54bbdddf74a27ed6，保留后端 4f8fffed；生产 BUILD_ID 与其回执一致，前端 active，lease 不存在。用户确认接管后，本任务同步核验记录，不重复生产发布。

仍需优化的主要方向是统一发布归属、减少重复 validate 和 runner 排队；后续相同分片策略的完整 CI 40442091206 为 707 秒，关键后端 job 延迟 139 秒启动；两个优化后样本均未证明整轮 CI 稳定加快。启动延迟混合调度与 runner 可用性，不能据此断言账户配额。减少 worker 可能延长串行执行，故本轮不做未经对照验证的并发或超时变更，也不能建立 P95 或保证固定发布时长。机器可读证据见 `docs/reviews/2026-10-27-release-latency-production.json`。


## 第二阶段：CI 启动顺序（2026-10-27）

用户继续授权优化。沿用本 Dossier、Harness trace 与 implementation / safety 流程；发布目标为 GitHub CI 工作流，无应用、Mobile 或发布器字节变化，不触发应用重启、授权轮换或重复 OTA。

G1/G2 PASS。基线 `1c78b9b800db4a35de9daa68ba0526f477d0e905`。最近两轮完整 CI 40438974052 / 40442091206 耗时 702 / 707 秒，关键后端 job 延迟 140 / 139 秒启动。短辅助任务与长测试同时申请 runner，启动顺序存在优化空间；没有把观察到的同时运行数量当成账户配额。

方案只为 frontend-artifact-integration、retained-runner-startup、ota-runner-startup、frontend-build、mobile-typecheck、type-drift 加入既有 docs-quality 依赖。后端分片、质量与 PostgreSQL 继续只依赖分类 job。所有 steps、条件、权限、制品、测试选择、worker 数、时限、聚合闸和发布准入保持原字节/结构。文档闸成功才放行辅助检查，失败/跳过/取消均由现有 always 聚合闸明确失败；成功候选的完整检查不减少。代价是辅助诊断稍晚返回。

GitHub 的 needs 成功依赖语义参见 [官方文档](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-jobs)。没有用 always 绕过新依赖，也没有把跳过的检查视为通过。

同批真实作业耗时的离线依赖回放见 `docs/reviews/2026-10-27-ci-admission-replay.json`。在模拟 20 个共享 runner 槽位时，两轮预计减少 104 / 26 秒；这不是 GitHub 实测或配额证明。16 槽位敏感性场景反而增加 21 / 40 秒，说明收益依赖排队形态，不能保证所有负载都加速。真实验收目标：首轮完整 CI 全绿，尽量低于 660 秒，后端启动长尾缩短；若总时长比原两轮中位数增加超过 10% 或发生遗漏/失败，停止继续推广并调查，不削减测试或延长超时。

G3 PASS：先新增契约测试，旧工作流 admission 测试 RED；新增依赖后 99 项 CI 合约、范围及准入回归通过。真实执行聚合 shell，覆盖文档闸 success/failure/skipped/cancelled 与是否选择 backend/release 两种范围，失败不能伪装为绿色。扩展工作流/发布准入回归 271 passed、7 个平台专属测试本地 skipped；这些检查仍保留真实 CI 入口。更新既有前端制品并行契约后，相关 31 项通过。已逐 job 比较，除六条 needs 依赖外所有属性相同。

G4 PASS：独立安全复核精确提交 `a3492a05af00f50a96ab552ac2403eb7d2e0658b` 为 GO。110 项复核通过；52 项缺失或非成功依赖注入全部被拒绝。DAG 无环，除六条依赖外所有 job 属性一致，长任务不依赖文档闸，聚合与发布准入保留失败语义。

G5 PASS：[完整 CI 40447632037](https://github.com/itsoso/health-llm-driven/actions/runs/40447632037) 绑定上述精确提交，attempt=1，32/32 job 成功，无 skipped、重跑或取消。Git 默认凭据的第一次推送因缺少 workflow scope 被 GitHub 拒绝，远端未变化；使用现有具备 workflow 权限的 gh 身份作为单次 Git credential helper 后推送成功，没有创建凭据、改变全局配置或修改仓库规则。

G6 PASS：工作流已在 main 生效，实际运行验证完成；本阶段只涉及 CI、测试及证据文档，不部署后端、不轮换生产授权、不重复 OTA。真实候选耗时低于 660 秒目标，未触发超过基线中位数 10% 的停止条件。

| 指标 | 基线 40438974052 | 基线 40442091206 | 本轮 40447632037 |
| --- | ---: | ---: | ---: |
| 完整 CI | 702 秒 | 707 秒 | 631 秒 |
| 全部后端分片最晚启动 | 140 秒 | 168 秒 | 27 秒 |
| 最后完成后端 job 的启动 | 140 秒 | 139 秒 | 15 秒 |
| 最慢后端测试步骤 | 484 秒 | 580 秒 | 547 秒 |
| 六项辅助检查全部完成 | 第 153 秒 | 第 168 秒 | 第 473 秒 |
| 成功 job 数 | 32 | 32 | 32 |

本轮总耗时比两轮基线减少 71 / 76 秒，约 10%；相对中位数减少 73.5 秒（10.43%）。辅助结果确实晚返回，但第 473 秒已全部完成，没有成为本轮关键路径。当前最后完成的 balanced-07：第 15 秒启动，依赖安装 35 秒，实际测试 547 秒，第 620 秒结束，聚合收尾至第 631 秒。后续优化重点转为测试执行长尾；先分析逐测试计时，不能靠削减检查、增大时限或重复挑选成功样本获得提速。

机器可读实测见 `docs/reviews/2026-10-27-ci-admission-production.json`，包含三轮完整 job/step 耗时、精确 SHA、attempt 与原始 jobs 导出摘要。一个候选样本不能建立 P95 或保证每次加速；runner 与测试执行波动仍存在。离线回放与真实 CI 明确分开。


## 第三阶段：近期测试耗时校准（2026-10-27）

用户再次要求继续优化 CI。沿用原 Dossier 和 Harness；implementation / safety-gate。本阶段只刷新 placement telemetry 及其证据/合约测试，不改应用、工作流 steps、worker 数、测试选择、进程边界、重试、时限或安全闸。

G1/G2 PASS。基线 main `dabcddab5e8ac33f9570f7ba1c1655ccf24b8db2`（文档 CI 首轮成功）；最近完整 CI `40447632037` 为 631 秒，最晚分片 27 秒启动。关键 balanced-07 在第 15 秒启动，其中 s-l-z 进程 412.584 秒，随后 d-data-device、n、timeline-medications 共 134.293 秒，合计 546.877 秒。逐测试 JUnit 最大单例约 25 秒，长尾主要是组合后的串行工作量，暂不修改单测语义。

原权重来自更早的 40358356587 / 40431390771。用现有严格刷新器，从 40438974052 / 40442091206 / 40447632037 三轮 GitHub 日志读取每个进程恰好一次、attempt=1、exit=0 的完整耗时，逐 shard 取最大值。已独立核验三轮 run_id、完整 SHA、attempt 和 success；日志归档摘要写入 catalog。保留所有非调度字段的规范化 SHA256 `53c3ead6686f4816b71f64ca5c19dcd611d117172784df7c9a4e14af8ec28425`。

同批真实进程耗时离线回放，最长 worker：483.901→455.467、579.295→451.798、546.877→449.668 秒。留一验证（只用另外两轮生成权重）：489.896、497.710、477.376 秒；最早样本比旧分配慢 5.995 秒，明确记录波动，不挑选样本。见 `docs/reviews/2026-10-27-ci-weight-refresh-replay.json`。回放不含排队、安装与收尾，不是实际新 CI，不足以建立 P95/P99。

成本与目标：仍使用 16 worker 和相同测试进程，不增加并发或测试计算量；希望完整 CI 低于 570 秒、最长测试步骤低于 500 秒。若完整耗时比 631 秒增加超过 10%（694.1 秒），或任一测试遗漏/失败，则停止推广并调查；不削减测试、不增加超时、不创建备份/回退副本。

G3 PASS：旧 catalog 在更新后的新鲜来源合约中 RED；校准后 66 项调度/CI 合约、23 项真实 runner 回归通过。新增完整执行策略摘要约束覆盖嵌套 process_groups、deadline_calibration 与 worker 数；逐字段比较一致。System Map、Dossier、LLM 变更闸（无需 live）、diff 检查通过。本地 runner 首次因默认 PostgreSQL 未运行而在 conftest 导入失败；按 CI 的 DATABASE_URL=sqlite:///:memory: 环境重跑通过，此处只验证执行器，不宣称 PostgreSQL 语义验收。

G4 PASS：固定提交 `51255fce58057c956e17569d984a806bedc73be9` 独立 GO。逐字段核验非调度策略一致；独立校验三轮日志摘要、每个进程首轮成功、最大值权重及全部回放/留一结果。独立 130 项合约/发布准入与 23 项 runner 测试通过，工作树未改动。

G5 PASS：[完整 CI 40451454145](https://github.com/itsoso/health-llm-driven/actions/runs/40451454145) 绑定精确候选，attempt=1，32/32 job 全部 success，无重跑、取消或 skipped job。完整时长 587 秒，最晚后端启动 26 秒，最慢后端测试步骤 496 秒。

G6 PASS：main 的调度权重已生效并完成真实运行。完整耗时比紧邻基线 631 秒减少 44 秒（6.97%），最慢测试步骤 547→496 秒，减少 51 秒（9.32%）。570 秒完整 CI 目标未达到，差 17 秒；500 秒最慢测试目标达到；未触发 694.1 秒停止阈值。保留此首轮结果，不重跑挑选样本。只涉及 CI 调度，无应用部署、生产授权轮换或 OTA。

新增实际日志确认 64 个进程全部首轮成功；JUnit 逐进程 testcase 身份与结果多重集合完全相同：35,701 条结果、155 条既有 skipped testcase、无 failure/error。跳过的 testcase 与 CI job 状态分开，不用通过率掩盖遗漏。对应规范化清单摘要和日志摘要见 `docs/reviews/2026-10-27-ci-weight-refresh-production.json`。

| 指标 | 第二阶段基线 | 第三阶段实测 |
| --- | ---: | ---: |
| 完整 CI | 631 秒 | 587 秒 |
| 全部后端分片最晚启动 | 27 秒 | 26 秒 |
| 最慢测试步骤 | 547 秒 | 496 秒 |
| 最后完成的后端 job 执行 | 605 秒 | 560 秒 |
| 最后完成后端 job 的依赖安装 | 35 秒 | 40 秒 |
| 测试结果条数 / 既有跳过项 | 35,701 / 155 | 35,701 / 155 |

本轮最后完成后端 balanced-09 在第 15 秒启动，实际测试 494 秒，第 575 秒结束，聚合至第 587 秒；另一个分片的测试步骤为全局最长 496 秒。更早两轮完整 CI 702 / 707 秒到本轮 587 秒累计减少 115 / 120 秒（约 16%～17%），但相隔运行仍受 runner 和执行波动影响，不构成稳定因果收益或 P95/P99 保证。


## 第四阶段：测试环境依赖预编译（2026-10-27）

用户继续要求优化 CI。沿用原 Dossier / Harness，implementation / safety-gate。本阶段仅修改 backend-test-shards 安装命令，保留所有测试、安全、PostgreSQL 与发布闸；不改应用运行时、不部署应用或 OTA。

G1/G2 PASS。基线 `53d7efa1626011228b2e66166d21540f425847d9`、最近完整 CI 40451454145（587 秒）。四轮 40438974052 / 40442091206 / 40447632037 / 40451454145 的 16 个 worker 安装依赖中位数为 35 / 36.5 / 35.5 / 35.5 秒，最新范围 23～42 秒。测试步骤依然是大头，但已有调度优化后，不继续盲目重排。

调查组合查询套件：最新 JUnit 累计约 1,190 秒；代表性 8 个原样 runtime 用例本地 cProfile 8 passed，36.64 秒 pytest 时间。耗时主要在真实执行/规则路径，setup 单例不超过约 0.42 秒；不把该采样当成完整 CI 基准，也不以 mock 取代真实语义覆盖。

方案：仅两条 pip install 增加 `--no-compile`，让实际导入的依赖正常按需编译。保留原 pip、相同 lock/dev 文件、`--require-hashes`、缓存机制和全部 runner 命令；不新增依赖缓存、不关闭 Python 断言、不设置 PYTHONOPTIMIZE/PYTHONDONTWRITEBYTECODE。官方参数定义见 [pip install 文档](https://pip.pypa.io/en/stable/cli/pip_install/#cmdoption-no-compile)。这是临时测试环境优化，不修改生产构建预编译策略。

成本/验收：16 worker 与全部进程保持不变；目标依赖安装中位数低于 25 秒、完整 CI 低于 570 秒。需同时观察首次导入及整个测试阶段，不能只将开销从安装移到测试。若完整耗时超过 645.7 秒（基线 +10%）、测试阶段超过 545.6 秒（基线 496 +10%）或覆盖/哈希/失败语义变弱，则停止进一步推广并调查；不削减测试、不延长超时、不创建备份副本。单轮样本不证明稳定 P95/P99。

G3：新增精确安装契约旧工作流 RED，修复后 142 项 CI 合约/发布准入/runner 调度回归通过。独立离线 wheel 探针验证安装后源码一致、默认预编译与按需编译结果一致、真实导入成功、错误哈希被拒绝；这是 pip 语义探针，不是生产依赖或性能基准。

G4 PASS：独立 reviewer 对 `c81b7098eaa38adabc78350f700bd431234267d7` 给出 GO，96 项合约/准入/布线测试通过；独立复跑 pip 离线哈希/按需编译探针、重算四轮安装基线一致，解析后 workflow 除两个参数外完全相等。

G5 PASS：[完整 CI 40454901291](https://github.com/itsoso/health-llm-driven/actions/runs/40454901291) 绑定上述精确 SHA，attempt=1、32/32 job success，无重跑或 skipped job。真实 PostgreSQL、端侧与发布聚合闸全部通过。

G6 PASS：安装配置已在 main 生效。完整 CI 587→560 秒（9 分 20 秒），减少 27 秒（4.6%）；依赖安装中位数 35.5→16 秒（减少 54.93%），本轮安装范围 11～22 秒。最长测试步骤 496→482 秒，最长单 worker 安装加测试 534→498 秒，没有只把全部收益转移到测试阶段。本轮 570 秒整轮目标、25 秒安装中位数目标均达成，未触发停止阈值。

| 指标 | 第三阶段基线 | 第四阶段实测 |
| --- | ---: | ---: |
| 完整 CI | 587 秒 | 560 秒 |
| 安装依赖中位数 | 35.5 秒 | 16 秒 |
| 最慢测试步骤 | 496 秒 | 482 秒 |
| 最长单 worker 安装加测试 | 534 秒 | 498 秒 |
| 全部后端分片最晚启动 | 26 秒 | 12 秒 |
| 后端 worker 执行时间总和 | 7,447 秒 | 6,402 秒 |

关键 balanced-14 第 12 秒启动，安装 16 秒、测试 482 秒，第 550 秒完成，聚合至第 560 秒。启动和执行均有波动，不能把 27 秒整轮改善或 worker 时间总和下降全部归因于单个参数，也不推断费用/P95/P99。此阶段不修改生产应用或重复 OTA。

原始日志复核 64 个测试进程全部首轮成功；与基线逐进程 testcase 身份及结果多重集合完全相同，共 35,701 条结果、155 条既有 skipped testcase，无 failure/error。证据见 `docs/reviews/2026-10-27-ci-bytecode-production.json`（精确 SHA、run、jobs 摘要、逐步骤耗时、覆盖清单摘要及目标裁决）。基线文档中的 candidate pending 描述保留为测量前记录，以本节和实际证据为最终裁决。


## 跨 Agent 复用：共享 Harness 入口（2026-10-27）

用户询问部署状态、Harness 留存与其他 Agent 如何复用。已上线的 CI 优化与本节治理补充分别验收；不触发应用重启或重复 OTA。

共享真源为 `docs/governance/performance.md` 的 CI / 发布流程，沿用 AGENTS §5 的既有链接，两端 Health Harness adapter 按任务条件读取。合同 patch 升为 1.0.4，注册表增加性能治理引用与新内容摘要，package 合同测试同步；不改变插件安装状态、路由、工具权限、测试选择或发布 Gate。流程要求按精确 revision 恢复证据、拆分耗时、复用现有报告器/权重刷新器、保持质量底线、真实 CI 验收，并将结果提交到原 Dossier / reviews。旧 checkout 或已加载的插件缓存不会自动刷新，接手 Agent 必须核对并更新到目标版本；本地 trace 不作为共享交付证明。

验证：先登记必需引用时治理检查 RED（adapter_semantic_marker_missing），补齐两端引用与摘要后 PASS。分别在内存删除引用、同时更新内容摘要仍被拒绝。治理及插件合同测试最终 115 passed；System Map、Dossier 一致性、两个 skill quick_validate、LLM change gate（无需 live eval）与 diff whitespace 检查通过。初轮发现 AGENTS 超过既有 10 KiB 约束及固定合同版本未同步，已保留原 AGENTS 入口、修正版本，未放宽测试；独立评审还修正了报告命令的解释器前缀。独立复核 GO，失败项及 package 12/12 通过，两端内容与边界一致。

交接基线为 `f466569f11aeef3616571a5d9adce1c0229f0ec9`，已 fast-forward 接入其他任务无重叠的 main 更新。此处记录本地验证；推送与新精确 SHA 的 CI 结果须以实际 GitHub 记录为准，不提前声明完成。


## 第五阶段：剩余瓶颈与 PostgreSQL 负载（2026-10-27）

用户认为 CI 仍太长，继续授权优化。Router implementation / health-harness-orchestrator + safety；沿用同一 Dossier 和 trace。上一轮 Harness 提交 `d83bfdf2866a583cb217e4c03cc9c697518ff874` 的 CI 40457581729 已首轮全绿。已 fast-forward 接入其他任务主干 `9fd15d602dc34be3f0a30146f76909c65233bbe6`；对应 CI 40460622845 首轮全绿，实际 586 秒。此轮仅调整测试分组，不改应用行为、不部署应用或 OTA。

G1/G2 PASS。当前安装约 15～18 秒，长尾已在测试执行。两轮完整 CI 40456684952 / 40457581729 的 PostgreSQL JUnit 两组累计分别为 291.798 / 396.142 秒、279.886 / 379.689 秒；最新 main 为 243.192 / 335.449 秒。每轮完整 499 条结果、无 skip。保持原两进程、独立 DB / Redis、所有选择器和执行参数，只把 `test_remote_health_oauth.py` 整个模块从第二组移至第一组。三轮同样本离线回放的最慢组减少约 37.53～45.96 秒；这是 JUnit 累计耗时回放，不含启动/资源争用，不保证总 CI 同幅下降。最新 main 的关键路径在普通 backend worker，故本轮首先消除 PostgreSQL 的剩余长尾，不能提前宣称整轮 CI 提速。

拒绝两种未经证实的加速：普通分片再次按最新权重校准，三轮留一回放均退化；16→18 worker 在假设 20 个共享 runner 槽位的 DAG 回放中均推迟总完成时间，原因是辅助任务排队。该模型不是账户配额证明，未改变实际 worker 数或权重。后续大幅缩短完整 CI 需要继续剖析测试执行热点；当前 cProfile 仅是调查线索，不修改健康语义或缓存授权判断。

目标：真实 PostgreSQL 阶段缩短，完整测试和隔离不退化；若病例集合、skip 或失败传播变化立即 NO-GO。若整轮耗时比本轮基线增加超过 10%，停止推广并调查，不以重跑挑选最好结果。共享回放证据为 `docs/reviews/2026-10-27-postgres-placement-replay.json`，包括三轮精确 SHA、job / attempt、逐选择器耗时、JUnit 摘要及前后分组。既有全选择器合约不改；新平衡测试在旧分组 RED。

G3 PASS：本地 CI 合约及编排回归 59 passed、3 项需要真实 PG/Redis 的检查 skipped（仍由真实 CI 执行）；本机旧 backend venv 缺少 MCP 依赖导致移动模块收集失败，创建隔离环境按项目 hash lock 安装后，移动模块真实 PostgreSQL 26 passed、无 skip。自建本地 PostgreSQL 实例已停止。不能把环境失败或 SQLite 结果当 PG 验收。

G4 PASS：独立 reviewer 对固定 `1259485b3` 给出 GO，独立 59 项回归通过、3 项真实 PG/Redis 条件 skip；三轮原始 XML 的 499 项集合、摘要、SHA、首轮成功、全部选择器耗时与回放逐项一致。移动模块 fixture 均按测试隔离，前置 navigation 模块连接与 patch 生命周期清理，无顺序/状态阻断。随后接入其他任务无交叠前端更新 `38be6d970f7973c878057bb708a3a13d6939f2f1`，本轮运行脚本及测试字节保持评审版本不变；独立 reviewer 对最终 `ea55da9c01c50154f460bd208666e3f76686dbb5` 再次给出 GO。

G5 PASS：[完整 CI 40469166838](https://github.com/itsoso/health-llm-driven/actions/runs/40469166838) 绑定上述精确 SHA，attempt=1、32/32 job 成功。PostgreSQL 499 项身份/结果集合与三轮基线及紧邻主干一致、零 skip；普通后端 64 份 JUnit 的 35,788 项身份/结果逐进程与紧邻主干一致，155 项既有 skip 保持不变。仅修改 CI 分组、回归和证据，未部署后端或 OTA。状态读取曾发生 EOF/超时；最终使用完整成功 run / jobs / artifacts 核验，没有重跑 workflow 或挑选成功样本。

G6 实测完成，但 PostgreSQL 提速目标未达，回 G2 继续定位；不将本轮标为提速交付成功。与紧邻主干相比，完整 CI 576→573 秒（9 分 33 秒），仅减少 3 秒；与预声明 586 秒基线相比减少 13 秒。PostgreSQL 测试步骤反而从 302→373 秒，整个 job 从 407→476 秒。两组 JUnit 负载差由 82.71 缩小到 24.13 秒，但累计用例执行时间也变化，不能将差异单独归因为分组或 runner。未触发整轮高于 644.6 秒的停止阈值；保留已验证的均衡分组，但没有证据证明 PostgreSQL 或整轮持续提速，也不追加重跑挑最好结果。

| 指标 | 预声明基线 40460622845 | 紧邻主干 40468093798 | 候选 40469166838 |
| --- | ---: | ---: | ---: |
| 完整 CI | 586 秒 | 576 秒 | 573 秒 |
| PostgreSQL 测试步骤 | 352 秒 | 302 秒 | 373 秒 |
| PostgreSQL 整个 job | 447 秒 | 407 秒 | 476 秒 |
| 最慢普通后端测试步骤 | 505 秒 | 509 秒 | 499 秒 |
| 最后完成的非聚合 job | balanced-09 | balanced-09 | balanced-15 |

机器证据见 `docs/reviews/2026-10-27-postgres-placement-production.json`。核心限制仍是普通后端执行阶段；样本不足以建立 P95/P99。下一轮不继续盲调权重或提高 worker 数，转向下述已有完整 CI 与本机调用证据的重复解析热点。

### 后续热点：组合查询的重复解析

主干 `38be6d970f7973c878057bb708a3a13d6939f2f1` 的完整 CI 40468093798 首轮成功，总耗时 576 秒。64 份后端 JUnit 共 35,788 条结果，累计用例耗时约 5,366.65 秒；其中 `test_agent_composed_synthesis_projection` 占约 1,191.61 秒（22.2%）。这是并行进程中 setup/call/teardown 的累计值，不能与整轮墙钟时长相加或直接相减。

相同源码上的一个原样组合查询用例在本机独立锁定依赖环境执行成功。cProfile 定位后，以只计数、不缓存的包装再次调用原函数：读取语义解析 9,317 次，仅 9 种参数组合；读取权限文本提取 22,117 次，仅 10 种参数组合；疾病实体解析 8,603 次、45 种参数组合。完整结果、环境、逐函数计时、原始 JUnit 摘要和可重现探针见 `docs/reviews/2026-10-27-ci-runtime-profile.json`。采样包含收集/fixture，profiler 有额外开销；重复参数不能单独证明缓存安全，也不能据此估计整轮收益。

下一轮优先评估同一不可变请求上下文内复用纯文本解析结果；权限决定仍逐次校验，不建立全局健康文本缓存。必须先验证 owner/date、第三方拒绝、引用文本、上下文变更、可变返回值、并发、取消和异常路径，再比较同一套测试及真实 CI。本轮未修改应用语义、引入缓存或替换真实执行为 mock；该方向仍是待验证实验，不属于已交付提速。

## 第六阶段：CI 分段、模块反馈与架构分层

用户要求从全局架构分析各阶段、修改时模块回归及模块拆分。G1/G2 PASS：沿用 Harness / safety / System Map，基线 `5b45d4ca0017fc16ae87a086539bfdcdb2462c30`；原共享工作区改动不动，在既有干净 main 目录推进。全景与聚焦源码确认 System Map 不是完整测试依赖图，CI 路径未索引后运行中央 System Map 检查通过。

设计见 [CI 分层与模块回归](../plans/2026-10-27-ci-layered-feedback.md)。当前 last-work-job 时间线 15 秒启动延迟 + 25 秒环境 + 16 秒安装 + 499 秒测试 + 2 秒其他步骤 + 5 秒未归属 + 11 秒收尾 = 573 秒。现有 local/PR 已有端侧分类，非文档 main push 强制 full；release-preflight 的后端分支尚未自动调用模块测试。旧发布器和 OTA 的完整 CI 准入不能通过单改 path filter 绕过。

本轮实现两项：现有 `release_performance_report.py` 增加逐 job 分类与最后完成工作 job 的时间分解，拒绝负时长、越界和重叠，缺失计时保留为未归属；`ci_module_feedback.py` 提供本地变更/显式模块反馈，未知或公共范围拒绝窄执行，保留真实 fixture、模块覆盖率 ≥80%、测试失败/超时非零，不重试。采集 staged/unstaged/untracked，输出始终 `full_ci_required=true`、`release_authority=false`。无 CI 选集/工作流/发布准入/应用行为变化。

G3 进行中：报告旧实现 RED；模块入口缺失 RED；84 项现有 CI 契约和新增回归已通过，包含真实子进程失败传播及真实 Git staged/unstaged/untracked 采集。覆盖率初版按模块名设置 source 触发提前导入和 SQLAlchemy 重复注册，已弃用；保持正常 app 采集/导入顺序，仅通过临时配置收窄模块报告并隔离 coverage 输出。初始格式化/表格测试模块覆盖率 75.12%，80% 闸正确拒绝；已补入现有日历展示和报告卡片消费者测试，未降低阈值或减少原测试。完整实测和 G4/G5 待补。

G3 功能验证补充：展示模块含消费者 99 passed、覆盖率 87.21%，本机入口墙钟 35.74 秒；提示缓存 24 passed、覆盖率 100%，墙钟 10.01 秒。普通 fixture 与应用导入顺序保留；覆盖率数据/HTML 使用临时目录，不覆盖开发者原报告。此处只是局部反馈结果，不是整个后端覆盖率或 CI 墙钟提速。相同测试集合的报告策略对照仍在进行。

后续 Agent：先读该分层设计，使用项目 Python 运行 `scripts/ci_module_feedback.py --base origin/main --run` 获取已登记模块的本地反馈；返回 2 代表需要常规完整验证，不能当成功。显式 `--module` 只表示手工探针。通过后仍按现有精确 SHA 完整 CI 与发布闸执行。影响选集在 CI shadow 对照、fixture 分层及发布端组合证据审查完成前，不得用此入口跳过 CI。

G3/G4 修复记录：独立 reviewer 对 `e4aea2d011d25800d739f86cb8e5cb806a38ba39` 判 NO-GO，真实 Git 仓库复现共享 fixture 在 index 修改、工作树恢复基线时被净 diff 漏掉。新增相消 fixture 回归先 RED，再分别合并 BASE→HEAD、HEAD→index、index→工作树及 untracked；85 项合约回归通过，等待新 reviewer 重审。接入其他任务主干 `4199dff8844b38aee5cc95f5f0881cbbdcfef389`，无重叠应用改动。

同测试集合对照已完成：展示模块 99 项，77.06→29.49 秒；提示缓存 24 项，49.89→9.78 秒。每组 JUnit 身份/结果多重集合完全一致、零 skip，正常应用 instrumentation 和 fixture 不变，模块报告要求至少 80%。单机每策略一次顺序样本，只证明本次局部反馈改善，不证明完整 CI 或 P95；详见本轮模块 JSON。此前“对照进行中”为过程记录，以本段为最新结果。

G4 PASS：新只读 reviewer 对修复候选 `261f64b060ec25b72164d64335436ab37813a321` 给出 GO；独立 85 passed，并额外验证已提交 fixture 修改被 index 恢复时仍拒绝窄执行。原始 JUnit 哈希、用例/结果集合和时间分解独立核对一致。preflight 通过秘密扫描、中央地图、Dossier、API 类型漂移和 56 项发布合约。父提交 `4199dff8844b38aee5cc95f5f0881cbbdcfef389` 的 CI 40477427714 首轮成功后推送候选。仅工具和文档，无应用部署或 OTA。

G5/G6 试点 PASS：[完整 CI 40478780352](https://github.com/itsoso/health-llm-driven/actions/runs/40478780352) 绑定 `261f64b060ec25b72164d64335436ab37813a321`，attempt=1，32/32 job 成功，无工作流重跑。模块反馈和分段报告已进入 main；该工具只改善开发反馈，不缩短完整 CI 的选集/执行。源代码和正常测试策略未变，因此不声称完整 CI 提速。候选实际 643 秒（10 分 43 秒），紧邻主干 546 秒（9 分 6 秒）；本轮全量时长增加 97 秒，后续全局优化仍未完成。

候选关键路径：17 秒启动延迟 + 22 秒环境 + 18 秒安装 + 505 秒测试 + 2 秒其他步骤 + 63 秒未归属 + 16 秒收尾 = 643 秒。紧邻主干测试 476 秒、未归属 4 秒。原始元数据中最后 step 在 09:19:55Z 结束，job 在 09:20:57Z 完成，间隔 62 秒；目前无法确定其平台内部归属，不能归为测试、安装或 artifact 上传。机器证据见 `docs/reviews/2026-10-27-ci-module-feedback-production.json`。本地模块反馈配对样本有改善，全量时长没有改善，两个结论分开记录。

## 第七阶段：单次读取操作内消除重复解析

G1/G2 PASS。继续优化 CI，基线 main `0852c0eab93a9fac2e5f63b88db874435e81e3c6`；最近完整 CI 40478780352 为 643 秒。沿用原 Harness / safety / System Map；地图未索引 longitudinal 文件，中央检查通过并回源码调查。发现 `_request` 对同一不可变快照执行两遍相同 projection，`longitudinal_read_limitations` 又先调用查询解析、随后重算 `_request`。本批只在一次同步公共调用内复用中间结果；不增加跨请求/全局缓存，不复用鉴权裁决，不改变测试选集或 fixture。

预声明：相同组合查询样本本地执行争取减少 10%，同时用例/结果集合完全一致；完整 CI 不预许固定降幅。任何 owner/date/引用/撤回/异常传播差异均停止推广；本地无收益则不发布。用当前主干和候选的完整 CI 首轮实测，不通过重跑挑选好结果。生产源码变化需独立安全审查和既有发布闸，CI 通过不冒充部署。

G3 PASS：两项计数回归在旧实现 RED，改后 383 项相关回归通过；隔离本机 PostgreSQL 179 passed，测试实例已停止并清理。另验证跨调用 owner/date 改变、返回字典被修改、异常仍向上抛出，均不复用旧结果。查询每次 projection 从 2 次变 1 次，限制说明从 4 次变 1 次。LLM change gate 无需 live eval，未豁免；未改数据库查询或 schema。

相同 10 项实际组合查询测试首轮 pytest 31.69→13.40 秒，但旧首例慢，故完整保留并补对照：精确旧 Git 源码在独立进程内加载，进程墙钟 25.44→20.86 秒，约下降 18.02%；pytest 20.08→14.27 秒。四份 JUnit 身份/结果集合完全相同、零 skip；不宣称稳定 P95 或完整 CI 同幅改善。配方、源摘要及原始 JUnit 摘要见 `docs/reviews/2026-10-27-ci-longitudinal-local.json`。

G4 PASS：独立 reviewer 对精确 `0633a4d02784abb465534faa86e19f68a3613926` 给出 GO，独立 scope/gateway 175 passed、unit/runtime 184 passed。另一次范围过大的组合测试在 309 passed 后主动中断，exit 2，不计为全套通过。CI-mode 383 passed、发布 preflight 与中央地图通过。

G5 PASS：[完整 CI 40484148406](https://github.com/itsoso/health-llm-driven/actions/runs/40484148406) 首轮 32/32 job 成功；64 个后端子进程均 attempt 1 / pass。原 35,788 项 testcase 身份与结果全部保留，只有本批 3 项回归新增为通过，155 项既有 skip 不变。全套原始 JUnit 摘要、集合对照、逐 job 时间分解见 `docs/reviews/2026-10-27-ci-longitudinal-production.json`。

| 指标 | 基线 40478780352 | 候选 40484148406 |
| --- | ---: | ---: |
| 完整 CI | 643 秒 | 520 秒 |
| 最后完成分片的启动延迟 | 17 秒 | 16 秒 |
| 环境准备 | 22 秒 | 26 秒 |
| 安装依赖 | 18 秒 | 17 秒 |
| 测试执行 | 505 秒 | 445 秒 |
| 其他步骤 | 2 秒 | 3 秒 |
| job 内未归属时间 | 63 秒 | 4 秒 |
| 汇总收尾 | 16 秒 | 9 秒 |
| 后端组合查询累计用例耗时 | 1167.24 秒 | 596.82 秒 |
| 全部 job 累计 runner 时间 | 9565 秒 | 7440 秒 |

整轮减少 123 秒，其中未归属时间也减少 59 秒，不能全部归因于源码优化。最后完成分片发生变化，分段比较不是同一 worker 的因果实验。更早的相邻完整 CI 40477427714 为 546 秒，候选比它快 26 秒；保留该背景，避免仅用平台等待偏慢的 643 秒样本夸大稳定收益。组合查询累计值包含并行测试的 setup/call/teardown，不能直接从整轮墙钟扣减。本轮只证明这些实际样本，不建立 P95/P99 或固定提速承诺。

G6 进行中：[发布 validate 40485381866](https://github.com/itsoso/health-llm-driven/actions/runs/40485381866) 成功。canonical staging 源码与受审摘要一致。首次普通 bootstrap 在凭据检查处失败：固定 `/etc/reva-github-api/credential.json` 已到期。只读复核输入与 canonical source PASS；原授权仍为 `0852c0eab93a9fac2e5f63b88db874435e81e3c6`，该授权尚无发布状态目录，候选状态目录未创建、业务 lease 不存在，生产仍为有 SUCCEEDED 回执的 `9fd15d602dc34be3f0a30146f76909c65233bbe6`。没有执行 backend dispatch 或替换线上代码。沿用现有仓库只读 App 凭据提供器准备一次性刷新，待独立审查后执行；不使用管理员 PAT、不跳过过期检查、不盲重试未知事务。

G6 最新状态为等待并发发布归属确认。刷新脚本静态复核及 7 项合成拒绝检查通过后、执行前，只读探针发现另一流程已刷新凭据，并推送新 main `12edbb30e9bf30247dbcb2ac6635e3fee322754a`（Mobile 考试历史，包含本批优化）。该新 main 的完整 CI 尚在运行；旧候选 canonical gate 拒绝 `Main contains runtime or unknown changes`。独立 reviewer 撤销旧前提下的刷新 GO，裁决旧刷新脚本及 bootstrap 重试 NO-GO。本任务未 mint、未刷新凭据、未再次 bootstrap、未 dispatch backend。最新观测仍为原授权、原生产 SHA、无业务 lease、无候选状态或旧授权 retirement 目录；时间点与摘要记录在 production JSON。首次 bootstrap 失败只有明确标注来源的工具输出转录，不能冒充保存过的原生日志。依 AGENTS.md §7 停止外部写入并询问本轮唯一发布者；后续必须重绑最终 main、完整 CI 和安全审查，不能发布旧候选或复用失效刷新脚本。

G6 后续核验 PASS，以上等待为历史断点。用户确认等另一流程完成后由本任务核验。独立读取 `12edbb30e` 的后端 run `40487980897`、OTA run `40489009144` 成功及服务器 SUCCEEDED 回执；当前生产已进一步升级到 `8f7d94696424f92ff57243edb906cd6d2dd14a3a`，其完整 CI `40496844800` 成功，发布 run `40500052228` 的 backend job 成功、服务器 SUCCEEDED。`agent_longitudinal_read.py` 线上摘要与本批 `0633a4d` 完全一致；三个服务 active、业务 lease 不存在、公网 health healthy、匿名 GET `/api/v1/auth/me` 为401。最初误用 POST 得405，未计为鉴权通过。生产独立进程仅以合成文本执行 scope 探针，验证单次 projection、owner/第三方拒绝及日期重算通过，不访问真实健康记录。本任务没有重复部署。最新整体发布中的 TestFlight job 失败独立保留，不把 backend 成功冒充整轮原生发布成功；其后 Apple 实际接收状态由唯一发布者另行核验。本批无需另发 OTA。

## 第八阶段：近期计时校准与只读漂移闸（2026-10-30）

用户确认按既定 CI/CD 优化顺序执行。沿用本 Dossier、implementation / Health Harness 和性能治理；本批只做 P0，先取得可归因的真实 CI，再决定是否拆分 release-invariants 与 PostgreSQL。共享 `main` 有两条本地提交、落后远端 89 条且含其他任务未提交改动，因此按已确认的窄范围 PR 方案，从远端 `a60a42a405c2d889accce7d91cf84591352e4439` 建立独立工作树；不移动、暂存或清理共享工作区。

G1/G2 PASS。最近完整 CI `40997603653` 首轮 32/32 job 成功、墙钟 608 秒；最长后端测试步骤约 530 秒，旧 catalog 仍来自 10 月 27 日三轮运行。首版使用 `40885514914`、`40912681271`、`40997603653` 三轮精确 SHA、attempt=1、完整成功日志，以既有严格刷新器逐分片取最大值。所有非调度策略摘要保持 `53c3ead6686f4816b71f64ca5c19dcd611d117172784df7c9a4e14af8ec28425`，worker 数、测试选择、进程边界、deadline、重试和超时均未改变。

首版离线回放的最长 worker 实际负载分别从 471.852 / 480.687 / 530.311 秒变为 409.275 / 404.905 / 409.267 秒；三轮 placement 预测 16 个 worker 为 408.048～418.012 秒，spread 9.964 秒。它不含 runner 启动、安装和聚合，不能冒充新 CI 或稳定分位数。脱敏机器证据见 `docs/reviews/2026-10-30-ci-timing-drift-replay.json`。

新增 `CI timing drift` 后置工作流只观察成功、main、attempt=1 的完整 CI，checkout 精确 head SHA，并下载该 run 的确切日志。漂移门按当前 catalog 的 16-worker 分配比较预测与实测关键路径；单个短分片比例仅作诊断。关键路径变慢超过 20%，或 catalog 已经过 5 次完整成功 main CI 未纳入新来源时，独立观察工作流标记 review required。报告和单轮 observed catalog 保存 14 天；权限仅 `contents: read` / `actions: read`，不自动改 catalog、push、dispatch、设置变量或提供发布授权。

G3 PASS：先写 7 项测试，旧实现因脚本和工作流不存在而 6/6 RED；增加精确 run/SHA 与 main 分支绑定反例后，timing drift、timing refresh、release CI contract 合计 74 passed。使用 `40997603653` 的真实日志和最近完整运行清单执行新观察器，结果 predicted=418.012、observed=409.267、drift=-2.092%、runs_since_source=0、status=CURRENT。首个候选提交后，从候选 workflow 原样读取完整 `Run deployment and rollback invariants` 命令，CI=1 新鲜执行 5645 passed、67 skipped、127 subtests passed，611.87 秒，退出码 0；随后只收紧观察器的精确 SHA/main 绑定并由定向反例覆盖，既有 zip duplicate-name warning 保留，不当作失败或新增 skip。G4 最终固定提交审查、精确候选完整 CI 和后置观察工作流真实运行尚未完成；在此之前不声明线上提速。仅 CI/治理范围，不部署后端、不轮换授权、不发布 OTA 或商店包。

首个 hosted 候选 `fe97a63a1dd0f7d1729fa90781ddbe9bd7538bdc` 的精确 CI `41012046528` 为 attempt=1、32/32 job success，但性能裁决 **NO-GO**：整轮 676 秒，比 608 秒基线慢 11.184%；最长测试步骤 548 秒。确切日志显示 `s-l-z` 从三轮窗口预测 311.506 秒回到 435.687 秒，使该 worker 实际进程负载 547.763 秒，比 418.012 秒预测高 31.04%。不重跑同 SHA、不把 correctness green 冒充性能通过，PR 未合并。

根因是三轮窗口过早淘汰已知长尾：旧 catalog 已观察到 `s-l-z=433.935` 秒。修复使用最近六次完整、首轮成功 main CI 的逐分片最大值，窗口为 `40438974052 / 40442091206 / 40447632037 / 40885514914 / 40912681271 / 40997603653`；滚动窗口随新完整样本自然淘汰旧值，不建立永久单调 floor。六轮 placement 预测为 464.920～472.651 秒，spread 7.731 秒；七个已有样本（含首个 hosted 反例）的回放最长值上界从旧 catalog 的 530.311 秒降为 467.703 秒，反例本身回放为 462.617 秒。该修复仍是离线回放，最终候选必须新的精确 SHA 完整 CI；不使用 workflow rerun 挑样本。

G5 代码候选 PASS：[精确 CI 41013492648](https://github.com/itsoso/health-llm-driven/actions/runs/41013492648) 绑定 `55ff86d29b0ea4b23ae79637a77003edcb6abd41`，attempt=1、32/32 job success，无 rerun。整轮 587 秒，比 608 秒基线减少 21 秒（3.45%），没有达到早期 8 分钟估计但消除了首版退化。最慢测试步骤 515 秒；按进程计时的实际关键 worker 514.644 秒，比 472.651 秒预测高 8.88%，未触发 20% 漂移阈值。`s-l-z` 实测 420.331 秒，历史 floor 覆盖成功；新热点为 `p=299.524` 秒，后续由观察器积累样本，不在本批继续叠加策略。release-invariants job 399 秒、agent-runtime-postgres job 476 秒，P1 是否拆分待 main 实测和 runner 竞争证据后裁决。当前只证明 PR 代码提交；main push 的完整 CI 与新 `workflow_run` 观察器尚未发生，不声明主干已生效。

G6 PASS：[PR #287](https://github.com/itsoso/health-llm-driven/pull/287) squash 合入 main `2d9e53df280dd40e03fe8e7820d017528a6fb3d5`。精确 main [CI 41015741501](https://github.com/itsoso/health-llm-driven/actions/runs/41015741501) 为 attempt=1、32/32 job success、墙钟 561 秒，无 rerun；比 608 秒基线减少 47 秒（7.73%），但候选和 main 两个样本差异仍大，不能建立稳定 P50/P95 或保证固定提速。main 最慢后端 job 533 秒；PostgreSQL job 491 秒、其中两组语义测试步骤 371 秒；release-invariants job 273 秒。因此 release-invariants 已不在关键路径，PostgreSQL 也在最后后端分片前 42 秒完成，不拆这两条 lane。

后置只读 [CI timing drift 41016674352](https://github.com/itsoso/health-llm-driven/actions/runs/41016674352) 绑定上述 main run 和 SHA，attempt=1、success。报告为 `status=CURRENT`、catalog_stale=false、runs_since_source=1；预测关键路径 472.651 秒、实测 479.279 秒，慢 1.402%，低于 20% 阈值。报告同时明确单轮不是稳定分位数、排除 runner/安装开销且 `release_authority=false`。P0 至此在 main 生效；仅 CI/治理变更，不部署后端、不轮换生产授权、不发布 OTA、TestFlight 或 App Store。

P1 分片拆分实验 **NO-GO**，未提交候选、未触发托管 CI。`s-l-z` 在 main 样本中为单进程 443.441 秒、2116 项。实验将其按 sleep / supplement / system / rest 分成四个互斥选择器；契约先 RED 后 96 passed，文件集合与用例结果多重集合完全一致。补齐与 CI 相同的锁定 Pi runtime 后，同机首轮有效样本：旧组 132.778 秒；新四进程 22.389 / 64.223 / 25.565 / 36.335 秒，顺序合计 148.512 秒，增加 15.734 秒（11.85%）。将新组按同机比例映射回 main 托管进程时长，并用 main 的其他 59 个精确进程耗时回放候选 LPT 分配，关键路径约 482.069 秒，略高于现状 479.279 秒；`r-other` 接替为 482.069 秒瓶颈。故回退全部实验代码，不通过增加进程或重跑挑样本制造提速结论。机器证据与日志摘要记录在 `docs/reviews/2026-10-30-ci-timing-drift-replay.json`。

后续只在观察器达到 5 次完整成功 main run、漂移超过 20%，或出现新的可归因热点时刷新 catalog。下一轮应用级性能工作应先对 `r-other` 与跨样本波动做请求/测试热点剖析；不先加 worker、不削减测试、不延长超时。

P0.1 边界修复：证据 PR 合入 main `7dc9ca389f3a4d0f9c67f7cdaf1f34457f98284a` 后，docs-only CI `41018930457` 首轮成功且没有后端分片；旧观察器仍启动，并在 run `41019007598` 因缺少分片日志失败。该失败不影响主 CI、代码或发布，但会制造错误告警。新入口先读取触发 run 的确切 jobs：0 个匹配后端分片表示 docs-only，正常输出 `eligible=false`；只有完整且成功的 `balanced-01..16` 才进入日志下载、漂移评估和制品上传；1～15 个、重复、失败或异常矩阵均失败。完整矩阵的评估失败仍以 `always && eligible` 上传诊断制品。测试先因脚本/门缺失 2 项 RED，修复后 timing drift / refresh / release contract 75 passed。待精确 PR 与 main CI 验证后更新 G6；不重跑既有失败 observer，不触发部署或 OTA。

P0.1 G6 PASS：[PR #289](https://github.com/itsoso/health-llm-driven/pull/289) 合入 main `ad49cccfda9a99b7ae9d5383635bccbd7eb8573b`；精确 main [CI 41020241592](https://github.com/itsoso/health-llm-driven/actions/runs/41020241592) attempt=1、32/32 success。后置 [observer 41021168613](https://github.com/itsoso/health-llm-driven/actions/runs/41021168613) 的完整矩阵 scope 成功，随后报告 `CURRENT`：predicted=472.651、observed=472.479 秒、slower_ratio=-0.0364%、runs_since_source=2、catalog_stale=false，并上传 artifact `12960964092`。旧 docs-only 失败 run 保留、未重跑。最终 docs-only 安静跳过路径由本证据提交合入后的 main run 再核验；该路径只影响诊断噪声，不赋予发布权限。

## 第九阶段：同一不可变回合内复用读取范围（2026-10-30）

用户继续授权优化 CI/CD。沿用 Health Harness、性能治理和同一 Dossier；从精确 `origin/main` `f169d6f35114d530fdd98d1d603368798fb34276` 创建独立工作树，保留共享根目录的分叉和未提交改动。最近两轮完整 main CI `41015741501 / 41020241592` 均为 32/32 成功；其中 `r-other` 进程分别为 261.777 / 263.418 秒，74 项 `test_running_analysis_runtime.py` 稳定占约 94 秒。cProfile 显示同一 frozen `TurnSnapshot` 的纯范围解析被重复调用，单个代表用例中 `resolve_owned_read_scope` 56 次、累计约 1.156 秒。

G1/G2 PASS。方案只在一个 `AgentExecutor` 内、且输入仍是同一 `TurnSnapshot` 对象时复用 `OwnedReadScope`。任何 owner、日期、来源消息、actionable context、intent 或 goal 重绑定都会创建新 snapshot 并重新解析；异常在写入缓存前继续上抛，不缓存失败；不建立全局缓存，也不缓存最终授权裁决。生产消费者静态核验只读 scope 或复制 query 字典，没有共享可变写入。停止条件为 owner/date/第三方拒绝或异常传播发生差异、用例集合变化、同机无收益，或托管完整 CI 退化超过紧邻 main 10%。

G3 本地 PASS。新增两项契约测试先分别因入口缺失、失败被错误缓存而 RED；最小修正后通过。同机按真实 `r-other` runner 对照：基线 103.609 秒，候选 88.395 秒，减少 14.684%；pytest 时间 97.46→83.21 秒。两侧均为 1093 passed、6 skipped、0 failure/error，1099 项 testcase 身份与结果多重集合摘要同为 `a4df9280...da63eda83`。此前同一 74 项热点的配对样本为 42.89→32.74 秒；只把这些结果视为单机样本，不推断稳定 P50/P95/P99。

安全与质量验证：最终精确 `r-other` 1099 项通过；缓存契约 2 项通过；修正前的相关宽回归 570 项通过，最终异常原子性由契约与完整分片覆盖。真实模型 gate 使用合成用户和内存 SQLite，不访问生产健康数据：invariants 12/12、health-agent-core 50/50、orchestrator 5/5（均分 0.94）、trajectory 12/12、goldens 9/9，无回归。System Map、agent-skill governance、diff 及 compile 检查通过。机器证据见 `docs/reviews/2026-10-30-ci-owned-read-scope-cache.json`。

G4/G5/G6 尚未完成：代码提交为 `fb6841425`，仍需最终证据提交、精确 PR 完整 CI、main CI 和后置 timing observer。由于修改了后端执行路径，合并后需按精确 main SHA 发布后端并验证健康/匿名 401；没有移动端或原生改动，不需要 OTA、TestFlight 或 App Store 发布。CI 绿色不冒充部署完成。

G4/G5 更新：PR #291 的精确 SHA `11fd244f4c46de4c64a1db50814cbe3f9e3cddd7` 在 CI `41041811504` 通过，23 个适用 job 成功、9 个按 PR 变更范围跳过。托管 `r-other` 为 165.146 秒，紧邻完整 main 基线 `41020241592` 为 263.418 秒，减少 37.307%；JUnit 累计 233.44→142.131 秒，1099 项身份/结果摘要完全相同（1093 passed、6 skipped）。新增两项缓存契约在 balanced-16 通过。PR 整轮 528 秒，但它是 change-scoped，不能与 main 全量运行直接等价。

PR squash 合入 main `afee20ab1fa38d1ec95d42f08194c776198c0853` 后，自动 CI `41043112706` 终态 failure：29 个独立 job 成功，根失败仅为 backend-quality 启动时快照的 `HARNESS_LIVE_LLM_EVAL_CONFIRMED` 仍是 PR SHA `11fd...`，目标已是 squash SHA `afee...`；backend-tests 与 backend-release-ready-v1 只因依赖失败。两份运行时文件摘要与实模型通过的候选逐字节一致，变量随后绑定 afee，但 workflow 的环境快照不会改变。保留该失败 run，不 rerun 或把 29 个成功 job 拼成绿色。恢复方案是提交本段证据，先将 live 确认绑定到该后续精确 main SHA，再直接 fast-forward 推送，并用一次显式 `workflow_dispatch` 完整 CI；这是 `docs/governance/deploy.md` 允许的失败恢复补验证，不用于挑选性能最好样本。恢复 CI、observer 和后端发布仍 pending。

恢复证据提交 `9aa3402ec6efd1a7afa00c3f356a163f55078163` 在 push 前已绑定 live 确认；自动 docs-only CI `41044413722` 成功，observer `41044486218` 正常安静跳过。一次 `workflow_dispatch` 命令退出 0，但连续按 event、branch 和精确 SHA 查询均未生成 run ID；结果未知，因此没有重放。改为补强同值新对象边界回归：即使所有字段相同，只要 `TurnSnapshot` 对象已被 replace，scope 也必须重新解析，不能按值跨重绑复用。该测试提交作为普通 main push 自动进入完整后端 CI；生产实现字节不变。前述“显式 workflow_dispatch”是执行前计划，以本段为最新恢复路径。

G6 最终 PASS：补强边界测试提交 `c9567c9a92fbd11cb6d52d0aa819c87e03a0accf` 的自动完整 [CI 41044942222](https://github.com/itsoso/health-llm-driven/actions/runs/41044942222) 首轮 32/32 成功、墙钟 538 秒。托管 `r-other` 进程 123.541 秒、pytest 110.72 秒，1093 passed / 6 skipped；相对紧邻完整 main 基线 263.418 秒和 233.44 秒分别减少 53.101% 与 52.570%。这是一次托管样本，不能建立 P50/P95/P99 或固定收益承诺。后置 [observer 41046073801](https://github.com/itsoso/health-llm-driven/actions/runs/41046073801) 为 `CURRENT`，predicted=472.651、observed=463.788 秒，较预测快 1.875%，catalog_stale=false、runs_since_source=3。live 确认变量和 waiver 均已清除。

发布闭环 PASS：[validate 41046550833](https://github.com/itsoso/health-llm-driven/actions/runs/41046550833) 仅运行 preflight 并成功；canonical staging、受限只读 GitHub App 凭据更新和成功授权轮换各执行一次。随后唯一 [backend release 41047898581](https://github.com/itsoso/health-llm-driven/actions/runs/41047898581) 成功，backend job 4 分 8 秒。独立回读生产干净 SHA 精确为 `c9567c9a92fbd11cb6d52d0aa819c87e03a0accf`，持久回执 `SUCCEEDED`（摘要 `a1212ec8...e720e49a`）；backend/worker/beat 均 active/running、NRestarts=0，公网 health 200 且 API/DB/Redis/Celery 健康，匿名 POST `/api/v1/agent/send` 返回 401，业务租约已释放。未读取或写入真实健康数据，未创建备份。没有 Mobile 或原生文件变化，因此无需 OTA、TestFlight 或 App Store 发布。

## 第十阶段：复用 System KB 文档词法派生结果（2026-10-30）

用户继续授权优化 CI/CD。沿用 implementation / Health Harness、性能治理和 `safety-gate`；从精确 `origin/main` `0b2470da1e16af102d15f9e4dade4a0aae41d87d` 的既有干净工作树继续，未触碰共享根目录。最近完整 main CI `41044942222` 为首轮 32/32 成功、墙钟 538 秒；最后完成的 `balanced-14` job 为 512 秒，其中测试步骤 464 秒。确切进程日志显示 `p=265.327`、`e=145.487`、`wearable-reports=35.514`、`timeline-medications=17.460` 秒，合计 463.788 秒，与 catalog 预测 465.023 秒接近，因此不刷新 timing catalog、不重排分片。

G1/G2 PASS。`p` 的 JUnit 热点集中在多组知识安全 eval。代表用例 cProfile 为 46973926 次调用、11.297 秒；`seg_text` 5296 次、累计 4.141 秒。根因是 BM25 每次检索都重新为相同 System KB 文档生成分词文本和词项。方案只缓存非用户 System KB 文档的派生结果，包括重建索引时读取的非归档草稿：4096 项 LRU，key 是精确文档 searchable text，value 是不可变词项 tuple；文档任一字段变化自然生成新 key。用户查询仍逐请求分词且不会进入该缓存；PostgreSQL `TSVECTOR` 不替代原 BM25 语料；tokenizer 异常继续使用既有 bigram fallback，但失败结果不入缓存。停止条件为词项/排序、安全 eval、用例集合或异常恢复发生差异，或托管完整 CI 相对 538 秒基线退化超过 10%。

G3 本地 PASS。五项缓存契约中，入口缺失、错误采用 `TSVECTOR`、缓存降级 fallback 和瞬时分词失败三类关键反例均先 RED；最终覆盖精确词项等价、同内容复用/改内容重算、用户查询不缓存、失败不缓存并可恢复，以及第一次分词成功、第二次失败时严格保持原来的两次调用与 bigram fallback。知识检索、vector、tokenizer 与 Agent 安全相关回归 444 passed。按真实 runner 对 `p` 做同机首次 attempt 对照：基线 126.400 秒，候选 111.211 秒，减少 15.189 秒（12.017%）；JUnit 累计 110.030→94.096 秒。两侧均为 1052 个相同 testcase、1046 passed / 6 skipped / 0 failure，身份与结果摘要同为 `8ac2c1ba...1f5b673`。System Map、blocking ruff、compile 和 diff 检查通过。机器证据见 `docs/reviews/2026-10-30-ci-system-kb-lexical-cache.json`。这是一组同机样本，不建立 P50/P95/P99 或固定收益承诺。

G4/G5/G6 pending：须先提交固定 diff 并按 `safety-gate` 取得独立 GO，再运行精确 PR 完整 CI；合入后核对 exact main 完整 CI、timing observer 和 `p` 进程。该改动进入后端运行时，最终 main 绿色后需要精确 SHA 后端发布与健康/匿名 401 复核。没有 Mobile 或原生改动，不需要 OTA、TestFlight 或 App Store 发布。

G4 首轮 NO-GO 已关闭代码缺陷。独立审查对提交 `aa2f9000237d69cea3c6074fc5694bead64deefc` 构造“第一次分词成功、第二次失败、第三次恢复”序列，发现候选失败分支会通过 `_query_terms` 发起历史实现不存在的第三次分词，并改变 BM25 词项。新增契约先稳定 RED；修正后的失败分支直接从空分词结果生成原有 regex/bigram 词项，不再重试，5 项缓存契约和上述 444 项宽回归通过。审查同时指出索引重建也会处理非归档草稿，故本节与机器证据已将范围从“reviewed 文档”校正为“非用户 System KB 文档”。修正后的精确 `p` 分片首轮 1052 项完成，1046 passed / 6 skipped / 0 failure，进程墙钟 101.079 秒；该结果只作最终代码结果集复核，不替换原始成对性能样本。G4 PASS：同一独立审查人对精确提交 `a3a0dfc6b818f3ab8a1772ffbfdf3fe6d0b7931e` 复审 GO。四种两次分词成功/失败组合均与父实现词项完全一致且调用数均为 2；持久失败与瞬时第二次失败都不缓存降级词项，恢复后可重算。5 项缓存契约和邻近真实路径 48/48 fresh pass；256 次并发结果一致（1 miss / 255 hits），两个 LRU 均保持 4096 上限；用户查询前后两个文档缓存均未变化；`TSVECTOR` 与 BM25 语料边界未变。

G5 PASS：[PR #292](https://github.com/itsoso/health-llm-driven/pull/292) 的精确提交 `841d76e951c79c51e4fa8a8599e5ad43dd3768d1` 在 [CI 41052552075](https://github.com/itsoso/health-llm-driven/actions/runs/41052552075) attempt=1、32/32 job success。托管 `p` 进程为 255.334 秒，相对紧邻完整 main 基线 265.327 秒减少 3.77%；PR 整体变更范围与 main 全量执行不同，不把该样本单独作为发布结论。

G6 PASS：PR squash 合入 main `4016634c9cfd768da1e7ee9a2700d274f225469f`。精确 main [CI 41053734560](https://github.com/itsoso/health-llm-driven/actions/runs/41053734560) attempt=1、32/32 job success、墙钟 581 秒；比 538 秒基线增加 43 秒（7.99%），低于预声明的 10% 停止阈值。最后完成的 balanced-14 job 为 392 秒，其中 `p=199.129` 秒，相对 265.327 秒减少 24.95%；同一 worker 的 `e=109.545`、`wearable-reports=28.531`、`timeline-medications=13.796` 秒。整轮包含 runner 排队、其他分片及收尾，单轮差异不能全部归因于本实现。

后置只读 [CI timing drift 41054941509](https://github.com/itsoso/health-llm-driven/actions/runs/41054941509) 绑定上述 main run 和 SHA，报告 `CURRENT`：predicted=472.651、observed=437.788 秒，较预测快 7.376%；最大单分片变慢 11.270%，低于 20% 漂移阈值；catalog_stale=false、runs_since_source=4。未刷新 catalog，也未重排分片。

发布闭环 PASS：[validate 41055221179](https://github.com/itsoso/health-llm-driven/actions/runs/41055221179) 仅运行 preflight 并成功；canonical staging、过期只读凭据更新与成功授权轮换各执行一次。随后唯一 [backend release 41056818134](https://github.com/itsoso/health-llm-driven/actions/runs/41056818134) 成功，backend job 8 分 15 秒，iOS/TestFlight job 均 skipped。独立回读生产工作树干净且 SHA 精确为 `4016634c9cfd768da1e7ee9a2700d274f225469f`，持久回执 `SUCCEEDED`（摘要 `b5cc39e1...70cf9079`）；runtime 终态 COMMITTED / code-only-no-backup / finalized。health-backend、celery-worker、celery-beat 均 active/running、NRestarts=0；公网 `/api/v1/health` 为 200 且 API/DB/Redis/Celery 健康，匿名 POST `/api/v1/agent/send` 为 401，业务租约不存在，授权策略绑定该 SHA。未读取或写入真实健康数据，未创建备份。没有 Mobile 或原生文件变化，因此无需 OTA、TestFlight 或 App Store 发布。

本轮托管 PR、main 和生产均只有单次样本，不能建立稳定 P50/P95/P99 或承诺固定降幅。结论限于：`p` 的重复文档词法派生在托管 main 样本中显著下降，完整 CI 未触发退化停止条件，安全边界和生产健康闸均通过。

## 第十一阶段：近期六轮 placement 校准（2026-10-30）

用户继续授权优化 CI/CD。沿用 implementation / Health Harness、性能治理和 `safety-gate`；从精确 `origin/main` `c27505a70cdbdada8637b5814ba0fdfc90efa123` 的干净工作树继续，未触碰共享根目录。上一阶段代码 main `4016634c9cfd768da1e7ee9a2700d274f225469f` 的完整 CI `41053734560` 首轮 32/32 成功、墙钟 581 秒，后置 timing observer `41054941509` 为 `CURRENT`，观测关键负载 437.788 秒。该观测表明 catalog 未漂移到阻断阈值，但原 catalog 混合了较早运行，仍有 placement 校准空间。

G1/G2 PASS。方案只用最近六轮精确 main、首轮成功、完整后端 CI 的 64 个进程墙钟，按既有每分片最大值规则刷新 `scheduling_seconds`，再由既有 16-worker LPT 平衡器分配。六轮为 `40912681271`、`40997603653`、`41015741501`、`41020241592`、`41044942222`、`41053734560`；每轮均有 60 个分片、64 个进程，超时样本为零。worker 数、分片数、测试选择、`estimated_seconds`、deadline、timeout、attempt、进程隔离、workflow 和发布准入均保持不变；非调度执行策略摘要前后同为 `53c3ead6686f4816b71f64ca5c19dcd611d117172784df7c9a4e14af8ec28425`。

离线回放中，catalog 预测关键路径由 472.651 降至 443.441 秒。使用六轮各自真实耗时回放旧/新 assignment，六轮都改善，降幅为 4.18%～13.02%；更保守的留一法每次只用其余五轮训练，六个 held-out run 仍全部改善，降幅为 2.28%～12.97%。这些结果只覆盖测试进程负载，不包含 runner 排队、依赖安装和收尾，也不建立 P50/P95/P99。机器证据及每轮 SHA、日志摘要见 `docs/reviews/2026-10-30-ci-recent-window-refresh.json`。

同时调查了最大单分片 `s-l-z`。在完全相同的本地 CI 环境中，原单进程为 132.277 秒；按 sleep / supplement / system / rest 拆成四个顺序进程合计 138.151 秒，增加 4.44% 进程开销。两侧均为 2121 项、2096 passed / 25 skipped，身份与结果摘要相同。旧 catalog 下拆分看似能降低关键路径。为避免把本机绝对时长冒充 hosted 时长，按四组本机耗时比例分配最新 hosted `s-l-z=399.136` 秒，再执行同一 16-worker LPT；拆分后的真实最大 worker 为 421.564 秒，而不是次高 worker 412.051 秒，故相对未拆分回放 412.124 秒恶化 9.44 秒（2.29%），并增加三个 pytest 进程。因此该拆分 NO-GO，未写入 catalog 或 workflow。缩放公式、四组投影值和最大 worker 结果均写入机器证据。

G3 PASS。先把真实 catalog 的来源和关键路径断言更新为目标近期窗口，旧 catalog 稳定 RED；刷新后 timing refresh、drift 和 release contract 共 75 passed，runner 合同 23 passed，change-scope 30 passed。CI-mode 完整 release invariants 真实退出码 0：5646 passed、67 个平台或条件性 skipped、127 subtests passed；没有缩短、跳过或替换该集合。16 个 worker 恰好覆盖 60 个分片，预测关键路径 443.441 秒。System Map 对 CI runner 路径无索引，按治理要求运行中央 System Map、mobile navigation 和 doc drift 检查并通过；未产生地图变更。Dossier 一致性、JSON、diff 和秘密扫描通过。当前只改变 placement telemetry 及其测试和证据，应用运行时、后端、数据库、Mobile 与原生资产均不变。

G4 PASS。独立审查对首个固定候选 `60f07bc1635d48637b1ce87bd3d6457a03756662` 给出 NO-GO：机器证据把拆分回放的次高 worker 412.051 秒误记为最大值。实现安全、拆分 NO-GO 方向和 catalog 均不受影响，但定量证据不可复现，因此没有推送该候选。修正公式与最大值后的精确候选 `202a9be3a2000193343280cb9c560b60f031abe2` 经同一独立审查复算为 GO：六轮 GitHub main push 均 attempt 1、32/32 success；六份日志摘要、60 shard / 64 process / 零 timeout 匹配；非调度策略摘要前后均为 `53c3ead...`，递归差异仅 `timing_source` 和 46 个 `scheduling_seconds`；same-run、留一回放、预测关键路径和拆分投影全部复现。

G5/G6 pending：随后运行精确 PR CI。合入后只接受精确 main 的首轮完整 CI 与后置 timing observer，不重跑挑选好样本。若任何 job 失败或遗漏，或完整 CI 相对 581 秒基线增加超过 10%，停止推广并调查。该阶段仅修改 CI placement，不部署后端，不发布 OTA、TestFlight 或 App Store。
