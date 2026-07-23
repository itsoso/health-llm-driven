# Dossier: Agent Runtime 全量接管与发布稳定化

| 字段 | 值 |
|---|---|
| slug | `agent-runtime-full-rollout` |
| 创建日期 | 2026-07-22 |
| 当前阶段 | G6 上线验证 |
| 状态 | in_progress |
| 负责 | Codex + 用户 |
| 反馈环 | production Runtime ledger + iOS Simulator + release gates + Mobile OTA |

## S0 · 用户需求

> Agent runtime 直接跑全量用户 模拟器登录我管理员账号直接做测试 其他按顺序改造

- 使用者: 所有云端 Agent 对话用户，以及负责发布和回滚的维护者。
- 目标: 将已经完成 canary 验证的 Agent Runtime 切换为全量接管；用管理员账号验证 Mobile Agent 真实交互；按 P0 到 P2 补齐发布、恢复、去重和可观测性缺口。
- 不变量: 不记录 prompt、回复、健康正文、工具参数或结果；不改变 strict-local iPhone 的本地优先边界；不绕过正式 API 或直接修改业务数据。

## S1 · Discovery

- Runtime 已具备一等 Run、Attempt、ToolOperation、事件游标、会话串行化、幂等写入回执、租约恢复、取消和自动熔断。
- canary 已完成真实只读、可逆写入、重放、取消、暂停和恢复验证；全量切换不需要客户端协议变更。
- Mobile Agent 已有回前台恢复、权威历史接管、状态码 200 断流恢复、终态卡片去重和多阶段自动滚底。
- 发布入口此前相互独立；部署、OTA、OTA 回滚和 TestFlight 可以并发运行，存在不同提交或渠道相互覆盖的风险。
- 当前主干设计令牌 Gate 有一处既有原始色值回归，必须先恢复基线后才能发布 OTA。

## G1 · 准入裁决

```yaml
RequirementAdmission:
  request: move the cloud Agent Runtime from canary to enforce for all users and verify the administrator Mobile flow
  classification: runtime reliability and release safety
  core_loop_step: Capture -> Reason -> Tool -> Receipt -> Recover -> Review
  first_class_objects: [ExecutionEvent, WriteIntent]
  target_surface: [Backend Agent Runtime, Mobile Agent]
  source_of_truth: PostgreSQL Agent Run Ledger and owner-scoped conversation messages
  safety_level: privacy_sensitive
  prescription_or_causal_verdict: false
  autonomy_tier: preserve_existing
  verification_window: production smoke plus rolling aggregate circuit evaluation
  success_metric: all selected cloud Turns use one durable Run without duplicate output or side effects
  added_user_burden: none
  non_goals: [framework migration, microservice split, strict-local upload, direct production data edits]
  smallest_end_to_end_slice: enforce admission -> durable Run -> terminal receipt -> client recovery -> aggregate circuit
  stale_surface_to_remove_or_archive: none
  spec_required: reuse_existing
```

- **裁决: PASS。** 复用 Agent Runtime Control Plane 的已批准 spec 和 rollout 设计；本轮只推进既有 Runtime 的全量运行与发布安全。

## S2 / S3 · 设计与计划

1. 生产配置切换为 `enforce`，统一重启 API、Celery worker 和 Celery beat。
2. 通过正式 Agent API 完成管理员只读 Run，并核对 Run、Attempt、消息和事件共用 canonical identity。
3. 审计 Mobile Agent 的历史恢复、断流、回前台、自动滚底、错误和重复卡片行为。
4. 为部署、OTA、OTA 回滚和 TestFlight 建立跨 worktree 的共享发布锁。
5. 在管理员 iOS 模拟器执行登录、连续对话、切前后台和最终滚底验证。
6. 主干提交后顺序执行后端部署与 Mobile OTA，重新核验 Runtime 配置、服务和 OTA manifest。

## G2 · 可行性与风险压测

- `off` 仍是硬回滚，`paused` 是自动或管理员熔断状态；不删除 unmanaged 兼容路径。
- Celery 每分钟运行过期 Run 恢复、未决 ToolOperation 核对和 rollout 自动暂停评估。
- 发布锁使用 Git common dir，因此同一仓库的 main 和其他 worktree 共用同一互斥域；死亡进程锁可恢复，父发布任务的受控子任务可重入。
- 发布入口只能串行，不把健康正文写入锁或日志。
- **裁决: PASS。** 风险均有 fail-closed 或可逆路径。

## S4 · 研发任务

- [x] T1 全量 `enforce` 配置同步与多进程服务健康核验。
- [x] T2 管理员生产 API smoke、Run ledger 与消息回执核对。
- [x] T3 Runtime 状态机、并发、恢复、rollout 和工具账本回归。
- [x] T4 Mobile Agent 状态恢复、滚底、错误与重复输出回归。
- [x] T5 共享发布锁及入口契约测试。
- [x] T6 修复 Mobile 设计令牌基线回归。
- [ ] T7 管理员 iOS 模拟器端到端验证与截图。
- [x] T8 提交、推送、后端部署、Mobile OTA 与上线复验。

## S5 · 实现与当前证据

- 生产 Runtime 配置为 `mode=enforce`，熔断器为 `active`；后端、Celery worker 和 Celery beat 均为 active。
- 管理员正式 `/agent/send` smoke 返回成功；Run、Attempt、conversation message 和 Runtime events 使用同一 durable identity，未产生工具副作用。
- 最近聚合窗口内失败、reconciliation 和 stale active Run 均为零；窗口内无新终态 Run 时延分位为空，属于无样本而非错误。
- `scripts/release_lock.sh` 为全部变更型发布入口提供原子互斥、死亡 owner 恢复和受控子任务重入。
- `AIGCMediaJobCard` 的错误文本颜色改用 `revaSemantic.risk.fg`，恢复设计令牌 ratchet。
- 管理员模拟器已经使用 Release 构建安装并启动；当前仅受 macOS 锁屏阻挡，未绕过账号认证或注入测试 token。
- 管理员模拟器正常账号登录接口返回 `200` 后仍跳回手机号登录页。生产日志确认首批受保护请求未携带 Bearer Token，触发全局 `401` 清理会话；根因是登录成功后的 React 会话切换与 SecureStore 逐请求读取之间存在竞态。
- Mobile 认证层现先同步安装进程内 Token，再异步双写 SecureStore 与共享 keychain；请求层优先使用进程内 Token，冷启动恢复时重新灌入，退出时同步清空，并拒绝把 Web Cookie 会话占位值当作原生 Bearer Token。
- 上下文餐食图片写入现遵循单写入者不变量：结构化视觉结果在回答模型运行前完成唯一一次 owner-scoped 写入；模型随后重复调用 `health_record(diet)` 或 `health_manage(diet/update)` 时只重放该记录的已验证回执，不再发起第二次业务写入。模型误选历史餐次 ID 时同样拒绝修改旧记录并回放本轮记录；同一 source message 在 Executor/进程重建后仍由数据库幂等键重放同一个记录和卡片。
- 主干 CI `29968072427` 在精确提交 `28c9e04bc765bbdd989c5202e36ff60d6186bbea` 上 `43/43` 任务通过。
- 同一提交已完成前后端生产部署；后端部署健康度 `60/60`，公网 API、数据库、Redis、Celery 均 healthy。
- Mobile production OTA 已发布并核验，runtime version `1.3.2`，group `ef03a27a-57bb-4d99-a2ae-b632b5cdd506`，iOS update `019f8c5e-56c8-726a-aeab-c77885edd63a`。

## G3 · 测试闸

- Agent Runtime 模型、API、并发、恢复、rollout 和工具操作：`208 passed, 3 skipped`。
- Mobile Agent hooks、历史、滚底、今日重点、composer 和卡片 registry：`147 passed`；聊天页面交互另有 `37 passed`。
- Mobile TypeScript：PASS。
- Mobile 账号、手机号、AuthProvider、登录页面、Token 存储与请求拦截聚焦回归：`45 passed`；TypeScript 与 lint PASS（lint 仅保留既有 warning）。
- Mobile design token ratchet：PASS，原始色值回到既有基线。
- 发布锁、部署入口和 Mobile 快速反馈脚本：`30 passed`，包含从仓库外启动发布脚本的路径回归。
- 上下文餐食单写入回归按 TDD 验证：新增的无份量重复更新和错误历史 ID 更新测试在修复前均准确失败；修复后相关 4 项通过，进程重建重放场景只保留 1 条 `DietRecord` 和 1 份回执/卡片。
- 受影响的 Agent Executor、回执、上下文餐食与 Runtime 回归：`313 passed, 4 skipped`；API 生命周期用隔离 SQLite 配置验证，未依赖或修改本机生产数据库角色。
- 零成本 Harness：`invariants 12/12`、`health_agent_core 50/50`，无 regression、无真实模型调用。
- 用户于 2026-07-23 明确授权真实模型回归；使用固定金标与隔离 SQLite 执行 live Harness：`invariants 12/12`、`health_agent_core 50/50`、真实 `orchestrator 5/5`，Orchestrator 平均分 `0.94`、无 regression，实际模型 `MiniMax-M2.5`。原始 JSON 仅保存在本地 `/tmp/agent-runtime-contextual-meal-live-eval.json`，未提交模型正文或健康数据。
- 所有修改 shell 入口 `bash -n`：PASS。
- `git diff --check`：PASS。
- 主干 CI `29968072427`：`43/43` jobs PASS。
- 上下文餐食单写入提交 `d5cc11c8c50adf10b6ef49293e2993450007007f` 的主干 CI `30002618781`：PASS。真实模型变更闸仅在该次重跑期间使用一次性仓库变量，运行进入终态后变量已删除并确认不存在。
- **裁决: PASS。** 最终提交前会重新执行受修改影响的聚焦集合。

### 主干 CI 纠偏

- 首次发布控制提交触发的主干 CI 继承了三个此前提交已经存在的红灯；按 Gate 规则没有继续部署。
- Mobile design token 的单个原始色值由本轮改为语义 token，ratchet 恢复通过。
- Agent fallback 已正式向 `_stable_fallback_provider` 传入失败 provider 以离开故障域，旧测试 mock 仍使用单参数签名；测试契约更新后与真实调用一致。
- `duration_seconds` 运动去重测试未像 reps 用例一样固定 `created_at`，慢 CI runner 会跨过生产 1 秒窗口；测试现固定首条记录时间，验证业务去重而不是 runner 速度。
- OpenAPI 类型由旧 FastAPI 环境生成；使用 CI 和 requirements 的同版 FastAPI 重新生成 Mobile/Web 类型，两个文件逐字节一致。
- 纠偏验证: 两项后端聚焦回归 `13 passed`，Mobile/Web TypeScript 均 PASS，Ruff 和 `git diff --check` PASS。
- Frontend 生产依赖审计识别出 `next@16.2.10` 的 high 漏洞；`next` 与 `eslint-config-next` 已精确升级到补丁版 `16.2.11`。
- 安全补丁验证: `npm audit --omit=dev --audit-level=high` 为 0 漏洞，Vitest `300 passed`，Next 生产构建和 ESLint 均 PASS（仅保留既有 warning）。

## G4 · 安全闸

- Runtime ledger 继续只存 content-free 运行元数据；本 dossier 不记录用户 ID、账号、prompt、回复或健康正文。
- 管理员模拟器使用正常登录，不建立测试后门，不读取或打印凭据。
- 发布锁只记录本机 pid、发布类型、随机 token 和开始时间。
- 全量接管不改变健康建议、药物、症状或 Safety Guardian 的业务判定。
- **裁决: PASS。**

## S6 / G5 · 部署与健康

- 已通过干净 `main` 副本执行完整 `deploy.sh -y`；数据库备份、恢复演练、站外加密归档和强制 RLS 完整性检查均通过。
- 前后端线上提交为 `28c9e04bc765bbdd989c5202e36ff60d6186bbea`；后端、Celery worker、Celery beat 均 active，公网依赖健康。
- 生产 Runtime 为 `mode=enforce`、circuit `active`；最近 15 分钟失败、reconciliation 和 stale active Run 均为零。
- Mobile production OTA manifest 已核对提交、channel、runtime version、group 和 update ID，并保留前一 known-good group 供回滚。
- 2026-07-23 从最新且干净的 `main` 重新执行后端生产部署；部署提交 `8538816de4e6080a9c4eb8d4459f92d2efc2d63b` 包含上下文餐食单写入修复，其主干 CI `30005194767` 已通过。
- 本次部署再次通过数据库备份、强制 RLS 完整性检查、231 张表临时恢复演练与站外加密归档；受控迁移无待执行项，后端与 Celery 重启成功，健康评分 `60/60`，远端 SHA 与 `main` 一致。公网 `/api/v1/health` 返回 API、PostgreSQL、Redis、Celery 全部 healthy。
- **裁决: PASS。**

## S7 / G6 · 上线验证

- 已完成: 正式生产 API smoke、durable Run/Attempt/message/event 核对、聚合 circuit 核对、精确 SHA 部署和 OTA manifest 核对。
- 待完成: 管理员模拟器登录后的连续对话、后台切换恢复、自动滚底和截图。
- **当前裁决: IN PROGRESS。** 不以锁屏状态冒充客户端验证成功。

## 回滚

- Runtime: 将 `AGENT_RUNTIME_MODE=off` 后通过 `deploy.sh -e -y` 同步；或先用管理员控制面暂停新 managed Run。
- Backend: 使用根目录部署脚本部署已验证的前一提交。
- Mobile OTA: 使用 `scripts/mobile-ota-rollback.sh production --confirm` 回滚到 manifest 中的前一 group。
- 发布冲突: 共享发布锁会拒绝第二个并发任务；异常退出后的死亡 owner 锁会在下一次发布时安全清理。

## S8 · 沉淀

- 发布提交与生产 SHA: `28c9e04bc765bbdd989c5202e36ff60d6186bbea`。
- CI: `29968072427`，`43/43` jobs PASS。
- 上下文餐食单写入修复生产 SHA: `8538816de4e6080a9c4eb8d4459f92d2efc2d63b`；CI `30002618781` 与最新主干 CI `30005194767` 均 PASS；后端健康评分 `60/60`。
- OTA: group `ef03a27a-57bb-4d99-a2ae-b632b5cdd506`；iOS update `019f8c5e-56c8-726a-aeab-c77885edd63a`。
- 待 G6 全部通过后补充管理员模拟器截图和最终裁决。
