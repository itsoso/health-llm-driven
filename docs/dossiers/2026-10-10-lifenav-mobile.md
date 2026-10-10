# 完整个人周导航 Mobile

| 字段 | 值 |
| --- | --- |
| 状态 | building |
| 当前阶段 | G5 受信发布 SSH 线路阻断 |

用户原话：「增加mobile 版本」。继续此前已授权的整合、提交和最终部署发布，采用单 surface Quick Flow。

## G1 准入

裁决：PASS。既有个人规划对象的 Mobile 完整编辑，核心循环为计划、执行和回顾，manual_confirm；不扩张健康写权限、通知或外接 LifeNav。移除「详细规划请去 Web」的旧降级说明。

## G2 可行性和规划

裁决：PASS。现有 `/life-navigation` 只有今日添加、完成和简短复盘；Web 已有完整八视图，API/schema 已具备。沿用现有认证、版本 CAS 和私密备份。无新依赖/原生权限/迁移。规格与验收见 [Mobile tech-spec](../specs/active/2026-10-10-lifenav-mobile.md)。用户已授权全部完成；没有待拍板分叉。

## 实现与验证

同一父流程委托 Health Harness：mobile-engineer 独占页面/组件/页面测试，root 负责服务、纯模型、文件 IO 和文档，独立 reviewer 做 G4；不切换分支、不修改其他 session 文件。

run_path：`docs/_generated/harness-runs/afdc5baa28fd.jsonl`（本地，不提交）。

## G3 实现验证

裁决：PASS。先观察八视图缺失、备份 API 缺失以及选中上午仍创建灵活任务的失败回归，再实现。当前四组周导航测试 31 passed，TypeScript 通过；固定 7ed816a7b 的完整源码 Mobile 验证 335 suites、3397 passed、1 skip。共享目录期间 Prompt 会话新增红测试，未覆盖该工作；隔离验证首次缺少 Watch 被源码测试读取的文件，补齐同 SHA 源码后全量真实通过。iOS 实际 Bundle 导出通过（无 dotenv 输入、无 vendor 发布）。后端现有导航契约合跑 48 passed、6 PostgreSQL 专项 skips；本任务未改变数据库语义，PostgreSQL 证明以新候选完整 CI 的实际 PG 集成闸为准。System Map、导航生成物、doc-drift 和 Dossier 一致性通过。

背景只隐藏正文并在同账号内存恢复草稿；账号/consent 变化彻底清除。系统文件选择/分享的 inactive 交接不会取消自身操作，真正 background 或换号仍拒绝迟到返回。严格导入先预览、显式确认，恢复使用当前 revision CAS；临时文件清理测试通过。

## G4 与发布验证

7ed816a7b69193ce721ab183cf666389fdbd4e81 的独立 G4 裁决：GO。随后收紧分享文案为「已打开备份分享」，不把系统分享取消误称文件已保存。

按用户已授权的跨 session 整合，Prompt 会话交接四个冻结 Mobile 文件：`chatTransparency.ts`、其测试、`AnswerEvidencePanel.tsx` 和 `services/chat.ts`。该会话 64 tests/3 suites、TypeScript、独立安全 GO；本流程已核对四个文件摘要相同。只显示实际上报的逐次模型/Token/缓存/耗时及记录核验/结束里程碑，缺调用明细或时钟对齐证据会明确保留未知。不改后端推理、健康写入、提示词或原生依赖；后续 Token 节省方案不混入本批。合并候选重新全量验证与固定 commit 独立 G4。

最终候选 5fe583bf315cffe9d5fd4050344a46785d48683e 已提交并推送 main；整合后 Mobile 全量 335 suites、3403 passed、1 skip，TypeScript、System Map、治理和 Dossier 检查通过。固定最终 commit 独立 G4：GO。精确 CI run 38007090779 completed / success，全部适用任务通过，其中 PostgreSQL 集成闸通过。OTA validate run 38007748124 与后端 validate run 38007761166 均 success；生产 canonical staging 再核对同一 CI run 和 SHA 通过。

G5：后端 PASS，Mobile OTA BLOCKED。canonical 授权轮换成功，原始锁及历史回执保留；后端 run 38008646071 success，生产源码干净且精确 SHA 5fe583bf315cffe9d5fd4050344a46785d48683e，durable completed.json 为 SUCCEEDED。四服务 active；内网与公网健康 200，实际周导航 workspace 未认证 401。

唯一 OTA publish run 38009227924 failure。安全诊断为 publication / command_failed，审计仅含 preflight、claim 输入及 diagnostic，没有 vendor receipt。只读核验服务器该 SHA OTA operation 不存在、business lease 不存在；供应商 production 列表最新仍是旧 b5e96ee group a87acf6d-c6b8-4ece-9390-97afaad6973e。不能将本地 claim 输入称为服务器 claim，不能猜测是 vendor update、读回或 RPC 的具体故障；没有原始 claim/receipt，禁止 recover，原发布不得重发。Mobile 新版本未发布成功，后续批次必须重新固定候选并走自己的完整精确 CI/准入/发布流程。G6 未验证：iOS 模拟器已启动，但 Mac 锁屏导致 CUA 无法操作，没有拿合成截图或旧包冒充候选 UI 通过。后续现场回执仅留工作区，保持发布器与候选精确绑定。

独立发布收口裁决：G5 partial，未识别到可恢复 mutation。发布所有权已交接至用户另行授权的下一批修复 session；它继承本批 Mobile 实现，需新固定 SHA 与完整 Gate，当前失败 run 不得重发。

## 继续验证与发布（2026-10-10）

用户明确授权「继续验证和发布OTA」。旧 5fe 唯一失败运行不重发。已重新只读确认无旧 OTA operation/lease，旧历史、部署窗口、loopback 及 backend status 均 PASS。新批继承完整 Mobile、透明 UI 及另一 session 已固定 G4 GO 的新建开场（6810463e6），不纳入其未验证的今日计划工作区修改。

新增闭集分阶段诊断（55653dd11），六个故障注入用例先观察 6 failed；实现后完整 OTA 四组 203 passed / 1 skip，固定独立 G4 GO。异常、供应商原输出、凭据不上传；顺序、原 claim、单次 vendor update 与 finish 校验保持。

最终候选 e278a0afa6dc83b47fc570bc1ca84590fe38266b，仅再修正交接 dossier 缺少 G1/G2 及状态字段，运行树与 556 完全相同。固定源码 Mobile 全量 335 suites / 3405 passed / 1 skip；backend opener 63 passed，tsc、真实 iOS export、System Map、治理、192 份 dossier 检查通过。固定最终 G4 承继 GO。已 push，CI run 38011123238 运行中，禁止将待执行 CI 称为完成。

G6 当前仍未验证：Mac 现已可操作，但可见模拟器是旧的 LifeNav Synthetic UI 应用与登录界面，不是本候选生产 OTA；不将其截图作为候选验收证据。

### e278 发布现场证据与阻断

精确 CI 38011123238 completed/success，30 项通过。OTA readonly validate 38011742705、backend validate 38011746085 success。canonical source staging 及 5fe→e278 授权轮换成功，原终态/锁/历史 b5 OTA 回执保留。

backend 请求 38012631907 只在无生产凭据 preflight 失败，固定错误 GitHub metadata unavailable；backend/readiness 未启动。新的只读 validate 38012783096 与服务器精确 gate 都 success。独立 review 确认整个 e278 workspace 不存在、无 lease/进程，未消费部署资格，允许新的首次实际业务调用，而非重跑消费。

38012816142 完整通过 preflight/readiness，backend SSH connection timed out，服务器仍无 e278 workspace/lease/进程。限定最后一次连接机会 38013153258 在 readonly readiness 阶段连接被关闭；两次均无 trusted handler 消费证据。原所有失败运行保留，不再循环 dispatch。没有调用 e278 OTA publish/claim/recover；不能把 readonly OTA validate 称作 Mobile 发布。

生产仍为 5fe583bf，四服务 active/health 200。当前授权为 e278，但并非部署成功回执。SSH 管理线路正常；sshd active、UseDNS=no、GSSAPI=no、未见 MaxStartups 饱和证据。托管 runner 线路失败的具体根因尚未知，不以推测改变鉴权、hostkey 或发布入口。待既有受信线路可验证恢复后再做准入；任何 workspace/intent/lease 出现先回到原证据调查，禁止重发。

## Mac 锁屏模拟器运行入口（2026-10-10）

用户要求：「要确保我在锁屏的情况下，也可以模拟手机。」新增独立 `scripts/mobile_sim_headless.py`，使用 simctl 和可选 XCTest，不依赖桌面点击；明确 UUID、有限等待手动锁屏、IORegistry 明确 bool 状态、私密证据目录、失败回执及真实非零退出。仅 `caffeinate -i` 防止空闲系统休眠，不改变锁屏或自动解锁。说明见 `docs/ops/mobile-simulator-locked.md`。工具改动保留本地，未改变冻结 e278 候选。

先观察 7 个 RED，再实现与审查整改；最终工具及相邻截图检查 21 passed。独立 reviewer 工具范围安全 GO，不代表候选 G6。

独立 Settings XCTest 实际执行启动、滑动、点击“通用”和导航断言：首轮因列表位置失败，保留 `/tmp/reva-simulator-unlocked-probe-20261010/tests.xcresult`；修正定位后 `/tmp/reva-simulator-navigation-v2.xcresult` 1 passed。最终完整入口 `/tmp/reva-simulator-unlocked-probe-v3-20261010/receipt.json` 与其 XCTest 结果通过，开始/结束均为 unlocked。安装包内容哈希已记录，源码 SHA 未知、业务功能验收仍 unverified。

真实锁屏：自动锁定操作后 IORegistry 仍明确报告 unlocked，不能伪报通过。第一次要求锁屏的失败回执保留 `/tmp/reva-simulator-locked-probe-20261010/receipt.json`；修正状态来源后等待用户手动锁屏，有限 600 秒后台探针目标 `/tmp/reva-simulator-locked-probe-v2-20261010/receipt.json`，尚未取得 locked 前后和 UI 通过的回执。G6 保持未验证。此项独立于受信 SSH 阻断，不重发 OTA。

## 授权历史校验 I/O 优化（2026-10-10）

用户追问 8 分钟/8 GB 校验并要求优化。已从原始会话数值定位 rotate pid90431：08:00 时 rchar 6,680,793,629、read_bytes 8,016,338,944。只读生产元数据清点确认四组 Web 发布备份合计 2,727,305,688 bytes / 210,290 entries，16.82 秒；两次 `_assert_idle` 会重读未变化历史内容。仅在一次持锁 rotate 内共享短期 memo，完整库存、权限、链接、ctime/inode、首轮完整内容与原回执、扫描稳定性仍核验；不落盘/不跨命令/live 无 cache。新增脱敏阶段日志，不改变 stdout 原协议。

固定 commit bd93515a03e3aab8f2989d792974f08ba6236e7c 六文件独立 G4 GO。最终完整工具回归 1,153 passed、10 skipped、84 subtests passed；针对检查 191 passed，System Map、secret scan 与 diff-check 通过。对同盘合成 512 MiB/2048 文件两轮旧新调用，内容读取 1 GiB → 512 MiB，1.17s → 0.60s，摘要兼容；不是生产 8 分钟减半的证明。改动已推送 main，精确 CI 进行中；未轮换新生产授权、未部署、未派发新的 OTA。详情 `docs/ops/release-authorization-io.md`。

## 发布关键路径优化实施（2026-10-10，待发布）

用户要求实施优化规划，沿用本 Dossier 与 harness run，不提前推进未满足的部署/OTA Gate。先前 `bc2fcee091eb8c5123edd293f519e3b091d0e494` 的精确 CI `38016712539` 与 OTA 只读准入 `38017227123` 成功，但尚未对该候选轮换授权或部署；这些结果不代替本次优化的新 SHA 验证。

本次实现：前端发布历史首次全量核验后，创建 root 私有 HMAC 封存检查点及递增代际锚点；常规检查仍读取每条原审计/证明和目录权限，只完整检查当前绑定的一组回滚备份与新增操作。归档内容不遍历、不声称当前完整，重新晋升/恢复必须全量校验原摘要。索引缺失终态、签名或权限异常、未知操作和未完成更新均阻断。封存独立于业务发布收尾；原 launcher/build 锁与无活动 lease/process 约束保留，中断只允许只读 inspect 后完成原检查点，不生成新的恢复回执或重放业务 claim。root 同时替换密钥与全部状态不在该协议的威胁覆盖内。

可信 workflow 增加无凭证、无发送的固定 TCP/SSH banner 前检与 `target=transport`，五秒预算内失败；成功仅证明路由响应，不代替 host identity/auth/readiness。Pi 安装增加独立阶段耗时，保留真实非零退出码。现有 OTA 单次 export、环境摘要复用、依赖锁复用和 timing-balanced CI 保留；Pi 缓存及跨 runner 工具复用需生产计时和来源协议，未冒充已实现。

G3 增量证据：封存/独立 operator 新增 61 项通过（含归档规模 0/4/12 时 hot 内容校验恒为两项）；相关既有回归 385 项通过；transport 相关 211 项通过、6 项原 Linux 专用测试在 macOS 跳过；Pi timing/deploy 186 项通过。完整 CI-mode release-invariants、固定提交安全审查、精确远端 CI、真实 transport、生产封存迁移、部署及 OTA 仍按顺序执行，未据这些局部结果宣称上线。
