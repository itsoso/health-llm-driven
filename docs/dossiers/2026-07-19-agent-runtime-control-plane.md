# Dossier: Agent Runtime Control Plane

| 字段 | 值 |
|---|---|
| slug | `agent-runtime-control-plane` |
| 创建日期 | 2026-07-19 |
| 当前阶段 | P2 Runtime Resilience 已完成，待合并/灰度 Gate |
| 状态 | in_progress |
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
- P1 设计: `docs/plans/2026-07-19-agent-runtime-tool-control-design.md`
- P1 实施计划: `docs/plans/2026-07-19-agent-runtime-tool-control.md`
- P2 设计: `docs/plans/2026-07-19-agent-runtime-resilience-design.md`
- P2 实施计划: `docs/plans/2026-07-19-agent-runtime-resilience.md`

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

- 分支: `codex/agent-runtime-control-plane`，已 rebase 到 `origin/main@3c73756ae`，包含最新 iPhone local-first 饮食自闭环、附件图片 AIGC 分流和症状/鼻炎写入安全修复。
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

- Draft PR: [#250](https://github.com/itsoso/health-llm-driven/pull/250)。
- 尚未进入部署阶段；Runtime 保持默认 `off`，远端 CI 全绿并合并前不部署、不灰度。

## P1 · Tool Control

- [x] ToolSpec Registry 覆盖全部 provider schema 和 specialist tool。
- [x] `ToolGateway.execute()` 成为验证后请求的唯一策略与执行入口。
- [x] Executor 改为 Registry adapter 分发，移除手写工具名分支。
- [x] enforce 模式接入 content-free `AgentToolOperation` 状态机。
- [x] verified fingerprint 不重复执行，uncertain operation 不自动重试。
- [x] SQLite/PostgreSQL、健康写入、图片饮食与 strict-local 交叉回归通过。
- 实现摘要:
  - `ToolSpec` 统一工具 effect、adapter、timeout、write receipt 与 mixed-action 分类；旧策略常量从 Registry 派生，避免新增工具漏接安全和观测。
  - `ToolGateway.execute()` 在策略裁决后最多分发一次；Executor 保留既有参数恢复、症状授权、参数校验、业务 adapter 和安全标注，不改变客户端或 iPhone strict-local 协议。
  - Runtime enforce 模式在业务写前 claim content-free operation；verified 结果可直接 replay，executing/uncertain 不自动重试。重复 claim 不改写原 owner 状态，避免原写入成功后无法登记回执而产生“先失败、后成功”。
  - Runtime 写指纹归一 `health_record` 类型别名和 `intervention_cycle` 确认字段；确认前后仍是同一业务操作身份，但不改变既有 turn-local 确认 checkpoint。
  - Executor 被取消或超时时，已 claim 的写操作先落 `reconciliation_required` 再传播取消；干预周期 start/update/cancel 返回保留人话消息的结构化回执，避免真实成功被误判为缺少回执。
  - 会话归属校验与 active Run 判断现在位于同一 conversation admission lock 内；SQLite StaticPool 以 Engine 弱引用绑定的数据库级可重入锁串行 Runtime 访问，Engine 销毁后锁自动回收，PostgreSQL 继续使用细粒度 advisory transaction lock。
  - operation identity 绑定 `tool_name + effect_class + fingerprint`；Runtime 表和事件只保存摘要标识、状态和资源引用，不保存健康正文、参数或结果。
- P1 验证证据:
  - SQLite Tool Registry/Gateway/Runtime/Executor/receipt/health manage 回归：`330 passed`。
  - SQLite 对话 API、图片生命周期、拍照饮食草稿和饮食卡片交叉回归：`173 passed`。
  - 变基到最新主干后 Tool Registry/Gateway/Runtime/干预周期 + 症状/鼻炎安全组合回归：`335 passed`；包含 SQLite Engine 锁弱引用回收回归。
  - 图片、对话、饮食交叉回归复跑：`114 passed`。
  - Mobile strict-local egress、身份、执行事件和本地饮食闭环：7 suites / `26 passed`。
  - 真实 PostgreSQL Runtime 状态机、并发、API 与 operation ledger 全集：`58 passed`；变基后并发 + operation ledger 定向复跑：`22 passed`，命令与临时库清理均 exit 0。
  - `ruff check` 本次 Python 文件：PASS；`git diff --check`：PASS。
  - `scripts/check_doc_drift.py` 在重新生成 `docs/_generated/system-map.json` 后 PASS；Dossier consistency：64 份 PASS。
- 明确推迟: 业务端点跨 Run 幂等键、资源级自动 reconcile、进程死亡恢复扫描、durable stream cursor、取消/supersede 和 parent/child Run。
- Rollout: Runtime 继续默认 `off`；P1 不部署、不灰度启用。

## P2 · Runtime Resilience

- [x] Run/Attempt worker lease、heartbeat 与 worker fencing。
- [x] 持久化 cancel request、deadline 与终态前二次裁决。
- [x] 进程中断与用户取消分离；未由用户取消的 worker interruption 为可重试失败。
- [x] 过期 Run 扫描与安全结算；只读 Run 可重试，未决写入进入 reconciliation，不自动重放。
- [x] 兼容 P1 无租约 active Run；给予宽限期后由扫描器结算，避免永久占用会话。
- [x] 仅包运行状态的持久事件游标，不保存 prompt、回复、token delta 或健康正文。
- [x] 有界 SSE buffer 与断开感知，客户端断开后不再无界累积内存。
- [x] owner-scoped Run 状态/事件接口和取消接口。
- [x] Celery 每分钟恢复入口，仅 `agent_runtime_mode=enforce` 时生效。
- [x] running Attempt lease partial index，避免历史 Attempt 增长后每分钟全表扫描。
- [x] 写回执资源类型和 ID 格式由 ToolSpec 注册；健康写入只接受正整数 ID，AIGC 草稿只接受既有 `aigc_confirm_<32 hex>` 格式。
- 终态不变量:
  - cancel/deadline 对 succeeded、failed、waiting completion 都执行二次裁决。
  - 已验证写入不会因任务中断或晚到 cancel 向用户伪报失败。
  - 未决写入遇到用户取消或系统中断都进入 reconciliation，不自动重试。
  - 心跳清理异常只记录，不覆盖主执行结果，也不跳过 SSE sentinel/会话关闭。
  - 本地租约截止点在数据库 `mark_running` / `renew_lease` 调用前记录；心跳延迟启动、慢续租或 control settlement 失败都不能把 worker 生命周期延长到数据库租约之后。
  - 心跳数据库暂时不可用时在剩余租约内重试；会话关闭失败或无法在租约到期前恢复时立即取消 owner task。
  - 旧无租约 Run 的恢复宽限不少于 deadline + 120 秒部署排空窗口，默认 420 秒。
- P2 验证证据:
  - SQLite Runtime/API/Executor/ToolSpec 定向与跨链路回归: `817 passed`。
  - managed migration 全集: `25 passed`。
  - 真实 PostgreSQL Runtime 状态机、并发、API、工具账本与恢复: `142 passed`。
  - PostgreSQL P0 + P2 migration 在最小旧 schema 上执行，P2 migration 重复执行 PASS；字段和 running partial index 实查存在。
  - Agent 对话、Executor、ToolGateway/Registry、SSE、拍照饮食、症状/鼻炎与干预周期交叉回归包含在上述 `817 passed` 中。
  - Mobile strict-local egress、身份、本地模型与饮食闭环: 7 suites / `24 passed`。
- 合并最新主干后的集成复核（2026-07-19）:
  - 真实 PostgreSQL Runtime 模型、服务、并发、API、工具账本与恢复: `116 passed`；ToolGateway/Registry、Executor 状态事件与写回执: `155 passed`。两次均使用一次性 `test` 数据库并在退出后删除。
  - SQLite managed migration: `25 passed`；Runtime/Executor/对话/工具/饮食/症状/鼻炎/移动预检组合回归: `292 passed`。
  - 高风险 LLM 真实回归: invariants `12/12`、health_agent_core `50/50`、orchestrator `5/5`，orchestrator 平均分 `0.94`；评估 SQLite 未建 usage 日志表只触发既有旁路告警，suite exit 0。
  - Web: `47` 个 test files / `263 passed`，Next 生产构建与 lint exit 0；仅输出仓库既有 warning。
  - Mobile: TypeScript 与设计 token ratchet PASS；`279` 个 suites / `1982 passed`、`1 skipped`。新增静态 `expo-video` Jest 映射，修复最新主干 AIGC 视频卡片导致的并行测试原生模块加载失败。
  - macOS: `swift build` PASS；HealthAgentMacCoreTests `416` executed、`0 failures`、`1 skipped`。
  - OpenAPI 使用 CI 同版生成器重建后，与 Mobile/Web 已提交类型逐字节一致；阻塞型 Ruff、系统地图漂移、Dossier 一致性和 `git diff --check` PASS。
  - Web `npm ci` 仍报告 `19` 个历史依赖漏洞（含 `2 critical`）；未在 Runtime PR 中强制升级依赖，另列安全治理，不作为 Runtime 代码回归隐藏。
- 独立复审发现的终态竞态、心跳启动/续租边界、心跳清理覆盖、中断语义、无租约旧 Run、索引、回执隐私和多态资源类型缺口均已增加回归并修复。
- Rollout: `agent_runtime_mode` 继续默认 `off`；本分支不部署、不发 OTA/TestFlight、不改 iPhone strict-local 协议。
