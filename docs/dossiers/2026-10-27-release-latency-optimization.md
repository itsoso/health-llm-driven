# 发布耗时优化

| 字段 | 值 |
| --- | --- |
| 状态 | in_progress |
| 当前阶段 | G4 修复后复审，尚未推送 |

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
- 定向首轮：53 passed；完整部署/无备份/CI 合约回归 322 passed。独立审查发现 AND-list 下 errexit 失效可能掩盖 Python 权限失败，第一版 NO-GO。已为每个 prerequisite/mutation 添加显式失败传播，测试同时覆盖独立 subshell 与实际 AND-list 上下文；修复后 69 项定向通过。第二轮独立审查 268 passed，但发现 stat 先输出再非零退出时被 test 命令替换吞掉错误；已拆开赋值与结果判断。旧实现独立/AND-list 两项 RED，修复后待第三位 reviewer 复审。
- 同源 CI 日志离线回放：最长测试进程组 554.761 → 439.374 秒、542.367 → 431.308 秒。总测试进程耗时不变，不包含 runner 排队或环境准备，不是新 CI 实测。来源和非调度策略摘要见 `docs/reviews/2026-10-27-release-latency-replay.json`。
- 本机同批 1000 个合成文件权限处理对照：旧 8004 次权限命令 / 83.996 秒，新 22 次 / 0.416 秒。chown/chmod 使用记录目标的桩隔离进程启动开销，不能宣称真实所有权已变更或生产同幅加速。真实 chmod、路径拒绝、忽略数据不变和失败传播另有回归。见 `docs/reviews/2026-10-27-permission-batch-benchmark.json`。

## G4–G6

待固定提交独立审查、精确主干完整 CI、部署及线上核验。OTA 不适用。
