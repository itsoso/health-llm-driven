# Dossier: Agent Runtime 单账号生产灰度启用

| 字段 | 值 |
|---|---|
| slug | `agent-runtime-canary-activation` |
| 创建日期 | 2026-07-20 |
| 当前阶段 | S8 单账号生产灰度已验证 |
| 状态 | complete |
| 负责 | Codex + 用户 |
| 反馈环 | backend config deploy + production Agent API + aggregate monitoring |

## S0 · 用户需求（逐字）

> 开始
>
> 继续执行

- 谁用 / 解决什么 / 现在怎么绕过: Reva 内部 anchor 用户需要先验证一等 Agent Runtime 是否能在真实云端请求中稳定承担 Run、工具回执、暂停和恢复；当前生产仍以 `off` 使用旧 unmanaged 路径。
- 锚点用户相关性: 先只覆盖一个已验证内部账号，不触达普通用户。

## S1 · Discovery

- 已有可复用:
  - `docs/plans/2026-07-20-agent-runtime-canary-design.md`: 已批准的稳定分桶、全局熔断、聚合监控和逐级放量设计。
  - `backend/app/services/agent_runtime_rollout.py`: `off/canary/enforce`、0% + allowlist、自动 pause、手工 resume。
  - `backend/app/api/monitoring.py`: 管理员聚合状态与 pause/resume API。
  - `deploy.sh`: 唯一生产配置同步、服务重启和健康闸入口。
- 已部署基线: 控制面代码和迁移已上线，生产有效模式为 `off`；控制行 `active`，此前验证 generation 为 `0/0`。
- 缺什么: 真实管理接口演练、内部身份核验、0% 单账号准入、读/写/中断回执验证和完整观察窗口。
- 硬约束:
  - iPhone strict-local 不调用该云端 Runtime，协议不变。
  - 不保存 prompt、回复、健康正文、工具参数或工具结果。
  - 不直接改生产数据库或服务器 `.env`。
  - 本轮不进入 1% 普通用户流量。

## G1 · 准入裁决

- first_class_objects: `ExecutionEvent`、`WriteIntent`、operational Run / ToolOperation ledger。
- core_loop_step: Agent 请求执行、写入回执、异常恢复和结果验证。
- target_surface / safety_level / autonomy_tier: Backend Agent Runtime / operational safety / internal manual gate。
- spec_required: 复用 `docs/specs/active/2026-07-19-agent-runtime-control-plane.md`，无新客户端或健康写入契约。
- smallest_end_to_end_slice: `off` 基线 → pause/resume 演练 → `0% + 1 internal allowlist` → 读写回执 → 恢复 → 观察。
- stale_surface_to_remove: 无；未管理路径保留为硬回滚。
- **裁决: PASS。** 用户已连续指示“开始 / 继续执行”，授权按既定设计进入启用 Gate。

## S2 / S3 · 设计与规划

- 设计: `docs/plans/2026-07-20-agent-runtime-canary-design.md`。
- 启用计划: `docs/plans/2026-07-20-agent-runtime-canary-activation.md`。
- 边界: 不改 Runtime 架构、不改客户端、不自动 resume、不做百分比放量。
- 未决问题: 无；若无法核验安全内部账号或可回滚写入对象，则该任务 fail-closed 停止。

## G2 · 可行性 + 安全压测

- 评审方式: Codex challenge，复用已完成的 P3 独立复审和真实 PostgreSQL 并发验证。
- 风险控制:
  - `off` 是硬回滚；`canary=0` 防止哈希用户进入。
  - allowlist 仅存配置，不进入聚合 API 或 rollout audit。
  - pause/resume 通过管理员 API 留有限 reason code 审计。
  - 任何未决写入优先进入 reconciliation，自动触发 pause，系统不自动恢复。
- **裁决: PASS。** 只允许在下列 Gate 全绿后保留单账号 canary；否则立即回 `off`。

## S4 · 执行任务

- [x] T1 记录 `off` 生产聚合基线和服务健康。
- [x] T2 核验一个既有内部账号，不输出 PII。
- [x] T3 在 `off` 下完成管理员 pause/resume 幂等演练。
- [x] T4 通过 `deploy.sh -e` 启用 `canary + 0% + 1 allowlist`。
- [x] T5 完成真实只读 Run / same-turn replay 验证。
- [x] T6 完成可回滚非临床写入 / receipt replay / cleanup 验证。
- [x] T7 完成 pause fallback、取消或中断恢复验证。
- [x] T8 观察完整窗口并裁决保留 canary 或回滚 `off`。

## 首轮灰度纠偏记录

- 触发: `canary + 0% + 1 allowlist` 首次启用后，内部只读验证请求被结算为 `mutation_without_tool`；Runtime 正确把 Run 标记为失败，没有工具调用或业务副作用。
- 原因: 请求中有两处“不要”，意图分类器只检查每个否定词第一次出现的位置，错过了紧邻“修改”的第二处“不要”，把否定写操作误判为肯定修改指令。
- 即时处置: 按安全不变量立即通过 `deploy.sh -e` 将生产恢复为 `AGENT_RUNTIME_MODE=off`；服务和公网健康恢复正常，recovery 在 `off` 下保持禁用。
- 修复基线: 否定判断必须遍历同一语句内全部否定词和目标操作位置；生产原句须在分类器层判为非写入，并在 Executor 层结算为成功且零工具调用。
- 返回阶段: 回到 S5 修复和 G3 回归；修复提交、CI、代码部署以及干净聚合窗口全部通过前，不重新启用 canary。

## 第二轮灰度执行证据

- 主干与部署: 修复提交 `85606de94816ecb13f8212035c1b5c2f8e8ff101` 已进入 `main`；CI run `29728258183` 成功完成全部任务；后端以 Runtime `off` 部署，健康度 `60/60`，随后才启用 `canary + 0% + 1 allowlist`。
- 准入与恢复: allowlist 账号命中 `canary_allowlist`，非名单账号命中 `canary_not_selected`；恢复扫描返回 `recovered=0`，熔断器保持 `active`。
- 只读重放: 新 Turn 产生一个 `succeeded` Run、一个 `succeeded` Attempt、零工具操作和三个连续事件；重放返回同一 Run、Attempt 和助手消息，Runtime 事件仅包含允许的 `input_seq/status` 键。
- 验收脚本纠偏: 首次数据库核对错误地按原始 `client_turn_id` 查消息，忽略消息表使用 `user_id:client_turn_id` 的用户域存储键，因此把已绑定消息误报为缺失。系统按硬规则先回 `off`；根因确认后使用 `AgentConversationService` 的正式查询契约重验通过，再恢复单账号 canary。该次不是 Runtime 或业务请求失败。
- 可逆写入: 通过正常 Agent API 创建唯一一次性测试提醒，得到一个 `smart_reminder` 已验证回执；同 Turn 重放没有第二次副作用；随后通过第一方删除接口取消，最终仅一条已取消测试对象。
- 暂停与恢复: 管理接口暂停后，历史 managed Run 仍可查询；新 Turn 完整回退 unmanaged 路径、消息正常持久化且 Runtime 表无对应 Run；聚合指标干净后手工恢复为 `active`。
- 取消: 一条只读 managed Run 在执行中收到取消请求，最终 Run/Attempt 均唯一结算为 `cancelled`；请求停止、助手消息为零、写副作用为零、无 reconciliation 或 stale active Run。

## 观察窗口前的环境同步纠偏

- 发现: API 已进入 canary 时，Celery 定时恢复任务仍返回 `status=disabled`。根因不是 Runtime 状态机，而是 `deploy.sh -e` 只重启了后端和前端，没有重启 `celery-worker` / `celery-beat`，导致同一生产版本内运行配置不一致。
- 即时处置: 停止观察窗口并将 `AGENT_RUNTIME_MODE` 回滚到 `off`；确认 API 和 Celery 都处于关闭语义后才开始修复，没有带着监控盲区继续灰度。
- 修复: 提交 `1472398b2dd751534dea0f41988bed51ff1412f5` 让环境同步统一重启后端、Celery worker、Celery beat 和前端；新增部署契约测试，验证环境同步不会遗漏 Runtime 后台进程。
- 重新启用: 主干 CI run `29730971672` 的首次 `backend-test-c` 因既有超大分片在 `conversation_starters` 后两次耗尽 600 秒保护而失败；失败分片重跑后 572 项全部通过，最终 41 个任务全部成功。随后先以 `off` 部署代码，再通过修复后的 `deploy.sh -e` 启用 `canary + 0% + 1 allowlist`。
- 生效验证: API、Celery worker 和 beat 均读取到 canary；恢复任务从关闭态的 `disabled` 变为连续 `ok`，且保持 `recovered=0 / failed=0 / reconciliation_required=0`。

## G3 · 测试闸

- 继承控制面交付证据: SQLite `196 passed, 3 skipped`；真实 PostgreSQL `170 passed`；真实 LLM `12/12 + 50/50 + 5/5`。
- 新增回归: 生产原句的分类器测试与 Executor 零工具成功结算测试。
- 新鲜证据: 意图识别、写入防误报、流式回复、Turn 结算和 Runtime API/服务共 `158 passed`。
- 精确 CI 分片复验: Agent Executor `153 passed`；主干 CI run `29728258183` 成功完成全部任务。
- 部署契约回归: 环境同步必须重启后端和两个 Celery 服务的聚焦测试 `7 passed`，`bash -n deploy.sh` 与 `git diff --check` 通过。
- 最终主干闸: 修复提交 `1472398b2dd751534dea0f41988bed51ff1412f5` 的 CI run `29730971672` 在失败分片重跑后 41/41 成功。
- 生产证据: 管理接口、只读/写入回执、同 Turn 重放、暂停/恢复、取消和完整窗口聚合指标均已通过。
- **当前裁决: PASS。** 自动化、生产功能路径和完整观察窗口均已通过。

## G4 · 安全闸

- 触发: 认证、生产写路径、健康数据隐私。
- 要求: 管理员鉴权、无 PII/PHI Runtime ledger、可回滚非临床测试写入、无人工 DB 修改。
- 结果: Runtime ledger 未保存 prompt、回复、工具参数或工具结果；可逆写入只使用非临床测试提醒并已取消；全过程未直接修改生产业务行。
- **当前裁决: PASS。**

## S6 / G5 · 部署与健康

- 路由: `backend-deploy`，仅允许 `deploy.sh -e` 同步本地受控 `.env`。
- 回滚: 将 `AGENT_RUNTIME_MODE=off` 后再次 `deploy.sh -e`。
- 健康门: 服务 active、公网 health healthy、聚合监控可用、Celery recovery/evaluator 正常。
- 当前生产状态: `canary + 0% + 1 allowlist`，熔断器 `active`；后端、Celery worker/beat 和主公网入口健康。
- 部署证据: 生产提交与 `main` 一致，部署健康度 `60/60`，Skills manifest `22/22`；环境同步明确重启后端、Celery worker/beat 和前端，恢复扫描无待处理 Run。
- **当前裁决: PASS。**

## S7 / G6 · 上线验证

- 真实路径: 一个内部账号的 normal Agent API；客户端版本和 strict-local 路径不变。
- 成功条件: 单一 Run identity、无重复输出、无重复副作用、无 reconciliation、无 stale lease、暂停/恢复符合设计。
- 首轮结果: Runtime 正确记录失败并未产生工具副作用，但请求意图误判导致用户路径失败。
- 第二轮结果: 只读重放、可逆写入回执和清理、pause fallback、恢复、取消结算均通过；普通用户流量仍为 0%。
- 最终观察: 2026-07-20 17:59:30 至 18:15:21（Asia/Shanghai）共 16 个逐分钟样本全部通过；三类服务、本地/公网健康、灰度配置、熔断器、失败、reconciliation、stale 和恢复任务新鲜度始终满足不变量。
- 窗口审计: 18 次恢复结果全部为 `ok`，`disabled=0`、非 `ok=0`、worker Runtime error=0、backend Runtime error=0；最终 15 分钟聚合为 `succeeded=1 / failed=0 / reconciliation=0 / stale=0`。
- **当前裁决: PASS。** 保留 `canary + 0% + 1 internal allowlist`，不进入普通用户百分比放量。

## S8 · 沉淀

- 最终生产模式: `canary + 0% + 1 internal allowlist`；普通用户仍走 unmanaged 路径，iPhone strict-local 路径不变。
- 主干: Runtime 否定意图修复 `85606de94816ecb13f8212035c1b5c2f8e8ff101`；环境同步修复 `1472398b2dd751534dea0f41988bed51ff1412f5`。
- 回滚路径已真实演练: 将模式切为 `off` 后通过 `deploy.sh -e` 同步并统一重启后端和 Celery；不依赖直接数据库或服务器配置修改。
- 观察和验证只保存聚合运行证据，不记录用户 ID、prompt、回复、健康正文、工具参数或工具结果。
