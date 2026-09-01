---
name: backend-deploy
description: "部署后端到生产 (deploy.sh -b)。当用户说「部署后端」「上线」「deploy」「发后端」「重启后端」「跑迁移上线」时使用。含「合并≠上线」铁律、managed 迁移、健康度自动回滚、ssh 复验。"
---

# Backend Deploy

后端上线唯一入口:`./deploy.sh -b`。长步骤异步执行并回报阶段进度；不要用重复部署代替状态查询。

## 铁律:合并到 main ≠ 上线

把代码合进 main **不会**让它生效——生产进程还是旧的。必须 `deploy.sh -b` 才会 pull + 重启。
(本会话踩过:agenda 路由合并了没部署 → 手机「加载失败」,生产 `/agenda/today` 返回 404 而非 401。)

## 流程

```bash
cd "$(git rev-parse --show-toplevel)"
git push origin main          # 先 push(deploy 在服务器 git pull)
./deploy.sh -b                # 后台跑
```
`deploy.sh -b` 自动做:git pull → **应用 managed 迁移**(`backend/migrations/managed/*`)→ 重启 `health-backend` + Celery worker+beat → DB 备份 → 同步 `backend/skills/*/SKILL.md` 到 OpenClaw 网关 → 跑 `system_health_score.py`。

**健康度门**:阈值 `DEPLOY_SCORE_THRESHOLD=35`(满分 60,skip-tests)。低于阈值**自动回滚到上一版本**。正常输出 `健康度: 60/60 ✅ PASS` + `Skills 同步: 本地 N = 线上 N`。

## 快速路径（不削减安全门）

1. 先按变更范围选最小发布目标：只有 Mobile JS 就只走 `mobile-ota`；只有后端才走本 skill；两端都改才先后端、后 OTA。
2. 发布前只读比较 `origin/main`、本地 HEAD 和生产 SHA。生产已是同一 SHA 且无 env 变更时，查询状态和健康度即可，不要重复备份、归档和重启。
3. `deploy.sh` 会在数据库备份、完整恢复演练和站外归档之前执行生产 env 快速预检；预检失败先修配置，不得用 `DEPLOY_ENV_FORCE=1` 绕过。相同 env 文件由摘要复用，进入 `sync_env` 时不重复远端比较。
4. 必须用干净 main 发布目录时，复用已经存在的 clean release checkout；不要每次重新 clone。发布结束只清理该 checkout 生成的 manifest/anchor，不动用户工作区。
5. 数据库备份、恢复演练、站外加密归档、回滚 schema、健康度和 runtime contract 仍无条件执行。成功发布的正常墙钟主要由站外归档决定，优化目标是消除重跑而不是跳闸。

## 部署后复验(必做)

```bash
# 路由活着 = 401(需鉴权);404 = 进程是旧的(没重启成功)
ssh health 'curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/api/v1/<新路由>'
```
401 = 上线成功;404 = 排查(进程没重启 / 路由没注册)。

## 已知坑

- **服务器 detached-HEAD** → `git pull` 失败。修:服务器上 `git checkout -B main origin/main`。`push_code` 对任何 dirty/untracked 树会硬退出。
- **改了后端 request/response schema** → 部署后记得 `cd mobile && npm run generate-types` 重生成移动端类型(否则手写类型静默漂移)。
- 涉及 用药/基因/化验/CGM/SpO2/safety规则/对外健康建议 的改动 → 部署**前**先走 `safety-gate`(派 safety-privacy-reviewer,GO 才部署)。
- 加了 model/service/router/safety规则/twin分区 → 部署前先过 `doc-drift-fix`(CI 会卡 doc-drift)。
- **`.env` 同步坑**:`-b` 会把 `DEPLOY_ENV_FILE`（默认根 `.env`，不是 `backend/.env`）作为完整候选配置。候选必须唯一包含 `APP_ENV=production`、`DEBUG=False`、规范 runtime/uploads/cache/Dedao 路径和 `HEALTH_EVIDENCE_RUNTIME_ENABLED=false`。本地文件若是 dev/陈旧配置，先从生产现行 `backend/.env` 生成权限 `0600` 的一次性候选，只补 `DEPLOY_SERVER=health`、`DEPLOY_PATH=/opt/health-app`；不得把 dev env 复制进发布目录，也不得把临时敏感文件留在废纸篓。
- **基因/RLS 多租户表(genetic_raw_files)**:迁移建表时上 `ENABLE/FORCE ROW LEVEL SECURITY`。**生产 DB 连接角色必须是非 superuser**(superuser 绕过 RLS → 隔离退化为仅应用层)。部署后看 `journalctl -u health-backend` 有无 `[SECURITY] ... superuser ... RLS 被绕过` 告警;有则把 prod DATABASE_URL 的角色换成非 superuser(如 `health_user`)。

## 坐标 / 排错

- 生产 SSH alias:`health` · `/opt/health-app/` · systemd `health-backend` → `health-api.executor.life` · PostgreSQL 同机
- 日志:`ssh health "journalctl -u health-backend -n 50 --no-pager"`
- 其它 flag:`-f` 仅前端 · `-a` 全部 · `-e` 同步 .env 重启 · `-r` 仅重启 · `-s` 看状态 · `-l` 看日志

> 前端/移动端不走这个:Web 用 `deploy.sh -f`;移动端 JS 走 `mobile-ota`,原生/发版走 `mobile-testflight-release`。
