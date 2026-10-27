# 发布耗时优化

| 字段 | 值 |
| --- | --- |
| 状态 | completed |
| 当前阶段 | G6 已独立核验生产；同版本由并行任务完成发布 |

## G1 范围

PASS。用户要求尽可能缩短发布耗时。工程优化，不新增用户行为、健康对象或权限。Router implementation / health-harness-orchestrator + safety-gate；superpowers 禁用。沿用既有干净 main 发布目录，原工作区其他改动不动。

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
