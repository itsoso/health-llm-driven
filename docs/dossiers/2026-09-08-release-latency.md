# Dossier: 发布关键路径优化

| 字段 | 值 |
|---|---|
| 当前阶段 | 2026-09-10 追加优化：TestFlight 上传与后端部署并行；验证中 |
| 状态 | in_progress |

## 2026-09-10 · 上传不再等待后端

用户明确要求构建完成即上传 TestFlight，与服务器部署并行，并写入发布 Skill。
本节是追加迭代；下文 2026-09-08 的串行上传规则和完成记录仅为历史基线，不代表当前设计。
Controller：health-harness-orchestrator；capability：skill-creator；overlay：safety-gate。
本地 ledger：`docs/_generated/harness-runs/7f1b36879119.jsonl`。
writing-skills 未安装，按可用 skill-creator 与 AGENTS 的 RED/GREEN、新鲜验证要求执行。

### 基线、范围与停止条件

同一次真实 release run `34441137527`（Build 270，SHA `23062626caf33701d936fe1c0ba1500b94ad578b`）：

| 阶段 | UTC 开始 → 完成 | 耗时 |
|---|---|---|
| backend | 05:27:59 → 05:38:46 | 647 秒 |
| ios-build | 05:27:59 → 05:36:13 | 494 秒 |
| 等 backend 后才具备上传调度条件 | 05:36:13 → 05:38:46 | 153 秒 |
| testflight | 05:38:50 → 05:41:54 | 184 秒 |

run 已成功；本次仅可证明存在 153 秒依赖等待，另有 4 秒 job 调度间隔。
目标是后续发布消除这段强制等待，让 Apple 处理/IPA 下载可与后端重叠；
实际节约时间须由新流程真实 run 验证，不以调度模型冒充测量或 P95 改善。
不重新构建 Build 270，不改写运行中授权，不修改业务 API 或健康数据；保留工作树其他任务改动。

新包须兼容部署前生产 API；不兼容先修兼容/能力开关，不能因 TestFlight 可能自动分发而忽略风险。
测试质量、制品身份、秘密隔离、备份/恢复与正式送审门不降低。重复 create、身份不符、已知失败或
证据缺失即停止外部写入；未知 vendor 结果只读调查，不重置 claim，不以新 ID 重放。

### 实现与验收（进行中）

- testflight 只 needs ios-build；独立 release-result 汇合 backend/testflight，失败/取消/跳过均失败。
- 上传 claim 复用 build.lock，不等待 backend launcher.lock；核验既有 build marker、时间窗及锁内未撤销授权。
  READY/STARTED 可上传，已知失败拒绝新 claim；上传后后端失败仍保留失败与全部消费标记。
- 更新发布 Skill、注册表与 deploy 治理；默认长期 Expo token 复用，下载/静态 QA 前移，旧手工 auto-submit 不再作为生产首选。
- 主回归先 18 RED / 131 PASS；撤权反例另行 RED。实现后聚焦 150 PASS / 1.87 秒。
  首轮 GREEN 尝试 7 FAIL 源于测试 UID 与真实 root-only 文件校验不一致；仅在测试 fixture 归一 UID，
  保留模式/硬链接校验和独立 root 身份测试，生产校验不改弱。
- G3 完整 CI-mode 集成、G4 独立复核与提交/启用证据待补；不把本机局部测试视为发布授权。

## G1 · 准入

沿用前序受审发布链的安全边界，优化已定义的发布过程，不新增健康能力或放宽权限。
本轮为发布工具代码交付，不执行生产配置、上线或商店提交。裁决：PASS。

## 范围与状态

- 用户要求：执行发布复盘中的优化。
- 当前阶段：本轮工具代码实现、回归与安全复核完成；未 push、未部署、未发布新包。
- Controller：health-harness-orchestrator；overlay：safety-gate。
- 前序证据：`2026-09-07-trusted-release-executor.md`。
- 不触碰正在进行的健康业务改动，不合并 PR #252；不更换生产备份目标、
  不跳过恢复/完整性验证，不安装服务器授权、不创建 EAS 构建。

## 基线与验收

同一版本 `34e32edc463d87a3331d38d552599d3c164c3db3`：CI run
34141329002 为 591 秒；release run 34142442888 中 backend job 648 秒、
testflight job 610 秒，后二者串行。依赖安装 24 秒，不优先引入缓存。
单次样本不能证明 P50/P95/P99；下一批真实发布保留同样分段和排队时间。

- T1：真实服务器 Git 主干/固定 HTTP transport/loopback 认证/授权时间窗在消费前检查。
- T2：只读预检完成后，后端和 iOS 构建并行；build job 内一次性 claim 防止单 job 重跑重复创建；上传仍 join 两端成功，
  重验精确 SHA、production/iOS/STORE/FINISHED 与固定 build ID。
- T3：固化只读 SSE/订单验收 helper，明确草稿不等于写入。
- T4：用同批 CI 成功 attempt 更新排程估时；保持既有测试选择、隔离与 timeout。
- T5：独立安全复核、完整 CI-mode 发布合同测试、秘密/文档/地图检查。

目标：常规发布 CI 开始至 TestFlight 可安装且本机验收完成 20–25 分钟；
这是待真实发布验证的目标，不是本轮实测结果。未知 vendor 结果、后端失败、
源漂移或任一证据缺失必须停止上传；不得清除一次性 marker 重跑。
回退：回到受审串行流程的新授权生命周期，不回滚/清除旧消费证据。
并行可能在后端失败时浪费一次原生构建，最大每授权一次；不扩大并发到多个版本。

## 实现证据

- T1/T2 server 回归先 RED（缺少能力的 9 项失败），随后新旧组合 77 PASS。
- EAS 制品校验与并行拓扑先 RED；补单 job 重跑/并发锁反例 3 RED，修复为
  独立 build.lock 和 job 内消费，组合 135 PASS。最终完整闸待补。
- T3 合成 SSE 36 PASS，明确没有网络/账号/数据写入，也不代替真实回查或 UI 验收。
- T4 56 个原始分片的选择、隔离和 timeout 字段保持逐字段一致；新增 scheduling_seconds
  只参与 LPT 排程。同批成功 attempt 离线重放最长 277.604 → 202.953 秒；不等同线上收益。
  a-agenda 180.064 秒超时重试及 runner 排队另列，未伪装成已修复。
- 旧 shard runner 新鲜回归 18 PASS；本轮真实 Build 265 的离线 vendor metadata 通过新
  精确 SHA/ID/project/bundle 校验，没有创建构建或访问生产。
- 首次完整集成在测试采集后追加了制品身份修复，旧 fixture 被新版 helper 拒绝：
  604 PASS / 1 FAIL / 430.45 秒。属于父任务验证排程失误，保留原失败；冻结代码后重新
  从当前 CI workflow 读取完整清单，设置 CI=1 重跑，不把混合版本结果作为最终通过证据。

## G4 · 独立安全复核

固定 `789253705` 的首轮阻断为制品未绑定 App/project。新增错误 project/bundle 反例
2 RED 后，以 `4e3e5de1b` 修复到受审 `mobile/app.json` 配置真源；15 项相关测试 PASS。
独立 reviewer 对两提交整体复审：**裁决：PASS（代码安全门）**，七组 208 PASS / 6.24 秒。
未授权生产安装、push 或上线。非阻断建议为 status 增加 build 消费状态；当前 marker
仍保留，可由操作员调查，不重置或复用。

## 后续诊断（不算已修复）

a-agenda 首轮日志停在 test_agenda_snooze.py，缺少具体 nodeid/阶段/线程栈；重试的
83 项在 37.004 秒通过。业务链没有 LLM/HTTP；共享 fixture 存在 Redis I/O 与
TestClient 生命周期等待，但不能据此断言根因。下一次有界 Linux 复现可针对该分片加
`-vv --setup-show -o faulthandler_timeout=30`，保留原 120 秒单例和 180 秒进程上限。
- 外部推荐 TDD/karpathy 等本机无 SKILL.md；按 AGENTS 的 RED/GREEN、最小修改、
  新鲜证据要求执行。System Map 未索引 workflow/server 路径，回到源代码与测试。

## G3 · 最终冻结版本验证

**裁决：PASS（本轮本机工具代码范围）**。

- 固定生产代码 `4e3e5de1b` 后，直接从 `.github/workflows/ci.yml` release-invariants
  读取完整命令，以 CI=1 执行：**673 PASS / 399.74 秒**，退出码 0。
  日志 `/tmp/xiaoba-release-latency-final-integration.log`，包含最慢测试分段。
- 对应本机 Python 3.12.13；新旧 worker 18 PASS，独立安全回归 208 PASS。
- bash 语法、阻断级 Ruff（F821/F822/E9）、秘密扫描、System Map、Skill 治理、
  Dossier 一致性与 diff whitespace 均通过。
- 外部推荐 verification-before-completion 无本机 Skill 文件，完成声明仍以本轮
  新鲜命令与实际退出码为准，没有用单元测试替代真实发布结果。
- 本机仍存在另一任务的健康业务未提交修改，均未纳入本轮提交。因此本机结果不是
  干净目标 revision 的发布授权；未来 push/启用前仍须相应精确 main 的真实 CI 与授权闸。
- G5/G6 生产部署/线上验证本轮未执行；20–25 分钟目标及并行节约时间仍需真实发布测量。

## 尚未声称完成的范围

本轮不建设长期凭据平台，也不自动退役或覆盖已有 root 安装。现有一次性安装的
下一轮授权生命周期仍需独立设计与复审；此项不能用删除目录/消费标记解决。
暂不优化备份吞吐：缺少同一存储目标的受控前后测量，保留现有安全验证。
完整真机验收和正式 Apple 审核不属于此流程代码优化的验证证据。
