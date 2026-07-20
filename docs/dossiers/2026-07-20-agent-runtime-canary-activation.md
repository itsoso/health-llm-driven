# Dossier: Agent Runtime 单账号生产灰度启用

| 字段 | 值 |
|---|---|
| slug | `agent-runtime-canary-activation` |
| 创建日期 | 2026-07-20 |
| 当前阶段 | S5 实现 / 首轮灰度纠偏 |
| 状态 | shipping |
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
- [ ] T4 通过 `deploy.sh -e` 启用 `canary + 0% + 1 allowlist`。
- [ ] T5 完成真实只读 Run / same-turn replay 验证。
- [ ] T6 完成可回滚非临床写入 / receipt replay / cleanup 验证。
- [ ] T7 完成 pause fallback、取消或中断恢复验证。
- [ ] T8 观察完整窗口并裁决保留 canary 或回滚 `off`。

## 首轮灰度纠偏记录

- 触发: `canary + 0% + 1 allowlist` 首次启用后，内部只读验证请求被结算为 `mutation_without_tool`；Runtime 正确把 Run 标记为失败，没有工具调用或业务副作用。
- 原因: 请求中有两处“不要”，意图分类器只检查每个否定词第一次出现的位置，错过了紧邻“修改”的第二处“不要”，把否定写操作误判为肯定修改指令。
- 即时处置: 按安全不变量立即通过 `deploy.sh -e` 将生产恢复为 `AGENT_RUNTIME_MODE=off`；服务和公网健康恢复正常，recovery 在 `off` 下保持禁用。
- 修复基线: 否定判断必须遍历同一语句内全部否定词和目标操作位置；生产原句须在分类器层判为非写入，并在 Executor 层结算为成功且零工具调用。
- 返回阶段: 回到 S5 修复和 G3 回归；修复提交、CI、代码部署以及干净聚合窗口全部通过前，不重新启用 canary。

## G3 · 测试闸

- 继承控制面交付证据: SQLite `196 passed, 3 skipped`；真实 PostgreSQL `170 passed`；真实 LLM `12/12 + 50/50 + 5/5`。
- 新增回归: 生产原句的分类器测试与 Executor 零工具成功结算测试。
- 新鲜证据: 意图识别、写入防误报、流式回复、Turn 结算和 Runtime API/服务共 `158 passed`。
- 本次仍需新增的新鲜证据: 管理接口、生产只读/写入回执、重放、暂停与恢复、完整窗口聚合指标。
- **当前裁决: PASS。** 修复通过本地测试闸，生产 Gate 仍须从 `off` 重新开始。

## G4 · 安全闸

- 触发: 认证、生产写路径、健康数据隐私。
- 要求: 管理员鉴权、无 PII/PHI Runtime ledger、可回滚非临床测试写入、无人工 DB 修改。
- **当前裁决: 待生产演练后复核。**

## S6 / G5 · 部署与健康

- 路由: `backend-deploy`，仅允许 `deploy.sh -e` 同步本地受控 `.env`。
- 回滚: 将 `AGENT_RUNTIME_MODE=off` 后再次 `deploy.sh -e`。
- 健康门: 服务 active、公网 health healthy、聚合监控可用、Celery recovery/evaluator 正常。
- 当前生产状态: `off`，服务与公网健康正常；首轮 canary 已安全回滚。
- 当前状态: 待修复提交、CI 和代码部署后重跑。

## S7 / G6 · 上线验证

- 真实路径: 一个内部账号的 normal Agent API；客户端版本和 strict-local 路径不变。
- 成功条件: 单一 Run identity、无重复输出、无重复副作用、无 reconciliation、无 stale lease、暂停/恢复符合设计。
- 首轮结果: Runtime 正确记录失败并未产生工具副作用，但请求意图误判导致用户路径失败。
- 当前状态: 首轮证据保留，等待修复部署后以新 `client_turn_id` 重新验证。

## S8 · 沉淀

- 完成后记录生产模式、观察窗口、聚合计数、回滚结果、主干提交和 CI；不记录用户 ID 或健康内容。
