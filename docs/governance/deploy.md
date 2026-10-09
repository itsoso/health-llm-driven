# 部署规范 🚀

> 从 `AGENTS.md §8` 拆出（2026-05-31, Agent Operating Harness Phase 2,见 [`docs/design-agent-operating-harness.md`](design-agent-operating-harness.md)）。`AGENTS.md` 现在只留章节导航,本文件是本章权威全文 —— 硬规范裁判权不变。


### 8.1 部署方式

#### 复用候选的完整 CI

`main` 的非纯文档 push 首次即运行完整 CI；PR 和本地预检保留按变更范围执行，
纯文档 push 保留轻量验证。发布前查询并等待目标精确 SHA 已有的 CI，不能例行
再触发一轮 `workflow_dispatch`。手动完整 CI 只用于明确的恢复或补验证需求
（例如历史候选或纯文档候选尚无所需完整验证）。不得通过取消同 SHA 的运行中
或失败记录制造绿色；全部适用运行仍按现有 trusted release gate 裁决。

#### 版本化后端准入（backend-v1）

`trusted-release.yml` 的显式 `target=backend-v1` 可在无关端侧 job 仍运行时申请
后端发布；旧 `backend` / `release` / 原生及 OTA 开始入口继续要求完整 CI。
该目标并非调用方声明“只改后端”即放行：服务器必须读取实际生产 HEAD 和该
SHA 的 root-owned `SUCCEEDED` 回执，使用 `backend_release_scope.py` 验证
生产至候选的完整逐提交变更。初版仅允许该脚本列明的三个服务实现文件及限定
测试/文档；未知范围、缺失基线、合并、重命名、安全/依赖/迁移/共享契约/发布
代码均回到 full。所有后端分片、PostgreSQL、质量、类型、发布不变量、文档
及 `backend-release-ready-v1` 必须在当前 main 精确 SHA 的可信 CI 中成功。
所有同 SHA 运行及 attempt 都须核验；任何已观察到的失败、取消或未知状态拒绝。

可信 bootstrap 的 `install/rotate --backend-ci` 是同一服务端范围闸的显式入口，
不豁免旧授权终态、锁或独立 G4，不可与恢复/原生收尾选项混用。新 key 调用旧
`run` 或原生/OTA claim 时仍在领取资格前检查 full；既有 finish 动作继续按原
绑定回执完成收尾，避免发布成功后因 main 前进留下悬挂租约。
协议启用须安装新受审 canonical executor；仅合入 workflow 不等于线上已启用。

#### 同主机前端制品准备与复用

canonical `deploy.sh --prepare-frontend-artifact --publisher-sha <sha>
--frontend-tree <tree> --artifact-id <32hex>` 默认只读预检，携相同
`--evidence-sha256` 才实际准备。准备仍要求当前 main 完整 CI 和独立 G4，
使用原 systemd sandbox，领取独立编译锁，不占用业务发布租约、不停服务。
发布时给原 `--publish-frontend` 增加 `--prepared-artifact`，使用与 operation ID 相同的制品 ID；
原证据摘要流程、生产检查、租约、切换和回滚全部保留。

READY 绑定 publisher SHA、完整 frontend tree、锁文件、公开配置、工具链/
平台、构建配方、构建日志及制品摘要。消费前重验并原子领取，禁止重用、失败
重发或自动回退重编译。相同主机准备只能缩短最后发布阶段及允许准备与后端
工作重叠，不等于跨 runner CI 制品投产，也不证明总构建算力下降。

**唯一部署入口: `deploy.sh`**

所有线上部署必须通过项目根目录的 `deploy.sh` 脚本执行，禁止手动 SSH 到服务器进行部署操作。

```bash
# 部署命令
./deploy.sh           # 部署全部 (前端 + 后端)
./deploy.sh -f        # 仅部署前端
./deploy.sh -b        # 仅部署后端
./deploy.sh -e        # 仅同步环境变量，并证明 backend/Celery 运行时 flag=false
./deploy.sh -H        # 受控启用 health-evidence runtime
./deploy.sh -r        # 仅重启服务
./deploy.sh -s        # 查看服务状态
./deploy.sh -l        # 查看服务日志
```

#### 生产服务器的 GitHub 网络路径

生产服务器已配置 `reva-github-relay.service`，通过 `base.executor.life` 转发
`github.com:443`。服务器上的标准 GitHub HTTPS URL 自动使用该线路，无需修改
`deploy.sh`、仓库 origin 或 GitHub Actions 的代理环境变量。新 Agent 在服务器
拉取 canonical source、轮换发布授权或触发发布前，先完成
[GitHub 代理运维手册](../ops/github-relay.md)的只读检查。

本机和 GitHub Actions runner 不使用服务器的 loopback 映射。网络检查成功不替代
精确 main/CI、版本授权、旧操作终态和发布锁检查；发布失败仍按原回执恢复，不能
因为修好了网络就重放已消费的 `run`。代理故障按手册恢复，不关闭证书校验、不换
第三方源码镜像，也不靠延长超时掩盖断线。

### 8.2 线上配置管理

#### 独立视觉模型配置事务

`deploy.sh --select-vision-model --publisher-sha <current-main-sha>
--production-sha <deployed-sha> --operation-id <32hex>` 是 operator-only
入口，默认只读预检；携相同 `--evidence-sha256` 才执行。执行前须精确
publisher 完整 CI 与独立 G4 GO、实际生产成功回执及原 launcher/business
锁检查。只允许 `qwen3.8-flash`，不开放 SSH RPC 或新的认证入口。

仅创建 `/var/lib/reva-vision-model/model.env` 与三个现有服务的模型专用
drop-in；不修改原 `.env`、持久健康授权、发布身份、服务用户或沙箱。
必须证明有效 EnvironmentFile 顺序保留原 `.env` 和可选 `enabled.env`，
模型文件实际最后加载，并拒绝环境删除规则及未知来源。受保护文件采用
身份与变更元数据检查；证据只声明本操作未写这些文件且元数据未漂移，
不声明逐字节比较，不读取其秘密内容。

配置安装、有界重启、三服务真实 PID 中唯一非秘密模型变量、既有授权
开关和沙箱、loopback 健康检查通过后，先持久化
`CONFIG_SUCCEEDED_PENDING_MODEL_ACCEPTANCE` 回执再释放原 lease。
该终态明确真实模型调用为零、模型验收仍 pending，不是
`VISION_SUCCEEDED` 或 G6。线上合成验收另行核对现有已授权服务通道、
实际型号、usage 与请求硬边界；不得伪造真实评测确认。

同入口的 `--rollback` 默认仍只读预检，执行同样绑定新鲜摘要和独占
lease，只恢复本操作模型专用文件。未知写入或重启结果保留现场与锁，
禁止盲目重放；配置恢复不证明已退役型号能够服务。后续 canonical
后端发布保留模型 overlay，须将其纳入有效配置验收；受审替换或移除
必须显式处理，不能凭基础 `.env` 的模型值推断实际运行模型。
未终结模型配置审计阻断其它 canonical 发布，禁止删审计或清锁绕过。
`--finalize-config` / `--finalize-rollback` 只允许在已持久化 verified
效果、真实服务与模型专用文件回读及原 lease 身份一致时补终态和锁收尾，
不重放安装、daemon-reload、restart 或模型调用。缺失 verified、部分锁
身份不明或效果漂移均 BLOCK，保留原现场供负责方受审处理。

注册隔离修复的独立 operator 入口为 canonical `deploy.sh --security-hardening
--sha <final-sha>`，只在该版本 backend 与前端制品均已成功发布后执行。
入口、配置备份、互斥与实际隔离验收约束见
[注册隔离修复发布](../security/2026-09-29-registration-hardening-release.md)。
它不授予自主注册权限，不替代后端或 Web 成功回执，不扩展云端 SSH RPC。

固定版本在账户创建前中断时，仅可按
[主机加固前置失败恢复](../security/2026-09-30-host-preflight-recovery.md) 使用
新受审发布器的 `--resume-preflight`。原失败/备份/租约不删除、不重建；
独立恢复成功及外部回读不能替代原后端/Web 发布凭据。


#### 独立发布新前端树（已加固服务）

用户明确批准仅发布前端后，使用独立的 canonical operator：
`deploy.sh --publish-frontend --publisher-sha <current-main-sha>
--production-sha <original-backend-sha> --frontend-tree <40hex>
--operation-id <32hex>`。只从服务器对应 publisher 的 root-owned canonical
staging，以固定系统 Python `-I -S -B` 执行。默认仅返回只读预检摘要；执行
必须提供相同 `--evidence-sha256`。该入口不改变下述同树重建条件。

发布器必须是当前 main、精确 CI 绿色并通过独立 G4（包括实际前端依赖修补）。
显式目标树必须匹配 publisher 的完整 frontend tree。原 production SHA 必须
保持 clean revision，并具有自己的精确 CI 与原后端 `SUCCEEDED` 回执。
后端、Mobile、共享包与发布器源码不复制进生产 checkout；不轮换授权，不启用
OAuth，不创建健康数据访问授权，不更改服务 unit 或网络权限。

仅适用于已存在的 `health-web` systemd 前端固定启动契约。沿用隔离构建
sandbox、资源上限、数据根隔离和公开端点配置白名单；npm 生命周期脚本禁用。
构建配置中已在白名单内的 `http://localhost:8000` 与 `http://127.0.0.1:8000`
统一为固定运行时地址 `http://127.0.0.1:8000`；原配置文件及摘要不变，其他地址
和端口仍拒绝，多配置文件间的冲突仍阻断。
仅切换 `.next` 与 `node_modules`，保留旧制品；运行时 `.next/cache` 的账户
权限单独核验，其他制品不可由服务账户修改。生产 Git SHA、后端/worker/beat
进程身份、restart count 和配置摘要在构建及页面复验前后保持一致。

独立 `frontend-publications/<operation-id>` 在任何副作用前 fsync intent，
持有原 launcher/build 锁并领取既有 business lease。验证内部与真实公网
`/privacy` 和 `/connect/health` 后，释放本次 lease 并持久化绑定 SHA、前端树、
制品与证据摘要的 `FRONTEND_SUCCEEDED`。这不是后端成功回执，也不证明真实
OAuth grant 完成。失败、未知结果、部分回执或库存漂移阻止后续操作，不自动
重试、换 ID、回滚、删锁或伪造成功。

当前 GitHub Actions Trusted workflow 没有 frontend 目标；本入口通过既有
管理通道控制服务器执行与构建，不上传本机脚本，不扩大 cloud RPC。

2026-10-03 的 `637078dd8c584686a59000de91d2dad2` 操作在停止旧前端后、
制品首次 rename 前失败。用户明确授权接管后，仅该固定操作可在上述入口增加
`--resume-stopped-publication`，从当前绿色 main 的 canonical staging 续发。
它绑定原 f8dd publisher、dbad backend、完整 frontend tree、原发布器源码和
原构建摘要；不重新构建、不换 operation ID、不轮换身份。原五项证据保持字节
和 inode，原租约保留到成功。旧前端已恢复时，新预检独立绑定当前稳定进程与
旧制品摘要，不改写原 before.json。

续发先写独立 recovery intent，再核验双锁、原租约、后端/config、制品与
停止状态（含固定 cgroup 无残留进程及重复状态读取），然后切换已有候选。
内外网页面、制品摘要、备份和后端不变均验证后，先 fsync recovery completion，
再写原 publication completion，最后释放原租约。原 failed.json 保留；历史
验证仅对该固定操作接受完整交叉绑定的恢复链，其他失败仍阻断。任何恢复意图
已存在、未知结果或部分切换都禁止自动重试，必须另行调查，不删除证据。

#### 已部署同树前端的受控重建

用户明确授权后，可从当前 main、真实精确 CI 绿色、独立 G4 GO 的 canonical
root staging 执行 `deploy.sh --rebuild-deployed-frontend --publisher-sha <sha>
--production-sha <deployed-sha> --operation-id <32hex>`。这是只重建前端的窄
operator 入口，不扩展 cloud SSH RPC，不领取 native/上传权限，不改变原后端
授权或成功/退休审计。必须通过固定系统 Python `-I -S -B`，不上传本机脚本。
默认只读取证；核对摘要后传入相同 `--evidence-sha256` 才允许执行。

发布器须为当前 canonical main 且精确 CI 绿色；实际生产 revision 要有原
后端成功回执与自己的精确绿色 CI。双方完整 frontend tree 必须相同，生产
干净 revision 证明不得放宽；不同 tree 的新前端功能不适用此入口。普通
`-f` 的 exact-SHA 规则不变，不以重建名义 checkout 或 push 线上代码。

持有原 launcher.lock inode，并占用既有 business lease；独立
`frontend-rebuilds/<operation-id>` 先 fsync intent，再开始副作用。所有旧
未完成/未知操作阻止换 ID 或后续普通部署、授权轮换；不得用其完成记录替代
backend `SUCCEEDED`。失败保留现场、旧制品和 lease，不自动恢复或重试。

构建仅复制经 Git blob 核验的 canonical 前端，使用无特权、受限 CPU/内存
的 systemd sandbox；生产目录、健康配置、发布凭据和 home 不可读。
数据隔离必须覆盖 `/opt`（含共享文件）、`/var/lib`（含健康运行数据及数据库）、
缓存/日志/备份和可选数据挂载根。只把 canonical 输入显式绑定进私有 `/tmp`；
不存在的可选根可跳过，存在时必须隐藏。Linux CI 使用原样 deny list，验证
普通用户可读的合成数据在沙箱内不可读，同时构建输入及私有缓存仍可用。
npm 全局/用户配置禁用，依赖生命周期脚本禁用。仅允许固定的公开 API/site
端点配置，按数据解析不执行 shell，原配置文件与元数据不变。只停经核验的
前端 PM2 进程，保留旧 `.next` 和 `node_modules` 后成对切换，再启动前端。
原生依赖安装脚本被禁用不能替代实际 build 和页面验收。

成功必须回读内部及真实公网隐私页，并证明生产 Git SHA、后端/worker/beat
PID 与 restart count、健康环境文件及授权文件摘要未变。只有这些验证与
lease 释放均完成才记独立 `FRONTEND_SUCCEEDED`；不改 DB/schema，不重启
后端，不声称全端发布已完成。

锁父目录同步使用 `_sync_business_lease_parent()`：先验证固定 root-owned
`/var/lock → /run/lock` 与目标 1777 元数据，再以 `O_NOFOLLOW` 打开真实目录，
前后核对同一 inode 并 fsync。通用目录同步仍拒绝符号链接；不接受任意解析目标。

此 operator 的 `--finalize-verified` 仅收尾受审旧实现中已切换、已验证后发生的
锁父目录同步失败。先从新 current-main、精确绿色 CI、独立 G4 GO 的 canonical
staging 读取证据，再提交同一 `--evidence-sha256` 执行；`--production-sha` 保持
实际已成功部署的旧 revision，`--operation-id` 保持原操作。它不构建、不切换
制品、不重启服务、不改后端成功记录，也不恢复已删除的 lease。

必须证明原 `verified`/`failed`/安装记录、受审原实现与保留旧制品一致，实际
前端完整摘要仍匹配原验证值，内部及公网页面通过，后端进程、配置、生产 SHA
保持原快照。已回收的 systemd unit 只能结合该实现中 `verified` 写入必然晚于
成功 wait 和空 cgroup 的证据、当前精确终态及无残留进程共同验证；缺失 unit
自身不是成功证据。持原 launcher 锁及存在时的原 build 锁；不存在的 build 锁
不得创建，执行期间须持续证明不存在。其他未完成操作一律阻断。

原失败与验证记录保持原样，独立 `frontend-finalizations/<operation-id>`
持久化 intent 与带恢复来源的终态。部分 intent、证据变化或未知库存阻断后续
发布，不能重跑或换 ID。后续历史检查只验证持久证据，不把以后新的生产版本
与旧现场快照比较。完成该收尾不代表主机加固或 OTA 成功；后续发布继续使用
完整的同 revision 合同，不借此放宽 publisher/production 绑定。

仅作为证据读取的旧 `previous-*` 归档可能保留历史组写普通文件及 npm 内部
硬链接。归档验证须自行核对固定路径、实际 root-owned 0700 审计祖先及前后
身份；目录仍执行严格检查。普通文件必须 root:root，拒绝世界可写、特殊权限
和特殊文件。硬链接的全部别名必须位于同一归档树内，数量等于 inode 的
`st_nlink`，身份与内容一致，并在遍历后复核。原权限和 inode 参与证据摘要，
不得通过 chmod、复制或删除掩盖原现场。此例外不适用于在线制品、代码或回执。

此 operator 的 `--retire-failed` 仅在用户明确授权后关闭已知 npm 配置启动
失败：完整历史 publisher 实现摘要、精确三行错误、四文件失败审计共同证明
未进入安装。安装意图、未知文件、不同日志/实现、构建非终态或残留进程均
BLOCK；不可仅凭 install-started 缺失推断安全。持原 launcher flock/inode，
核验生产 revision/后端成功回执/精确 CI、原 before 的后端与配置快照，以及
当前前端稳定身份。旧 before 未记录前端 PID，不声称证明历史前端 PID 未变。
默认只读，核对摘要后提供 `--evidence-sha256` 才执行；新代码同样必须当前
main、精确绿色 CI、独立 G4，且只从 canonical root staging 运行。

独立 `frontend-rebuild-closures/<原 operation-id>` 先 fsync intent，仅将原
lease 四文件完整复制到持久 root-only 审计，再同文件系统 no-clobber 移至
`/run/lock/health-app-release.frontend-retired-<原 operation-id>`，保留 inode。
原失败审计和构建现场完全不改，不重启服务、不改健康数据、不撤销/新增身份。
全部后验与终态 fsync 成功才返回随机回执；回执只经受保护 stdin 传给独立
`--acknowledge-retirement`，不得写入命令行、日志或用户消息。该只确认入口
验证完整关闭证明和回执后写私密 acknowledgment，普通发布/轮换历史闸此后
才放行。失败或回执丢失不补发、不重跑、不换 ID；原状态永久保持
FRONTEND_NEEDS_OPERATOR。后续历史核验依赖持久原证据、归档和有效回执，
不绑定未来生产 SHA/PID，也不依赖重启后可能消失的 `/run` 归档。新部署和
新重建仍独立通过既有全部闸，不把此收尾计为发布成功。

#### 受审隔离发布入口

手动触发 `.github/workflows/trusted-release.yml`，先以 `target=validate` 验证当前 main
的精确 SHA 和真实 CI，再以同一 SHA 执行 `target=release`。各 job 均使用新的
GitHub 托管 VM，不上传本机工作区、不复用测试 runner 或缓存；生产权限只在只读闸后使用。
GitHub 控制面、受审代码、固定工具链和服务器 root 是信任前提，不声称抵御 runner root 失陷。
仅后端变更使用同一入口的 `target=backend`，仍先经过 preflight 与服务器 readiness，
再执行相同 backend job；不读取 Expo 凭据、不领取构建/上传权限、不运行 iOS jobs。

固定候选的运行中检查允许有限文档漂移：触发时仍须 candidate SHA = workflow SHA =
当时 main，绝不执行调用方任意指定的旧源码。其后 main 只能沿最多八个线性提交前进，
每个提交的完整比较仅包含 `AGENTS.md`、`docs/governance/deploy.md`、
`docs/ops/github-relay.md` 或扁平 `docs/dossiers/*.md`；不按 `.md` 后缀泛化放行。
发布器、依赖、配置、运行时知识和其他路径一律阻断，代码修改后回退也不例外。
合并/分叉、比较截断或未知结果阻断。候选及观察到的新 main 均须精确 CI 绿色，
检查末尾重验 main 和 CI attempt；构建/上传来源始终是原固定候选。
服务器的 Git main 观察值必须与同一 canonical gate 的 API 证明一致；先核对受审
helper 字节再隔离执行，不接受本机上传 helper 或缓存证明。不改变已有 claim、
授权、锁、终态及恢复边界，也不放宽其他发布器的独立检查。

用户明确授权后，已成功部署运行树的 iOS 续发使用 `target=testflight`，不运行 backend
job、不补写或复用新的后端成功回执。仍先 validate、当前 main 精确 CI 和独立安全复审，
由 canonical bootstrap 切换至新 SHA，可沿用当前专用发布公钥；不得复用旧 SHA 或清除消费记录。
`check-testflight`、`claim-testflight-build`、`claim-testflight-upload` 均在原 launcher
锁内原子领取既有业务 lease，并持有它完成证明和 vendor claim：实际生产 clean revision、
对应 SUCCEEDED 和精确历史 CI、无未处理维护、服务及健康检查通过。不能仅检查业务
lease 不存在；普通 deploy.sh 不持有 launcher flock，必须由同一 mkdir 协议互斥。
候选除明确列出的发布器/测试/审计文档外，完整 Git
对象清单必须与已部署树相同；Mobile、后端、共享包或未知路径变化均不能借此续发。

首次构建 claim 在共享 build 锁内持久化私有 `testflight-base.json` 绑定生产 SHA，
上传前重验相同生产状态。临时业务 lease 使用固定 label/stage、随机 token 和 inode
证明，检查器通过私有 stdin 接收身份；成功或已知失败退出前仅释放本次完整 lease。
初始化中断、inode/内容/库存漂移不清理、不接管，保留给人工取证。旧 RPC 在锁内拒绝
此绑定，run 也拒绝再部署；共享的一次性
build/native 标记仍防止跨入口重放。锁冲突、授权过期、未知结果或生产漂移即停止。
原始后端成功审计不改，native-only workspace 绝不标成 backend SUCCEEDED。
该 workspace 出现 vendor intent 后仍需人工核对精确 EAS/ASC 终态并走独立受审的
后续收尾；仅下述固定历史收尾可解除对应阻断，未知 native-only 库存仍拒绝，不得删除绑定以强行轮换。
上传完成不等于 Apple processing、测试可用或正式 App Review 完成。

#### 签名工具链的固定安全回补

`node-forge@1.4.0` 的 `GHSA-86w9-cpqp-85rv` 尚无已发布修复版。项目回补固定绑定
上游提交、原始与修复后源码、补丁及实际安装副本；不修改真实版本号，不添加漏洞豁免。
`node scripts/node-forge-backport.cjs --root <安装根>` 默认只验证；`--apply` 只应用
固定回补并执行真实验签正反验证。未知版本、字节漂移、缺失副本或符号链接越界均拒绝。
Mobile 的既有 patch-package 路径负责普通安装；Trusted Release 与 OTA 禁用生命周期
脚本，必须在任何凭据或 vendor 调用前，对 mobile 和 release-tools 安装分别显式
apply/verify。不能用 CI 工作区的通过证明替代新 runner 的实际安装验证。
OSV 审计继续显示原始发现，仅逐安装路径通过固定验证器的精确公告标为
`verified_backport`；其他阻断和空 exceptions 保留。上游发布修复后须重新评审移除回补。

#### 固定历史 native-only 收尾

`native_release_retirement.py` 只接受源码固定的历史 profile。默认仍为
`cad1fd1d33621532e587b265e79f737dfb06d1fe`、GitHub run 36111598240 attempt 2
及指定 build/submission；旧收尾证据格式和前次未进入 vendor 的验证不变。
显式 `--native-sha e19043ecb269e20f3bc0a546165e43d467f1fc8c` 选择 TestFlight 273：
run 36877321184 attempt 1、build `20d5e73a-a6b9-4c70-ad69-e63d31e058f2`、
submission `fcfbb57d-4804-4a36-9c57-eab062bf321e`。该 profile 另绑定完整 jobs 摘要，
拒绝虚构 prior attempt、新旧 profile 混用和任意调用方提供的 ID/摘要。未知 SHA 拒绝。

当前活跃授权不满足收尾 inspect 前置条件：操作者必须先获得生产授权变更许可，
按 canonical contract 撤销精确旧身份并销毁旧 loopback 私钥；不能为只读取证放宽
这一检查。受审 canonical root staging
以系统 Python `-I -S -B` 执行，先 inspect，再传相同 `--evidence-sha256` 执行；GitHub
只读凭据只经 stdin JSON 输入。旧 workflow、job、完整日志摘要、原始库存/锁 inode、
撤权和无残留进程均须匹配。实时生产 SHA 与旧 native binding 的历史 SHA 分开证明，
两者不得混写。旧尝试未到 vendor write 也必须有精确步骤证据。

独立 `native-only-closures/<old-sha>` 先持久化 intent，再保存
`CLOSED_NATIVE_ONLY_VENDOR_UPLOAD` 和随机私密回执；原 workspace、消费记录、锁
和授权不改。仅证明上传完成，不证明 Apple processing、TestFlight 可用或商店审核。
轮换通过既有 `--recovery-receipt-stdin` 消费回执，禁止把回执放 argv/日志。执行中断、
摘要变化或丢失回执均阻断，不自动重跑、不伪造 backend SUCCEEDED。历史校验仍保留
当时生产证明，但不要求未来生产永远停留在该 revision。

#### Native 收尾后已完成后端事务的固定续接

仅旧 native `e19043ecb269e20f3bc0a546165e43d467f1fc8c` 已关闭、原私密
receipt 完整且身份已撤销时，canonical bootstrap 的 `rotate` 可显式传入
`--finalized-production-sha 5c3eb6ed2c0c7f18f2a36443aee4216f5fe21670`。
它只接受源码固定的 `30ac1c67 → 5c3eb6ed2` 单跳 finalized runtime transaction，
完整原始终态摘要、结构、受保护文件身份都必须一致；不接受任意版本或多跳推断。
发布器必须是该生产提交的直接子提交，仍须当前 main、精确 CI 与独立 G4。

此路径保留 native closure 的 receipt、原 workspace、锁、安装与撤权证明，
另行在原双锁内核验当前生产 root-owned clean revision、原生产 ancestry、
当前生产精确 CI、稳定服务及健康依赖。任何业务 lease、准备事务、reap 残留、
未知进程或读取中漂移均阻断。证据在 intent 前以及归档前后重复验证。

退休 intent 保存完整 finalized 终态与文件身份摘要；后续历史验证依赖该不可变
副本，不要求未来生产继续保留同一终态文件。默认轮换与其他 closure 路径不变。
此证明只允许恢复发布身份，不生成或冒充 backend `SUCCEEDED`；后续正式后端
部署仍须独立通过运行时闸并生成真实成功回执，再发布前端。数据库备份、恢复
演练与站外归档沿用下文用户明确设置的 `DEPLOY_DATABASE_BACKUP` 策略，不在
此恢复入口中覆盖默认值，也不得将跳过记录为通过。
部分 intent 或轮换失败仍禁止清理、自动恢复或重试。

#### 受审 OTA 发布与未知结果恢复

`.github/workflows/trusted-ota.yml` 为生产 iOS OTA 唯一执行入口；本机
`mobile-ota.sh` 与 `mobile-ota-rollback.sh` 固定退出 78，不读取凭据或执行仓库 helper。
先 `target=validate`，再 `target=publish`，绑定同一当前 main 精确绿色 SHA。新的托管
VM 从固定 GitHub canonical source 安装锁定工具链，凭据仅在只读源码/CI 闸后暴露。
信任前提与 backend 相同，不声称防御 GitHub/runner root/供应商控制面失陷。

仅允许相对固定原生 build 的已知 JS/TS/图片变动。实际 production channel、完整
runtime 原生 build cohort 的 fingerprint、远端 production 环境变量都须匹配；
未知路径、缺失 fingerprint、超过有界分页、分流 channel、未受审环境输入即阻断。
只导出一次 iOS 制品，SHA256 绑定实际 bundle 和全部 asset 字节，不凭 CLI 成功判断上线。

服务器在 launcher 与原 build 双锁内验证同 SHA 后端 SUCCEEDED、真实生产健康和 CI，
持久化单次 `ota/<sha>` intent 后领取既有 business lease。只有成功 `claim-ota` 才允许
一次 vendor update。发布前后重验 channel/环境/制品，finish 通过固定 Expo endpoint
的 [protocol 1 multipart manifest](https://docs.expo.dev/technical-specs/expo-updates-1/)
独立核对 update ID、runtime、project、bundle 和 asset hashes。请求禁用可变代理/CA/重定向。

完成前把 lease 原四文件复制并 fsync 到持久审计，再在 `/var/lock` 同文件系统内将原
lease 改名为带 SHA 的退休目录，核对原 inode；不跨文件系统 rename。终态绑定 intent
和 verified receipt 摘要。历史完成证明依赖持久副本，不依赖重启后可能消失的 `/run`。
所有未完成 OTA 阻断后续发布和授权轮换，不能改 SHA 绕过。

失败后不得再次执行 vendor update。仅 canonical `trusted_ota_server.py --action recover`
可在原双锁内接受相同 SHA/group/update receipt，完成未完成的 manifest 验证和锁收尾；
不需要延长过期授权，不会发布或更改原 claim。已验证后网络不可用仍可完成同一收尾。
receipt 不同、租约身份改变、未知部分 claim 或在终态持久化前丢失原 tmpfs 归档均 BLOCK，
保留原现场人工取证。已完成回执重放不释放后来者的 lease。旧版本回滚同样需要新的
受审发布操作，不能借旧本机 rollback 脚本越过上述边界。

首次安装仅属于经授权的发布基础设施配置：管理员以固定系统 Git 从 canonical GitHub
检出已通过独立 G4 和 CI 的 SHA 到 `/var/lib/reva-release/bootstrap/<sha>/source`，
核验干净 revision、root ownership 与受审字节，再以系统 Python `-I` 执行该源码中的
`scripts/bootstrap_trusted_release.py`。禁止上传本机脚本充当 bootstrap。
安装器只接受专用 ed25519 公钥，拒绝覆盖现有安装。用户于 2026-10-01 明确取消
八小时强制到期：`install` 和 `rotate` 的 `--expires-at` 默认 `0`，表示有效至主动
撤销。服务器策略同样以整数 `expires_at=0` 表示无自动到期，SSH 授权不写入
`expiry-time`。仍可显式指定未来 Unix 时间戳；原有正整数期限继续生效，不会因
升级代码自动续期或复活。负数、布尔值、缺失策略字段等无效输入仍拒绝。

后续授权使用同一 bootstrap 的显式 `rotate --retire-sha <old> --sha <new>`，仅从
新 SHA 的上述受审 canonical staging 执行。必须先撤销旧 cloud/loopback 授权并删除
旧 loopback 私钥，证明旧后端成功终止或从未启动、业务 lease 不存在、无发布进程。
轮换持有原 launcher.lock，核验旧源码哈希、私有目录库存和消费记录，原样归档旧安装，
再安装绑定新 SHA 的授权。默认永久模式可沿用**当前** `cloud.pub`，从而无需在每次
发布时更新 GitHub `REVA_RELEASE_SSH_KEY`；显式限时模式继续要求新身份。
已被替换的历史 cloud key、任何历史 loopback key 都不得恢复使用。
复用须在退休 intent 记录 `cloud_key_reused=true`；核查归档时只对完整连续复用链、
当前 canonical 执行器及唯一精确 forced-command/restrict 授权证明通过的 cloud key
允许仍然有效。待退休安装本身仍必须先撤权，历史 loopback 授权必须消失。
旧 SHA、消费标记和锁 inode 不得删除或复用。任何未知现场或
中途失败均保留 intent/安装证据并阻断，不支持通过再次执行重置授权或自动恢复。

loopback 仍限 `127.0.0.1`，每个新版本生成新密钥并在退休前销毁旧私钥。永久模式的
loopback 也不自动到期；不得对外导出。`revoke --sha <current-sha>` 撤销当前 cloud
和 loopback 的精确 SSH 授权，普通 revoke 不自动删除 loopback 私钥，退休前仍须完成
原有私钥销毁检查。密钥泄露时须主动撤销并更换；已经建立的 SSH 会话不因删除
authorized_keys 自动结束，仍须按发布进程与会话检查处置，不能仅凭撤权宣称泄露已收尾。

该调整只免去反复换密钥，不授予云端任意版本或 shell 权限。每次发布仍须由受审
管理员入口完成新 SHA 授权、精确 CI、旧操作终态和锁检查；只更新 GitHub Secret
不等于完成服务器授权。将旧限时安装迁移为永久模式同样走新受审 SHA 的 rotate，
不得原地篡改旧策略/期限；沿用其 cloud 公钥时 GitHub Secret 保持原值即可。

该生产站点已有一份旧格式 `retired/<sha>/{config,executor}` 归档。兼容读取只接受源码
中固定 SHA 和受审 inventory 摘要，逐次校验 canonical executor、撤权、无私钥、从未
启动及原始 bytes/owner/mode/inode；缺失或漂移均 BLOCK。不得移动、重写旧归档，不能
按目录形状接受任意 legacy 状态。其 SHA 与两类公钥继续参与全历史防复用。

云端身份由服务器 forced-command 限定为绑定同一 SHA 的 `run`、`status`、
`check`、`claim-build`、`claim-testflight`，不提供 shell/SFTP；服务器内部的 loopback 身份不离开服务器。
后端业务部署仍由受审 fresh source 中的 **`deploy.sh -b`** 执行全部事务闸。
`DEPLOY_SOURCE_SHA` 仅选择精确来源的 verify-only 模式，不是授权或绕过检查的开关。
候选环境从当前生产 `root:health-app 0640` 配置派生，不改变其凭据和权限合同。

2026-09-24 授权的 Laya 首次接入：仅当现行环境完全没有 `DECISION_*` 赋值时，
受审 publisher 在既有 snapshot/seal 前追加固定 loopback Laya 配置及新生成的
独立 bearer key；不修改已有业务凭据。数据库全站开关默认关闭，只有 active
且 is_admin 的 user_id=3 可修改。有显式配置（包括 off、Jev）时原样保留。
后端旧版本回滚后再次发布可以复用独立 sidecar 的受限凭据文件，安装器仍必须
验证完整回执、版本及服务身份。Laya 使用独立不可变 CPU 环境；重依赖和模型
从精确 candidate bundle 的受审源码准备，在停止 writer 前完成。首次 sidecar
激活须证明精确旧源码没有决策集成，并在旧 backend 健康时完成推理和稳定性验证；
checkout 后只复验、不重启 sidecar。后端回滚保留闲置 sidecar；不扩展现有
backend/worker/beat state transaction，也不更改其 sealed-stage artifact 清单。
未知部分安装、其他 unit、配置漂移或版本升级一律 BLOCK，禁止自动覆盖和删证据。

`check` 在消费前只读验证真实 Git HTTP/1.1 主干可达性、loopback 认证、固定 Python 与
授权窗口；其成功不是部署证明。随后 backend 与 ios-build 并行，构建不自动上传。
`claim-build` 必须位于 ios-build job 内每次 vendor create 前，独立短锁不与正在运行的
backend launcher 锁互斥；单独重跑失败 job 也不能复用旧 claim 再创建构建。
领取前先拒绝空白 Expo token，并用锁定 CLI 在隔离环境中执行只读身份验证；失败不消费
构建标记，输出固定错误码/文案而不输出身份或凭据。Secret 创建成功不证明其值有效。
启动和原生构建 claim 在调用前持久化；未知结果不得重新 dispatch 规避一次性标记。
源码准备先落盘绑定 executor 摘要的 PREPARING 回执，仅运行固定系统 Git，不执行仓库
脚本。Git clone 在同一次授权内最多三次；只有已退出且进程组不再存在的 exit 128
可以重试，部分 checkout 原样留在 clone-attempts。每条 Git 命令有独立超时；超时、
中断或残存子进程均进入 NEEDS_OPERATOR，不因尝试终止进程就宣称已安全结束。
源码准备的已知失败记为 PREPARATION_FAILED，仍不可重跑原 SHA。准备成功写 PREPARED，
首次运行仓库脚本和业务部署之前先持久化 DEPLOYING 意图；意图写入失败不得执行。
显式撤权/轮换只接受完整的准备失败阶段证明、canonical executor 摘要、受限库存及
无业务/构建/上传意图；仍须满足原有 idle、不可变归档、新 SHA/新身份约束。
旧 NEEDS_OPERATOR 没有这些阶段证明，禁止补写回执、仅凭文件缺失放行或新增特定 SHA
白名单；源码修复不能自动解除历史现场的恢复阻塞。

历史首次 clone 失败仅允许独立的 operator `recover-preparation` 处置：从新受审、真实
CI 绿色的 canonical staging 执行 bootstrap，先不传 `--evidence-sha256` 只读取证，
复核摘要后再显式传入同一摘要。此入口按完整旧 executor 实现摘要识别控制流，而非
按 release SHA 放行；要求 canonical/installed/policy 一致、完整四行初始 clone 失败
日志、精确库存及空 HOME。持有原 launcher/build 锁，核验锁 inode、全进程 argv/env/
cwd/exe 与进程身份、无业务 lease，并复用隔离 Git revision proof 核验独立指定的
实际生产 SHA。系统工具仅信任既有 root 受管 OS，不宣称日志是抗 root 篡改的执行证明。
独立 `recoveries/<old-sha>` 中的 intent 必须先 fsync，随后仅精确撤销旧双身份、删除
旧 loopback 私钥；原始 workspace、NEEDS_OPERATOR 回执与消费记录完全不改。后置证明
通过后才写终态，任何未知/不完整操作均阻断，禁止改 ID 或再次调用来续跑。普通 rotate
还要求恢复成功后才返回的随机 256-bit 回执。intent 仅保存其摘要，所有终态 fsync 成功后
才允许将明文交付操作者；回执经受保护 stdin 传入 `rotate --recovery-receipt-stdin`，
不放命令行、日志或用户消息。首次轮换在 mutation 前把已验证回执写入 root-only retirement
审计供后续历史核验。回执丢失或写盘结果未知均不补发、不以可见 completed 文件替代成功。
普通 rotate 只接受完整恢复审计、未变原始证据、已撤权且无私钥的安装；仍须新 SHA/新身份、真实 CI
及原有全部发布闸。此处置不部署、不恢复审核数据、不构建/上传，也不证明线上修复已生效。
为获得新恢复工具的精确 CI，可在固定代码独立 G4 GO 且远端主干 CI 绿色后推送受审代码；
这只发布源码，不解除历史事故、不 dispatch 发布或改变旧授权。实际生产处置仍须上述闸。

已获明确恢复授权的 phase-aware 初始 clone 超时也可使用该两阶段 operator，但必须
命中独立受审的完整 executor 实现摘要，不能按发布 SHA 或任意超时日志放行。仅接受
PREPARING（绑定同一 executor）、STARTED、NEEDS_OPERATOR 的精确回执、两次低速失败
后第三次初始 clone 的完整五行日志、空私有 HOME，以及只含 `.git` 的未 checkout
source；整个保留树须通过所有权、链接、边界和不可变 manifest 校验，不执行其中的
Git、hook 或 Python。任何 prepared、业务/native/build 意图或其他库存均 BLOCK。
这个 backend-only 类型必须证明 build.lock 从未出现，审计以 `build: null` 表示，并在
持原 launcher flock 的每个快照、intent 后、撤权前后及后续轮换复证缺失；禁止补建锁。
legacy 类型仍要求原 build 锁。所有进程、真实生产 revision、授权精确撤销、单次 intent、
终态 fsync 后才交付随机回执的规则不变。原 NEEDS_OPERATOR 永久保留；这只收尾旧权限，
不重跑旧 SHA、不启动业务、不修复用户数据，也不证明下一轮下载已经恢复。
同一两阶段 operator 也覆盖已审计 executor 的“首次 no-checkout clone 在 90 秒边界被
中断、尚未产生 Git 终态错误文本”现场。仅接受单行 clone transcript、空 HOME、仅含
`.git` 的 source、无 build.lock/checkout/业务或部署 intent，并绑定完整保留树 manifest；
新 executor 使用 root-owned 旧生产对象库做只读协商缓存，从固定 GitHub origin 仅获取
main 的浅历史窗口，并用精确旧生产 revision 生成增量 bundle；同时在成功命令返回后等待
整个受控进程组在两秒内退出，超时仍写 NEEDS_OPERATOR。
上传 job 只依赖 ios-build 成功，默认与 backend 部署并行；`claim-testflight` 使用
独立于 launcher 的短 build.lock，锁内核验时间窗、同 SHA 的 build claim 与未撤销的
loopback 授权，再持久化一次性上传权限。后端 READY/STARTED 不要求等待，已知
NEEDS_OPERATOR/PREPARATION_FAILED 则拒绝新的上传 claim。仅提交本轮 job 返回且经 EAS 再次验证的精确 build ID，
要求 source SHA、FINISHED、IOS、STORE、production 全匹配；禁止隐式 latest。
新包必须兼容部署前生产 API，依赖新服务端的能力先做兼容或关闭开关并验证；不能假设
上传后不会被现有 TestFlight 测试组自动获取。不兼容未解决则阻断发布。
若后端在上传开始后失败，保留已有 build/submission ID，发布仍未完成；不得以上传成功
替代后端恢复。无凭据的 release-result job 汇合两端，失败/取消/跳过均返回失败。
Apple 处理和不依赖新后端的同包静态检查可并行；完整验收结论与正式送审必须在两端
最终汇合后给出，不因并行删除备份、恢复或回滚闸。
后端失败后的修复使用新受审 SHA/授权的 backend-only 流程，旧 build ID 作为既有制品保留，
旧 release-result 仍为失败。不得把旧包自动视为新 SHA 的产物或跨 revision 续跑原上传 job；
跨版本组合的送审需另行受审的制品关联与兼容性验收，未具备该证据时保持阻断。
后端 STARTED/NEEDS_OPERATOR 时保留权限和 lease 供调查，不按“锁空闲”推断已终结。
EAS 调用响应丢失时按 source SHA 查询已有构建，记录其 build/submission ID，禁止重复 create。
整条 workflow 和 vendor 任务确认终结后才自动清理本次专用授权、临时环境 secrets 与私钥；
复用并保留既有长期 Expo token，不每轮创建/删除。只移除精确匹配项，保留其他密钥及审计记录。
权限到期/SSH 撤权不证明已启动的 EAS 任务或部署进程终止；准备失败伴随 build/native 意图
仍禁止按 preparation-only 退役，不拓宽既有恢复/轮换边界。

该入口不替代下面的备份、恢复、迁移、运行态、健康和回滚规则，也不提交正式 App Review。

#### checkout 前停服事故的旧服务恢复

`scripts/recover_contained_services.py` 是独立的 operator 恢复入口，不是部署、
回滚或再授权。仅在用户明确授权事故恢复后，从新受审且精确 CI 绿色的 canonical
staging，以固定 `/usr/bin/python3.12 -I -S -B` 执行。必须显式提供恢复代码 SHA、
失败 SHA、旧生产 SHA，原 business lease token 通过受保护 stdin 提供，禁止输出。
首次不传 `--evidence-sha256` 只读取证；独立核验后传入相同摘要才允许恢复。

准入限于 checkout 前 containment：原发布有完整准备与 NEEDS_OPERATOR 证据，
生产代码仍为旧 SHA，live env 同时逐字节等于原 sealed rollback/candidate 且
flag 唯一 false；原 stage/token/锁 inode、旧 runtime terminal、有效 unit、依赖
和所有权全部验证，无新 prepared/arming/reap、无运行中发布后代或激活授权。
入口持有原 launcher/build flock；不修改原 lease、stage pointer 或任何原始回执。

取证及执行两次准入都先完成旧 schema/KB 与依赖只读预检，再持久化独立恢复 intent。
仅原 sealed stage 允许跨 root:root 1777 `/tmp`；原 lease 仅允许固定 root-owned
`/var/lock -> /run/lock` 和 root:root 1777 `/run/lock`，其余路径仍禁止链接或组/全局写入。
持久化 intent 后复证静态证据与隔离状态，之后
只启动固定的 socket/backend/worker/beat。要求有界就绪、跨 RestartSec 的稳定
PID/restart/timestamp/socket 状态、全部 cgroup 进程 flag=false，以及 health/auth、
schema/KB 与原静态证据再验证。成功仅记 `RESTORED_PREVIOUS_SERVICES`，不得把
原发布改为 SUCCEEDED。任何启动或后验失败均停服并验证隔离，保留 intent 和现场；
恢复目录已存在时禁止重跑，也不得换操作 ID。成功仍保留原 lease/keys，后续退休
授权须另行评审，不能据恢复成功重跑原部署、上传或审核维护。

#### 已恢复事故的发布生命周期收尾

用户明确授权后，可从新受审且精确主干 CI 绿色的 canonical staging，以同一隔离
operator 的 `--retire-restored` 模式执行独立收尾；仍须提供 closing/failed/production
三个精确 SHA 和 stdin 原 lease token。默认只读取证，只有二次提供一致的
`--evidence-sha256` 才进入 mutation。此模式不启动服务、不部署、不写审核账号、不
触发厂商构建，也不改变原始 NEEDS_OPERATOR。普通恢复模式仍然不可重跑。

收尾持有原 launcher 锁及已存在的原 build 锁，核验完整恢复 intent/completed、原 lease/stage/终态、
实际旧 revision、恢复后的同一组稳定服务进程、schema/KB、health/auth、准确的双身份
授权与无发布残留进程；任何漂移阻断。仅后端发布可能从未创建 build 锁：必须与原恢复
证明中的 workspace inventory 一致，持有 launcher 锁期间持续复证其缺失，并在收尾及
历史审计中绑定 `build: null`；不得补造锁。原本存在的锁仍须原 inode，出现或消失均阻断。先在
`contained-release-closures/<failed-sha>` fsync 独立 intent，再把原 lease 和 sealed
stage 原字节/模式复制到 root-only 持久目录并复证。仅撤销准确匹配的旧 cloud/loopback
授权、删除旧 loopback 私钥；长期复用的 Expo Token 不在收尾范围内。

旧 lease 仅以同文件系统、禁止覆盖的移动归档到固定
`/run/lock/health-app-release.retired-<failed-sha>`，保留其 inode 和全部文件；不删除
原 stage、原消费记录或 launcher/build 锁。`/run` 归档可能随重启消失，因此后续历史
核验以 mutation 前已 fsync 的持久私有副本及完成摘要为准，不依赖临时目录存活。
持久副本含敏感配置，禁止导出、打印或提交到仓库。

撤权/归档后再次证明安装字节、原失败/恢复记录、锁、健康状态及相同稳定服务，
完成仅记 CLOSED_RESTORED_RELEASE。只有全部完成 fsync 后才返回随机 256-bit 回执，
intent 仅存其摘要。普通 rotate 经 protected stdin 验证该回执、完整收尾审计和未变化
的持久归档，之后才可按既有规则安装新 SHA/新短期发布身份。轮换把回执放入私有审计
供未来历史核验；不得把它放在 argv、日志或用户消息。新发布仍须全部原有闸。
任意中断、未知结果或不完整收尾都保留现场并 BLOCK；不得重跑收尾、换 ID、补发回执
或将可见 completed 文件当作成功授权。收尾失败不擅自停掉已恢复的健康服务。

若后端发布在 checkout、停服和 Laya 安装前失败，服务从原 lease 创建前一直保持旧
revision、零重启且健康，可由新受审、精确 CI 绿色的 canonical staging 使用互斥的
`--retire-unchanged` 模式收尾。该模式不是恢复或部署：live env 必须逐字等于 sealed
rollback，旧 runtime terminal 必须仍为旧 SHA 的 COMMITTED，preparing/reap/activation
状态均不存在；四个 unit 的 activation 和全部 cgroup 进程启动身份必须早于原 lease，
并跨稳定窗口保持不变。候选 env 仍须由 sealed manifest 绑定，但不得安装。

Laya 只接受两种固定 root-only 未安装状态：`sources/<failed-sha>` 空目录，或仅含受审
asset allowlist 与 `source.json` 的完整导出目录。完整导出必须绑定 failed/production SHA、
精确 manifest，且每个文件逐字节等于 failed canonical source；任意多项、缺项或漂移都
BLOCK。`sources/` 中更早的 sibling 只可保留已由完整 retirement history 复核的
CLOSED_UNCHANGED_RELEASE 空目录，其 inode/owner/mode 必须等于原 closure snapshot；
未知 SHA、未关闭 sibling 或新增文件一律 BLOCK。任何账号、组、unit、进程、配置、
generation 或 install receipt 出现仍 BLOCK。入口保留原 NEEDS_OPERATOR、日志、stage
和已验证源目录，以独立 `unchanged-release-closures/<failed-sha>` 记录真实状态，
复用同 inode lease 归档和精确双身份撤权，终态只记 CLOSED_UNCHANGED_RELEASE。只有最终
fsync 后才返回受保护回执供后续 rotate 验证；不得补造 RESTORED 回执或重跑失败 SHA。

已安装 Laya 的只读复用校验失败使用独立的 `--retire-installed-laya`，不改变上述
未安装分支。该模式还要求旧生产、失败候选与收尾源码的全部 Laya 资产相同，
原 INSTALLED 收据绑定可验证的历史 canonical 安装来源，且早于旧生产成功回执和
失败租约；sealed 前后 Laya 配置相同，失败候选导出目录完整匹配。验证实际
unit/覆盖路径/ExecStart/账号、代际模型与锁定依赖、boot ID、cgroup、PID/starttime
和零重启，并证明进程早于租约。鉴权拒绝与真实合成推理须跨稳定窗口通过。

此模式只调用只读安装验证，禁止 prepare/activate、安装、重启或变更业务配置。
快照使用独立 `installed-reuse-v1` profile；归档撤权前后复核全部身份和原 env，
未知、混合、缺字段 profile 拒绝。沿用原同 inode 租约归档与受保护回执协议，
不修改失败终态、不续跑原 SHA。历史验收保存原证明，不要求以后版本维持该 PID。

已安装 Laya 的收尾可证明既有 `security-network.conf` 组合，但不得删除安全依赖
或忽略任意额外 drop-in。三个业务服务必须同时具有固定 Requires/After 依赖，
guard unit 和 helper 字节须与旧生产、失败候选及收尾源码一致；实际 systemd
配置、依赖边、启用状态、无进程的 oneshot 成功终态及早于原租约的 activation
身份全部匹配，稳定读取前后不变。证据写入独立 `network-guard-v1` profile，
撤权归档后重新核验完整 unit 组合；历史读取严格验证 profile，旧无 guard 证明
保持原合同。该证明不运行网络加固命令，不改防火墙，也不冒充实时防火墙规则审计。

已构建但未领取上传权限的混合失败不得套用以上旧模式。针对 `514c8c28a` /
run `37116403140` / build `274`，显式的
`--retire-installed-laya-built-unuploaded --mixed-secrets-stdin` 变体在全部 installed
Laya 原状态证明之外，使用 `scripts/built_unuploaded_proof.py` 读取 GitHub 与 Expo
实时证据：固定 canonical 源码哈希、唯一 attempt、六个 job 均终结、构建成功、后端
失败、上传 claim 失败且上传步骤 skipped，以及精确 EAS ID / 项目 / bundle / SHA /
版本 / iOS STORE production / FINISHED / 非模拟器 / 空 submissions。厂商构建日志
和规范化 job 证据均绑定已核验摘要；缺失、漂移、未知状态一律 BLOCK。

该变体必须持有原 build.lock，原 build-started.json 必须精确匹配，任何 native-started
或 testflight-base 状态拒绝。保护 stdin 仅接受 lease_token、github_token、expo_session
三项 JSON，不接受 argv 凭据；凭据仅用于本次只读取证，禁止打印或持久化。GitHub
签名日志重定向不转发凭据，TLS 使用系统信任库，不采用调用者代理或证书覆盖。
外部证据在 inspect、持久化 intent 后、撤权前及最终复证时重读；历史校验理解严格的
finished-build-unuploaded-v1 profile，不能丢弃或混用。旧终态、所有 claim、锁和 274
制品保留。完成只表示 CLOSED_UNCHANGED_RELEASE；不授权上传，不伪造后端成功。
Laya 资产本身不得在收尾源码中改变。后续使用新绿色 SHA 的 backend-only 发布；
旧 274 与新后端的组合及独立上传仍须专门受审，禁止重跑原 release 或原上传 job。

#### 固定保留制品 274 的独立上传

完成上述原 mixed-release 收尾和授权轮换后，允许使用新受审 publisher 的
`target=retained-testflight`。该目标只运行精确 CI/source preflight 和保留制品
上传，不运行 backend 或 ios-build，不创建新包、不提交 App Review。必须先以
同一新 SHA 完成真实 backend-only 部署；完整 Git object inventory 与 514 比较，
仅允许受审代码显式列出的发布工具、测试及审计文档差异，Mobile/backend/shared
或任意其他路径不同即阻断。不能把 274 改称新 SHA 构建。

`scripts/trusted_retained_testflight.py` 固定原 SHA/run/build/project/bundle/版本
与 ASC app，不接受操作员选择任意制品。干净托管 runner 在暴露凭据前取得两版
canonical source，并安装/校验锁定工具和安全回补；凭据只在 runner 内使用。
实时预上传证明要求原 workflow 精确失败终态、上传步骤 skipped 和精确 FINISHED
制品空 submissions。服务器在原 launcher/build 锁内独立证明原收尾与退休审计、
原 build claim 未变且 native claim 不存在、当前真实后端成功与精确版本健康。

全局 `retained-testflight/<固定 build-id>` 一次性 intent 在副作用前持久化，
业务 lease 从 claim 保持到上传验证完成；旧 514 的记录、锁及制品身份不改。
同一 build 换新 publisher 也不能重新领取权限。runner 仅调用一次固定 ID 的
submit，CLI 成功后仍须独立读取厂商状态：唯一 submission、FINISHED、IOS、
项目/ASC app/submittedBuild 全部精确一致，才允许 finish 重新核验生产并收尾。

finish 先持久化已验证结果和 lease 副本，再 fsync `UPLOADED`，最后将原 lease
同文件系统 no-clobber 归档并复证。释放锁之前已存在完整持久证明，避免中断后
出现业务锁空闲但上传审计未完成的窗口；终态已写但尚未归档时，原业务锁继续
阻断普通部署。只有最后的锁身份检查通过才向调用方返回完成。

终态只记 `UPLOADED`，不代表 Apple processing、测试组可用或 App Review。
未完成/未知 intent 阻断后续发布与授权轮换；禁止清标记、删锁、重跑 workflow
或再次 submit。finish 已验证并持久化的同一结果可按受审 recover 入口完成原
lease 归档与终态写入，不允许用新结果替换原回执。归档保存原 lease 字节和身份，
已完成 finish 的重放不能释放后来者的 lease。原 mixed closure 的空 submissions
只表示当时的历史事实，上传后不修改它，也不重新调用旧 live 未上传证明来伪造历史。

#### 固定 Laya PREPARING 事故的缺失租约行政收尾

`scripts/partial_laya_retirement.py` 是独立的窄化入口，仅处理脚本内固定的 a6b6
失败版本、ba861 已退休历史基线、05b6 旧生产及对应 generation。它不扩宽
`--retire-unchanged`，不重新执行 installer、venv、pip 或其中任何代码。原 business
lease 缺失原因必须记为 `ABSENT_CAUSE_UNKNOWN`，不能重建、补写或当作正常释放。
只有用户明确接受此事故并授权处理，才可提供 `--accept-unknown-lease-loss`；默认仅
只读检查，执行须再次提交完全一致的 `--evidence-sha256`。

新入口只能来自全新受审、精确 CI 绿色的 canonical root staging；持有原 launcher
和已存在的原 build 锁。它独立复核 ba861 完整退休/closure 链，以该历史保存的
live env 字节身份、旧 COMMITTED terminal、有效 units 和全部稳定 PID/starttime 为
未变证明，不接受新生成的当前环境摘要作为基线。任何服务重启、租约出现、未知
writer/事务、Laya 账号/unit/listener/进程或证明缺失均 BLOCK。其安装来源只接受
a6b6 canonical assets、精确 PREPARING receipt 和固定 generation；venv 作为有界、
root-owned 的不可信静态字节记录，固定解释器链接仅记链接目标、不遍历不执行。

一次性 intent fsync 后，同文件系统、no-clobber 移动原 generation 和原 install.json
到各自固定 retired 私有目录，保留 inode 和全部原字节，再精确撤销旧双身份及旧
loopback 私钥。不修改原 NEEDS_OPERATOR、日志、业务数据或服务，不签发新身份。
终态只记 `CLOSED_PARTIAL_LAYA_ORPHANED_LEASE`；最终复证和 fsync 完成后才交付
随机回执。操作 stdout 必须定向到 root-only 私有文件，回执仅经 protected stdin
交给后续 rotate，禁止打印、日志泄露、argv 传递、补发、重跑或换操作 ID。
普通轮换和未来历史核验必须复核该专门终态、原失败记录、静态归档、旧基线链、
原锁与精确撤权；历史证明不依赖将来的 live SHA/PIDs。任意中断均保留现场并 BLOCK。

若且仅若 `CLOSED_UNCHANGED_RELEASE` 的原始明文回执在成功交付后遗失，可走独立的
`acknowledge-lost-closure-receipt` 管理确认；这不是补发或重建原回执，也不修改原 closure。
入口必须来自新的受审、精确主干 CI 绿色 canonical SHA，并持有原 launcher 锁和已有的
build 锁（后端-only 已证明不存在时继续复证缺失）。第一阶段只返回绑定完整 closure、
持久 lease/stage 归档、已撤销双身份、已删除 loopback 私钥、无业务 lease、无发布进程、
稳定生产 revision 和当前 authorized_keys 身份的 `evidence_sha256`。第二阶段必须同时传入
相同摘要与 `--accept-lost-closure-receipt`，在独立
`lost-closure-receipt-acknowledgments/<failed-sha>` 中先 fsync intent、复证全部状态，才写
终态并产生新的随机一次性确认回执。任何原 closure 不完整或漂移、生产 revision 变化、
身份仍授权、活动 lease/进程、历史已退休、重复/部分确认均 BLOCK。新回执只经受保护文件
和 stdin 交给普通 rotate；不得进入 argv、日志、代码库或用户消息。rotate 将该路径记录为
独立 `ACKNOWLEDGED_LOST_CLOSURE_RECEIPT` 状态，仍须新 SHA、新身份和全部既有发布闸。

#### 审核账号维护入口

只有用户明确授权的审核 fixture 恢复，才可由管理员从同样的受审 canonical staging
以系统 Python `-I -S -B` 执行 `scripts/trusted_review_reset.py --sha <sha> --operation-id <32hex>`。
它不是 cloud SSH RPC，不接受账号、密码、命令或路径参数，不用于业务部署。
必须是干净精确源码、真实 CI 绿色、安装执行器/策略同源、授权未过期、后端已成功且
实际生产 revision 一致；固定 loopback、包装命令及派生环境逐字节校验，漂移直接阻断。
复用原 launcher.lock 和 `deploy.sh -R` 的业务 lease，仅访问服务端配置的审核账号。
在 `review-resets/<operation-id>` 持久化绑定 SHA/操作 ID 的意图后才执行，不改密码。
任何中断、未知结果、非法回执或历史未完成操作均保留锁和证据，禁止重复操作 ID，
也不能换 ID 绕过未完成操作。只有精确成功才记为 SUCCEEDED；未结束的审核重置同样
阻止发布身份撤销和轮换。不得直接调用 seeder、修改会话排序或套用管理员 shell 例外。
准备失败或旧 NEEDS_OPERATOR 不满足这个入口的后端成功前置条件。

审核重置不能用 HEAD 相同代替执行内容证明。持有业务 lease 后、读取重置凭据和启动
seeder 前，须从 canonical 源运行隔离生产 revision proof，并按 Git blob inventory
验证 canonical backend 的完整导入与资源树（含 fixture）；ignored 额外文件/目录、
缓存、链接或字节漂移均 BLOCK。实际 seeder 只从该树执行，不遍历 live 私有媒体，
不把 live backend 或调用方 cwd 加入导入路径，不修改媒体目录权限。
operator、lease 内执行和摘要校验均使用固定系统 Python `-I -S -B`，仅在 OS 标准库
路径后显式加入一个经过 root/non-writable/link 校验的依赖目录；不处理 `.pth`。
受管 `.pth` 仅作为不执行的文件保留，editable、导入根及其缓存中的 customize、
外部链接及额外 site 目录仍 BLOCK。依赖包内部同名模块不属于顶层启动入口，仍须
通过完整依赖 metadata 校验，且该包内部目录不得添加到 sys.path。
生产配置通过元数据校验后按 dotenv 数据读取，不执行 shell；缺失
PostgreSQL URL 或固定审核凭据必须失败，不退到默认数据库/账号。应用导入前加载
配置；拒绝 dotenv 解析错误、重复/大小写冲突的键及未解析的目标引用。审核邮箱必须
为字面有效格式，密码仅按 dotenv 数据解析不做变量展开。只从 canonical backend
首次导入纯 `app.config`，在任何 seeder/DB 导入前证明实际 effective_database_url
与已校验 PostgreSQL URL 完全一致，拒绝 `POSTGRES_*` 隐式改目标或预加载 app 模块。
首次写入前及完成后再次核对 lease token 与原 inode。摘要有大小上限，拒绝
重复/额外字段和布尔计数。失败保留现场，不通过现场修权限或删缓存自动重试。
依赖信任限于既有 root 受管安装，不宣称已逐字节证明 wheel 与 lock 一致。

离线订单 SSE 验收辅助：`python scripts/release_acceptance.py analyze < sanitized-events.sse`。
仅输入合成或已脱敏事件，输出不含原文。pending_confirmation 是需要用户确认的草稿；
recorded_receipt 仍要求独立数据库回查，不能凭该脚本通过声称完整 App 或 Apple 验收通过。

#### 明确接受未知审核写入的独立行政收尾

只有用户针对具体失败维护明确接受“审核账号可能已部分写入”的风险，并授权专用收尾时，
才可使用 `scripts/review_maintenance_retirement.py`。泛化的发布授权不等价于此风险接受。
该窄化例外仅适用于后端发布已 SUCCEEDED、实际生产仍是该 SHA、一个明确指定的审核维护
NEEDS_OPERATOR；其他未完成操作仍阻断。不处理失败部署、不恢复数据，不触碰其他用户，
不把旧 UNKNOWN 转换为 SUCCEEDED，也不授权新操作 ID 重新执行原 fixture reset。

实现须经固定提交独立 G4 与精确主干 CI，管理员仅从 canonical 新 SHA staging 使用系统
Python `-I -S -B` 执行，显式传入旧发布 SHA、操作 ID、`--accept-unknown-review-writes`。
原 lease token 只由受保护 stdin 输入；默认只读取证，提供同一 `--evidence-sha256` 后才执行。
持有原 launcher/build 锁，核验完整原回执、源码/安装字节、lease 元数据和当前稳定服务。
`review-maintenance-closures/<old-sha>` 独立 intent 先 fsync，绑定明确风险接受和 UNKNOWN；
原 lease 与操作回执先复制至 root-only 持久归档并 fsync，再精确撤销旧 cloud/loopback 授权、
移除旧 loopback 私钥。长期 Expo Token 不在范围内。

撤权前后均检查完整进程及 SSH 会话；原执行、可继续派生的旧会话或不确定身份均 BLOCK，
不得广泛杀 SSH 或业务进程。随后使用 PostgreSQL REPEATABLE READ READ ONLY，验证实际
只读状态及数据库目标，按服务端配置唯一绑定非管理员审核账号。固定表与子表关联范围内
只读取现状，不调用 seeder、登录或会产生写入的业务读函数；摘要仅包含计数及由 root-only
随机 key 生成的行 HMAC，不暴露账号、健康原文或低熵裸 hash。前后快照漂移阻断；快照相等
也不证明历史无写入或 fixture 正确。

数据核对后把原 lease 同文件系统 no-clobber 移动归档，保留 inode；原操作/发布记录永久
不改。健康、稳定服务身份、旧授权、原始证据及持久归档复证后才写
`CLOSED_UNKNOWN_REVIEW_MAINTENANCE`，最终 fsync 完成才交付随机回执。任何中断或后验
失败保留所有证据，不重跑、不补发回执、不修改原失败状态、不停掉健康服务。
普通 rotate 仍须 protected stdin 回执及完整收尾审计、持久归档、原锁/原源码和精确撤权证明；
历史证明不依赖未来服务 PID、当前生产版本或易失 `/run` 归档。只有已完成退休证明中明确
绑定的那个 UNKNOWN 操作可视为行政已处置。新部署、发包及最终审核仍分别通过全部既有闸。

#### 行政收尾期间临时暂停一个已授权管理密钥

`scripts/admin_key_pause.py` 仅用于用户明确授权的单个管理密钥临时暂停与恢复；不是
部署入口，也不能解除原 closure 的 SSH/proc 闸。只从新受审、精确 CI 绿色的 canonical
staging 以系统 Python `-I -S -B` 执行。首次 `pause` 默认只读取证；匹配摘要后才执行。
目标必须是唯一的普通 ed25519 静态管理公钥，禁止选择当前操作者或任一历史发布身份。

不修改 authorized_keys 或动态授权命令。完整 fsync 的单 key 公钥文件先就绪，再以
no-clobber 原子方式发布固定 RevokedKeys drop-in；绑定实际 sshd PID、启动参数、二进制、
版本、完整支持的 Include 库存和有效配置，除该单项外不允许任何配置变化。仅 reload，
绝不 restart。新 TCP、固定 host key、无私钥/agent 的公钥 offer 要证明目标由允许变为
拒绝、操作者仍允许；超时、关闭或协议错误为 UNKNOWN，不作为拒绝证据，也不宣称登录成功。
固定全局槽位拒绝所有其他未完整 RESTORED 的暂停审计，不能凭 drop-in 消失接受新操作。
对目标连接先持久化冻结意图，通过 pidfd STOP 并核验内核 stopped 状态，再次确认无子进程，
才对该精确父进程 KILL；它在最终检查与终止间不能 fork，不扩大至其他进程或进程组。
冻结异常立即尝试精确 CONT；硬中断后的 restore 从原冻结审计恢复，拒绝向复用 PID 发信号。

暂停前持久化独立 root-only intent；失败保留 RESTORE_PENDING 语义。restore 只能撤销
本次精确 drop-in，重新核验磁盘配置、reload 与新 TCP 正反基线；磁盘文件消失不等于
已恢复。原单 key 公钥文件保留，避免仍持有旧配置的 preauth 进程因文件缺失拒绝所有 key。
恢复使用原审计中的 host key，不依赖后续发布配置目录；不恢复 authorized_keys 备份、
不复活已撤销发布身份、不重跑维护、不补发回执。先完成原 closure，再恢复管理 key，
最后进行新的发布身份轮换。当前 Linux 实测闸在隔离 sshd 上覆盖静态与动态授权来源。

reload 返回不等于新连接已就绪。暂停与恢复使用同一有界只读探测窗口，每次新 TCP
分别证明目标与操作者的完整结果，并把剩余时间传给 SSH 子进程；未知、超时或旧策略
仅允许窗口内重新探测，不重复 reload/撤权/终止，不把未知当拒绝，最终未证明必须失败。
Linux 实测复用生产就绪实现，禁止只在测试外围加重试掩盖生产时序问题。
新受审恢复代码可用 `restore --sha <new-code-sha> --pause-sha <original-audit-sha>`
恢复已有暂停审计，须核验原 canonical 源及原证据；该参数禁止用于 pause，不能换审计
或重放暂停，也不重写旧 intent。恢复成功前所有新暂停仍受全局未完成审计闸阻断。

同一受审 revision 的后续独立暂停可显式指定 `--operation-id <32hex>`，该 ID 同时绑定
审计目录、公钥文件、证据与恢复调用。旧无 ID 审计保持兼容且原样保留；任何旧操作缺少
完整恢复证明时，即使换 ID 仍拒绝新暂停。已有 ID 永不覆盖或重放；新 ID 只用于所有旧
操作已确认 RESTORED 后的新一轮已授权单 key 操作，不处理未知结果或绕过失败维护。
执行 canonical operator 应以 SSH shell 的 `exec` 替换 shell，避免包装命令在严格进程
证明中被判定为未结束的维护执行。收尾返回后另行恢复密钥；不要用保留旧命令正文的
串行 shell 包裹收尾与恢复，更不能削弱进程闸来放行该包装器。

**配置文件: `.env`**

- 位置: 项目根目录
- 管理方式: 本地管理，**不被 git 追踪**
- 用途: 存储线上环境的所有敏感配置

```bash
# .env 结构示例
# -------------------------------------------
# 服务器信息 (deploy.sh 使用)
# -------------------------------------------
DEPLOY_SERVER=root@39.98.206.178
DEPLOY_PATH=/opt/health-app

# -------------------------------------------
# OpenAI 配置
# -------------------------------------------
OPENAI_API_KEY=sk-xxx
OPENAI_BASE_URL=https://api.openai-proxy.com/v1

# -------------------------------------------
# 数据库配置
# -------------------------------------------
DATABASE_URL=postgresql://user:pass@localhost:5432/health_db

# ... 其他配置
```

生产数据库采用双角色：应用 `.env` 中的 `DATABASE_URL` 只使用
`health_app_runtime`；DDL 迁移凭证单独写入服务器
`/etc/health-app/migration.env`（root:root, `0600`）：

```bash
MIGRATION_DATABASE_URL=postgresql://health_app_migrator:***@localhost:5432/health_db
```

`deploy.sh` 只在执行 managed migrations 时加载该文件，随后立即清除变量。文件缺失、迁移
账号带 superuser/BYPASSRLS 等高权限、或迁移与运行账号相同时，生产部署必须失败。

### 8.3 服务器信息

| 环境 | 服务器 | 部署路径 | 备注 |
|------|--------|---------|------|
| 生产 | 39.98.206.178 (阿里云) | /opt/health-app | 主服务器 |

### 8.4 部署流程

```
1. 修改代码 → 2. 本地测试 → 3. git commit → 4. ./deploy.sh → 5. 验证线上
```

**后端部署脚本执行流程:**

1. 检查 `.env`、干净 `main`、`origin/main` 精确 SHA 与发布 lease。
2. 把本次提交的 backup/rollback/schema-probe 工具和生产 systemd runtime
   drop-in 上传到 root-only stage，并逐文件校验 Git blob hash；候选 effective
   unit 还必须通过目标 systemd 版本的 `systemd-analyze verify`。
3. 按用户明确要求，发布默认跳过数据库备份、恢复演练和站外归档。
   只有显式设置 `DEPLOY_DATABASE_BACKUP=1` 才执行以下备份策略；`0` 为跳过，其他值阻断。
   跳过备份仍须准备并校验发布工具、验证回滚 schema 和运行态事务，不跳过健康验收。
   显式启用时，在 Git 工作树外创建数据库备份并完成临时库恢复演练。普通无迁移发布还必须
   证明存在 24 小时内、已完成远端哈希和 HMAC 校验的 age 加密站外归档；证明有效时
   本次不重复上传。证明缺失/过期/远端三件套不完整，或无法证明本次不含 managed
   migration 时，发布前同步补做加密站外归档。任一步失败即停止。夜间任务仍每天执行
   完整本地备份、恢复演练和站外归档验证。
4. 在修改 live env、checkout 或停服前，使用 staged probe 验证“当前生产 SHA 与
   实时 schema 兼容”。只有 stage hash、HEAD、clean tree、完整表/列/零行写探针及
   release token 前后均通过，才记录 rollback point。
5. 同步根目录 `.env` 时先备份到 `/var/backups/health-app/env/`；发布前 env
   （legacy 缺 flag 时只追加唯一规范的 false）与候选 env 一起进入 root-only
   stage，并与 release 工具统一写入 SHA-256 manifest。候选再由去激活事务原子
   安装。live 文件强制为 `root:health-app`、`0640`，外部滚动备份为 `0600`。
6. 先停 backend socket、backend、Celery worker 与 beat 并证明全部 inactive，再
   checkout 精确 SHA。checkout 后只把 repo root、`.git`、tracked paths 及其
   ancestors 规范为 root-owned/non-group-writable；tracked 目录固定 `0755`，
   tracked 文件按 Git mode 固定为 `0644` 或 `0755`，使运行账号可读但不可改；
   不得由 checkout normalization 递归改动 ignored `.env`、venv、uploads 或
   其他 runtime data，随后安装锁定依赖；legacy uploads 只允许由下述持久事务按
   manifest/hash 迁移。
7. 仅临时加载 `/etc/health-app/migration.env`，在 migration runner 紧前重新核验
   release token，再执行 managed migrations 并清除 migration URL；在启动任何
   writer 前，用 runtime role 再跑完整 schema probe，并再次核验 release token。
8. 启动 writer 前，把 legacy uploads 无损合并到
   `/var/lib/health-app/uploads`：old authority 为 legacy 时，事务准入只接受
   external tree 缺失或为空；任何既有非空内容都因无权威来源而 BLOCK，禁止静默
   union 或删除。prepare 后的拷贝断点只接受 external 是 sealed legacy manifest
   的逐路径、同 kind/hash 子集；完整 copy/hash/fsync 证明后才退役 legacy tree。
   每次首次或重入退休前，仍存 source 必须是对应 sealed manifest 的 deletion-only
   子集，且 uid/gid/mode、kind 与文件 hash 未漂移；新增、改写、类型或权限变化都
   保留现场并 BLOCK，绝不自动删除不可信树。
   old-SHA rollback 必须从旧 effective backend+worker `ReadWritePaths` 机器判定
   old upload authority：首次迁移回 legacy 时，把 external tree（含 candidate
   窗口新增与删除）精确复制并校验回 legacy，再退役 external；旧版本已使用
   external 时则保持 external 权威，两个 writer 判定不一致必须 BLOCK。任一终态
   只保留当前 SHA 的 upload authority；root-only in-flight snapshot 随
   terminal cleanup 清除。Skills Hub 可重建 cache 固定为
   `/var/cache/health-app/skills-hub`，生产 install/uninstall 禁止写 tracked
   skills。随后把 Celery Beat shelf 从 checkout 迁到 systemd
   `StateDirectory=/var/lib/health-app/celery-beat`，原子安装 staged drop-in 并
   校验 `FragmentPath`、`DropInPaths` 与 effective `ExecStart`；只允许迁移已知
   shelf 后缀，拒绝
   symlink 或 group/world writable state。重启服务后跨越 `RestartSec` 双采样
   `MainPID`、`NRestarts` 与 activation timestamp，逐 cgroup PID 证明 feature
   flag 终态；socket 的 ready SubState 只接受跨 systemd 版本的
   `listening|running`，且 record/compare 必须逐字不变，其他状态或窗口内切换都
   fail closed。随后再验证 exact SHA、health/auth、脱敏后的健康硬闸与
   runtime-only KB serving contract。只有新 state 已存在且服务稳定后，才精确
   清理 legacy shelf。
   `ExecStart` 比较只允许忽略 systemd 同一命令记录里的运行态
   `start_time/stop_time/pid/code/status`，必须严格保留并比较静态
   `path/argv[]/ignore_errors`。旧 journal 与实时输出只接受单条、固定字段顺序的
   systemd raw 记录或内部三字段 canonical 记录；未知字段、多命令、缺失字段或
   静态漂移一律 BLOCK。candidate 的 backend、worker、beat 三个 unit 都必须经过
   同一严格解析并与精确预期命令比较，不能只从 beat 命令抽取 schedule。
9. 远端 SSH/信号结果不明确时保留 release lease 与 stage；没有独立 terminal
   证明时禁止并发 rollback 或第二次部署。恢复必须显式提供原 token 并接管 lock
   记录的原 stage；接管只校验、复用 immutable artifacts，禁止重传覆盖。正常
   发布/恢复工具绝不改写 `lock/stage`。deploy staging 与 rollback shell 负责验证
   stage root、sealed manifest、精确 allowlist/hash，额外文件（包括可 shadow
   Python stdlib 的模块）一律 BLOCK；rollback shell 还必须在任何停服或 checkout
   前验证 lock/token/stage pointer 的 root metadata、单链接与精确字节。runtime
   helper 的每个命令独立验证 root-only lock/token、exact stage pointer，并在相关
   命令验证 candidate files；helper 使用 isolated Python mode。若原 stage 的 runner
   自身有缺陷而不能安全恢复，保持全部服务 inactive、保留现场并上报 BLOCK；本规范
   不授权临时 rebind，也不得用文档步骤替代一个另行评审、测试并落库的 recovery
   workflow。持久事务 journal 位于
   `/var/lib/health-app/release-state`，记录 old/candidate SHA、boot gate、快照
   与不可逆 candidate floor。journal 必须在任何 restore mutation 前完成
   old-effective、metadata、snapshot tree/record、upload authority 与 enablement
   的完整结构/类型/权限校验及 `ExecStart` canonicalization，进入 `PREPARED` 时
   持久化 canonical 静态值。
10. health-evidence activation 在第一次 systemd/D-Bus RPC 前原子、fsync 写入
    root-only `launch-intent`。断线接管先只读验证原 14-entry sealed stage 与
    state/outcome：已终结只做 exact proof；只有 state dir 为空（durable negative
    proof）才可复用原 candidate/guard 启动；intent 存在但 outcome 缺失时保留
    stage/lease，禁止并发重启。revision proof 不读取部署仓库的 local/global
    Git config，也不复制 live index。它在 root-only 临时 Git dir 中以 expected
    SHA 执行 `read-tree` 重建 proof index，再用显式 worktree 做 clean/untracked
    检查；repo metadata、非 symlink tracked paths 与 ancestors 必须 root-owned
    且不可 group/world 写。filter/fsmonitor/hooks 与 live-index semantic flags
    被隔离，不能影响 proof；ownership 或 clean-tree 异常在 mutation 前
    fail closed。
11. System KB import 与 skills manifest 完成后，必须再次跨完整稳定窗口证明
    backend/Celery 的 PID、restart count、flag=false、exact revision、health 与
    staged KB contract；全部通过后才 `finalize` 并删除持久回滚快照。old 分支
    rollback 同时恢复旧 code、drop-in、runtime state、发布前 env，并按第 8 项恢复
    机器判定的 old upload authority；candidate floor 分支保持候选 env 原字节不变。
    live `backend/.env` 的终态必须为 `root:health-app`、`0640`。回滚不能沿用
    root-only stage snapshot 的 `0600` 元数据，因为应用在降权为 `health-app`
    后仍由 Settings 读取该文件；权限不满足时必须保持服务 inactive 并让回滚失败，
    禁止把启动失败误报成恢复成功。目标 `.env` 在写入前后都必须是 non-symlink
    regular file，rename 使用 exact-target `mv -fT`；文件 fsync、rename、父目录
    fsync 任一步失败都不能启动服务或输出成功哨兵。

### 8.5 环境变量同步

当仅修改配置而不需要更新代码时:

```bash
# 编辑本地 .env
vim .env

# 同步到服务器并重启
./deploy.sh -e
```

同步前 `deploy.sh` 会自动备份服务器当前 `backend/.env` 到 Git 工作树外，并保留最近 20 份。长期密钥管理策略见 `docs/ops/secrets-management.md`。

### 8.6 注意事项

- ❌ **禁止** 直接在服务器上修改 `.env` 文件 (会被下次部署覆盖)
- ❌ **禁止** 将 `.env` 提交到 git
- ✅ **必须** 通过 `deploy.sh` 进行所有部署操作
- ✅ **必须** 在本地维护 `.env` 的备份

---

#### braces 递归深度修复

`braces@3.0.3` 的 `GHSA-vfj7-8cjw-p6xm` 使用项目本地修复，保留真实版本和原始
HIGH 公告，不作为上游已发布修复版或风险豁免。解析器限制总括号/花括号嵌套为 100，
compile、expand、stringify 对直接 AST 输入也限制递归深度（含 root/leaf 开销）。
超限抛出明确 SyntaxError；调用方仍需正常处理无效输入，不承诺未捕获异常自动恢复。

`frontend/scripts/braces-depth-guard.cjs --root <安装根>` 只验证；显式 `--apply`
检查所有安装副本的固定原始/修复后字节、完整可执行文件清单和包身份后才应用。
任何未知版本、缺失/漂移文件或链接均失败。每次验证执行真实恶意/正常模式和 AST
调用；OSV 只将该精确公告、版本、安装路径标为 `verified_mitigation`，保留其他阻断。
Mobile 使用固定 patch-package 补丁；Frontend 普通安装及 build 命令执行自包含验证器，
确保只复制 frontend 的隔离重建仍覆盖修复。Trusted Release/OTA 的 ignore-scripts
安装在凭据前显式修复 mobile/release-tools 两个根。上游发布后重新评审替换本地修复。

### Retained candidate 的失败发布闭合

`retained_candidate_retirement.py` 处理一种独立终态：backend-only 发布原回执为
`NEEDS_OPERATOR`，rollback 已保留 candidate，runtime terminal 已是该 candidate 的
`COMMITTED / finalized / target=candidate`，transaction/reap、business lease 和发布进程均已退出。
此入口不修复服务、不再次 finalize、不重写失败回执，也不把失败发布标成成功。
若上述条件不成立，必须先诊断真实运行态，不能用闭合绕过。

操作来自新 main 精确绿色 SHA 的 canonical root-owned checkout，使用系统
`python3.12 -I -S -B`。关闭前按既有 revoke 流程撤销旧双身份并移除旧 loopback 私钥；
闭合只接受原 installation 的撤权证据，不提供 credential 清理捷径。入口参数为
`--sha <reviewed-closing-sha> --failed-sha <failed-candidate-sha>`；第一次只读 inspect
返回 evidence digest。确认后第二次加 `--evidence-sha256 <digest>`，固定原 launcher lock
并重新检查：完整失败 workspace 的原始字节/元数据、原 canonical executor 与各阶段回执、
生产 clean revision、runtime terminal、服务进程及 runtime flag、schema、runtime-only KB、
health 依赖与未认证 auth 拒绝。任何变化均阻断。

独立 root-only `retained-candidate-closures/<failed-sha>/` 先持久化 `intent.json`，
再次验证后才写 `completed.json` 并签发随机 receipt。成功终态仅为
`CLOSED_RETAINED_CANDIDATE_FAILURE`。receipt 输出必须直接接入受保护回执文件或既有保密
传输通道，禁止进入终端日志、用户消息或命令行。若 intent 已存在、完成写失败或回执遗失，
不允许重试、删目录或重建回执；保留现场另行审核。

后续 bootstrap rotate 通过既有 protected recovery-receipt 通道消费这个独立终态，
不会允许旧 SHA 再次发布。历史核验继续校验原 workspace、installation 归档、原锁与闭合
审计，但只验证审计内的 runtime/service/probe 快照，不要求未来生产仍运行旧 candidate。
当前首次 rotate 仍须核验实时生产没有漂移。该回执不代表 OTA、TestFlight、业务验收或新发布完成。
