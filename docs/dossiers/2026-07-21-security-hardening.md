# Security Hardening Dossier

| 字段 | 值 |
|---|---|
| slug | `security-hardening` |
| 创建日期 | 2026-07-21 |
| 当前阶段 | S5 实现与验证 |
| 状态 | building |
| 负责 | Codex |
| 范围 | 2026-07-21 只读审计确认的安全问题 |

- 明确例外: 保持当前 JWT 两年有效期。该例外不允许 URL token、脚本可读存储、缺少撤销控制或 scope 绕过。

## G1 · Requirement Admission

- 裁决: PASS。该工作保护 L3/L4 健康与凭据数据，直接支撑 Health OS 信任边界，不新增产品 surface。

## G2 · Feasibility And Risk

- 裁决: PASS。采用分批交付，先关闭生产匿名读写；兼容 URL 保留，但必须经过当前用户或管理员授权。后续批次需通过各自安全测试才可进入部署 Gate。

## Current Evidence

- Production returned `200` without authentication for multiple per-user Garmin, recommendation, disease, and diet endpoints.
- Anonymous write routes accept client-supplied `user_id` for disease and daily-health records.
- Main CI is red and includes a direct-database-write guard failure for voice shortcuts.
- Production database backup is currently captured by the deployment Git stash instead of remaining in the backup directory.
- Full finding inventory and execution order are in `docs/plans/2026-07-21-security-hardening-execution-plan.md`.

## Gate Ledger

| Gate | State | Evidence |
|---|---|---|
| G1 Admission | GO | Security/privacy requirement |
| G2 Feasibility | GO | Compatibility-preserving staged design |
| G3 Tests | LOCAL GO / CI PENDING | 本地回归、真 PostgreSQL、安全脚本、跨端构建与静态闸通过；分支 CI 待 push 后取证 |
| G4 Safety review | RE-REVIEW PENDING | 首轮 NO-GO 的 5 个 P1 已逐项修复，等待独立复审 |
| G5 Deploy health | BLOCKED | 未满足生产角色、真实异地恢复演练、基础设施安装和原生 Keychain 发版前不进入部署 |
| G6 Production verification | NOT ENTERED | 尚未部署，不作上线成功声明 |

## Delivery Log

- 2026-07-21: Read-only audit completed; overall verdict NO-GO.
- 2026-07-21: User accepted the current JWT lifetime and authorized all other findings to be fixed in severity order.
- 2026-07-22: P0 匿名路由、API key scope、Agent 写入授权、跨端凭据存储、上传与解析配额、备份与基础设施配置已完成本地实现；部署仍受 G3-G5 约束。
- 2026-07-22: 首轮独立安全复审裁决 NO-GO，指出报告上传资源耗尽、药盒 OCR 自动写入、备份实例歧义、异地备份弱校验、部署 SHA 漂移 5 个 P1。
- 2026-07-22: 5 个 P1 已修复：报告页数/字节/像素/线程配额 fail-loud；药盒 OCR 改为可编辑草稿并显式确认；备份绑定 PostgreSQL host/port；异地对象逐字节 SHA-256 校验；部署强制 `main` 与精确 SHA。

## G3 Verification Evidence

- Backend broad CI shard `e-g`: `1043 passed, 1 skipped`。
- Backend focused SQLite security suite: `71 passed`。
- Backend focused PostgreSQL security suite: `67 passed`，覆盖 API Key、报告上传、旧路由租户隔离和 Web Session。
- Backup/deploy/infrastructure script tests: `19 passed`；相关 shell 脚本 `bash -n` 通过。
- Frontend: `297 passed`；`next build` 成功；ESLint `0 errors`（45 个既有 warning）。
- Mobile: TypeScript `tsc --noEmit` 成功；Expo lint `0 errors`（103 个既有 warning）；设计 token ratchet 通过。
- 此前本批次已完成 Mobile `2052` tests、Mac Core `448` tests、Frontend/Mobile/npm 与 Python dependency audits，未引入依赖漏洞。
- `ruff` 未定义名/语法闸、`git diff --check`、secret scan、system-map/doc drift 均通过。

## G4 Remediation Ledger

| 首轮 P1 | 修复 | 验证 |
|---|---|---|
| 报告上传可耗尽内存/线程 | Base64、源文件、总页数、像素、渲染字节、worker/queue 全部有界；任务提交失败标记 `failed` 并返回 503 | `test_family_health.py` |
| 药盒 OCR 自动写入用药清单 | 识别接口只返回草稿；Web 展示可编辑核对表单，显式确认后才写入 | Backend + Frontend regression |
| 备份忽略 PostgreSQL 端口 | 从 `DATABASE_URL` 解析并传播 host/port/database 到 dump、restore drill | `test_backup_security.py` |
| 异地备份只信对象名 | 文件名绑定源 SHA；上传与既有对象均执行远端下载哈希比对并校验 sidecar | `test_backup_security.py` |
| 分支部署可能部署旧 `origin/main` | 只允许本地 `main` push 到 `origin/main`；远端 checkout/verify 精确 40 位 SHA | `test_deploy_script.py` |

## Production Blockers

- PostgreSQL 仍未完成按在线请求、后台任务、迁移/备份拆分的最小权限角色；广泛 RLS 需要先完成后台任务租户上下文设计，不能在不了解运行时角色的情况下直接开启。
- 需要在真实异地存储执行下载、解密、临时 PostgreSQL 恢复和查询验证；本地脚本测试不能替代灾备演练。
- Nginx/systemd/UFW 等生产配置需要实际安装后检查有效配置与端口暴露。
- Mobile/Mac 的 Keychain 改动需要原生签名发版；OTA 不能改变原生安全边界。
- 必须从干净 `origin/main` 的精确 SHA 部署，并通过健康检查、鉴权负例和审计日志验证后，G5/G6 才可转 GO。
