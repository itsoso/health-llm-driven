# 发布耗时优化

| 字段 | 值 |
| --- | --- |
| 状态 | building |
| 当前阶段 | 第五阶段 G4 通过：PostgreSQL 分组负载调整，待精确 SHA CI 验收 |

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

G4 PASS：独立 reviewer 对固定 `1259485b3` 给出 GO，独立 59 项回归通过、3 项真实 PG/Redis 条件 skip；三轮原始 XML 的 499 项集合、摘要、SHA、首轮成功、全部选择器耗时与回放逐项一致。移动模块 fixture 均按测试隔离，前置 navigation 模块连接与 patch 生命周期清理，无顺序/状态阻断。随后接入其他任务无交叠前端更新 `38be6d970f7973c878057bb708a3a13d6939f2f1`，本轮运行脚本及测试字节保持评审版本不变。G5/G6 新候选完整 CI 与实际性能对照仍待完成。
