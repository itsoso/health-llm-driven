# Dossier: Agent Runtime Control Plane P0

| 字段 | 值 |
|---|---|
| slug | `agent-runtime-control-plane` |
| 创建日期 | 2026-07-19 |
| 当前阶段 | S5 实现与验证完成 |
| 状态 | ready_for_integration |
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
  target_surface: [Backend Agent Runtime, first-party /agent conversation paths]
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
- 实施计划: `docs/plans/2026-07-19-agent-runtime-control-plane.md`
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

- [x] T1 定义 Runtime 状态机、模型、managed migrations 和协调服务。
- [x] T2 统一 API、Kernel、Usage、消息回执的 canonical `run_id`。
- [x] T3 加入同一会话单 active Run 的数据库准入与 duplicate client turn replay。
- [x] T4 接入 Executor terminal 状态，覆盖 live、GenUI 和 starter pregen 路径并保持既有 SSE/消息行为。
- [x] T5 完成 SQLite、真实 PostgreSQL 并发测试、迁移测试、隐私约束、文档同步和安全复审。
- 并发策略: 独立 worktree `codex/agent-runtime-control-plane`，不改主工作区未提交文件。

## S5 · 实现

- 分支: `codex/agent-runtime-control-plane`，已 rebase 到 `origin/main@f9d298031`，包含最新 iPhone local-first 饮食自闭环与附件图片 AIGC 分流。
- 基线验证: 126 项 Agent event/conversation/replay/completion 测试通过。
- 新增 content-free `agent_runs`、`agent_run_attempts`、`agent_tool_operations`、`agent_run_events`，带状态 CHECK、client-turn/input-seq/active-run 唯一约束。
- `AgentRuntimeCoordinator` 负责 canonical identity、会话级准入、状态转换、消息绑定和 allowlist 事件；Runtime 表不存 prompt、回复、健康正文或原始工具参数/结果。
- `/agent/stream`、`/agent/send`、GenUI shortcut、已命中的 starter pregen 使用同一 Run/Attempt identity；API、Kernel trace 和 LLM usage 不再各自生成 Run ID。
- 同一 client turn 的失败重试复用 logical Run 并创建新 Attempt；会话归属在准入前 owner-scope 校验，Run 生命周期与事件序号在 PostgreSQL 行锁/SQLite 本地锁下串行。
- active duplicate 只观察、不启动第二个 Executor；仅显式标记 retryable 的失败可建立新 Attempt，旧 Attempt 由 `current_attempt_id` fencing 禁止再改写 Run。
- 新会话在 `request_persisted` 后立即绑定 Runtime，而不是等最终回答，关闭首轮生成期间的会话并发窗口；锁顺序固定为 client turn -> conversation -> Run lifecycle。
- Siri、微信和离线 starter-pregen producer 尚未接统一 durable adapter，明确推迟到 P1，不计入本次 P0 完成面。
- `agent_runtime_mode=off` 默认只贯通身份，不写新表、不改变准入；`enforce` 才启用 Ledger 与会话级单 active Run。strict-local iPhone 路径不调用云 API，因此不创建服务端 Run。
- 既有 client-turn replay、写前 checkpoint、写后 receipt 与 uncertain fail-closed 保持为业务副作用真源；P0 未复制或替换。

## G3 · 测试闸

- **PASS**，证据:
  - 最新主干 Agent Runtime/API/Executor/会话/饮食照片回归: `202 passed, 6 warnings`，exit 0。
  - managed migrations 全量: `24 passed, 5 warnings`，exit 0。
  - 真实 PostgreSQL Runtime 模型/状态机/并发重试: `40 passed, 6 warnings`，exit 0；临时测试库已删除。
  - PostgreSQL managed migration 在最小既有 schema 上直接执行并创建 4 张 Runtime 表，exit 0；临时库已删除。
  - iPhone local-first 数据与饮食界面: `7 passed`，exit 0。
  - 最新主线附件图片 AIGC 分流 + Runtime 交叉回归: `124 passed, 6 warnings`，exit 0。
  - `ruff check`（本次改动文件，排除仓库既有 `models/__init__.py` 未导出告警）与 `git diff --check`: PASS。
  - `scripts/check_doc_drift.py`: PASS；`backend/scripts/check_dossier_consistency.py`: 64 份 dossier PASS。
- 已验证不变量: owner-scoped conversation/client turn、conversation 单 active Run、连续 input sequence、terminal 后释放准入、terminal retry 新 Attempt、同 turn 并发事件串行、非法状态拒绝、合法字段健康正文拒绝、快捷路径异常后不遗留 active Run。

## G4 · 安全闸

- 触发: Agent 写路径、健康数据运行元数据、数据库 schema。
- producer 自审: Runtime payload 仅允许有限标量键和 ASCII operational token；消息只保存外键，健康正文仍在既有 owner-scoped message store；strict-local 无隐式上传。
- 独立 reviewer 初审发现的 P0（会话归属、terminal retry、同 turn 并发）和 shortcut active-run 清理均已修复并新增 SQLite/PostgreSQL 回归。
- 最终 producer 复审补出并修复“带/不带 conversation 的同 turn 重试锁分裂”和“新会话最终回答前未绑定”两个竞争窗口；隐私、owner scope、失败会话恢复和 strict-local 边界复核通过。
- 裁决: **PASS**。`agent_runtime_mode` 继续默认 `off`，本分支不直接部署；合并与灰度启用另走部署 Gate。

## S6–S8

- 尚未进入部署阶段。
