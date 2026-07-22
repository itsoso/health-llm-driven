# Security Hardening Dossier

| 字段 | 值 |
|---|---|
| slug | `security-hardening` |
| 创建日期 | 2026-07-21 |
| 当前阶段 | S8 服务器生产验证完成，原生安全发版待执行 |
| 状态 | server-live-native-release-pending |
| 负责 | Codex |
| 范围 | 2026-07-21 只读审计确认的安全问题 |

- 明确例外: 保持当前 JWT 两年有效期。该例外不允许 URL token、脚本可读存储、缺少撤销控制或 scope 绕过。

## G1 · Requirement Admission

- 裁决: PASS。该工作保护 L3/L4 健康与凭据数据，直接支撑 Health OS 信任边界，不新增产品 surface。

## G2 · Feasibility And Risk

- 裁决: PASS。采用分批交付，先关闭生产匿名读写；兼容 URL 保留，但必须经过当前用户或管理员授权。后续批次需通过各自安全测试才可进入部署 Gate。

## Current Evidence

- 服务器生产版本为 `da4984771307f6eb7c6e217f278a324d9ed7c895`，对应 CI `29905540429`，`43/43` jobs 成功。
- 未认证访问 `/auth/me`、个人饮食记录和 Garmin 设备路由均返回 `401`；用户 3 的内部签名正例返回 `200`。
- Backend、Celery Worker 与 Beat 均以 `health-app` 非 root 用户运行；应用数据库连接角色为 `health_app_runtime`。
- API 与前端监听仅位于 `127.0.0.1:8000`、`127.0.0.1:30001`；公网直连两个端口均超时，HTTPS 入口健康。
- 发布备份完成 force-RLS 数据检查、231 表恢复演练、age 加密站外归档 SHA-256 与 HMAC 真实性验证。
- Mobile/Mac Keychain 变更仍需原生签名发版，服务器上线不能替代该安全边界。

## Gate Ledger

| Gate | State | Evidence |
|---|---|---|
| G1 Admission | GO | Security/privacy requirement |
| G2 Feasibility | GO | Compatibility-preserving staged design |
| G3 Tests | GO | main CI `29867658752` 在 commit `cee9e70aa` 上 `43/43` jobs 成功；最终文档提交的 CI `29868838292` 重跑后同样 `43/43` 成功；锁定版 OpenAPI 类型、部署契约、FastAPI 0.139 路由漂移闸和 live LLM 回归均通过 |
| G4 Safety review | GO | 第五轮独立复审确认无 P0/P1 代码 blocker；rollback containment 与统一 ORM bootstrap 均关闭 |
| G5 Deploy health | GO | 精确 SHA 部署；备份、231 表恢复演练、站外加密归档真实性校验、最小权限角色、非 root systemd 与 `60/60` 健康检查均通过 |
| G6 Production verification | GO (server) | 公网健康、鉴权正反例、pgvector `895/895`、loopback 监听、依赖完整性和发布后日志均通过；原生 Keychain 发版单列为残余项 |

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
- 2026-07-22: 第四轮独立安全复审确认上述路径大部分关闭，但指出 cleanup 的 `systemctl stop ... || true` 仍可能吞掉停服失败，以及生产启动额外注册的 `BowelTimer` 未进入统一模型 bootstrap，裁决 NO-GO。
- 2026-07-22: 第四轮 2 个 P1 已修复：常规停服失败后强制终止并逐服务读取 `ActiveState=inactive`，无法证明时以专用 containment failure 退出且部署端要求人工隔离；`BowelTimer` 迁入 `app.models`，生产与回滚探针共享统一 ORM 注册入口。
- 2026-07-22: 第五轮独立安全复审裁决 G4 GO：无 P0/P1 代码 blocker；故障注入确认 cleanup stop 失败可收口到 inactive，彻底失败时返回 70 并要求人工隔离；模型层与完整 API runtime 均注册同一 196 张表。
- 2026-07-22: 首次 main CI `29865182529` 的 `type-drift` 失败；根因是本地旧 FastAPI/`python-multipart` 生成类型与仓库锁文件版本不同。使用 CI 锁定的 FastAPI 0.139.2、Starlette 1.3.1、`python-multipart` 0.0.32 重新生成 Web/Mobile API 类型；新 CI 未绿前 G3 保持 RED。
- 2026-07-22: 同一 CI 的 `backend-test-d` 仍要求未引用的远端 bundle 路径，已改为断言安全的单引号形式并禁止未引用形式；`backend-test-h-j` 依赖旧 FastAPI 展平后的 `routes`，已改为校验生产 OpenAPI 最终路由表。部署测试 `8 passed`，完整 h-j 分片 `695 passed`。
- 2026-07-22: 使用固定假数据和隔离临时 PostgreSQL 账本执行 live LLM 回归；`invariants 12/12`、`health_agent_core 50/50`、`orchestrator 5/5` 通过，Orchestrator 平均分 `0.92`、无 regression，实际模型 `MiniMax-M2.5`。临时数据库已删除，原始 JSON 仅保存在本地 `/tmp/security-live-llm-eval.json`。
- 2026-07-22: 修复提交 `cee9e70aa` 的 main CI `29867658752` 完成，`43/43` jobs 成功；G3 转 GO。一次性 `HARNESS_LIVE_LLM_EVAL_CONFIRMED` 仓库变量已在质量闸消费后删除，未来高风险改动不会被永久放行。
- 2026-07-22: 最终文档提交 `d8c993e81` 的 CI `29868838292` 首次运行仅 `voice-watch` 分片在 GitHub runner 上两次达到 600 秒截止时间；相同锁定依赖和测试顺序在本地 `161 passed`，单独 `watch_summary` 为 `18 passed`。只重跑失败 job 后 `voice-watch` 用时 1 分 59 秒成功，整条 CI `43/43` jobs 成功；未放宽分片超时闸。
- 2026-07-22: 生产数据库完成 owner/migrator/runtime 角色拆分；runtime DML 探针通过且 DDL 被拒绝。Backend、Celery Worker、Beat 切换为 `health-app` 非 root 用户，独立 canary 与自动回滚预案验证通过。
- 2026-07-22: 将 pgvector DDL 迁入受控 migration，运行时仅做存在性检查；生产迁移应用后重建 `895` 条 dense vectors，向量后端为 `pgvector:text-embedding-v4`，无权限降级。
- 2026-07-22: 发布后发现 Celery 冷启动时 `fuel_strategist` 与 Orchestrator 循环导入；先以新进程回归测试复现，再将 Orchestrator 公共 runner 改为惰性导出。相关 `103` 项测试通过，live LLM 回归 `12/12`、`50/50`、`5/5`，平均分 `0.96`、无 regression；一次性 CI 确认变量已删除。
- 2026-07-22: 精确 SHA `da4984771` 部署完成；备份 `/var/backups/health-app/database/health_db_2026-07-22_17-14-19_3726896.sql.gz` 为 40 MB，恢复 231 表，站外 age 对象哈希与 HMAC 验真。生产健康分 `60/60`、skills `22/22`。
- 2026-07-22: G6 复核通过：四个匿名访问负例均为 `401`，用户 3 正例为 `200`；数据库角色 `health_app_runtime`；依赖无冲突；公网 8000/30001 不可直连；发布后饮食定时任务实际运行 4 次，Traceback、循环导入、权限错误、pgvector 降级均为 0。

## G3 Verification Evidence

- Backend broad CI shard `e-g`: `1043 passed, 1 skipped`。
- Backend focused SQLite security suite: `117 passed`。
- Backend focused PostgreSQL security suite: `73 passed`，覆盖 API Key、报告上传、家庭代管撤权与畸形 claim、旧路由租户隔离和 Web Session。
- Backup/deploy/infrastructure/rollback script tests: `26 passed`；相关 shell 脚本 `bash -n` 通过。
- Runtime schema compatibility probe: SQLite `5 passed`，PostgreSQL `5 passed`；覆盖统一模型 bootstrap、`bowel_timers` 缺失失败、当前应用完整 ORM metadata、缺表失败与读写语句兼容。
- Frontend: `297 passed`；`next build` 成功；ESLint `0 errors`（45 个既有 warning）。
- Mobile: TypeScript `tsc --noEmit` 成功；Expo lint `0 errors`（103 个既有 warning）；设计 token ratchet 通过。
- 此前本批次已完成 Mobile `2052` tests、Mac Core `448` tests、Frontend/Mobile/npm 与 Python dependency audits，未引入依赖漏洞。
- `ruff` 未定义名/语法闸、`git diff --check`、secret scan、system-map/doc drift 均通过。
- CI 锁定依赖复现：部署契约 `8 passed`；完整 `h-j` 分片 `695 passed`；Web/Mobile generated API types 确定性重生成且两端一致。
- Voice/Watch 稳定性复核：完整分片 `161 passed`，`watch_summary` 单文件 `18 passed`；最终 main CI 重跑 `43/43` jobs 成功。
- Live LLM synthesis gate：`invariants 12/12`、`health_agent_core 50/50`、`orchestrator 5/5`，平均分 `0.92`、无 regression。

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

## G4 Round 4 Remediation Ledger

| 第四轮问题 | 修复 | 验证 |
|---|---|---|
| P1 cleanup 停服失败被吞掉 | 常规 stop 失败后对非 inactive 单元执行 SIGKILL、再次 stop/reset-failed，并逐个读取 systemd `ActiveState`；仍无法证明 inactive 时返回 containment failure，部署端不再声称服务已阻断 | `test_release_rollback.py` 故障注入第二次 stop 失败，最终三个服务 inactive；`test_deploy_script.py` 禁止虚假文案 |
| P1 schema probe 漏掉 API 模块内 ORM | 将 `BowelTimer` 从 `app.api.nfc` 迁入 `app.models.bowel_timer` 并加入统一模型导出；删除生产入口的 API 副作用注册 | 子进程 bootstrap 必须注册 `bowel_timers`；缺少该表时 probe 必须失败；NFC `14 passed` |

## Residual Follow-ups

- JWT 两年有效期是用户明确接受的例外；仍需维持 URL token 禁止、撤销校验和 scope 隔离。
- Mobile/Mac 的 Keychain 改动需要原生签名发版；OTA 不能改变原生安全边界。
- 更广泛的 PostgreSQL RLS 仍需先完成后台任务租户上下文设计；本轮已完成 runtime/migrator/owner 最小权限拆分，不在未知上下文下直接开启全库 RLS。
