# Dossier: Agent Runtime Control Plane P0

| 字段 | 值 |
|---|---|
| slug | `agent-runtime-control-plane` |
| 创建日期 | 2026-07-19 |
| 当前阶段 | S3 规划 |
| 状态 | defining |
| 负责 | Codex |
| 反馈环 | PostgreSQL/SQLite 集成测试 / Agent SSE 回归 / backend deploy |

## S0 · 用户需求

> 如果影响不大，那你就单独做Agent Runtime的改造，重新review代码，形成一个新的规划，目标是提升Agent的这个能力。

> 开始

- 使用者: Mobile、Web、Mac、Watch、语音等入口后的统一小巴 Agent。
- 解决的问题: 一次 Agent 运行缺少统一身份、持久状态和会话级并发控制，导致观测、恢复和写入核对分散在消息元数据与进程内状态中。
- 当前绕过方式: `client_turn_id` 重放、消息 `meta` checkpoint、PostgreSQL advisory lock 和请求内后台任务共同维持可靠性。

## S1 · Discovery

- API 层为 Usage 生成 `run_id`，Kernel 在未接收该 ID 时再次生成，消息、Usage 与 Kernel trace 不能稳定关联。
- `AgentExecutor` 已有写前 checkpoint、写后 receipt、重复 client turn replay 和 uncertain fail-closed；这些能力必须迁移复用，不能平行重写。
- `AgentConversationService` 只按 `(user_id, client_turn_id)` 加锁，不阻止同一会话的不同 turn 并发写历史。
- `ToolGateway` 当前只做 preflight；schema、写入判断、执行和回执处理仍散落在 Executor。
- SSE 使用无界进程内队列；客户端断开后任务继续，但进程退出后没有一等 Run 可接管。
- `codex/local-first-private-task2` 未修改后端 Agent Runtime。严格本地模式禁止隐式云请求，因此本地执行不创建服务端 Run；未来显式云增强仅通过可选 origin 关联字段接入。
- 旧分支 `codex/reva-runtime-phase0` 实际是多端产品能力集合，`codex/rolling-runtime-next-slice` 内容已被主干吸收；都不作为本次实现基线。

## G1 · 准入裁决

```yaml
RequirementAdmission:
  request: establish a first-class Agent Runtime control plane without replacing the existing AgentExecutor
  classification: core runtime reliability and write-path governance
  core_loop_step: Capture -> Reason -> WriteIntent -> ExecutionEvent -> Receipt -> Review
  first_class_objects: [ExecutionEvent, WriteIntent]
  target_surface: [Backend Agent Runtime, all cloud Agent entry points]
  source_of_truth: PostgreSQL Agent Run Ledger plus existing conversation messages
  safety_level: privacy_sensitive
  prescription_or_causal_verdict: false
  autonomy_tier: preserve_existing
  verification_window: immediate run terminal state plus crash/concurrency fault injection
  success_metric: one canonical run identity and no duplicate or interleaved execution under retries
  added_user_burden: none
  non_goals: [framework migration, microservice split, full event sourcing, local-only run upload]
  smallest_end_to_end_slice: canonical run ID -> durable run row -> one active run per conversation -> terminal state
  stale_surface_to_remove_or_archive: duplicate API and Kernel run identity generation
  spec_required: yes
```

- 裁决: **PASS**。
- 用户确认: 2026-07-19 已确认按 P0-A/P0-B 开始。

## S2 · PRD / Spec

- PRD: `docs/prd/2026-07-19-agent-runtime-control-plane.md`
- Feature Spec: `docs/specs/active/2026-07-19-agent-runtime-control-plane.md`
- 边界: 不替换 AgentExecutor；不实现 ToolSpec 全量迁移；不在本批实现进程死亡后的自动恢复；不让严格本地健康正文进入服务端。
- 未决问题: 无。

## S3 · 规划

- 设计: `docs/plans/2026-07-19-agent-runtime-control-plane-design.md`
- 实施计划: 设计基线提交后按 writing-plans 协议生成并回填。
- 第一里程碑: canonical RunContext、Run Ledger、会话级准入与兼容适配。
- 第二里程碑另立 Gate: ToolSpec/operation idempotency/reconcile 后再做进程重启恢复。

## G2 · 可行性 + 安全压测

- 评审方式: 当前代码逐路径复审 + iPhone 本地优先分支契约对照。
- 已焊入规划的硬约束:
  - Runtime 表不保存健康正文、工具参数或工具结果正文。
  - schema 迁移为 PostgreSQL/SQLite managed migration 对。
  - 所有接口为 additive，旧客户端不需要升级。
  - strict-local 不创建服务端 Run；显式云增强才可携带 `local_execution_id`。
  - 既有 checkpoint/replay 行为保持兼容。
- 裁决: **PASS**，用户已确认 P0 范围。

## S4 · 研发任务分解

- [ ] T1 定义 Runtime 状态机、模型、managed migrations 和仓储服务。
- [ ] T2 统一 API、Kernel、Usage、消息回执的 canonical `run_id`。
- [ ] T3 加入同一会话单 active Run 的数据库准入与 duplicate client turn replay。
- [ ] T4 接入 Executor terminal 状态并保持既有 SSE/消息行为。
- [ ] T5 完成 SQLite 单测、PostgreSQL 并发/迁移测试、安全评审和文档同步。
- 并发策略: 独立 worktree `codex/agent-runtime-control-plane`，不改主工作区未提交文件。

## S5 · 实现

- 分支: `codex/agent-runtime-control-plane`，基线 `origin/main@1cd38e3e4`。
- 基线验证: 126 项 Agent event/conversation/replay/completion 测试通过。

## G3 · 测试闸

- 待实施完成后填写。

## G4 · 安全闸

- 触发: Agent 写路径、健康数据运行元数据、数据库 schema。
- 待 producer-reviewer 复审。

## S6–S8

- 尚未进入部署阶段。
