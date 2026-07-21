# Dossier: Agent Runtime Write Reconciliation

| 字段 | 值 |
|---|---|
| slug | `agent-runtime-write-reconciliation` |
| 创建日期 | 2026-07-20 |
| 当前阶段 | G5 生产部署健康验证完成，旧未决 operation 已结算，等待受控 G6 |
| 状态 | deployed_runtime_paused_reconciled |
| 负责 | Codex |
| 反馈环 | Agent Runtime canary / PostgreSQL operation ledger / diet write receipt |

## S0 · 用户需求

> 继续执行

延续 Agent Runtime 控制面改造，处理单账号 canary 中暴露的未决写入，目标是在进程退出、超时和重试下仍能核对业务副作用，并避免重复写入或错误回执。

## Correction Block

- 旧假设: 单账号 canary 已完成，可继续评估扩大比例。
- 新证据: 生产出现 `worker_lease_expired_write`，Run 进入 `reconciliation_required`，熔断按设计自动暂停；对应用户意图“晚餐只吃了原记录的四分之一”还被误判为新增饮食记录。
- 影响: 原 G5/G6 只证明默认关闭部署和控制面生效，不能证明写入进程中断后的业务闭环。
- 回退点: 返回 S3/S5，保持 `canary=0%` 且 circuit paused，重新执行 G2、G3、G4、G5、G6。
- 已核对事实: 该 Run 的业务时间窗内没有新增 `diet_records`，本次事故未产生实际重复饮食记录；旧 operation 没有下游幂等标识，不能由系统自动推断后直接重放。

## S1 · Discovery

- API、Kernel、Usage 与 Runtime 已使用统一 Run identity；故障不再丢失，而是可靠进入 reconciliation。
- 业务写入前已创建 content-free `agent_tool_operations`，但 operation ID 没有传到饮食写接口。
- 饮食创建接口已经支持 `Idempotency-Key`，并用 `(user_id, client_action_id)` 唯一约束去重，可直接复用。
- recovery 目前只把未决写入转成 reconciliation，无法查询业务库确认“已写入”或“确定未写入”。
- 当前分类器只识别“修改/改成/调整”等显式词；“没吃那么多、只吃四分之一”被当成 create，而不是既有晚餐的 update。
- 生产 Uvicorn worker 在工具请求后退出，Runtime 租约与熔断正确止损；普通流量仍为 0%。

## G1 · 准入裁决

```yaml
RequirementAdmission:
  request: make managed Agent writes idempotent and reconcilable after process interruption
  classification: runtime reliability and health-data write safety
  core_loop_step: WriteIntent -> ExecutionEvent -> Receipt -> Reconcile
  first_class_objects: [WriteIntent, ExecutionEvent]
  target_surface: [Backend Agent Runtime, diet write adapter, admin runtime control]
  source_of_truth: PostgreSQL Runtime ledger plus owner-scoped business table
  safety_level: privacy_sensitive
  autonomy_tier: preserve_existing
  success_metric: interrupted managed write resolves without duplicate side effect or false success
  added_user_burden: none
  non_goals: [framework migration, full event sourcing, client protocol change, broad canary expansion]
  smallest_end_to_end_slice: diet operation idempotency -> resolver -> safe retry/replay -> verified receipt
  spec_required: reuse_existing
```

- 裁决: **PASS**。这是既有 Runtime 可靠性缺口，不新增健康建议或处方行为。

## S2 · PRD / Spec

- 复用 PRD: `docs/prd/2026-07-19-agent-runtime-control-plane.md`
- 复用 Feature Spec: `docs/specs/active/2026-07-19-agent-runtime-control-plane.md`
- 新设计: `docs/plans/2026-07-20-agent-runtime-write-reconciliation-design.md`
- 实施计划: `docs/plans/2026-07-20-agent-runtime-write-reconciliation.md`

## G2 · 可行性 + 安全压测

- 方案一，纯人工核对: 能处理当前事故，但无法满足自动恢复和快速迭代目标，拒绝。
- 方案二，重写成通用事件溯源 Runtime: 风险和范围过大，且会影响 iPhone 自闭环分支，拒绝。
- 方案三，现有模块化单体内加入幂等 transport 与资源 resolver registry: 复用业务唯一约束，按资源逐步接入，推荐。
- 隐私约束: Runtime 只保存 operation ID、有限 resource type/id、状态和 reason code；不保存食物正文、工具参数或结果正文。
- 失败约束: 未识别资源、旧 operation 或核对器异常继续保持 reconciliation，不自动重放。
- 裁决: **PASS**。

## S3 · 规划

1. 先补分类、幂等下传、核对结算和旧事故显式结算的失败测试。
2. 实现 diet scoped idempotency 与 resolver，不扩展到未验证资源。
3. 修正隐式饮食更正意图和 fast route，避免把 correction 当 create。
4. 完成 SQLite、真实 PostgreSQL、Agent 对话和饮食写入回归。
5. 安全评审、提交、合并；生产继续 paused/0%，仅重新运行单账号 Gate。

## S4 · 研发任务分解

- [x] T1 ToolSpec 声明预期资源类型，Runtime claim 在 dispatch 前持久化该类型。
- [x] T2 将 operation ID 作为作用域化 `Idempotency-Key` 传给饮食写接口。
- [x] T3 增加 diet create operation resolver 和 content-free reconciliation 结算。
- [x] T4 增加旧/未知 operation 的显式安全结算入口。
- [x] T5 修正“只吃了部分/没吃那么多”等饮食更正意图与工具路由。
- [x] T6 故障注入、并发、隐私、迁移和跨端无回归验证。
- [x] T7 多写入按稳定 lineage 分别恢复；写入轮次在回执裁决前不流出成功措辞。

## G3 · 测试闸

- SQLite Runtime 最新回归: 207 passed，3 skipped。
- SQLite stream / diet / date / intent / migration 最新回归: 159 passed；最终流式回执增量复测: 7 passed；本次定向 tool/reconciliation/migration 回归: 92 passed。
- 真实 PostgreSQL 本次 lineage/并发/核对回归: 76 passed；图片饮食事务幂等: 1 passed。
- Managed migration: 25 passed。
- 覆盖: 写前退出、写后回执前退出、同 Run 多写入重排后分别恢复、跨 attempt 参数重建、retry 计划外写入拒绝、retry 首次产生多笔写入、餐次别名归一、缺省日期的多餐记录、不同餐次与明确不同时间的多记录、同餐食物文本重述 fail closed、照片 token 丢失且文本重述 fail closed、照片确认控制字段不改变 identity、可选区分器出现/消失拒绝、等价日期/餐次/时间/参数层级在同 attempt replay、Runtime identity 与真实 diet payload 一致、历史补录日期不被 API 静默换日、旧 NULL lineage exact replay、重复同 turn、业务记录已存在、业务记录明确不存在、宽限期、未知资源保持未决、跨用户资源拒绝、人工核对审计、饮食 correction 不新增、图片 token 与 Runtime operation 双幂等、第一笔成功第二笔失败不提前显示成功文案。
- PostgreSQL migration: P0→P3 Runtime 迁移加 operation-lineage 迁移在最小旧 schema 上执行；旧行回填 exact-compatible lineage，但首次 attempt 编号保持未知，避免从已被 retry 更新的 `attempt_id` 错推；lineage 迁移重复执行无副作用，字段与唯一索引实查存在。CI 已加入相同真实 PostgreSQL 硬门。
- Live LLM 回归证据（2026-07-21）: `uv run --env-file .env --with-requirements backend/requirements.txt python scripts/harness_llm_regression_gate.py --include-live-llm --json`；`invariants` 12/12、`health_agent_core` 50/50、`orchestrator` 5/5 通过，Orchestrator 平均评分 0.92、无 regression，实际模型为 `MiniMax-M2.5`。原始 JSON 仅保存在本地 `/tmp/agent-runtime-live-eval.json`，不提交模型回答或健康正文。
- 静态闸: Ruff、Python compile、`git diff --check` 均通过。
- **裁决: PASS**。

## G4 · 安全闸

- Runtime ledger 和事件只保存 operation/run/resource 标识、状态与 reason code，不保存饮食正文、工具参数或模型回复。
- 每笔写入的跨 attempt 身份保存为顺序无关业务目标键的 SHA-256；规范化日期+餐次范围、食物身份和照片/用餐时间区分器均只保存哈希，Runtime 不保存食物名称、时间或 token 明文；参数指纹仍保持独立 SHA-256，避免字段复用或明文泄漏。
- operation 保存不可变的首次 attempt 编号，只用于区分历史计划与当前 retry 新计划，不包含健康正文。
- exact fingerprint 优先兼容旧 operation；新饮食 operation 基于与 dispatch 相同的 canonical payload 计算 fingerprint，等价表达不会在成功后误报身份冲突；retry 无法证明属于原计划的写入直接拒绝，不把模型新生成的副作用带入恢复尝试。
- 自动核对仅开放 owner-scoped `diet_record` create；不支持的资源保持 `unknown`，不自动重放。
- `verified_effect` 人工结算要求已注册资源类型、合法 ID、业务库 owner 一致，并记录管理员、验证方式和机器可读原因。
- 流式写入回复在取得可验证回执前不向用户输出成功措辞；歧义 correction 降级为选择具体记录。
- 多写入回合不使用 Turn 累计回执提前放行模型正文；第二笔失败时只展示确定性部分成功/未决说明。
- 工具异常日志只记录参数长度，不记录健康正文。
- 独立只读安全复审完成；连续关闭 canonical fingerprint、API 静默换日和照片确认控制字段三类 P1 后，最终结论无 P0/P1。
- **裁决: PASS**。

## G5 · 部署健康闸

- 生产部署（2026-07-21）: 最新主干 `0fa40389b3102bdf73fdfd5ae892ec50e526860a` 已部署；Agent Runtime 核心提交 `f6997a2bb` 与远端 bundle 隔离修复 `500ad6cfb` 均在其历史中。
- 主干 CI: `29797730524`（bundle 修复）与 `29798138723`（最终主干）均为全绿，最终主干 42/42 jobs 成功。
- 回滚证据: 部署前 PostgreSQL 备份 `/opt/health-app/backups/health_db_2026-07-21_11-31.sql.gz` 成功并通过 force-RLS 数据段完整性检查；远端环境备份为 `backend/.env.backup.20260721_113124`。
- 数据库: managed migration `20260720_180000_agent_runtime_operation_lineage` 已登记；`agent_tool_operations` 的 5 个 lineage 字段和 2 个目标索引均实查存在。
- 服务: 生产仓库位于 `main` 且 SHA 与部署目标一致；`health-backend`、`celery-worker`、`celery-beat` 均 active，公网健康接口 HTTP 200。
- 健康评分: 60/60 PASS；API、PostgreSQL、Redis、Celery 均 healthy，健康接口 12ms，API P95 7ms，最近 200 行错误率 0%。重启后 10 分钟内后端与 worker 均未发现 ERROR、CRITICAL 或 Traceback。
- 部署可靠性: 唯一远端 deploy bundle 在脚本退出后已清理；服务器旧固定路径遗留文件不再阻断发布。
- 流量约束: `AGENT_RUNTIME_MODE=off`、canary 0%；circuit 保持 `paused:reconciliation_detected`，本次部署未恢复 Runtime 流量。
- **裁决: PASS**。

## G6 · 上线验证

- 状态: **PARTIAL / PENDING**。G5 已通过，旧 `worker_lease_expired_write` operation 已通过应用服务显式结算为 `verified_no_effect`；生产不再存在 `reconciliation_required` Run/operation。
- 当前约束: Runtime 仍按安全约束关闭并保持熔断暂停；不得把部署健康或旧 operation 结算等同于受控写入闭环通过。
- 生产核验证据（2026-07-21）: `run_df30df9ec1244ae1` 已变为 `failed / reconciled_no_effect / retryable=true`；`op_0bc25120f3450a9576adad466fd62031f58810baabf67e84` 已变为 `failed / reconciled_no_effect`；rollout state 仍为 `paused / reconciliation_detected`，generation `1` 尚未 acknowledge。
- 验收: 当前旧 reconciliation 经应用服务显式结算；单账号只读和受控饮食写入均得到同一 Run/operation/receipt 链路；无重复写入、无 stale lease、无新 reconciliation 后才可人工恢复。
