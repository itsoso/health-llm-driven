---
name: backend-deploy
description: "部署后端到生产 (deploy.sh -b)。当用户说「部署后端」「上线」「deploy」「发后端」「重启后端」「跑迁移上线」时使用。含「合并≠上线」铁律、managed 迁移、健康度自动回滚、ssh 复验。"
---

# Backend Deploy

后端上线唯一入口:`./deploy.sh -b`。**异步执行,触发后切别的活,别同步等。**

## 铁律:合并到 main ≠ 上线

把代码合进 main **不会**让它生效——生产进程还是旧的。必须 `deploy.sh -b` 才会 pull + 重启。
(本会话踩过:agenda 路由合并了没部署 → 手机「加载失败」,生产 `/agenda/today` 返回 404 而非 401。)

## 流程

```bash
cd /Users/liqiuhua/work/personal/health-llm-driven
git push origin main          # 先 push(deploy 在服务器 git pull)
./deploy.sh -b                # 后台跑
```
`deploy.sh -b` 自动做:git pull → **应用 managed 迁移**(`backend/migrations/managed/*`)→ 重启 `health-backend` + Celery worker+beat → DB 备份 → 同步 `backend/skills/*/SKILL.md` 到 OpenClaw 网关 → 跑 `system_health_score.py`。

**健康度门**:阈值 `DEPLOY_SCORE_THRESHOLD=35`(满分 60,skip-tests)。低于阈值**自动回滚到上一版本**。正常输出 `健康度: 60/60 ✅ PASS` + `Skills 同步: 本地 N = 线上 N`。

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

## 坐标 / 排错

- 生产:`39.98.206.178`(SSH 22)· `/opt/health-app/` · systemd `health-backend` → `health-api.executor.life` · PostgreSQL 同机
- 日志:`ssh root@39.98.206.178 "journalctl -u health-backend -n 50 --no-pager"`
- 其它 flag:`-f` 仅前端 · `-a` 全部 · `-e` 同步 .env 重启 · `-r` 仅重启 · `-s` 看状态 · `-l` 看日志

> 前端/移动端不走这个:Web 用 `deploy.sh -f`;移动端 JS 走 `mobile-ota`,原生/发版走 `mobile-testflight-release`。
