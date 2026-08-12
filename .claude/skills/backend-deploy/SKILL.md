---
name: backend-deploy
description: "部署后端到生产 (deploy.sh -b)。当用户说「部署后端」「上线」「deploy」「发后端」「重启后端」「跑迁移上线」时使用。含「合并≠上线」铁律、managed 迁移、健康度自动回滚、ssh 复验。"
---

# Backend Deploy

后端服务器 mutation 的唯一入口:`./deploy.sh -b`。对已经提交的跨端变更，优先先让
`scripts/release.sh` 做 source-aware 路由；它最终仍委托 `deploy.sh`。
**异步执行长部署,触发后切别的活,别同步等。**

## 铁律:合并到 main ≠ 上线

把代码合进 main **不会**让它生效——生产进程还是旧的。必须 `deploy.sh -b` 才会 pull + 重启。
(本会话踩过:agenda 路由合并了没部署 → 手机「加载失败」,生产 `/agenda/today` 返回 404 而非 401。)

## 流程

```bash
cd /Users/liqiuhua/work/personal/health-llm-driven
git push origin main          # 先 push(deploy 在服务器 git pull)
./deploy.sh -b                # 后台跑
```

统一发布入口（推荐）：

```bash
./scripts/release.sh plan --base <last-published-sha> --target origin/main
./scripts/release.sh validate --base <last-published-sha> --target origin/main
./scripts/release.sh publish --base <last-published-sha> --target origin/main \
  --message "release message"
```

- `plan` 只读；unknown path fail closed。backend + Mobile JS 会严格按 server-first、
  OTA-second 排序；frontend 新 SHA 使用 full deploy。
- `validate`/`publish` 使用仓库旁永久 `<repo>.release`，必须 clean、detached/main、
  且精确等于本地和远端 `origin/main`。dirty/feature branch 不会被自动清理。
- partial success 记录在 Git common dir 的 `reva-release-state/release-state.json`
  （目录 `0700`、文件 `0600`）；重试同一 base/target 不重复成功 surface。
- production `.env` 仍只从 owner workspace 通过 `DEPLOY_ENV_FILE` 传入，绝不放进
  release worktree 或 shared state。
`deploy.sh -b` 自动做:git pull → **应用 managed 迁移**(`backend/migrations/managed/*`)→ 重启 `health-backend` + Celery worker+beat → DB 备份 → 同步 `backend/skills/*/SKILL.md` 到 OpenClaw 网关 → 跑 `system_health_score.py`。

**健康度门**:阈值 `DEPLOY_SCORE_THRESHOLD=35`(满分 60,skip-tests)。低于阈值**自动回滚到上一版本**。正常输出 `健康度: 60/60 ✅ PASS` + `Skills 同步: 本地 N = 线上 N`。

## 提速 proof 的安全模式

Python dependencies、frontend dependencies/build、System KB 只允许使用
`off` / `shadow` / `on` 三态 proof：

- `off` 完整执行；`shadow` 只报告候选 hit，仍完整执行；`on` 仅在输入、toolchain、
  输出、postcondition 与 root-owned receipt 全部匹配时跳过该单步。
- receipt 固定在 `/var/cache/health-app/release-proofs`（目录 `0700`、文件 `0600`）。
  missing/corrupt/symlink/权限或任何 digest 漂移都 fail closed 到完整步骤；失败步骤
  不得写入或保留 receipt。
- 生产先保持 `shadow` 至少三次并人工核对，再逐 step 评审是否切 `on`；KB whole
  import 最后启用。

proof 永远不能跳过 DB backup/restore rehearsal、managed migrations、schema probe、
release lease、runtime-state transaction、服务稳定窗口、revision、health score、
rollback/finalize。并行验证的每项耗时与日志路径由 `run-all-tests.sh` / `validate.py`
输出；禁止用 `tail` 管道包住运行中的测试。

## 部署后复验(必做)

```bash
# 路由活着 = 401(需鉴权);404 = 进程是旧的(没重启成功)
ssh root@39.98.206.178 'curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/api/v1/<新路由>'
```
401 = 上线成功;404 = 排查(进程没重启 / 路由没注册)。

## 已知坑

- **服务器 detached-HEAD** → `git pull` 失败。修:服务器上 `git checkout -B main origin/main`。`push_code` 对任何 dirty/untracked 树会硬退出。
- **改了后端 request/response schema** → 部署后记得 `cd mobile && npm run generate-types` 重生成移动端类型(否则手写类型静默漂移)。
- 涉及 用药/基因/化验/CGM/SpO2/safety规则/对外健康建议 的改动 → 部署**前**先走 `safety-gate`(派 safety-privacy-reviewer,GO 才部署)。
- 加了 model/service/router/safety规则/twin分区 → 部署前先过 `doc-drift-fix`(CI 会卡 doc-drift)。
- **`.env` 同步坑(`deploy_backend` 调 `sync_env`)**:`-b` 会把**根 `.env`**(`$SCRIPT_DIR/.env`,非 `backend/.env`)scp 到 `prod:backend/.env`(先备份远端 .env,留 20 份)。所以**必须从有真 prod 根 `.env` 的目录跑**(根 .env 形态=含 `DEPLOY_SERVER`/`DEVICE_ENCRYPTION_KEY`/`DATABASE_URL=postgresql`)。**从干净 worktree 跑要先把根 `.env` 拷进 worktree**,否则 sync_env 推空/dev .env 污染 prod(`backend/.env` 是 dev/sqlite,别混)。并发 agent 翻分支时,worktree 跑更稳(`git push` 在 main 上是空操作)。
- **基因/RLS 多租户表(genetic_raw_files)**:迁移建表时上 `ENABLE/FORCE ROW LEVEL SECURITY`。**生产 DB 连接角色必须是非 superuser**(superuser 绕过 RLS → 隔离退化为仅应用层)。部署后看 `journalctl -u health-backend` 有无 `[SECURITY] ... superuser ... RLS 被绕过` 告警;有则把 prod DATABASE_URL 的角色换成非 superuser(如 `health_user`)。

## 坐标 / 排错

- 生产:`39.98.206.178`(SSH 22)· `/opt/health-app/` · systemd `health-backend` → `health-api.executor.life` · PostgreSQL 同机
- 日志:`ssh root@39.98.206.178 "journalctl -u health-backend -n 50 --no-pager"`
- 其它 flag:`-f` 仅前端 · `-a` 全部 · `-e` 同步 .env 重启 · `-r` 仅重启 · `-s` 看状态 · `-l` 看日志

> 前端/移动端不走这个:Web 用 `deploy.sh -f`;移动端 JS 走 `mobile-ota`,原生/发版走 `mobile-testflight-release`。
