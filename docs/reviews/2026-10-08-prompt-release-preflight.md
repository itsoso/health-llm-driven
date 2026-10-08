# Prompt 修复发布预检

日期：2026-10-08。状态：本地候选已实现；外部发布阻断，尚未推送、合并或部署。

## 候选与边界

固定代码候选：`246e697eaa94d3ef5795c7efc23c183db966d80e`。本地已无冲突接入远端 main `8a7d85df0d9c19a40613a1f1c704dc80dd52e7af`，保留原主工作树。三个后端运行时文件逐字匹配已审 `d201cdcc9866f7315286fdfa52e5e0bf143eaaf0`；既有固定源码真实模型闸的 26 个源码摘要也全部匹配。复用该证据，不声称本轮重新调用模型。

本次仅发布有界评分/事实保真修复、组合提示布局去重及默认关闭的预规划代码。预规划激活、512/8192 预算、写工具说明精简继续 NO-GO；不能把历史实验节省量或小样本结果称为线上收益或统计非劣。

## CI 阻断修复

远端 main 的 [CI 37721192561](https://github.com/itsoso/health-llm-driven/actions/runs/37721192561) 因 Mobile 依赖安全审计失败。补充 Web 审计又发现两个阻断项。本地修复如下，没有增加审计豁免或放宽严重级别：

| 范围 | 包 | 修复版本 | 官方公告 |
|---|---|---|---|
| Mobile | compression | 1.8.2 | [GHSA-vc2v-76pw-4v95](https://github.com/advisories/GHSA-vc2v-76pw-4v95) |
| Mobile | shell-quote | 1.11.0 | [GHSA-pqg4-j6r4-53mv](https://github.com/advisories/GHSA-pqg4-j6r4-53mv) |
| Mobile / Web | source-map-js | 1.2.2 | [GHSA-68fv-2mgg-jv7q](https://github.com/advisories/GHSA-68fv-2mgg-jv7q) |
| Web | Next.js / eslint-config-next | 16.3.8 | [GHSA-cjq9-62q9-8jv4](https://github.com/advisories/GHSA-cjq9-62q9-8jv4) |
| Web | sharp | 0.35.5 | [GHSA-wq5f-xc86-pv6w](https://github.com/advisories/GHSA-wq5f-xc86-pv6w) |

独立 reviewer 对固定候选代码/依赖范围 GO：Mobile 无新增包或原生模块；Web 无增删包，SWC、sharp 及 libvips 各平台版本同步，无新安装脚本。已有 node-forge/braces 受验证补丁继续保留。发布仍须精确 main CI、Linux 实际制品及 Trusted 发布闸。

## 本地验证

- Mobile / Web 均从锁文件执行 `npm ci` 成功。Web 首次升级下载发生 ECONNRESET，由 npm 正常重试完成，未改 registry 或跳过安装。
- 两端 OSV 审计通过。Mobile 前三次因 `fetch failed` 闭锁失败，均保留；诊断运行只记录原 fetch 的路径、状态和耗时，不改请求、响应或重试语义，最终完整审计通过。没有将网络失败当成绿色。
- Mobile TypeScript 通过；聊天头部两组 Jest 共 6 项通过。
- Web Vitest 78 文件，447 passed / 1 skipped；生产构建成功；lint 0 errors / 37 warnings。
- 既有 node-forge/braces 安全补丁测试通过。shell-quote 正常参数往返及注释后换行拒绝通过；两端 source-map-js 正常映射及超大索引偏移拒绝通过。
- macOS 实际 sharp 0.35.5 加载 librsvg 2.63.2，良性 SVG 转 PNG 通过。此项不能替代最终 Linux 产物验证。
- System Map、秘密扫描、diff whitespace 检查通过。
- 后端 CI-mode 关联集成：2468 passed / 2 skipped，982.6 秒，0 failure/error；不替代 GitHub CI。两项 SQLite 跳过的 consent 并发用例在先前同源 PostgreSQL 验证中已通过，本轮未重复 PG。

本地 Node 为 25.8.0，GitHub CI 使用 Node 22；最终 CI 须验证其固定工具链。

## 生产只读状态与发布续点

生产仍为 `a10e642cde189c9b414dc8d41346e22f088eaa0e`；后端、worker、beat、GitHub relay active，健康依赖正常。本轮只读配置检查：`SYNTHESIS_THINKING_BUDGET=0`、`STAGED_RESPONSE_MODE=off`、`PARALLEL_SYNTHESIS_SECTION_THINKING=off`，预规划未显式配置（候选默认 false）。部署后还必须重验实际进程配置。

`AGENTS.md` 第 7 节明确要求“主干非绿……停止外部写入并报告”。当前 main 仍为失败状态，因此尚未推送修复分支、创建 PR、合并、更新 CI 确认变量或操作生产授权。需要明确允许在这一红色基线上推送受审修复以恢复 CI；不能把已有部署请求解释为绕过该明文规则。

获此窄范围授权后：推送受审候选并完成真实 CI；候选绿色后合并，确认 main 精确 SHA CI 全绿；核对发布锁/原回执/旧授权终态；通过 canonical bootstrap 轮换、Trusted validate/backend 及 Web 制品发布；验证 Linux sharp/librsvg、生产 SHA、服务健康与持久回执。任何失败保留原操作，不清锁或重复发布。Mobile OTA/原生包不在本次后端与 Web 发布范围。

结构化摘要与本地日志摘要见 [预检证据](2026-10-08-prompt-release-preflight.json)。

## 后续：PR 277 的真实 CI 修复

用户要求先发布、再处理餐食图片识别与失败文案，继续推进修复推送。官方 SSH 连接失败后先确认远端未更新，再经同一仓库官方 HTTPS 成功推送，未改全局 Git 配置。已创建 [PR 277](https://github.com/itsoso/health-llm-driven/pull/277)；尚未合并或部署。

首轮 CI `37726902417` 抓到 `multidict 6.7.1` 的 [CVE-2026-104874](https://github.com/aio-libs/multidict/security/advisories/GHSA-54p9-h82j-f925)，以及测试仍断言旧 Next/sharp 版本。固定修复 `305ca6777911a007a7733a1137ca5cb08ef5bbbf` 仅改变 lock 中 multidict 为 6.9.1（其余锁定版本不变）和三条版本断言；原安全测试未删除或豁免。三种集合操作引用计数无泄漏，50 项锁/版本合同、56 项 provider/usage/integration 测试通过。

本地原 venv 与生产锁有版本差异，不能将此前本地测试称为锁定环境验收；现已用完整 hash 锁对齐，`verify_locked_requirements.py` 校验134包通过。普通本地 pip-audit 因 ensurepip 子进程 SIGABRT 失败，原错误保留；完整锁库存的 `--disable-pip --no-deps --require-hashes` 审计通过，CI 原审计命令保持不变，Linux 结果仍须等待新 CI。

已在锁定环境重新执行标准真实模型闸：10 次 API、完整 API 用量、0 失败，固定305源码及 requirements.lock 共27份运行前后摘要不变；见[锁定环境真实验证](2026-10-08-release-locked-live-regression.json)。这仍不激活任何历史 NO-GO 候选，也不构成新的统计非劣证明。新精确 CI、main合并与Trusted发布尚待完成。
