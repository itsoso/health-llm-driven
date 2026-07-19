# Agent Runtime Control Plane P0 PRD

> Status: approved for P0-A/P0-B
> Updated: 2026-07-19
> Dossier: `docs/dossiers/2026-07-19-agent-runtime-control-plane.md`

## 1. Problem

Reva 已有稳定的 Agent Loop、能力策略、工具恢复和写入回执，但“运行”不是一等对象。API、Kernel、LLM Usage 和消息持久化分别维护运行身份与状态；客户端断线依靠进程内后台任务继续，进程丢失后只能由下一次请求基于消息元数据推断是否接管。

这使以下问题难以可靠回答：一次请求是否仍在运行、是否已执行工具、是否需要用户确认、是否可以安全重试、哪个模型与工具调用属于同一次运行、同一会话是否出现并发交错。

## 2. Product Outcome

建立模块化单体 Runtime 控制面，让每次云端 Agent 运行具有唯一身份、持久状态、明确的尝试次数和会话级准入，同时保持现有 AgentExecutor、客户端 API 和用户体验不变。

## 3. Users And Surfaces

- Mobile、Mac、Web、Watch、语音等云端 Agent 入口。
- 后端运维和质量系统，用于关联延迟、模型用量、工具调用和最终回执。
- iPhone strict-local 模式不属于云端 Runtime；只有用户显式授权云增强时才建立服务端 Run。

## 4. P0 Scope

### Included

- Canonical `run_id` 在 API 边界生成一次并贯穿 Kernel、Executor、Usage、事件和消息元数据。
- 一等 Run Ledger：Run、Attempt、Tool Operation、健康正文无关的 milestone Event。
- 同一 `client_turn_id` 幂等返回同一逻辑 Run。
- 同一 conversation 同时最多一个 active Run，防止历史交错。
- Run 终态与现有 assistant message、completion status、write receipt 对齐。
- 可选 origin 关联字段，为未来显式 local-to-cloud 调用留接口。

### Excluded

- 不迁移 LangGraph、Temporal 或其他 Agent 框架。
- 不拆 Java/TS/Python 多服务。
- 不做完整 Event Sourcing，不持久化 token 流。
- 不在 P0 自动恢复进程死亡的 Run；P0 只需把恢复所需状态做成一等对象。
- 不在 P0 全量重构 ToolGateway 或下传所有业务幂等键。

## 5. Required Invariants

1. 一个 `client_turn_id` 只创建一个用户输入和一个逻辑 Run。
2. API、Kernel、LLM Usage、审计事件和完成消息使用同一 `run_id`。
3. 同一会话不会有两个 active Run 并发写入消息历史。
4. 每个 Run 最终处于 terminal 或明确的 `waiting_for_user` 状态。
5. Runtime Ledger 不保存健康正文、图片内容、原始工具参数或结果正文。
6. 已出现写前 checkpoint 或 uncertain 写状态的 turn 不因 Runtime 接管而重复执行。
7. 旧客户端不传任何新增字段时行为不变。
8. strict-local 执行不产生服务端 Run。

## 6. Success Metrics

- Run ID 关联缺失率为 0。
- duplicate client turn 的额外业务副作用为 0。
- 同会话并发测试中历史交错为 0。
- Run terminal/waiting 覆盖率达到 100%，异常退出有明确 error code。
- Runtime 事件和日志敏感正文泄漏测试为 0 命中。
- 现有 Agent Runtime 回归测试零退化。

## 7. Rollout

### 2026-07-19 Implementation Correction

- `off`（默认）：canonical Run/Attempt ID 已贯通 API、Executor、Kernel 和用量统计，但不写 Run Ledger、不启用新准入。
- `enforce`：写 Run Ledger，同时启用 conversation active-run 准入。
- 不实现“写 Ledger 但不阻断”的 shadow 档。active-run 数据库唯一约束本身就会阻断并发；绕过约束会让观察数据失真。
- GenUI 与 starter pregen 的确定性快捷回复也属于云端对话回合，必须获得同一套 Run 身份；strict-local iPhone 执行仍不创建服务端 Run。
- kill switch 可回退到 `off`；数据库迁移保持 additive，既有 Ledger 只读保留。
