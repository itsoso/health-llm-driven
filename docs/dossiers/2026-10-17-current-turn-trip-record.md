# 本轮本人行程记录误拦修复

| 字段 | 值 |
|---|---|
| 创建日期 | 2026-10-17 |
| 当前阶段 | S7 发布回读完成；设备生效未验证 |
| 状态 | shipped |
| 范围 | 现有生活事件记录的授权与本轮事实投影修复 |

## G1 · 修复准入

- **裁决**: PASS。按 `docs/specs/reva-product-governance-spec.md` 的现有能力修复边界处理；恢复用户明确授权的本人生活事件记录，不新增行程规划产品对象或跨端职责。
- 沿用既有 HealthEpisode/life_event、认证用户隔离和工具写回执。否定、转述、假设、其他所有者或未知附言不得授权；计划目的地不得表述为已到达。

## 范围与状态

- 现有生活事件记录能力的局部修复；不增加产品对象、API、表结构或移动端行为。
- Router: `quick_fix` + `safety` overlay；发布阶段 `release/backend`。遵守用户禁用 superpowers 的要求，不加载其能力。
- 当前状态：发布版本 `8711e424113b674f54a4646b4127adde6153da0a` 完整 CI、后端部署、production iOS OTA 和公开 manifest 回读均成功；设备拉取与真实账号写入未重放。
- 不回填截图中的真实行程；测试使用合成地点和隔离测试账号。

## 根因与改动

`记录我的行程` 被后置所有权语法当作非当前用户资料，导致分类为 unknown、无写入授权。原有简短 `记录行程` 仅支持前一条助手提议中的事件内容，无法把本轮明确提供的位置、计划目的地与路线绑定到工具载荷。

共享命令语法增加显式第一人称所有者。仅在完整授权检查通过且消息结构为“记录命令 + 我目前所在地点 + 可选计划/路线”时，从用户本轮文本生成标题和备注。保留计划措辞；模型自行添加的到达状态、时间、用户标识和备注不进入载荷。未知附加句不被静默丢弃。复用原有工具网关、回执和幂等身份投影。

## 证据

- RED：新增测试在修复前 3 failed / 14 passed，包含本人命令及真实工具网关不派发复现。
- GREEN：分类、共享写授权、工具网关、文本工具恢复四个测试文件，4,757 passed。
- PostgreSQL：独立临时测试数据库；`test_agent_trip_record.py` 11 passed。包含真实 `run_stream` → 工具网关 → HTTP 测试客户端 → 生活事件 API → PostgreSQL → assistant write_receipts；仅模型传输和 HTTP 网络传输使用测试替身，策略和持久化代码均未替换。
- 安全负例：否定、撤回、转述、假设、引用、其他所有者和问句均不派发；模型提供的其他用户 ID 被丢弃，落库归属认证用户。
- 截图原句本地无持久化探针通过；不把私人地点写入仓库。
- `PATH="$PWD/.venv/bin:$PATH" ./scripts/system-map-check.sh` 通过；该局部实现未改变生成图结构。
- `git diff --check` 通过。

## 独立安全审查与修复

- 首轮固定候选 `a790be24e`：独立 reviewer 裁定 NO-GO。宽地点字符集吞入括号示例/假设或句尾授权否认；授权规范化还会损失英文地点大小写及空格。
- 补充真实网关负例和保真测试，修复前 5 failed / 9 passed。修复后拒绝元语言限定词和括号，授权检查与原始事实投影分离；PostgreSQL 新文件 18 passed。待固定新提交重新独立审查。
- 完整 executor completion 状态回归 178 passed。
- 第二轮 `519de2e98` 仍 NO-GO：地点后的未知假定、转述、撤回附言可被吞入。新增 6 个失败网关用例后，改用正向有界实体终结词，匹配首次地理实体结尾，任何剩余附言均拒绝授权。支持口岸等设施、行政区/港岛目的地和桥路等路线；未覆盖的地名表达不自动授权。PostgreSQL 新文件 24 passed；截图原句无持久化探针仍通过。旧候选完整相关回归为 4,775 passed。
- 最终代码候选：相关分类/授权/gateway/文本恢复/行程回归 **4,781 passed**；PostgreSQL **24 passed**；System Map 和 diff check 通过。
- 第三位独立只读 reviewer `/root/trip_safety_final` 对固定 `fad84c255..af2f0cdec` 裁定 **GO**：额外 57 条撤回/转述/假设/历史附言探针全部拒绝；新增行程、分类与 completion 共 **1,082 passed，退出码 0**。同时确认拒绝不会借用旧上下文授权、规范载荷进入原有去重身份计算。

## 发布断点

`APP_ENV=test DATABASE_URL=sqlite:///:memory: python scripts/harness_llm_regression_gate.py --include-live-llm` 返回失败：离线 invariants 12/12、health_agent_core 50/50、trajectory contract 12/12、goldens 9/9 通过；真实 orchestrator 0/5。默认 provider 报 ValueError，OpenAI 备用路径被 `recipient_not_disclosed` 拦截。没有修改披露/同意配置，没有设置 confirmed 或 waiver 冒充通过。

已定位本地现有发布配置内的模型连接参数。只在进程内加载限定的模型参数用于合成评测，数据库强制保持隔离内存测试库，不输出凭据、不变更生产配置或披露规则。第一次配置修正评测 5/5、平均 0.96；最终代码候选重新评测 **orchestrator 5/5、平均 0.94**，其余离线/trajectory 闸均通过。

2026-10-17 只读发布现场：生产仍 `c2b6f87469999f134bd1853274def9e0f4153f95`，backend 与 GitHub relay active；服务器当前授权已绑定另一任务的 `fad84c25524e73d3c4df8bac1e80dfb5915577a1`。该任务在本轮 11:50–11:57 更新了 canonical staging / revoke / rotate 证据，且未向本任务移交发布归属。无锁不视为交接。没有更新远端 main、CI 确认变量或生产授权，避免破坏对方精确主干准入。

交接后需绑定最终发布 SHA 的真实模型确认，推送并等待完整 CI，再按受控后端发布流程执行。此修复没有 Mobile JS/原生差异；其他候选包含的 Mobile 改动仍由相应发布任务核对 OTA。生产路径与模拟器复验尚未完成。保留开工前全部其他任务的工作区改动；本任务临时 PostgreSQL 已正常停止。


## 用户授权接管后的发布推进

- 用户明确指令“忽略另外一个发布流程，直接接管和发布”。已复核上一候选 `fad84c255` 后端 SUCCEEDED、服务正常、无活动发布进程/业务租约；其 OTA 在 claim 前失败且服务器未创建 OTA operation。保留原回执，不重放旧失败操作。
- 新候选 `d18434bea` 已推送；绑定该 SHA 的真实模型 gate 5/5、平均 0.94，其他合成评测全通过。CI `39002909907` 的 dossier consistency 发现本文件缺少状态字段与 G1 段，现补齐真实准入范围和发布阶段；代码未改变。修正后须等待新 SHA 全量 CI。
- 接管 transport 独立审查 GO：使用 canonical staging、原锁内撤权、销毁已撤销私钥及 no-backup rotate；所有外部写入仍待新候选精确绿色 CI、本机 CI-mode 和足够 GitHub API 预算。旧候选 wrapper 未执行，新的 SHA 绑定将重新审查。
- 当时上线验收与 OTA 尚待完成；未把本地验证、已推送或已批准接管当作发布成功。最终结果见下节。


## 最终发布结果（8711e424）

- 用户授权接管已完成。新候选与安全 GO 代码 `af2f0cdec` 的 backend/scripts/.github 内容一致，仅补全文档。四个绑定最终 SHA 的 transport 包装脚本独立 GO；原锁、原回执保留，未备份、未重放旧失败 OTA。
- 完整 CI：[39003285151](https://github.com/itsoso/health-llm-driven/actions/runs/39003285151) success，32 个 job 成功。自动文档 CI 39003205667 success 不替代完整 CI；旧 d184 的失败文档已修正，旧 run 39002909907 已取消。
- 最终 SHA 本机 CI-mode：3,953 passed、84 subtests passed、23 平台限定 skips；JUnit 4,060 项、0 failures/errors；Dossier 一致性与 18 项测试通过，干净验证 checkout，退出码 0。真实模型闸 5/5、平均 0.96，invariants 12/12、health_agent_core 50/50、trajectory 12/12、goldens 9/9。
- 后端：[39004592806](https://github.com/itsoso/health-llm-driven/actions/runs/39004592806) success；服务器 completed=SUCCEEDED、runtime=COMMITTED，生产 SHA 精确一致，backend/worker/beat active，无 pending/preparing 或业务租约。当前客户端 API 域名为 health.executor.life；公开 `/api/v1/health` healthy。旧 skill 中 health-api.executor.life 地址已不适合作为当前验收地址，此次未修改 DNS/TLS 配置。
- 上线行为复核：生产源码绑定候选 SHA，合成行程事实投影及 6 个拒绝误写探针通过；无数据库访问或真实用户写入。完整 stream → gateway → API → PostgreSQL → write receipt 已在隔离合成测试中通过；线上真实账号写入未重放，不冒充真实设备验收。
- OTA：[validate 39005027157](https://github.com/itsoso/health-llm-driven/actions/runs/39005027157) 与 [publish 39005169224](https://github.com/itsoso/health-llm-driven/actions/runs/39005169224) 均 success；服务器 completed=SUCCEEDED。group `bedc735f-39d7-401f-89cd-aaf9f89fa387`，update `01a14847-14cc-79a7-b277-3cc5b5d35aeb`，runtime `1.3.5`，公开 manifest 实时回读匹配。
- 本次 OTA 一并交付上一候选尚未发布的用药提醒按钮 JS/TS 修复；相对上一已发布版本无原生依赖、签名或权限变更。未操作真机，设备拉取、模拟器端实际加载未验证。
- 结构化回执：`docs/reviews/2026-10-17-trip-record-release-receipt.json`。发布之后的证据提交只修改本 Dossier 与回执，不改变已上线版本。
