# Security Hardening Dossier

| 字段 | 值 |
|---|---|
| slug | `security-hardening` |
| 创建日期 | 2026-07-21 |
| 当前阶段 | S6 独立安全复审 |
| 状态 | review |
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
| G4 Safety review | FINAL RE-REVIEW PENDING | 第三轮仅余回滚验证 1 个 P1；已补失败停服闭环、旧代码数据库读写探针、鉴权负例与 Celery 存活探针，等待最终独立复审 |
| G5 Deploy health | BLOCKED | 未满足生产角色、真实异地恢复演练、基础设施安装和原生 Keychain 发版前不进入部署 |
| G6 Production verification | NOT ENTERED | 尚未部署，不作上线成功声明 |

## Delivery Log

- 2026-07-21: Read-only audit completed; overall verdict NO-GO.
- 2026-07-21: User accepted the current JWT lifetime and authorized all other findings to be fixed in severity order.
- 2026-07-22: P0 匿名路由、API key scope、Agent 写入授权、跨端凭据存储、上传与解析配额、备份与基础设施配置已完成本地实现；部署仍受 G3-G5 约束。
- 2026-07-22: 首轮独立安全复审裁决 NO-GO，指出报告上传资源耗尽、药盒 OCR 自动写入、备份实例歧义、异地备份弱校验、部署 SHA 漂移 5 个 P1。
- 2026-07-22: 5 个 P1 已修复：报告页数/字节/像素/线程配额 fail-loud；药盒 OCR 改为可编辑草稿并显式确认；备份绑定 PostgreSQL host/port；异地对象逐字节 SHA-256 校验；部署强制 `main` 与精确 SHA。
- 2026-07-22: 第二轮独立安全复审仍为 NO-GO，指出代管授权撤销未即时生效、自动回滚假成功 2 个 P1，以及上传总请求体、异地对象与 sidecar 可协同替换 2 个 P2。
- 2026-07-22: 第二轮问题已修复：代管 JWT 每次请求重验账号状态与家庭授权；回滚移动到精确 SHA 并要求旧代码在当前向前数据库结构上通过健康检查；报告请求在 Pydantic 前限制为 10 MB且预处理移出事件循环；异地备份增加源 SHA/密文 SHA/对象名的 HMAC 清单。
- 2026-07-22: 第三轮独立安全复审关闭代管授权、请求体、HMAC 清单问题，但因回滚失败后服务可能保持运行，且 `/health` 不能证明旧代码与当前数据库结构兼容，裁决仍为 NO-GO。
- 2026-07-22: 第三轮 P1 已修复：回滚任一运行时探针失败都会重新停止 Backend、Celery Worker 与 Beat；旧代码对其全部 ORM 表执行列存在性、零行读取和零行写权限/语句兼容探针，同时校验未认证请求为 401、三个服务均 active；删除无法取证的 `database_schema=forward-compatible` 声明。预检失败不会误停仍在运行的生产服务，且 `.env` 仅由应用配置解析，不作为 shell 脚本执行。

## G3 Verification Evidence

- Backend broad CI shard `e-g`: `1043 passed, 1 skipped`。
- Backend focused SQLite security suite: `117 passed`。
- Backend focused PostgreSQL security suite: `73 passed`，覆盖 API Key、报告上传、家庭代管撤权与畸形 claim、旧路由租户隔离和 Web Session。
- Backup/deploy/infrastructure/rollback script tests: `24 passed`；相关 shell 脚本 `bash -n` 通过。
- Runtime schema compatibility probe: SQLite `3 passed`，PostgreSQL `3 passed`；覆盖当前应用完整 ORM metadata、缺表失败与读写语句兼容。
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

## G4 Round 2 Remediation Ledger

| 第二轮问题 | 修复 | 验证 |
|---|---|---|
| P1 代管 Token 绕过账号禁用/授权撤销 | 每次请求重新校验发起账号与目标账号状态、同组关系和编辑授权；claim 不一致直接 403 | `test_web_session_security.py`；SQLite + PostgreSQL |
| P1 自动回滚假成功 | 独立回滚 runner 停止写进程、移动 `main` 到精确旧 SHA、重装旧依赖、重启并验证健康；失败保持阻断且不输出成功 | `test_release_rollback.py` 动态临时 Git 仓库测试 |
| P2 报告请求在 schema 前可达百 MB | ASGI middleware 在 FastAPI/Pydantic 前把该路由请求限制为 10 MB；原始有效载荷限制 7 MB；图片/PDF预处理进入有界线程池 | `test_family_health.py` |
| P2 远端对象与 sidecar 可协同替换 | 独立 `BACKUP_INTEGRITY_KEY` 生成 HMAC 清单，绑定源哈希、密文哈希和对象名；模拟协同替换测试必须失败 | `test_backup_security.py` |

## G4 Round 3 Remediation Ledger

| 第三轮问题 | 修复 | 验证 |
|---|---|---|
| P1 回滚健康失败后旧服务仍可能运行 | EXIT trap 在切换代码后任一失败路径重新停止 Backend、Celery Worker 与 Beat；预检阶段失败不触碰运行中服务 | `test_release_rollback.py` 覆盖成功、健康失败停服、预检失败不停服 |
| P1 `/health` 无法证明数据库向前兼容 | 使用旧 SHA 的代码和虚拟环境导入全部 ORM model，检查声明表/列，并在回滚事务中对每张表执行零行 `SELECT` 与 `UPDATE`；同时验证 `/auth/me` 返回 401 和三个 systemd 服务 active | `test_runtime_schema_compatibility.py` 在 SQLite 与真实 PostgreSQL 均 `3 passed`；回滚脚本集成测试 |
| P2 回滚脚本执行 `.env` | 删除 shell `source .env`，由旧代码的 Pydantic 配置只读解析；恶意 shell 行回归测试不得执行 | `test_release_rollback.py` |

## Production Blockers

- PostgreSQL 仍未完成按在线请求、后台任务、迁移/备份拆分的最小权限角色；广泛 RLS 需要先完成后台任务租户上下文设计，不能在不了解运行时角色的情况下直接开启。
- 需要在真实异地存储执行下载、解密、临时 PostgreSQL 恢复和查询验证；本地脚本测试不能替代灾备演练。
- 生产环境需生成并安全配置至少 32 字符的独立 `BACKUP_INTEGRITY_KEY`；不得与 age recipient/private identity 共用。
- Nginx/systemd/UFW 等生产配置需要实际安装后检查有效配置与端口暴露。
- Mobile/Mac 的 Keychain 改动需要原生签名发版；OTA 不能改变原生安全边界。
- 必须从干净 `origin/main` 的精确 SHA 部署，并通过健康检查、鉴权负例和审计日志验证后，G5/G6 才可转 GO。
