# 部署规范 🚀

> 从 `AGENTS.md §8` 拆出（2026-05-31, Agent Operating Harness Phase 2,见 [`docs/design-agent-operating-harness.md`](../design-agent-operating-harness.md)）。`AGENTS.md` 现在只留章节导航,本文件是本章权威全文 —— 硬规范裁判权不变。


### 8.1 部署方式

#### 默认完成部署与 OTA（用户持续授权，2026-10-13）

用户要求“后续改完默认部署和 ota”。后续代码修改的交付范围默认包含验证、提交、推送、生产部署、适用的 Mobile OTA 及发布后检查，无需再次询问部署或 OTA 许可；不得仅停在本地修复、提交或准备阶段。用户明确要求仅分析、暂不发布或限制范围时遵循当次要求；仅文档/规则修改不触发无关制品发布。

持续授权不替代精确主干 SHA 的完整 CI、安全审查、发布锁、回执和线上健康检查。OTA 仍须遵守原生兼容边界，同一绿色 SHA 先部署后端，再经 trusted-ota validate/publish。原生不兼容、CI 失败或发布状态未知时，修复可处理的阻断，继续其他已满足条件的工作，明确报告部署与 OTA 各自状态；不得绕过门禁、重复领取不明状态的发布操作，或把 validate 当成 publish。需要原生包时按原生发布规则与已有授权处理，不把 OTA 授权扩大为新的商店公开发布授权。

#### 后续不执行备份（用户要求，2026-10-13）

用户明确要求：“后续不要备份，取消备份的操作，写入到要求里边”。此要求持续适用于后续部署、发布及其授权准备，优先于本文件下方旧的自动备份、回退副本和历史备份全量核验条款。

- 不新增数据库备份、配置/env 备份、旧代码/前端制品备份或运行态回退快照；不得将同一操作改称“归档”或“快照”继续执行。
- 不执行随发布触发的备份恢复演练、备份站外归档，或为了普通发布例行遍历、读取、哈希历史备份正文。自动备份任务也不得作为替代手段新建备份；已有任务是否停用须以真实配置检查为证，不能仅据此文档宣称已停用。
- 旧备份保留，不自动删除。只有用户明确要求恢复时，才核验所需的目标备份；不扩展为扫描全部历史。重新开启备份需用户新的明确指令，`DEPLOY_DATABASE_BACKUP=1` 或其他旧配置本身不构成授权。
- 发布锁、精确 SHA/CI、权限与来源校验、回执、审计、迁移兼容性和线上健康验证继续执行；这些小型状态证明与当前候选制品校验不属于备份。
- 不再依赖新备份承诺自动回退。现有发布器若仍将备份/回退副本作为前置契约，先同步修改生产者、消费者与测试，再执行后续发布；禁止仅跳过原检查后伪装成功。

当前无备份发布路径为代码更新：`deploy.sh -b` 保持现行 env 不变，仅核验摘要、权限与固定配置；旧 `DEPLOY_DATABASE_BACKUP=1` 不能重新授权备份。运行时 `preflight-code/prepare-code` 使用 v2 小型事务日志，不复制上传文件、知识库、beat 状态或 drop-in；只允许已迁移布局和相同候选 drop-in。配置、模型/schema、managed 迁移或运行态布局变化在停写前拒绝，env-only 与 Health Evidence 激活入口暂不支持该路径。旧前端发布/重建及 stopped-recovery 的新切换操作已冻结：deploy入口和直接module执行均在产生意图、领取锁或生成previous-*前拒绝；旧回执读取与独立恢复/终态核对消费者继续保留。

本次每日 GPS 行程有一个精确限定的无备份新增表例外，由 `scripts/daily_journey_release.py` 随同 `deploy.sh -b` 执行，不是通用迁移放行：只允许固定摘要的 `20261018_120000_daily_journeys` PostgreSQL/SQLite 文件、新模型从不存在变为受审字节，以及 `models/__init__.py` 的唯一 import 插入；所有其他模型、迁移或 drop-in 差异仍在停写前拒绝。精确 current-main CI、canonical bootstrap、原发布租约、旧版本 schema 兼容检查和候选启动前完整 schema 检查保持不变。迁移仅创建三个新表和索引，保留旧表及账户删除 CASCADE 语义；不恢复旧代码、不复制数据。

该例外只从 root 保护的 canonical 候选加载 helper。helper 直接读取固定 `/etc/health-app/migration.env` 的唯一字面 `MIGRATION_DATABASE_URL`；不将凭据放入参数、日志、发布父环境或 stage，不接受调用者环境注入。预检要求 PostgreSQL TCP 连接实际地址/端口与库名一致（不扩大权限读取 Unix socket 私有配置）、不同且无 superuser/BYPASSRLS/建库/建角色权限的运行与迁移角色，拒绝运行角色继承迁移角色或拥有 schema CREATE。已有 managed ledger 必须存在，除本迁移外不得有 pending/checksum 漂移；目标表必须全部不存在。文件缺失、不安全权限或角色权限不足均保留阻断。

停写和精确候选 checkout 后，在 `/var/lib/reva-release/daily-journey-migrations/<candidate-sha>/` 先落盘并 fsync 小型 intent（旧/新 SHA、迁移摘要、租约及数据库身份摘要）。三个表、索引、只给实际 runtime role 的 CRUD grants、managed ledger 和表 COMMENT 中的小型 schema/binding 证明在一个 PostgreSQL 事务中提交，并使用事务 advisory lock。禁止额外角色或 PUBLIC 读取位置表，禁止 runtime 的 TRUNCATE/TRIGGER/REFERENCES 权限。提交后回读目录证明、FK/check/index 元数据和实际 CRUD 权限才写 `completed.json`；之后原发布流程用 runtime role 验证候选完整 schema 再启动服务。

中断后同一 intent 只可回读：ledger 与 schema/binding 完全匹配才能确认已提交并补齐完成回执；ledger 仍 pending、表不完整、intent 缺失或身份漂移均 NEEDS_OPERATOR，绝不自动重放 DDL、清除意图、领取新操作或改用通用 migration runner。该入口不创建或检查任何备份。合入与本地 PostgreSQL 测试仅证明实现；生产角色/固定凭据就绪及精确候选发布回执必须另行验证。

备考作答新增表使用第二个封闭 profile `scripts/exam_attempts_release.py`。它只允许固定摘要的 `20261028_120000_life_exam_attempts` 成对迁移、新 `exam_practice.py` 模型和唯一模型 import；不能与每日行程 profile 混合扩大 schema 差异。沿用 canonical 源、原租约、固定迁移凭据、停写前预检和候选完整 schema 检查。新表 `life_exam_attempts` 对 runtime role 只授予 SELECT/INSERT，序列只授予 USAGE；账号删除通过外键 CASCADE 清理。运行角色不能更新或删除作答流水。新 intent 和完成回执位于 `/var/lib/reva-release/exam-attempts-migrations/<candidate-sha>/`，同时证明序列身份、表约束、owner 索引、权限与绑定；未知提交状态只回读，不重放 DDL。其 PostgreSQL 迁移及应用并发语义必须分别通过 CI，不能用 SQLite 代替。

新的 Web 发布使用显式 `deploy.sh --publish-frontend-no-backup`，旧 `--publish-frontend`、重建和 stopped-recovery 切换入口仍冻结。新入口只能消费由 `--prepare-frontend-artifact` 完成的同 operation-id 制品，不能在停服后编译。候选须为精确完整 CI 绿色的 current main，先通过独立安全审查并以既有 canonical bootstrap 安装该候选的历史消费者；入口核验当前授权 SHA、有效期与实际 installed server 摘要。后端可保持原已部署且有 SUCCEEDED 回执的 revision，不制造后端发布回执，也不重复发布没有 Mobile 变化的 OTA。

在 `/var/lib/reva-release/bootstrap/<publisher-sha>/source` 使用系统 Python 的固定 deploy 入口，传入 `--publisher-sha`、`--production-sha`、`--frontend-tree`、`--operation-id`；先只读预检，确认返回的证据后再加 `--evidence-sha256` 执行。原 launcher/build 锁和 business lease 继续互斥。停服前完成候选校验，核验固定 live 目录、父/根 inode、同设备且无嵌套挂载；确认 systemd control-group 已停空后删除旧 `.next` / `node_modules`，移入已验证的新制品并同步两个父目录，不保留旧制品副本。全部制品摘要一致才启动，公共/本地页面与后端保持证据均通过后才写终态并释放租约。删除、移动、fsync、启动或回读异常均保留原租约与 NEEDS_OPERATOR，不自动回滚、重试或换 operation-id。

Web 制品发布保留生产跟踪配置，默认拒绝 `public` 与 `next.config.*` 差异。 Edu 统一登录新增第二个固定、单向的配置摘要对，只接受既有 KBase 配置到受审 Edu 确认页 CSP 与固定 API rewrite 的完整字节变更；不接受任意来源或其它配置变化。新发布须同时验证内外网 `/connect/edu` 的唯一 CSP、精确 Edu form-action、strict-origin、no-store 和 referrer metadata；历史固定 finalizer 保持原页面契约。既有受审例外为 `trusted_frontend_publish.py` 固定内容摘要对绑定的 KBase `headers()` 默认来源变更；不接受任意配置改动或逆向摘要对。生产 Next 从候选 `routes-manifest.json` 读取响应头，发布后同时核验内网与公网 `/connect/kbase` 的唯一 CSP、精确 form-action、strict-origin 和 no-store，并核验 `/login` 仍仅允许 self。源 staging 必须包含保留的后端 revision 对象用于差异核验；缺失时只从 canonical GitHub 获取精确对象，不能跳过对比。发布器代码变化须重新绑定候选及制品，不能修改旧 READY 回执复用。

新发布回执以 `publication_policy=no-backup-v1` 绑定全部阶段，`backups_digest={}`；历史消费者复核完整 phase/proof 及原 prepared artifact 的 intent/ready/claim、构建日志和 manifest 摘要，不访问已移动的 stage。新旧历史进入同一 catalog/seal 链；旧历史检查不放宽，新格式拒绝 previous-*、recovery 附件、未知 policy 与部分终态。显式要求验证新格式的备份恢复集会拒绝，不能将空集称作可恢复。后续 seal/rotate 沿既有 canonical 路径更新。

`scripts/frontend_no_backup_finalization.py --finalizer-sha <current-main>` 仅收尾代码中固定绑定的已安装 no-backup Web 发布。该次 `/login` 为 CSR，初始 HTML 没有登录文案导致验收误判；新验收保留 200、固定 URL、有界 HTML 和 CSP 检查。入口先只读预检，再以返回的 `--evidence-sha256` 执行；只接受新精确绿色主干 canonical 源码，验证原安装授权、原制品/claim、后端配置快照、稳定进程、内外网页面和原租约。原 operation 的全部文件保持原 inode/内容，`failed.json` 不改写；新 sibling `frontend-publication-finalizations/<operation>` 写 intent/verified/completed，小审计闭合后历史消费者才承认安装已验收。收尾不重建、不切换、不重启、不建备份；任一步中断保持阻断，不自动重试。它先在旧授权仍安装时收尾，随后新 canonical bootstrap 才能 seal/rotate 安装新消费者，避免租约与授权循环。

前端 finalizer 的普通历史、pending、inspect 和 finalize 路径仅核对备份根目录与审计，记录 `integrity=not_checked`；旧完整摘要只验证其结构和终态绑定，不重读正文或冒充新鲜完整性证明。只有明确请求恢复某一操作时，才显式选择该操作验证正文。

中途失败保留原锁、事务和回执，状态为 NEEDS_OPERATOR；不再承诺通过新副本自动恢复。已有旧事务在普通无备份入口被拒绝，不读取旧 snapshot 正文、不删除旧备份。普通授权准入核验历史签名/终态/身份元数据，明确 `backup_integrity=not_checked`，不表示旧副本已经验证可恢复；用户另行请求恢复时才限定确切操作核验。

授权轮换 `no-backup-v1` 留存身份和来源摘要审计，受控替换已撤销的当前安装，不复制旧配置或发布器。旧归档保留；部分轮换失败保留 intent 并阻断，不自动重发。2026-10-13 已读回确认生产 Health 数据库备份与备份验证两项 root cron 停用，其他任务保留。代码合入不等于新发布器已在生产安装；部署回执必须单独提供。

#### 复用候选的完整 CI

`main` 的非纯文档 push 首次即运行完整 CI；PR 和本地预检保留按变更范围执行，
纯文档 push 保留轻量验证。发布前查询并等待目标精确 SHA 已有的 CI，不能例行
再触发一轮 `workflow_dispatch`。手动完整 CI 只用于明确的恢复或补验证需求
（例如历史候选或纯文档候选尚无所需完整验证）。不得通过取消同 SHA 的运行中
或失败记录制造绿色；全部适用运行仍按现有 trusted release gate 裁决。

#### 本次发布的真实模型评测豁免

默认仍要求高风险 LLM 变更具备真实评测证据。只有用户明确取消当前发布的
真实评测时，维护者才可将仓库变量 `HARNESS_LIVE_LLM_EVAL_WAIVED_SHA` 设置为
当前发布的完整小写 SHA。CI 将它与目标 SHA 精确比较，返回 `status=waived`、
`confirmed=false` 和固定豁免原因。不得设置 CONFIRMED 冒充评测通过。

没有目标、布尔值、短 SHA、旧 SHA、变更检测错误均不放行。豁免不作用于下一
提交，也不取消离线安全测试、独立安全审查、精确 CI、失败发布收口或 OTA 回执
校验。用户决定及候选绑定写入当前 Dossier；发布后清除该临时仓库变量。

#### 生产凭据之前的 runner 线路预检

`trusted-release.yml` 在精确源码/CI preflight 后运行固定 TCP/SSH 标识预检，再进入
含生产凭据的 job。显式 `target=transport` 仅执行 preflight，不执行授权轮换、部署、
原生构建或上传。`trusted_runner_transport.py` 固定连接 `39.98.206.178:22`，建连和
读取共用五秒预算，不读凭据、不发送认证数据、不领取 claim。成功只证明该 runner
当时可读取 endpoint 的 SSH 标识，不证明鉴权、主机身份或服务就绪。

真实发布仍须后续 strict host key、只读 readiness、执行前精确 CI 和一次性 claim；
不得用 transport 回执代替这些闸。预检失败不会自动重发已消费的发布或 OTA。此入口
可在昂贵的授权轮换前发现线路阻断，但网络可达不代表授权或发布已经完成。

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

#### 保留 Runtime 隔离的发布准入

代码发布不要求先恢复 Runtime 或进行应用管理员登录。部署健康检查显式使用
`--allow-paused-runtime`；普通健康检查仍将暂停报告为不健康，不改变原评分语义。
仅 `paused/reconciliation_detected`、有效非负 generation/ack 且存在未确认代际、
reconciliation 事件总数与 generation 一致时，发布报告可将这项移入
`deferred_failures`。保留 `healthy=false`，额外的 `release_safe=true` 只表示现有
隔离可保持，不表示未决写入已解决或 Runtime 已恢复。

部署端再次验证精确的暂停原因、代际关系、唯一延后项及明确安全声明，并打印
恢复延后警告。未知原因、事件账本不一致、数据库或会话关闭异常、其他健康失败
仍阻断。部署不 ack、不 resume、不结算 UNKNOWN、不新增写入授权。
Runtime 原有受影响账号隔离和未受影响账号的准入策略均不改变。

#### 分段计时与 Pi runtime

`deploy.sh` 的脱敏计时写入 stderr，保留原 stdout 回执和失败退出码。本地与远程
shell 分别计时，覆盖源码、依赖、迁移、schema、服务与收尾边界。Pi 安装另有
`remote_pi_install_started` / `remote_pi_install_completed`；失败不输出 completed。
Python 锁文件未变时的依赖复用不证明 Pi runtime 可用，Pi 安装仍执行。计时不能
替代健康或终态证明；尚未实现 Pi 缓存及跨 runner 工具镜像，需实测再裁决。

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

#### 独立 Neo 微信桥的首次休眠安装

canonical `deploy.sh --neo-wechat --publisher-sha <current-main-sha>
--production-sha <deployed-sha> --operation-id <32hex>` 默认只读检查；二次提供
相同 `--evidence-sha256` 才安装隔离账号、锁定运行时和 inactive/static unit。
要求当前 main 精确完整 CI、独立 G4、外部先验验证的 root-owned canonical
staging、原 launcher flock/business lease，以及已通过既有 bootstrap 安装的
同字节新版 executor。入口不修改发布身份、Health 服务或共享凭据。

唯一成功终态为 `INSTALLED_DORMANT`；不启用服务、不发布 nginx 路由、不生成
配置/秘密、不扫码、不授权、不发 Slack。用户密钥输入与后续激活另过受审流程。
持久 intent/verified/completed 绑定同一源码与操作；未知或部分失败保留原审计与
lease，且经既有历史检查链阻断发布/轮换，重启丢失临时锁也不能绕过。禁止换
operation ID 重试、删锁、自动回滚或手动复制文件完成安装。前置可信执行与恢复
边界、未合并 PR252 的冲突和人工接力见 [微信桥部署说明](../ops/neo-wechat-deployment.md)。

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
若候选 SHA 本身已有 SUCCEEDED 后端回执，续发在原 launcher 锁和业务 lease 内
逐次核验实际线上 SHA 必须与候选完全相同，以及原有 CI、服务和健康证明。
此分支保留后端生命周期，复用原一次性 build/native claim，不创建 testflight-base.json，
不重部署或改写后端回执。STARTED、失败终态、线上 SHA 不同或已消费 claim 仍拒绝。
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

TestFlight 280 的固定 profile 为 `c28050786c1e9aa70cca33d7e3d5c093652aeb26`，
GitHub run `40158185108` attempt 1、build `1faa3a05-2385-44fd-bf84-296cc68e84c2`、
submission `0491eb1a-3f04-4488-8996-91f65e5b2932`。完整 job 集含明确 skipped 的
`retained-testflight` 和 `backend`，其他 job 必须成功；job 身份、源码、完整 jobs
与上传日志摘要均固定绑定。不得据此承认任意新 job 或原生 SHA，也不改变旧 profile。
用户已确认该发布由其另一处启动并在完成后交接本会话；收尾仍保留撤权、私钥销毁、
进程互斥、只读 inspect→摘要绑定 execute 和原消费记录不变的全部前置。

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

`validate` 在无凭据预检与精确 CI 闸后使用既有 Expo 凭据，调用 `--prepare`：
检查原生 baseline/cohort、channel 和 production 环境，实际导出并核验 iOS 制品，
再复验源码、CI、channel、环境及制品，停在 claim 前。它不领取 claim、不调用服务器
RPC 或 vendor update，也不注入 SSH 私钥。`--admission` 保留为不导出制品的廉价
只读诊断入口，不替代 workflow validate。`PREPARATION_PASSED` 不表示后端已部署、
授权可消费或 OTA 已发布。publish 在自己的新 runner 再次导出一次并完成全部原闸，
不会把前一 runner 的准备结果当作发布许可或共享可信缓存。通过预检后的准入/发布失败
只归档固定字段的闭集 phase/reason 诊断，禁止上传原始供应商输出、异常和凭据。

仅允许相对固定原生 build 的已知 JS/TS/图片变动。实际 production channel、完整
runtime 原生 build cohort 的 fingerprint、远端 production 环境变量都须匹配；
未知路径、缺失 fingerprint、超过有界分页、分流 channel、未受审环境输入即阻断。
2026-10-14 固定等价例外：runtime 1.3.5 的 production iOS STORE cohort 仅允许已取证的
276/277 两个具体 build ID、source SHA 与 fingerprint 组合。实际 EAS 指纹来源中除
`eas.json` 和方向插件外逐项一致；两版插件在已观察到的 `supportsTablet=false`
配置执行结果一致。源码闸仅允许已审文件的精确 SHA256，禁止新的原生差异、未知构建、
iPad/其他原生开关及非 production 环境。证据见
[`固定原生等价证据`](../reviews/2026-10-14-ota-native-equivalence.json)。此为源码/配置等价审定，
不宣称 IPA 二进制逐字一致；候选仍须独立安全审查、完整 CI、实时 cohort 和远端环境复验。

2026-10-21 新基线迁移：当前发布契约绑定 runtime 1.3.6、已完成的 production iOS STORE
279（`399eb452-402e-47cd-a0e3-18dff2d1ca51`），原生源码
`1ba724dcb62ac389a72e41eecf40fea7aaca27e3`。旧 276/277 等价例外仅作历史证据，
不迁移到新契约；新 runtime 下任何额外构建、来源或指纹变化继续阻断。
唯一源码例外为已审计的 package-lock 精确摘要，差异仅为 follow-redirects 与
launch-editor 的 Node/开发工具更新；不允许任意 lockfile 或原生依赖变化。
证据见 [`1.3.6 基线`](../reviews/2026-10-21-ota-runtime136-baseline.json)。
此次迁移不解除 279 的送审 OTA 冻结，不代表已发布。正式操作仍须实时核对完整 cohort、
同 SHA 完整 CI、后端部署与 trusted validate/publish；旧 runtime1.3.5 不接收1.3.6更新。

2026-10-26 工具补丁等价更新：最老宿主仍固定为 279，同时精确纳入 production
STORE 280（`1faa3a05-2385-44fd-bf84-296cc68e84c2`、源码 `c28050786c1e9aa70cca33d7e3d5c093652aeb26`）。
官方 EAS 的两份 fingerprint 各 287 项，仅 patches 目录不同；该差异为 Expo CLI MCP、
Zod v3 的 JS 补丁及说明，其余 286 项完全一致。准入只接受受审 package/lock、两项补丁、
README 与兼容测试脚本的精确字节，覆盖此前单 lockfile 例外；第三个构建、未知来源、
指纹或文件漂移仍拒绝。见 [工具等价证据](../reviews/2026-10-26-ota-runtime136-tooling-equivalence.json)。
用户已明确解除送审前冻结；这不豁免精确 CI、后端回执、实时 cohort 与制品校验，
也不把模拟器启动当作两个 Store 包的真机验证。

2026-10-29 守护图标基线迁移：源码准入基线更新为已完成、已签名且 Apple 处理状态
`VALID` 的 production iOS STORE 283（`ea1dda2a-86b3-4e46-adf8-b2b024465154`，源码
`ae7a5972921ee9d51eec2c90c7893e6941d2d7ff`，fingerprint
`0f13707a06be8ea69d9a8f083e4c38edfa08cbe4`）。runtime 1.3.6 的实时闭集仍须同时精确包含
279–283 五个已审 build；缺少旧宿主、出现额外 build、来源或指纹漂移均阻断。283 已在
TestFlight 内部组可用，含已确认的下开口守护图标与聊天 UI 原生资产；这不证明真机安装，
也不替代每次 trusted validate/publish 的实时 cohort、制品、环境、精确 CI 与后端回执复验。
证据见 [283 守护图标基线](../reviews/2026-10-29-ota-runtime136-guardian-baseline.json)。

2026-10-29 后台定位隐私修复基线迁移：production iOS STORE 286
（`cc90f439-f400-4059-9a60-c1b400ff298a`，源码
`e6f26f6230e429a29113e4322ff5d7be22764787`，fingerprint
`0a16db1dc4ea8c10bb95a43481e64c7605fc2d4a`）已完成、签名、Apple 处理状态
`VALID` 且在 TestFlight 内部组可用。该宿主移除了未交付的 production 后台定位
能力和 always-location 描述，同时保留 build 283 的守护图标。runtime 1.3.6 的实时
闭集精确扩展为 279–286；284–286 的原生指纹一致，但仍逐个绑定 build ID、源码和
指纹，缺失旧宿主、出现额外 build 或任一字段漂移均阻断。当前 App Review 状态与 OTA
准入相互独立；基线迁移不提交、回复或更改审核。证据见
[286 后台定位隐私修复基线](../reviews/2026-10-29-ota-runtime136-build286-baseline.json)。

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

OTA 的网络 CI 准入必须在写入 intent 与领取 business lease 之前完成；同一进程、
原双锁内仅允许短时单用的精确 SHA 证明，取得租约后仍完整核验本地生产源码、
成功回执、服务健康与租约身份。相同生产 SHA 不重复查询已刚刚验证的 CI；
不同生产 SHA 的原生续发仍须独立核验。额度不足在消费前拒绝，不跳过 CI。

已遗留的未完成 claim 不适用普通 recover。专用 canonical
`trusted_ota_unclaimed_retirement.py` 仅处理受审的未发布失败形态：原 workflow
精确 SHA/run/attempt 的终态、官方审计制品摘要、固定 publisher 控制流及原
intent/lease 必须相互一致，证明该流程未进入 vendor publish。任何 claimed、
vendor 回执、未知文件、活跃发布进程或租约身份变化均拒绝。关闭保留原失败
证据，先落小型审计意图，再按原租约身份收尾，最后写独立失败终态；不创建
配置/代码/应用制品备份，不伪造 OTA SUCCEEDED，不允许原 SHA 再次发布。
未完成关闭仍阻断后续操作，新的授权轮换只有在历史消费者验证关闭证据后
才可继续；新候选仍须自己的完整 CI、后端部署与 OTA validate/publish。

`151f26b0dd6c1c976e6d26cd6e21ab247a6fdb90` 与 `f2022e10027bcf35c4225bf1cc898a9001161ecc` 的领取前失败，使用该入口的固定 `--failed-sha` profile 绑定官方失败运行和审计制品；默认历史 profile 保持不变。选择仅限源码内受审的精确 SHA，不接受调用方提供制品摘要或替换流程阶段。历史消费者按原操作目录选择独立 profile，禁止跨 profile 复用证据。已验证的固定演示维护收尾仍保留 UNKNOWN，OTA 预检只在完整退休历史验证成功后接受其固定版本和操作绑定，不将其标记为演示数据成功。

`c29d2a60f3fa8e49b87c183af3d7cfba72b9dfaf` 的新增固定 profile 只接受
run `40281092624`、attempt `1`、job `121434341485` 和官方 artifact `12633145149`
（2532 bytes）的领取前失败；ZIP、原控制流与三项审计 JSON 的摘要固定在源码内。
必须以新的精确绿色 reviewed SHA 执行收尾，原 c29d 的后端成功状态、原 intent/lease
与未进入 vendor 的证据仍须逐项通过；不修改历史 profile，不复用 c29d 重发。
本入口先严格读取有界私有 stdin JSON 的唯一 `github_token` 字段，再核验 canonical
root 源码；同一凭据经 `trusted_release_gate.py --token-stdin --target full` 的 stdin
传给精确 CI 闸，并用于官方审计制品读取。凭据不进入 argv/env/输出，空、非法或
读取失败立即阻断，不回退到过期的服务器凭据或环境变量；root、源码、原双锁和
领取前失败证明不豁免。inspect 返回的证据摘要仍是执行收尾的必需绑定。

`a4d922886c859f4a2a43d4322fd43d128bf934f3` 的固定 profile 仅接受 run
`40735832856`、attempt `1`、job `122983994390` 和官方 artifact `12835953802`
（2565 bytes）。审计包只有 `claim-ota` 的 `command_failed` 诊断、原 intent 与
preflight；不存在 vendor receipt，原 publisher 控制流在 RPC 返回前不会调用供应商。
收尾仍须由新的精确绿色 reviewed SHA 执行，并重新验证原 intent/lease、双锁、生产
后端终态和健康状态。它只关闭未发布失败，不把 a4d 标为 OTA 成功，也不允许重发 a4d。
新收尾证据同时绑定 lease 文件的 device、inode、内容摘要与 `ctime_ns`，因此 Linux
即使在删除重建时复用 inode，也会因变更时间漂移而阻断。历史四个已关闭 profile
继续兼容其原先没有 `ctime_ns` 的持久记录，但同一份 lease 快照的四个文件必须全部
使用旧 schema 或全部使用含 `ctime_ns` 的新 schema，禁止部分降级或混用；a4d 的新记录
必须在全部文件中包含该字段。

`1c30cfa94a689f5b99f6c638a27c622a87a35d35` 的固定 profile 仅接受 run
`40851087780`、attempt `1`、job `123370445233` 和官方 artifact `12887890387`
（2568 bytes）。官方 ZIP 精确包含 intent、preflight 和 `claim-ota` 的
`command_failed` 诊断；服务器现场同样只有 `intent.json` 与 `lease.json`，没有
`claimed.json`、vendor receipt 或完成回执。收口仍须由后续精确绿色 reviewed SHA
执行，重新验证原 intent/lease、双锁、生产后端终态和健康状态，并为全部 lease 文件
绑定 device、inode、内容摘要和 `ctime_ns`。该终态只证明 1c30 未发布并关闭其原租约；
不允许重发 1c30，也不把它记为 OTA 成功。新的 OTA 候选必须重新通过自己的完整 CI、
后端部署及 trusted validate/publish。

`53f9c6aee3eb30d8937a4582e206cce47de80157` 的 run `40861067214` 在
`claim-ota` RPC 处失败；服务器尚未创建 `ota/<sha>` intent，publisher 也未进入
vendor update。同期 no-backup Web 流程随后完成，但现有持久证据不足以把该流程或其
lease 认定为失败原因，因此收口只记录“领取前失败”，不写入未经证明的因果。
专用 `trusted_ota_preintent_retirement.py` 仅接受该 run 的 attempt `1`、job
`123404134816`、artifact `12890544500`（2566 bytes）及固定 publisher 源码摘要，
并要求同期操作 `dbbb6a5caeb94991ab079a39b7a1275d` 已以
`FRONTEND_SUCCEEDED` 完整收口、business lease 已释放、53f 后端终态和线上健康均
保持一致。执行收口前必须先把精确绿色 closing SHA 的授权策略和 canonical
`trusted_release_server.py` 安装为当前 consumer；operator 在 launcher/build 双锁内
对 closing SHA、策略、执行器源码与已安装字节做前后两次一致性验证。禁止用旧 53f
consumer 写 closure 后再轮换，因为释放双锁到安装新 consumer 之间会留下重发窗口。
它只在 `ota-preintent-failure-closures/53f…` 写一次审计终态，不创建 OTA
intent、不释放或改名任何 lease、不调用 Expo；历史消费者永久拒绝 53f 再次 claim。
任何已出现的 `ota/53f…`、vendor receipt、活动 lease、前端收据漂移或非固定官方
制品均阻断。固定 artifact entry 摘要按 ZIP 内原始字节核验，JSON 解析只承担结构与
语义检查，禁止用 canonical JSON 摘要替代原始证据。后续候选仍须独立通过完整 CI、
后端部署及 trusted validate/publish。

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
当前身份对应已成功完成的后端发布时，撤权与轮换必须由同一个 canonical `rotate`
进程持原 launcher/build 双锁执行，并显式传入该成功工作区 `completed.json` 的固定
SHA256。发布器先持久化 `successful-auth-revocations/<old>/intent.json`，重复核验成功
工作区、固定回执、授权文件、执行器、双锁和 loopback 公私钥，再撤权、销毁原私钥并
写完成证明；随后才进入普通 retirement intent。该成功关闭记录由所有后续轮换重读，
缺少完成证明、与 canonical retirement 不匹配或目标 SHA 漂移都必须阻断，禁止改用
另一候选或重放来绕过部分关闭。
已完成的历史成功撤权审计允许四种精确旧格式只读兼容：回执/工作区摘要格式，以及
携带 backend、OTA 或 credential 审计字段的完整工作区格式。读取必须重新核验成功
工作区、canonical 旧执行器和匹配的完整退休记录；有原后端回执摘要时校验原始字节。
历史授权文件、OTA 和 credential 摘要仅是审计元数据，不代表当前凭据或发布授权。
兼容不改写旧记录，不恢复身份，仍执行完整安装证据及旧公私钥撤销检查；未知、混合、
部分或不匹配的记录继续阻断。
轮换持有原 launcher.lock，核验旧源码哈希、私有目录库存和消费记录，原样归档旧安装，
再安装绑定新 SHA 的授权。默认永久模式可沿用**当前** `cloud.pub`，从而无需在每次
发布时更新 GitHub `REVA_RELEASE_SSH_KEY`；显式限时模式继续要求新身份。
已被替换的历史 cloud key、任何历史 loopback key 都不得恢复使用。
复用须在退休 intent 记录 `cloud_key_reused=true`；核查归档时只对完整连续复用链、
当前 canonical 执行器及唯一精确 forced-command/restrict 授权证明通过的 cloud key
允许仍然有效。待退休安装本身仍必须先撤权，历史 loopback 授权必须消失。
历史 Web 备份可使用受保护的 `frontend-history-seal` 封存索引。首次封存必须完整
校验全部历史正文与原回执；无索引时继续旧全量路径。索引绑定 live publication
及其唯一活动回滚集合，使用独立 root 私密密钥、用途隔离 HMAC、代次链和 anchor。
日常仍全量核验所有小审计、日志摘要、顶层库存、消费/撤权和未完成操作；仅已封存且
审计一致的 archived 备份跳过内部遍历和正文哈希。live 与活动回滚制品仍须完整核验。
新未知或部分操作、证据消失、签名失效和未完成索引更新均 BLOCK，不自动删锁、
删索引或降级放行。物理历史备份不会因此被删除。旧备份恢复或晋升回滚前必须重新
全量校验原摘要，封存不证明 archived blob 当前仍完整。

独立 canonical bootstrap 的 `seal-frontend-history --sha <reviewed-sha>` 可在轮换前
首次封存；`--inspect` 只读检查原部分 checkpoint；`--checkpoint-sha256 <original-digest>`
仅完成原更新。三者仍要求精确 CI、原锁、授权策略、无业务租约/发布进程和 OTA 历史
闭合，seal/finish 还核验 live 绑定和活动回滚内容。更新持原锁、原子写入并 fsync；
中断不生成新授权、不消费业务 claim，不重跑发布。密钥与全部 state 被 root 同时
回退不在此签名保护的威胁覆盖内，不能宣称外部防回滚。

同一次持锁轮换仍可对确需全量核验的备份共享进程内 memo：首轮完整哈希且匹配
原回执，次轮验证权限、链接和前后库存指纹，仅完全未变时复用摘要；纳秒 ctime
变化也使其失效。不落盘、不跨命令，不用于 live。实现和收尾边界详见
[授权校验 I/O](../ops/release-authorization-io.md)。新版索引必须从受审且精确 CI
绿色的 canonical revision 启用，源码实现或本地测试不证明生产迁移完成。

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

原子发布成功但没有 legacy `deployment.env` 时，旧 reset 不可重试或手工补文件。
专用 `scripts/trusted_review_maintenance.py --operator-sha <current-main> --target-sha <deployed-sha> --operation-id <32hex>`
区分当前维护工具与固定生产版本。仅用户明确批准审核演示重置后可用，须独立安全审查和完整 CI。
两者从 canonical staging 加载；当前工具要求精确 main 全绿，目标要求历史完整 CI 稳定成功、
生产 SUCCEEDED/runtime COMMITTED、原 installed policy 和执行器匹配。全 scripts/ 与 deploy.sh
执行闭包字节和权限相同，仅新维护入口及其测试例外；不执行 operator 的业务代码。
在原 launcher 锁内先完成目标证明，再以独占 0600 创建派生环境，前后核对生产配置身份及摘要。
独立 `/var/lib/reva-release/review-maintenance/<target-sha>` 意图绑定两个 SHA、原配置身份、CI 及 operation ID；
已存在配置或准备意图均拒绝重试，不覆盖、不备份、不轮换。准备后再次通过原 workspace 校验，
由固定 target 的 `deploy.sh -R` 和原 lease 内 seeder 执行；原 reset 回执格式保持不变。
先写原 reset 意图，再准备环境；专用审计成功后才写原 reset 成功。部分失败保留 NEEDS_OPERATOR 或不完整意图，由既有历史消费者阻断，需独立调查，不以新 ID 重发。
此入口不授予 backend/OTA 发布权限，不放宽普通 reset、release gate 或轮换规则。
可选 `--token-stdin` 仅消费既有只读 GitHub App 的短期令牌；复用有界解析，所有 CI 请求显式绑定同一内存令牌，错误不回退，不写服务器凭据或传给 deploy.sh。未指定则使用原凭据读取边界。


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

#### 无原 lease 的审核维护：仅登记已接受 UNKNOWN

针对已明确授权的失败审核维护，可通过独立 `review_maintenance_acknowledgement.py`
登记 `UNKNOWN_ACCEPTED_AUDIT_ONLY`。此入口不沿用上节需要原 lease 的退休流程。
执行仍要求受审固定代码、精确主干 CI、canonical staging、原 launcher/build 锁、
实际生产与源码证明、持续无 lease、执行进程静止、两组原始失败回执稳定。
只对服务端配置唯一绑定的非管理员审核演示账号进行 PostgreSQL 只读计数和随机密钥
HMAC 核对；相同快照不证明历史未写入，也不证明演示样例正确。

默认仅检视；执行绑定检视摘要、明确风险接受与具体原操作。新增独立一次性审计意图和
结果，原件原地保留，不复制配置或数据作备份，不改原 NEEDS_OPERATOR，不创建替代
lease，不撤权、不轮换、不重新执行 reset。失败保留证据，禁止重放。
结果必须包含 `reset_authorized=false` 与 `release_unblocked=false`；现有 reset、
rotation 与发布历史消费者不得将它当作退休或成功凭据。该记录仅完成用户授权的
行政确认，演示数据修复、发布和送审仍由各自 Gate 裁定。

#### 279 审核简报的独立窄化修复

用户已确认既有 loopback 5030 隧道用于 chatlog 并要求保留。仅专用审核
acknowledgement 保留历史固定会话证明，并允许验证正常重连：仍绑定同一固定公钥，
当前 boot、PID、启动时刻与该进程生命周期内唯一的 root 认证事件；要求无 TTY、
无子进程且唯一的 5030 监听归属该进程并仅绑定 loopback。一次完整观察前后必须
保持进程库存、身份、socket 和认证事件一致；观察期间重连、额外 SSH 或未知身份
仍阻断。此证明仅适用于专用 acknowledgement，不授权重试失败操作。通用发布检查
不变，不终止连接、不修改密钥或网络配置。

`review_demo_briefing_repair.py` 与 `trusted_review_briefing_repair.py` 仅服务固定
279 审核演示简报。要求同一受审 operator 的 UNKNOWN 审计确认先完成，再使用独立
明确授权、新鲜 inspect 摘要和独立一次性 intent。仅向固定生产审核账号新增一条
`app-store-review-demo-279` 会话及两条已固定字节摘要的演示消息；旧会话、消息和
健康记录保持不变。目标 session key 已存在即拒绝，不重用、不删除、不复制旧数据。
PostgreSQL SERIALIZABLE 事务、账号及既有行锁、快照比对、提交后只读核验必须通过。
任何提交结果或回执不确定均保留 intent，禁止重试；不得把原维护标为成功或解除
普通 reset、轮换及部署阻断。最终送审继续使用原始 live-demo 和实际 IPA 检查。

#### 279 简报 intent-only 的专用审计收尾

`review_briefing_unstarted_closure.py` 仅处理受审 `1e676eaa` 操作者留下的固定
简报 intent。默认只读，执行需要明确的本次收尾授权和新鲜摘要。必须验证固定原件、
完整目录仅含 intent、原 canonical 源码中数据库连接前持久化 marker 的顺序、
原失败维护及 reconciliation 证据、无执行进程、原双锁及当前生产条件。
任何 marker、完成回执、身份变化或无法证明的条件均拒绝。

成功仅在独立 sibling 目录记录 `CANONICAL_WRITE_NOT_ENTERED`；它依赖 root 管理的
审计证据未被外部删除或回退的信任边界，仅说明这一次 canonical 写路径未进入，
不证明所有数据库内容没有变化。原 repair 目录与原 UNKNOWN 状态保持不变，
reset、retry、release、rotation 和 new_attempt 权限全部为 false。

如需继续修复，必须另行明确授权固定的新 attempt，使用当前受审精确 CI 候选、
新鲜 inspect 摘要、独立目录及绑定该 attempt 的父子证明。不得重跑旧 apply、
复制旧 parent proof、覆盖旧记录或仅凭审计收尾放行 advance。advance 必须验证
旧 intent、专用审计收尾和新 attempt 的真实成功回执完整链。失败均保留证据，
没有自动重试或自动解除发布阻断。

#### 行政收尾期间临时暂停一个已授权管理密钥

固定 `49a742fa` 的 `after-1e676eaa-intent-only-v1` 后继尝试可使用
`review_briefing_unstarted_closure.py --successor-audit` 作独立审计收尾。
它只接受固定 intent 摘要、原 canonical 源码字节及已完成的前序闭合链，
要求目录仅含 intent、双锁、无执行进程和生产条件保持稳定。结果另存
`review-demo-briefing-successor-closures`，原件不改。该结果仍是
`CANONICAL_WRITE_NOT_ENTERED`，不证明所有历史数据未写，所有操作权限均为 false；
不被现有部署、轮换或简报修复消费者视为成功。用户的“审计收尾”授权仅覆盖
此审计写入，不重试失败 apply、不调用数据库、不调查或修改 chatlog。
可经 `--token-stdin` 使用现有仓库只读凭据核验精确 CI，凭据不写入配置或回执。

#### 固定审核维护与后端发布解耦

`bootstrap_trusted_release.py close-review-maintenance-for-release` 通过独立
`review_maintenance_release_closure.py` 处理固定 `1ba724dc` 的已接受 UNKNOWN
维护，不要求为了部署再次写入审核演示数据。必须显式传入
`--accept-unknown-review-writes` 与 `--accept-fixed-maintenance-advance-without-demo`，
绑定当前受审精确绿色主干、canonical 源、原双锁、新鲜检视摘要、健康生产条件与
完整固定历史链。历史各自使用原 operator 验证，不能改称当前候选的回执。

该链仅证明两次固定简报 canonical 路径未进入数据库，不能证明原 reset 未写入，
也不声称数据库无活动事务。原 UNKNOWN、intent 和所有失败记录原地保留。
新协议不调用数据库、不重试 reset、不修复演示数据、不触碰 chatlog。
普通 reset、普通 advance 与 App Store 演示账号验收要求保持不变。

新 intent 必须先于精确撤销旧 managed 授权行及旧 loopback 私钥；成功后独立记录
`FIXED_MAINTENANCE_RETIRED_WITH_ACCEPTED_UNKNOWN`，其中 `demo_verified=false`、
`reset_authorized=false`、`retry_authorized=false`。失败保留现场且禁止重放。
仅 `rotate --review-maintenance-release-closure-receipt-stdin` 可消费与同一候选绑定的
受保护一次性回执。此入口 stdin 为有界、严格字段的 JSON（`receipt`、`github_token`），
令牌限本仓库只读 App 短期凭据，仅在内存中用于现有精确 CI 校验，不写配置、argv 或回执。
禁止与其他收尾或宽化 CI 权限混用；退休记录使用独立字段
`review_maintenance_release_closure`，历史消费者复核静态原件链，不将旧服务 PID
与未来生产 PID 比较。执行前后仍必须核对实际生产状态。新终态不等于部署成功，
后续部署、OTA 及提审各自完成验证与回执。

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
3. 以下为旧实现说明，受“后续不执行备份”要求覆盖，不得据此重新开启备份。发布默认跳过数据库备份、恢复演练和站外归档。
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
5. 旧实现（须按“后续不执行备份”适配）：同步根目录 `.env` 时先备份到 `/var/backups/health-app/env/`；发布前 env
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

旧实现会在同步前自动备份服务器当前 `backend/.env`，并保留最近 20 份；这不是后续执行许可，须按“后续不执行备份”适配入口。长期密钥管理策略见 `docs/ops/secrets-management.md`。

### 8.6 注意事项

- ❌ **禁止** 直接在服务器上修改 `.env` 文件 (会被下次部署覆盖)
- ❌ **禁止** 将 `.env` 提交到 git
- ✅ **必须** 通过 `deploy.sh` 进行所有部署操作
- 按用户“后续不执行备份”要求，不自动维护本地 `.env` 备份；禁止将 `.env` 或历史备份提交到 Git。

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
若上述条件不成立，必须先诊断真实运行态，不能用闭合绕过。操作前还必须独立读取原 GitHub
发布 run 的最新状态、核对 SHA/workflow/run attempt 并确认已终态，留存脱敏回执。此次原
失败 run 为 `37933398517`、candidate 为 `e3210b1161f76944733b6522e0ff21695858614c`；
closure 本身不调用 GitHub 写接口，也不把本机 launcher 无进程视为远端 workflow 已终止。

操作来自新 main 精确绿色 SHA 的 canonical root-owned checkout，使用系统
`python3.12 -I -S -B`。闭合前保留旧双身份和 loopback 私钥；通用 revoke 对 `NEEDS_OPERATOR` 的拒绝不变。
独立闭合先核验原 installation 和精确双授权，持久化 intent 并重复完整证明后，才精确撤销
这两条授权、删除已绑定的旧 loopback 私钥，重新核验 installation 与运行态后写 completion。入口参数为
`--sha <reviewed-closing-sha> --failed-sha <failed-candidate-sha>`；第一次只读 inspect
返回 evidence digest。确认后第二次加 `--evidence-sha256 <digest>`，固定原 launcher lock
并重新检查：完整失败 workspace 的原始字节/元数据、原 canonical executor 与各阶段回执、
生产 clean revision、runtime terminal、服务进程及 runtime flag、schema、runtime-only KB、
health 依赖与未认证 auth 拒绝。candidate-effective 检查复用现有 unit proof，核验
FragmentPath、全部 DropInPaths、ExecStart、ReadWritePaths、安全配置、enablement 与 network guard；
Laya 检查绑定 candidate 的导出源码/manifest、原安装回执及 immutable generation，并复用
`verify_install` 验证隔离账户、服务身份、未授权拒绝和 synthetic inference。上述探针均只读，
不创建 lease、不 activate、不 finalize。任何变化均阻断。

独立 root-only `retained-candidate-closures/<failed-sha>/` 先持久化 `intent.json`，
再次验证后才写 `completed.json` 并签发随机 receipt。成功终态仅为
`CLOSED_RETAINED_CANDIDATE_FAILURE`。receipt 输出必须直接接入受保护回执文件或既有保密
传输通道，禁止进入终端日志、用户消息或命令行。若 intent 已存在、完成写失败或回执遗失，
不允许重试、删目录或重建回执；保留现场另行审核。

后续 bootstrap rotate 通过既有 protected recovery-receipt 通道消费这个独立终态，
不会允许旧 SHA 再次发布。历史核验继续校验原 workspace、installation 归档、原锁与闭合
审计，但只验证审计内的 runtime/service/probe 快照，不要求未来生产仍运行旧 candidate。
当前首次 rotate 仍须核验实时生产没有漂移。该回执不代表 OTA、TestFlight、业务验收或新发布完成。


retained candidate 的已治理 Vision overlay 通过独立证明处理：核验原 model-selection
的 before/intent/verified/completed 操作绑定、摘要、canonical publisher 与原 production
成功回执；model.env 与三个 drop-in 必须是现有 operator 的精确只读字节。真实服务四个
DropInPaths 必须恰为已知基础三项加唯一末位 model overlay，EnvironmentFiles 顺序、
UnsetEnvironment、进程身份与实际 model 均由现有 vision validator 检查。
只有这个已验证 overlay 可在私有基础 unit 证明视图中剥离，其他属性一律透传；原始四路径、
model 文件、进程及历史摘要独立归档，前后变化阻断。历史验证不读取未来 live model/PID。
CLI 失败仅输出固定 stage、白名单异常类和禁止自动重试状态，不输出异常原文、回溯或 argv。

retained rollback 的 KB 状态使用独立 `ROLLBACK_QUARANTINED` 契约：
`rollback_release.sh` 在 candidate-retained 分支也先归档 runtime-only pack，
随后才 commit/finalize runtime 文件事务。因此该终态不意味着 KB 已重新导入或
处于 staged active 状态。retirement 不复用 staged 的 active-pack 前置，不在
staged 失败后 fallback，也不通过恢复 KB 或修改数据库绕过验证。
固定隔离子进程保留 canonical/revision/venv/schema 验证，另证明 sealed 全集
完整、类型与 reviewed 元数据正确、全部 archived、sealed claim artifact 一致、
generic/runtime serving 均为零。原 rollback 审计必须与完整候选 SHA 对应的不可变
workspace 部署开始/完成时间窗一致；短 SHA actor 只是其中一项约束，不能单独授权。
审计 target/matched 必须等于精确全集，archived 允许 0（幂等隔离）到全集数量。
保留原 Desktop/Genetic 正反 projection、PostgreSQL 事务 advisory lock 与
`_TransactionPreservingProbeSession`：探针包含 savepoint 内合成记录与 schema
空 UPDATE，保证回滚、无持久业务写入，并非零 SQL 写操作。独立归档仅保存摘要、
计数、审计身份和时间窗；首次 rotate 重验当前状态，历史轮转只验证归档。
定向 PostgreSQL 验证入口为 `RETAINED_TEST_DATABASE_URL`（库名须含 test），
使用测试专属 schema，不能用 SQLite 或 mock 代替 JSONB、时间窗、锁和回滚证明。

retirement 服务快照归档区分 socket 与 service：systemd 的 socket 无
`MainPID` / `NRestarts` 属性，固定读取器返回空串，归档只接受这两个字段的精确
空串；数字 `0`、任意文本、缺字段或 null 均不代替缺省属性。service 仍要求
数字 MainPID/NRestarts、有效启动时间和绑定的进程身份。socket 仍须 active、
listening/running、Result=success 且启动时间为正数；该适配不改变实时服务验证。


### a8 exam 迁移失败的固定前向恢复

`scripts/exam_release_recovery.py` 仅接受
`a8cd1e7635eb697c0f0bc528382c98b3602893c3` 在 checkout 后、固定 exam 迁移事务回滚、
runtime v2 `INSTALLED` 且所有 writer/socket inactive 的已知事故。原发布仍为
`NEEDS_OPERATOR`，旧迁移仅有 intent，表、序列及账目必须明确未提交；未知结果或
已提交不授予重放权限。此入口不是普通 deploy、rollback 或 lease 重置。

从新 main 精确绿色 SHA 的 canonical root-owned source 运行，独立 G4 绑定同一 SHA。
默认只读 inspect 返回 evidence digest；另行明确授权固定新尝试
`exam-a8-forward-acl-v1` 后，才可传 digest 与同名 accept 开关执行。launcher lock、
原 business lease/stage、原 workspace、迁移 intent、runtime journal、配置和身份
须前后核验。任何既存新尝试一律拒绝自动续跑，保留新旧审计等待独立处置。

唯一 DDL 是原 canonical a8 的固定 exam SQL。只收紧新建表/序列的 runtime ACL，
保留全局默认权限；PUBLIC、额外角色、列级或继承的越权继续拒绝。数据库事务回执、
完整 schema、依赖、Pi、Laya、KB、health/auth 及跨 RestartSec 稳定证据通过后，
才沿原 runtime state machine commit/finalize。KB 完整检查包括保存点内合成 DML
与回滚，须在授权后执行；默认 inspect 不执行该 DML，也不能声称完整 KB 检查通过。
失败尝试停止服务并记录 containment 是否已证明，不恢复旧配置、不建备份。

armed runtime gate 临时禁用原先 enabled 的业务 service 时，systemd 会移除其
`Before=multi-user.target` 隐式关系。恢复器只在原 journal/禁用态均已证明、实际
Before 恰为 `shutdown.target` 时向原验证器呈现原始关系；未知、重复或提前恢复的
关系继续阻断。网络 guard 本身、Requires/After 和 finalize 后的关系不作转换。

独立完成记录仅为 `FORWARD_RECOVERED`，生产源码仍是 a8；不代表通知修复、OTA 或
App Store 送审完成。原失败回执、原迁移 intent、lease、stage 与发布身份均保留。
新恢复和凭据续期审计目录一旦存在，bootstrap/server 的持久历史闸拒绝普通发布与
轮转，包括 completed、未知文件、断链及重启丢失临时 lease 的情况。仅下述独立受审的
完整 closure 链可解除阻断，不能删除目录或手工解绑 stage 绕过此闸。

同事故的 `scripts/exam_recovery_credential.py` 使用独立固定尝试
`exam-a8-read-credential-v1`，仅在原证据、双锁与摘要匹配时续期仓库只读 GitHub App
凭据。新 token 只经有界 stdin 进入内存，先通过现有 canonical/TLS 精确完整 CI 闸，
再 CAS 原子替换已绑定的凭据；不授予部署权限、不改业务 lease、身份、数据库或服务。
inspect 不 mint token、不写文件，亦不声称线上 CI 已核验；凭据结果未知时禁止重试。

已完成的 `52d2dbc619e58ce75dadf79877192ee424771afa` 固定续期不可重跑。后续恢复候选
仅可通过 `exam_provider_reconciliation.credential_binding_sha` 消费其两份精确原始
回执摘要、原 G4、凭据文件摘要及到期时间；旧回执保持原 SHA，不改写为新候选。
原事故快照仅允许 G4 摘要更新，其他字段及 JSON 类型必须完全相同。新候选独立通过
当前 main 完整 CI 与 G4；执行恢复时仍检查当前凭据文件。closure/history 复用同一
纯历史验证函数和安全读取所得原始摘要，不依赖以后会轮换或过期的当前凭据。
配置加载只在读取 Settings 时临时进入 backend，成功或异常均恢复工作目录，避免
第二次原始源码证明将 backend 相对路径误当仓库根路径；原证明代码不得绕过。

统一恢复入口还须先拒绝替代恢复的任何持久痕迹：固定 a8 的 exam-service-recovery、
exam-attempts-migrations/recovery、exam-recovery-lease-retirement、retained-candidate-closures、
retired 与旧安装归档路径，以及 provider refresh 下任意 exam-* 和 credential.exam-*
临时文件。文件、目录、断链、异常父目录和检查中新增记录一律阻断；不读取令牌内容，
不把外部 completed 解释为授权。该只读检查在 inspect、双锁及每个既有变更边界重复；
出现痕迹后须独立对账及重新受审，不能删除记录、忽略记录或沿用失效的旧凭据摘要。

固定外部 `exam-3127c8678bec90e57cc05f359e629f072e0d133f` 凭据更新已独立核对完成，
专用 `exam_provider_reconciliation.py` 只消费其精确原始摘要、字段及文件身份；核对原
lease/workspace 与 canonical 旧实现摘要，不执行旧实现、不推断历史签发或 CI 成功。
新凭据操作仍使用独立未消费 attempt，绑定新旧摘要并在 CAS 前实时验证完整 CI。
恢复与凭据入口同时持有原 launcher、存在时的原 build lock 和 provider refresh lock。
其他替代尝试、临时凭据、文件替换或未知审计继续阻断。

`exam_forward_retirement.py` 的固定 `exam-a8-forward-close-v1` 仅在完整
`FORWARD_RECOVERED`、凭据链及新鲜服务/健康证明成立后收口；默认 inspect，执行须绑定
摘要和明确的固定 accept 开关。其完成状态 `CLOSED_EXAM_FORWARD_FAILURE` 不改写原
`NEEDS_OPERATOR`，不宣称通知已发布。撤销旧发布身份，销毁旧 loopback 私钥，将原
lease 在同一文件系统无覆盖地原子移走，保留原 inode、stage 及四个审计文件；不复制
配置、源码或运行时数据。随后 canonical bootstrap 通过原 closure receipt 执行无副本
授权轮转。普通发布重复验证完整持久链；仅有完成字符串、缺少临时 lease、未完成轮转
或有冲突审计均不授予发布权限。

### 自动回滚至旧 revision 的独立收口

`scripts/rolled_back_release_operator.py` 仅处理已完成自动回滚、原回执为
`NEEDS_OPERATOR` 的 backend-only 发布。默认只读取证；不重新部署原失败 SHA，
不恢复 Runtime、不确认 UNKNOWN 操作。原 workspace、日志、失败回执及 launcher
lock 保持原字节。收口状态为独立的 `CLOSED_ROLLED_BACK_RELEASE`。

必须从精确完整 CI 全绿的 current main canonical staging，以系统 Python
`-I -S -B` 和 root 本地管理通道执行。验证精确旧 SHA 的 `RESTORE_FINALIZED`
九字段 terminal、原日志唯一完整 `ROLLBACK_OK`、原发布窗口、旧配置及 Laya
来源、PostgreSQL schema/KB 隔离、服务 PID 稳定、HTTP、双身份、无活动发布及
无 transaction。原自动回滚会删除 preflight stage；不存在本身不能证明恢复。
环境来源只能是原日志唯一完整行指定的 `/var/backups/health-app/env/.env.*`，
核对这一份文件的 root 私有元数据、文件名时间和 ctime，再按原回滚规则
归一化，与当前 env 字节相等；不遍历其他备份，不以候选 deployment.env 代替。

显式执行须绑定先前 inspect 的完整 `--evidence-sha256`，intent 前后重复取证。
独立审计先落盘，然后归档必要的 rollback.env、精确撤销原 cloud/loopback
授权，并验证 loopback 私钥的派生公钥后删除该旧私钥。任何 intent 后失败
保留原现场且禁止自动重试。新 receipt 只能写入新建的 root0600 单链接文件
`/var/lib/reva-release/operator-receipts/<closing-sha>/closure-<32hex>.json`，
父目录 root0700；不得输出到终端、管道、临时目录或已有非空文件。

后续 canonical bootstrap rotate 从服务器保护文件通过既有 receipt stdin
通道消费收口回执；不放入命令行、日志或聊天。历史复核保存原失败链和
归档 preimage 的摘要，不要求未来生产仍停留在回滚 SHA。收口成功仍不是
新候选部署成功；新 SHA 继续走 backend、Web、trusted OTA 各自的回执与验证。

### 部署前 GitHub 再校验失败的独立收口

`recover-preparation` 可识别独立的 `predeploy-attestation-failure` 实现 profile：
仅接受经审查的完整 executor/gate 摘要与 canonical/installed/policy 三方一致、
STARTED/PREPARING/PREPARED/DEPLOYING/NEEDS_OPERATOR 精确回执、固定 wrapper 与
唯一末行 GitHub 元数据失败。全保留树 manifest 不变，deployment.log、build.lock、
业务 lease、原生 claim 或未知文件任一出现即拒绝，不将“没有日志”单独当执行证明。

该实现控制流证明失败 gate 仅使用标准库读取 GitHub 元数据，尚未启动 deploy.sh。
收口不扫描 schema/KB 或个人健康数据，也不证明业务功能验收。生产证明绑定独立指定的
旧 SHA、COMMITTED 终态、现有配置派生的完整 candidate env、早于消费的进程/配置身份、
backend socket/backend/worker/beat 的规范化有效启动命令、unit/drop-in 与环境文件路径；
排除 runtime activation override，并跨六秒稳定窗口复核。frontend 不在此 profile 的
服务验收范围；不得据此宣称全站验收。首次随机 Laya 配置无法确定性重建时拒绝。

沿用原锁和两阶段摘要确认、先 fsync intent、精确撤销旧双身份与私钥、后置证明及
受保护回执通道。新终态为 CLOSED_PREDEPLOY_ATTESTATION_FAILURE，保留原
NEEDS_OPERATOR 与全部消费记录，不将原发布改为成功，不重试原 SHA；任何意图后失败
保留未完成记录并阻断再次执行。此入口只撤权，后续候选仍须独立 G4、精确绿色 main CI、
新授权、后端部署与 OTA validate/publish。授权来源仍是用户的部署维护授权，设计审查
本身不授予操作权限。GitHub 配额耗尽只给明确原因；短暂 429/5xx/连接故障最多三次
尝试，共享原十秒预算，TLS/鉴权失败及真实 CI 红灯不得重试。

### 无备份发布在只读 preflight 失败后的收口

`recover_contained_services.py --retire-no-backup-preflight` 是独立收口模式，不重试原部署、不重启服务、不改生产 env。仅接受受审实现摘要绑定的无备份部署在 runtime preflight 处失败，或独立 `laya-context-missing-candidate` profile 证明在 Laya context 读取已取消的配置副本时失败；原 STARTED/PREPARING/PREPARED/DEPLOYING/NEEDS_OPERATOR、原锁/租约、14个 canonical 工具及 manifest 均完整；未知状态拒绝。与其他恢复/收口模式互斥。

必须使用精确完整 CI 绿色 current main 的 canonical staging 和系统 Python `-I -S -B`。先只读 inspect，再以相同证据摘要执行；原 lease token 走受保护 stdin，收口 receipt 只进入 root0600 保护文件供 rotate 消费。原失败回执永久保留，任何 intent 后失败禁止重跑。

此模式没有历史 env 摘要，也不能补造备份：准确绑定失败控制流，要求现行 env 安全元数据与 ctime/mtime 早于原启动回执和租约、检查期间当前身份/摘要不变；明确记录 `historical_env_digest_available=false`。旧 SHA、COMMITTED 终态、所有旧服务和进程早于租约且稳定，公开运行配置与外置 runtime/gene 路径必须真实核验；外置子项禁止链接回 checkout。未知时序、活动事务、写入或发布进程均阻断。

收口仅写小型 intent/completed 审计，不复制 lease、stage、env、旧代码或运行数据；原 stage 原地保留，原 lease 按既有同文件系统原 inode 终态归档。撤销本次精确 cloud/loopback 授权和已验证旧 loopback 私钥，复证服务与原始证据后才签发 `CLOSED_UNCHANGED_RELEASE`。审计记录保存身份及摘要，后续历史校验不把这些摘要当备份恢复证明，也不重新遍历暂存目录或历史备份正文。无备份身份轮换后的历史校验由 durable retirement audit 绑定原安装摘要和公钥，不要求已退役安装副本存在。

该收口不是 backend SUCCEEDED；后续候选仍需独立安全审查、精确 CI、新授权、部署及对应 OTA/native Gate。

Laya context profile 另绑定失败脚本、runtime 与原 installer 的精确摘要、原日志中 runtime/env 验证成功及唯一终止位置，并拒绝任何停服、事务 prepare 或安装迹象。原 Laya 导出源必须完整，已安装 generation、unit/env、安装回执与运行进程必须早于原租约且稳定；所有 pending 安装路径必须不存在。仅 GET 健康探测，不调用真实模型。后续部署使用单独封存的只读 verifier 复核现有安装，不恢复 env candidate/rollback 副本；原 installer 与 generation 的资产保持不变。收口后仍使用原租约证据复核；历史消费者仅验证保存的证据与 canonical 源，不扫描现行模型或历史备份。

#### 行程配置预检失败的限定收口

同一 `--retire-no-backup-preflight` 入口新增独立的
`daily-journey-config-preflight-v1` profile，绑定失败候选
`6a24b64596464f41eac852306da29bef6ff31da0` 与仍在运行的
`25b85536e3722dc111c528b8a915062a3f971397`，并必须匹配五份失败代码
摘要和唯一停写前日志顺序。它不以 SHA 或“现在检查通过”作为充分条件，不重放原发布。
原迁移工具动态编译配置时继承 future annotations，导致 Pydantic 配置类型解析
失败；后续工具以 `dont_inherit=True` 保留配置自身语义，并只输出脱敏异常类别、
阶段和 helper 行号，绝不输出异常正文、SQL、连接串或局部变量。

收口继续验证旧运行版本、COMMITTED 终态、原租约与启动时间、配置身份、服务
代际和两次完整快照一致。独立 PostgreSQL 只读连接只读取角色、目录和迁移账本
元数据，绑定数据库身份和账本摘要，要求目标迁移 pending、三个目标对象不存在、
候选迁移目录/intent/完成回执均不存在。路径父链、日志或任何状态漂移均阻断。
不读取个人健康记录、不执行 DDL、不停服、不改 env、不创建备份；已准备但未
发布的独立 Web 制品保留原回执，不视为线上切换。

关闭原失败仅恢复后续新候选的发布前提，保留原 NEEDS_OPERATOR。新候选仍需
独立 G4、精确完整 CI、CI-mode、新授权及后端/Web/适用移动端的各自回执。

### 首次 Health / KBase 认证启用（独立无备份配置入口）

`deploy.sh --activate-kbase-login` 是普通 env-only 冻结之外的明确、受审例外，
不放宽 `-e` 或旧发布入口。仅首次关联同机已部署的 Health 和 KBase，保留原后端
revision。参数绑定当前受审 publisher SHA、原生产 backend SHA、KBase SHA 和
经本人现有 Health 凭据 `/auth/me` 验证的 owner；凭据仅通过有界 stdin 输入，
不保存、不记录、不转成浏览器会话。先完成精确绿色 CI、独立安全审查和 canonical
bootstrap，再从该 root-owned staging 调用。默认只读预检，`--apply` 才执行。

启用前必须实际读回专用确认页的固定 KBase form-action、strict-origin、no-store，
以及两端未配置认证、原 backend SUCCEEDED 回执与唯一环境来源。前端固定公开
origin 只放行确认页的表单目标，不启用签发。服务身份、其它 env 与 drop-in 不改。

新密钥仅在服务器生成，保存在 root-only 操作目录并写入两个既有 env 文件；
只变更 KBASE_SSO_* 与 KBASE_HEALTH_LOGIN_* 固定字段，逐文件原子替换并保留
其它字节、所有者与权限。整体分阶段执行：KBase 写入/重启/验证后，Health
写入/重启/验证。每一步前后 fsync journal；无备份、无自动回退。

小型状态放在 `/var/lib/reva-kbase-login`，独立于既有发布历史目录；全过程使用
原 launcher flock 和 business lease。失败留下原 intent、同一新密钥与 lease，
只能显式 `--resume --apply` 续接同一版本绑定；不得重新生成密钥或新建事务替代。
`CONFIGURATION_SUCCEEDED` 后还须另验本人真实浏览器回传、匿名/过期/重放拒绝及
KBase 注销，不能把配置成功写成登录验收完成。全局退出联动不在本入口范围。

#### 业务租约创建前的历史校验失败

`bootstrap_trusted_release.py recover-preparation` 新增独立的
`prelease-vision-history-failure` 证明，仅处理固定 `17f9c29f32123ada929fac9af61a17e6521094d8`
候选在创建业务租约之前的视觉历史检查失败。它绑定原 executor、deploy、gate 和
history checker 的精确字节、原工作区清单及唯一初始失败日志；不能仅凭 SHA 或
当前网络恢复放行。原通用错误不证明具体 GitHub 错误，收口只证明未到达修改步骤。

原生产仍须为 `25b85536e3722dc111c528b8a915062a3f971397`，核验服务启动时间、
运行配置、COMMITTED 终态与稳定健康状态；候选配置、业务租约、迁移和 Laya 安装
意图必须不存在。复用既有独立 inspect / evidence-digest 执行、撤销及秘密回执流程，
保留原 NEEDS_OPERATOR，不重新部署、不复制备份。下一候选仍需独立 G4、完整 CI、
新授权和各端发布回执；未知或部分操作不得重发。

视觉历史检查的限流错误保留固定阶段、可信 gate 的错误代码及 `not_before` /
`retry_after_seconds` 整数，不输出异常正文或凭据。限流依然是失败，不自动重试。
生产固定 App 凭据缺失时仍为匿名额度，本机 GitHub CLI 授权不构成生产提额。
发布协调者须在消费新发布前预留足够元数据查询额度，遵守冷却时间并避免并行校验
耗尽同一服务器额度；不可注入管理员 PAT 或删除失败回执代替收口。


#### 已安装隐私页文案误判的精确收尾

`frontend_no_backup_finalization.py --operation-id e94f8c89521046fcae79cdb8fd54dc09`
仅选择 `privacy-title-readback-v1`，保留旧 CSR profile 默认行为。绑定原6e发布源码摘要、
已消费制品、原失败文件及租约身份；新 current-main 精确CI与独立G4通过后，从canonical staging
先inspect再按证据摘要执行。重新核验内外网当前隐私标题和全部连接/登录页面安全条件、
完整在线制品及后台进程/配置。原失败回执不改写，不重建、不重新切换、不重启、不备份。
只有持久化验证与原租约释放完成才写独立finalization终态；部分执行仍阻断，禁止重放。

#### 文字晚餐候选的停写 guard 事故恢复

`scripts/dinner_guard_recovery.py` 仅恢复失败候选
`ae49cf1fc53c567b305c2a9f6cfff5c3257e7309` 停止的旧生产
`f42bb4c6d1c962453a6eadd1318ca6b663174b80` 服务。用户已于
2026-10-23 明确授权该次事故恢复。该失败发生在 worker 停止证明拒绝
`failed` 状态之后；原多行依赖命令逸出 shell 条件链，尚未 checkout 就执行
Pi 安装并因路径不存在退出。修复后的 guard 将整个依赖块放入同一个条件操作数。

恢复必须使用新的受审、精确完整 CI 绿色 revision 的 canonical source，先只读取证，
再按相同摘要执行一次性恢复。固定原失败日志、回执、租约、旧代码、配置、依赖、
有效服务单元和 runtime 终态；不接受其它失败状态或目录漂移。保持原发布锁和
`NEEDS_OPERATOR` 回执，仅启动固定旧服务并验证稳定进程、健康检查与匿名认证拒绝。
恢复完成不等于晚餐修复已部署，不授权重跑失败候选，也不执行备份或回退副本操作。


#### 静态配置误判后的原服务恢复限定继续

用户在获知首次专用恢复后验失败、服务已再次停止后，于 2026-10-23 再次明确
授权恢复原版本服务。本例外仅适用于 `ae49cf1fc53c567b305c2a9f6cfff5c3257e7309`
发布事故中，`6492f31789edf257ace6710cdfdff7b6c6c3b8b6` 恢复程序把 ExecStart
运行时字段误当静态配置变化的失败。它不开放通用重试，不重跑部署、不轮换授权、
不释放 lease、不创建备份，原生产仍须为 `f42bb4c6d1c962453a6eadd1318ca6b663174b80`。

专用 continuation 必须保留原 intent 原字节（SHA256
`bb519db5741aeed48403c686f0f5c7539f0fa77c86a813ad3bdad8f3ae7c7367`），
原目录仅存在 intent，全部服务已隔离，其他证据与原 snapshot 完全一致。
仅允许受审静态桥将原 units 中的动态 show 摘要关联至新静态投影；unit 文件、
执行路径与完整参数、环境文件顺序、用户及依赖等不允许变化。
在原 audit 下固定 `continuation-20261023-static-unit-proof` 子目录记录新一次 intent/terminal，存在即拒绝，
不可换目录绕过。执行前必须新精确绿色 CI、独立 GO、只读 inspect 摘要一致及
显式限定授权参数。保留数据库只读探针、进程稳定、健康/认证后验和失败隔离；
错误必须有脱敏阶段证据。恢复完成仍不代表新业务修复已部署或原发布成功。


#### 晚餐事故恢复后的无副本收尾

用户于 2026-10-23 要求继续上线。`scripts/dinner_guard_retirement.py` 仅用于上述
固定 ae49 失败发布及 f42 恢复状态，不重跑已消费部署或恢复。收尾读取原 6492
intent 和 2c2679 固定 continuation 子目录的 intent/completed，校验原字节摘要、
静态配置桥和非 unit 证据；不得补造原根目录 completed 或忽略未知 snapshot 字段。

新候选必须是完整 CI 绿色的精确当前 main，独立审查通过，先 inspect 再以相同证据
摘要执行。持有既有 launcher/build 锁，保持原服务稳定，核验原失败 workspace、
租约和 runtime。仅撤销准确匹配的旧 cloud/loopback 身份及旧 loopback 私钥；
租约按同文件系统原 inode 移至固定终态路径，不复制配置、lease、stage 或数据。
原失败回执、恢复 intent、continuation 审计均保留原字节。

持久化收尾 intent/completed 并复证后，才产生受保护的单次 rotation receipt。
新 canonical bootstrap 的 `rotate --dinner-guard-rotation-stdin` 仅接受该回执及
只读仓库 token 的受保护 stdin，复验完整 CI 和原收尾状态；秘密不得进入 argv、
公开日志或仓库。历史消费者只消费完整持久审计，不依赖已删除旧安装副本。
任何 intent 后失败均保留证据并停止，禁止换 ID 或自动重放。收尾不重启服务，
也不代表业务修复已部署；后续新候选仍须通过 trusted backend 发布及线上复验。

#### fdd 停服检查事故的限定恢复与诊断续行

`fdd5659502888d44bf91c9b35a7368366932098f` 在 checkout 前的停服检查失败，
旧生产仍为 `f42bb4c6d1c962453a6eadd1318ca6b663174b80`。沿用用户明确授权的
原版本服务恢复范围，不重跑原部署、不改变代码、配置、数据库、租约或发布身份。
首次恢复保留 quiesce intent 与 restore intent；后验失败后已停止全部原服务，
不得把健康探针曾通过或进程曾启动宣称为恢复成功。

固定 `continuation-20261023-snapshot-observer` 仅用于该事故的单次限定续行：
原两份 intent 的原字节与文件身份必须固定，旧代码、原静态快照、依赖、配置、
服务定义、租约与已安装发布器全部一致，保持 canonical 恢复核心的稳定性、
健康、匿名鉴权拒绝与失败停服检查。新增观察器只投影首个失败的固定字段名或
函数行号，并原样抛出异常；不忽略差异、不放宽原判断，不把原因未确定写成已修复。

先只读 inspect，再以相同摘要单次 apply，固定子目录存在即拒绝重放。只读阶段
在进程清单变化时失败、且尚无执行意图的，可在保留原本地失败证据并独立审查后
作一次有界只读复核；这不授权重试已消费操作。唯一恢复成功证据是该固定子目录
内 canonical `completed.json`，传输输出不得代替持久回执。后续新发布须消费完整
原始意图及续行链，另经候选精确 CI、收尾审查、实际部署及线上验证。

`fdd_guard_retirement.py` 的后续收尾仅接受上述 fdd 失败及 f42 恢复状态，必须核对
quiesce intent、restore intent、固定 continuation intent/completed 四份真实摘要。
原 restore 目录保持 intent-only，不能补造完成；续行必须逐项绑定两份原 intent
完整文件身份和原静态快照。原审计保留，不复制数据或配置，不重启服务。
新当前 main 精确完整 CI、独立审查与相同 inspect 摘要通过后，方可通过固定收尾
事务撤销旧发布身份、移动原 lease 到固定退休位置，并生成单次受保护 rotation
回执。canonical bootstrap 按固定失败 SHA 分派该 profile，旧 ae49 profile 保持不变；
历史消费者只接受完整四段恢复与收尾链。任一步已消费后失败，仍禁止自动重放。

#### 固定 native 授权轮换收尾

`bootstrap_trusted_release.py finalize-native-rotation --sha <current-main>` 仅处理
c280 native-only 授权已退休、ace 后继尚未安装的固定事件。原 retirement 两份审计
由固定摘要绑定，原 closure/receipt、生产版本与原锁继续校验。默认只读，返回
`evidence_sha256`；显式传回该摘要才执行一次安装。配置、执行器、业务 workspace、
租约或收尾记录已存在均拒绝。新发布者必须是当前精确绿色 canonical 源码。

收尾保留原审计，在独立 `native-rotation-finalization` 记录新发布者、原审计摘要、
原授权文件身份、closure 与锁。先写 intent，再安装并核验严格公钥授权行与执行器，
最后写完成记录并读回完整继承链。任一步失败不得重试、删除记录或重建旧授权。
该记录只修复发布授权，不代表业务部署或 Edu 登录验收完成。

### 手机号开放注册配置切换（2026-10-26）

用户已明确取消邀请制，并要求管理员能直接创建用户。应用变更完成后，
`scripts/public_registration_activation.py` 是本次固定注册策略的独立无备份入口；
不开放通用 env-only，不使用历史 `invitation_only_config` 恢复生成器改写现行配置。
它只接受完整旧策略 `false/true/true` 到新策略 `true/false/false`，字段顺序为
`AUTH_PHONE_SELF_REGISTRATION_ENABLED`、`REGISTRATION_INVITATION_ENFORCEMENT_ENABLED`、
`REGISTRATION_INVITATION_ROLLOUT_ENABLED`；其它字节及 root:health-app 0640 权限保持。
新部署校验与 public-host 运行态校验接受两种完整受审策略，拒绝混合状态；
`HEALTH_EVIDENCE_RUNTIME_ENABLED=false` 等无关约束不变，历史回执不重写。

必须先完成独立 G4、精确当前主干完整 CI、canonical bootstrap，以及同一 SHA 的
后端 `SUCCEEDED` 发布。使用系统 `/usr/bin/python3.12 -I -S -B` 运行该 SHA 的
`/var/lib/reva-release/bootstrap/<sha>/source/scripts/public_registration_activation.py`
并传入 `--publisher-sha <sha>`；默认只读预检，返回 `READY` 后加 `--apply`。
入口同时核验已部署源码、installed authorization、环境来源、三服务运行策略、
历史终态，并复用 launcher flock 和 business lease，不能用旧候选或任意目录执行。

`/var/lib/reva-public-registration/journal.json` 只保存绑定、摘要和阶段，不复制 env。
配置经 CAS 原子替换与 fsync 后，依次重启并读回 health-backend、celery-worker、
celery-beat，确认三者为新策略及后端健康才记 `CONFIGURATION_SUCCEEDED` 并释放租约。
中断保留原 journal/lease；只有相同 SHA 的 `--resume --apply` 可以续接可证明的原阶段。
未知目录、配置漂移、不完整租约和失败的前置证明仍阻断，不自动回退或新建操作覆盖。
该终态仅证明注册配置生效，不发送短信、不创建账号；真实手机号注册、管理员创建、
Web 和 OTA 用户路径分别验收。
