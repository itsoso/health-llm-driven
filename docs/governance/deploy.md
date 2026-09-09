# 部署规范 🚀

> 从 `AGENTS.md §8` 拆出（2026-05-31, Agent Operating Harness Phase 2,见 [`docs/design-agent-operating-harness.md`](design-agent-operating-harness.md)）。`AGENTS.md` 现在只留章节导航,本文件是本章权威全文 —— 硬规范裁判权不变。


### 8.1 部署方式

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

### 8.2 线上配置管理

#### 受审隔离发布入口

手动触发 `.github/workflows/trusted-release.yml`，先以 `target=validate` 验证当前 main
的精确 SHA 和真实 CI，再以同一 SHA 执行 `target=release`。各 job 均使用新的
GitHub 托管 VM，不上传本机工作区、不复用测试 runner 或缓存；生产权限只在只读闸后使用。
GitHub 控制面、受审代码、固定工具链和服务器 root 是信任前提，不声称抵御 runner root 失陷。
仅后端变更使用同一入口的 `target=backend`，仍先经过 preflight 与服务器 readiness，
再执行相同 backend job；不读取 Expo 凭据、不领取构建/上传权限、不运行 iOS jobs。

首次安装仅属于经授权的发布基础设施配置：管理员以固定系统 Git 从 canonical GitHub
检出已通过独立 G4 和 CI 的 SHA 到 `/var/lib/reva-release/bootstrap/<sha>/source`，
核验干净 revision、root ownership 与受审字节，再以系统 Python `-I` 执行该源码中的
`scripts/bootstrap_trusted_release.py`。禁止上传本机脚本充当 bootstrap。
安装器只接受八小时内到期的专用 ed25519 公钥，拒绝覆盖现有安装。

后续授权使用同一 bootstrap 的显式 `rotate --retire-sha <old> --sha <new>`，仅从
新 SHA 的上述受审 canonical staging 执行。必须先撤销旧 cloud/loopback 授权并删除
旧 loopback 私钥，证明旧后端成功终止或从未启动、业务 lease 不存在、无发布进程。
轮换持有原 launcher.lock，核验旧源码哈希、私有目录库存和消费记录，原样归档旧安装，
再安装新的短期身份；旧 SHA、消费标记和锁 inode 不得删除或复用。任何未知现场或
中途失败均保留 intent/安装证据并阻断，不支持通过再次执行重置授权或自动恢复。

该生产站点已有一份旧格式 `retired/<sha>/{config,executor}` 归档。兼容读取只接受源码
中固定 SHA 和受审 inventory 摘要，逐次校验 canonical executor、撤权、无私钥、从未
启动及原始 bytes/owner/mode/inode；缺失或漂移均 BLOCK。不得移动、重写旧归档，不能
按目录形状接受任意 legacy 状态。其 SHA 与两类公钥继续参与全历史防复用。

云端身份由服务器 forced-command 限定为绑定同一 SHA 的 `run`、`status`、
`check`、`claim-build`、`claim-testflight`，不提供 shell/SFTP；服务器内部的短期 loopback 身份不离开服务器。
后端业务部署仍由受审 fresh source 中的 **`deploy.sh -b`** 执行全部事务闸。
`DEPLOY_SOURCE_SHA` 仅选择精确来源的 verify-only 模式，不是授权或绕过检查的开关。
候选环境从当前生产 `root:health-app 0640` 配置派生，不改变其凭据和权限合同。

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
上传 job 必须同时等待 backend 和 ios-build 成功，仍以 `claim-testflight` 验证后端
SUCCEEDED 并消费一次性上传权限。仅提交本轮 job 返回且经 EAS 再次验证的精确 build ID，
要求 source SHA、FINISHED、IOS、STORE、production 全匹配；禁止隐式 latest。
后端失败时可能浪费本次构建费用，但不得上传；不因并行删除备份、恢复或回滚闸。
后端 STARTED/NEEDS_OPERATOR 时保留权限和 lease 供调查，不按“锁空闲”推断已终结。
EAS 调用响应丢失时按 source SHA 查询已有构建，记录其 build/submission ID，禁止重复 create。
完成后撤销本次专用授权、环境 secrets 与新建 Expo robot token；只移除精确匹配项，
保留其他密钥及审计记录。权限到期不证明已启动的进程终止。

该入口不替代下面的备份、恢复、迁移、运行态、健康和回滚规则，也不提交正式 App Review。

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
受管 `.pth` 仅作为不执行的文件保留，editable、customize、外部链接及额外 site
目录仍 BLOCK。生产配置通过元数据校验后按 dotenv 数据读取，不执行 shell；缺失
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
3. 在 Git 工作树外创建数据库备份，完成临时库恢复演练及 age 加密站外归档；任一步
   失败即停止。
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
