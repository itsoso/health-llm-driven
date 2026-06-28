# Dossier: ConnectorPolicy 降级连接健康解释

| 字段 | 值 |
|---|---|
| slug | `connector-policy-degraded-health` |
| 创建日期 | 2026-06-28 |
| 当前阶段 | S5 实现 |
| 状态 | in_progress |
| 负责 | Codex |
| 反馈环 | backend deploy |

## S0 · 用户需求(逐字)

> 继续执行

- 上下文解释: 按 PRD/Plan/Code 对比继续推进“按 PRD 完整执行”的下一批切片。上一批已把 runtime key fact provenance 发布；本批选择剩余 A 切片中风险较低、价值清晰的 `ConnectorPolicy` 降级状态解释。
- 谁用 / 解决什么 / 现在怎么绕过(四问 Q1): 用户和前端连接中心需要知道外部数据源是否正常、是否还能使用已授权缓存、是否需要重新授权；当前 API 只暴露原始 `connection_status`、`token_status` 和 `sync_error`，每个端都要重复猜 UI 语义。

## S1 · Discovery(现状勘察)

- 已有可复用:
  - `backend/app/models/data_connection.py`: 已有 `DataConnection` / `ConsentGrant` / `ConnectorPolicy` / `ProvenanceRecord`。
  - `backend/app/services/data_connections.py`: 已有 `record_sync_result`，失败时会把连接置为 `degraded`，鉴权失败时把 token 置为 `expired`。
  - `backend/app/api/data_connections.py`: `/api/v1/data-connections/me` 已返回连接列表；`/{connection_id}/revoke` 已撤权。
  - `docs/plans/2026-06-27-health-runtime-governance-plan.md`: D0.1/D0.4 明确缺“连接健康解释”和“连接器降级策略”。
- 缺什么:
  - 序列化层没有统一的 `connection_health` 合同。
  - 前端无法直接判断 “继续只读使用缓存 / 等待重试 / 需要重连 / 已撤权阻断”。
- 硬约束:
  - 不改数据库 schema。
  - 不删除派生数据。
  - 不改变同步执行、token refresh 或 provider 调用行为。
  - 不返回 token、raw metadata 或敏感原始数据。

## G1 · 准入裁决(governance §8 RequirementAdmission)

- first_class_objects: `DataConnection`, `ConnectorPolicy`, `ConsentGrant`
- core_loop_step: Observe -> Decide 的数据可信度与可用性解释
- target_surface / safety_level / autonomy_tier: Backend data-connections API / privacy_sensitive / none
- spec_required(§8.1): 复用 `docs/plans/2026-06-27-health-runtime-governance-plan.md` D0.1/D0.4；本切片不新增写路径。
- smallest_end_to_end_slice: `serialize_data_connection()` 返回只读 `connection_health`，覆盖 healthy/degraded/revoked。
- stale_surface_to_remove: 无
- **裁决**: PASS
- 用户确认: 已由“继续执行”授权继续。

## S2 · PRD

- 链接: `docs/prd/reva-personal-health-os-prd.md`
- 引用的权威能力: 真实数据、授权、可追溯、跨端一致状态。
- 边界(不做): 不做跨端 UI、不做撤权删除、不接新 provider、不做 token 自动刷新。
- 验收 Gate: API 对 active/degraded/revoked 连接返回结构化健康解释。

## S3 · 规划

- 链接: `docs/plans/2026-06-27-health-runtime-governance-plan.md`
- 本批只做后端只读合同，为 Mobile/Mac/Web 连接中心后续展示打底。
- 长杆 / spike: 撤权后删除和多 provider refresh policy 涉及真实数据删除/外部调用，不并入本切片。

## G2 · 可行性 + 安全压测

- 评审方式: Codex self-challenge
- 硬阻断(已焊进范围): 不做删除、不做自动刷新、不扩大授权 scope。
- **裁决**: PASS

## S4 · 研发任务分解

- 跨端 API 契约:
  - `connection_health.status`: `healthy | degraded | revoked | unknown`
  - `severity`: `ok | warning | blocked`
  - `message_code`: 稳定机器码，供前端 i18n 或文案映射。
  - `can_attempt_sync`: 当前是否可尝试同步。
  - `can_use_cached_data`: 是否可继续使用已授权缓存数据做只读判断。
  - `needs_reconnect`: 是否需要用户重新授权。
  - `user_action`: `none | retry_later | reconnect`
- 任务表:
  - [x] T1 RED: 增加 active/degraded/revoked 合同测试。
  - [x] T2 GREEN: 服务层序列化 `connection_health`。
  - [ ] T3 文档回写、验证、部署和生产 smoke。

## S5 · 实现

- 委托: Codex
- 分支: `codex/rolling-runtime-next-slice`
- commit: 待提交

## G3 · 测试闸

- RED: `backend/tests/test_data_connections.py::test_connection_health_explains_active_degraded_and_revoked` 先失败于 `KeyError: 'connection_health'`。
- GREEN: 同测试通过。
- 集成闸: 待跑。
- **裁决**: 待定

## G4 · 安全闸

- 触发?: privacy_sensitive 数据源状态解释。
- 自查:
  - 只读序列化。
  - 不新增用户数据读取范围。
  - 不返回 token 或原始外部数据。
  - 撤权状态下 `can_use_cached_data=false`。
- **裁决**: 待定

## S6 · 部署

- 路由: backend-deploy
- 部署 SHA / 回滚点: 待定

## G5 · 部署健康闸

- 健康分: 待定
- prod smoke: 待定
- **裁决**: 待定

## S7 · 上线验证

- 真实路径验证: 待定

## G6 · 验证闸(人在环)

- 裁决: 待定

## S8 · 沉淀

- 待上线验证后回写计划状态。
