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
2. 把本次提交的 backup/rollback/schema-probe 工具上传到 root-only stage，并逐文件
   校验 Git blob hash。
3. 在 Git 工作树外创建数据库备份，完成临时库恢复演练及 age 加密站外归档；任一步
   失败即停止。
4. 在修改 live env、checkout 或停服前，使用 staged probe 验证“当前生产 SHA 与
   实时 schema 兼容”。只有 stage hash、HEAD、clean tree、完整表/列/零行写探针及
   release token 前后均通过，才记录 rollback point。
5. 同步根目录 `.env` 时先备份到 `/var/backups/health-app/env/`；候选文件先进入
   root-only stage，再由去激活事务原子安装规范 `false`。运行时文件强制为
   `root:health-app`、`0640`，外部备份为 `0600`。
6. 先停 backend socket、backend、Celery worker 与 beat 并证明全部 inactive，再
   checkout 精确 SHA、安装锁定依赖。
7. 仅临时加载 `/etc/health-app/migration.env`，在 migration runner 紧前重新核验
   release token，再执行 managed migrations 并清除 migration URL；在启动任何
   writer 前，用 runtime role 再跑完整 schema probe，并再次核验 release token。
8. 重启服务，逐 cgroup PID 证明 feature flag 终态，验证 exact SHA、health/auth、
   脱敏后的健康硬闸与 runtime-only KB serving contract。
9. 远端 SSH/信号结果不明确时保留 release lease 与 stage；没有独立 terminal
   证明时禁止并发 rollback 或第二次部署。

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
