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

`deploy.sh` 仍是服务器 mutation 的唯一执行器；对一个已经提交的跨端变更，优先用
source-aware planner 决定是否需要调用它：

```bash
# 只读计划；<baseline> 必须是可信的上一已发布 SHA/ref
./scripts/release.sh plan --base <baseline> --target origin/main

# 在永久 release worktree 中跑验证，不发布
./scripts/release.sh validate --base <baseline> --target origin/main

# 验证后按计划发布；server mutation 仍委托 deploy.sh，Mobile OTA 仍委托 mobile-ota.sh
./scripts/release.sh publish --base <baseline> --target origin/main \
  --message "release message"
```

planner 的安全边界：

- `plan` 是只读操作，不创建运行状态；未知路径 fail closed。Mobile native、Watch、
  Mac 或 package/lock/native 配置变化只给出人工发版路由，不会误发 OTA。
- `validate` / `publish` 默认维护仓库旁的 `<repo>.release`：只接受干净、detached
  （或严格的 `main`）且 `HEAD == local origin/main == remote origin/main` 的 worktree。
  dirty worktree 或 feature branch 一律拒绝，脚本不会替操作者 reset/clean。
- backend + Mobile JS 混合变更先发布 backend、再 OTA；frontend 新 SHA 使用
  `deploy.sh --all`，避免 `--frontend` 在远端仍是旧 checkout 时构建错代码。
- planner 在验证后及每次 mutation 前重验 release source。成功 surface 以
  `base_sha + target_sha + completed_actions` 记录；同一事务重试只执行剩余 surface。

### 8.1.1 共享发布状态、验证日志与耗时

所有 worktree 通过 Git common dir 共享运行状态：

```text
<git-common-dir>/reva-release-state/
  release-state.json            # schema v2 当前/最近一次事务快照
  release-transactions.jsonl    # append-only 私有阶段审计
  release-publish.lock          # 跨 worktree 的生产发布互斥锁
  logs/
  credentials/
```

目录必须为 `0700`、文件必须为 `0600`，拒绝 symlink；这里不存 `.env`、密钥或健康
数据。生产配置由 owner workspace 的 `DEPLOY_ENV_FILE` 显式传给 `deploy.sh`，不得
复制进 Git worktree。

每次 `publish` 创建一个 transaction ID；同一 `base_sha + target_sha` 的失败或中断
重试会复用这个 ID、增加 attempt，并把遗留的 running stage 明确标成 interrupted。
状态记录每阶段开始/结束时间与耗时、失败阶段、已完成/待完成 surface 和精确的安全
重试 argv。重试 argv 只包含 base/target、repo/worktree 和 `.env` **路径**，不持久化
message、环境变量值、令牌或健康数据。已成功的 server surface 在同一事务重试时不会
重复执行；corrupt/旧 schema、权限不为 `0600`、symlink、额外硬链接或参数漂移都
fail closed。

`release-publish.lock` 使用 Git common dir，因此 owner/release/其他 worktree 会争用同
一个非阻塞锁；已有发布运行时，第二个 `publish` 必须立即停止，而不是排队后拿陈旧
计划继续写生产。事务 JSONL 只允许固定字段并逐行 fsync，供失败定位与后续耗时分析，
不能替代 GitHub 当前 commit 的 blocking CI 证据。

`scripts/run-all-tests.sh` 最多四路并行，每个 child 写独立私有日志，coordinator
直接 `wait` 真实 PID/退出码；失败后才读取日志末段用于显示。它会输出每项耗时与
日志路径。`python scripts/validate.py` 并发执行结构闸，`--full` 再委托全栈协调器，
并输出墙钟耗时。禁止把正在运行的测试接到 `tail`。

`scripts/validation_credential.py` 可签发/验证以 Git tree（不是 commit）、profile
版本、精确命令、lockfile、toolchain、结果日志和 TTL 为身份的复用凭证。任一字段
变化、日志缺失/漂移、过期或文件权限异常均为 miss；GitHub CI 仍以当前 commit 的
blocking job 为准，不能用本地凭证替代。

### 8.1.2 Server step proof 的渐进启用

只有 Python dependencies、frontend dependencies、frontend build 和 System KB
import 可以评估 step proof。receipt 位于 root-owned
`/var/cache/health-app/release-proofs`，输入、toolchain、输出和 postcondition 必须
全部匹配；缺失、损坏、权限过宽、symlink、漂移或无法观测都回退到原全量步骤。

三种模式语义固定：

- `off`：不读、不复用 proof，完整执行原步骤。
- `shadow`：报告候选 hit/miss，但仍完整执行并在 postcondition 成功后记录 receipt。
- `on`：仅完整 proof hit 时跳过该单步；miss 仍完整执行。失败步骤不得留下/沿用 receipt。

生产首次落地必须保持 `shadow`，至少积累并人工核对三次生产部署证据，再逐个 step
评审切到 `on`；System KB whole-import 最后启用。无论哪种模式，数据库备份与恢复
演练、managed migrations、schema probe、release lease、runtime-state transaction、
进程稳定性、revision、health score、rollback/finalize 始终无条件执行。

### 8.1.3 回退与回滚

- planner/classifier/credential/proof 任一判断不确定：停止发布，或执行原有完整步骤；
  绝不把“没有证据”当作成功。
- server mutation 失败：沿用下文持久 release journal、旧 SHA/env/upload authority
  和健康闸的原子回滚流程；不要另起并发部署。
- OTA 失败：同一事务只允许复用同一已校验 export 做一次瞬时网络重试；仍不确定时
  查询 transaction，禁止第三次盲发。人工回滚先运行
  `./scripts/mobile-ota-rollback.sh production` dry-run，再显式追加 `--confirm`。
- 验证或发布失败时保留并报告真实退出码、私有日志、已完成/待完成 surface；修复
  原因后用相同 `base`/`target` 重试，planner 会从共享状态恢复。

### 8.1.4 iOS Simulator smoke 的边界

`scripts/run_ios_real_device_acceptance.sh --platform "iOS Simulator"` 可以在已手动登录
的 Simulator build 上遍历安全 Settings 路由；同时提供 `--location <lat,lon>` 与
`--expected-city <city>` 时，会 grant/set 模拟位置，断言 GPS 自动城市与 ready
状态，并在 `EXIT/INT/TERM` trap 中 clear。两个位置参数必须成对出现，且物理设备
明确拒绝它们。

自动化不得点击 Garmin、Apple Health、退出登录、账号删除、更新应用或其他第三方/
破坏性动作。Simulator 不能替代 Garmin OAuth/MFA、HealthKit、APNs、camera、
microphone、Keychain、后台执行、真实权限弹窗或最终 physical-iPhone gate；review
credentials 也不得传给 XCTest/Xcode 日志，设备必须由人预先登录。

### 8.2 线上配置管理

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
