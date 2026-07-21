# Dossier: Agent 多药合并确认与可信写入

| 字段 | 值 |
|---|---|
| slug | `agent-medication-batch-confirmation` |
| 创建日期 | 2026-07-21 |
| 当前阶段 | G4 已通过；等待 G5 显式发布批准 |
| 状态 | shipping · implementation complete, not deployed |
| 负责 | Codex |
| 反馈环 | Backend pytest/PostgreSQL / Mobile Jest / Web Vitest+build / Mac Swift / Agent chat / WriteIntent / MedicationLog / SafetyGuardian |

## S0 · 用户需求

> 系统变弱智了，怎么办？Agent越改造越差了

生产截图中的精确输入是“记录服用两种胃药：伊托必利 替普瑞酮 各一粒”。系统耗时约 27 秒、执行多轮工具后，却回复无法判断记录类型和值，既没有正确呈现待确认状态，也没有完成记录。

用户接受推荐路线：保留用药人工确认，先修状态机，再补多药合并确认、实际服量、幂等和失败真实性；不做整版回滚。

## S1 · Discovery

- `health_record(medication)` 已返回 `[NEEDS_CONFIRMATION]`，Agent Kernel 也登记 pending confirmation。
- 回归提交把“是否调用写工具”替换成“是否已有写回执”；正常待确认没有回执，因此在两处被通用缺参文案覆盖。
- 无回执流式缓冲本身是正确的，能阻止只调用查询工具后模型谎称“已记录”；不能简单恢复成任意 tool count。
- 现有 medication 工具与 intake classifier 只表达单 item，原句会成为一个合并药名；executor 的日志 POST 还丢失 `actual_dosage`。
- 现有跨轮确认信任模型提交 `confirmed=true`，无法证明用户确认的是上一轮同一组参数。
- 既有 `WriteIntent.confirm` 已有 owner-scoped 原子认领和事务回滚骨架，可扩展为可信批次计划。

## G1 · 准入裁决

- 分类：bugfix + medical-boundary product change。
- 一等对象：`WriteIntent`、`ExecutionEvent`；事实真源是 `MedicationLog`。
- 自治等级：`manual_confirm`，不得升级。
- 最小闭环：明确多药原话 → 合并确认 → 原子写入 → 逐项回执 → 安全筛查。
- 非目标：处方、剂量建议、同服判断、自由文本全覆盖。
- **裁决：PASS**。修复既有记录闭环，且不新增医疗建议权力。

## S2 · PRD / Spec

- PRD：`docs/prd/reva-personal-health-os-prd.md`
- Feature Spec：`docs/specs/active/2026-07-21-agent-medication-batch-confirmation.md`
- 实施计划：`docs/plans/2026-07-21-agent-medication-batch-confirmation.md`

## G2 · 可行性 + 安全压测

- 方案一，回滚近期 Agent 改造：会同时丢掉“无回执不放行成功话术”的安全修复，拒绝。
- 方案二，确认后让模型重放两个 `health_record`：模型可自报 confirmed、参数会漂移，且两次 HTTP 写不能保证原子，**NO-GO**。
- 方案三，保留无回执缓冲，pending confirmation 独立收口；多药使用服务端冻结的 WriteIntent，由同一事务执行并返回逐项回执，采用。
- 硬约束：owner/conversation/source message 绑定；items 冻结；永不自治；同源唯一；同槽异量冲突；核心失败全回滚；日志/metrics 不含药名剂量。
- **裁决：PASS WITH CONDITIONS**。只有上述承重墙和对抗测试全部通过后才能进入 G4。

## S3 · 规划

1. 先写 P0 红测并修复可见状态与 meta 自相矛盾。
2. 写确定性解析、WriteIntent、原子执行和幂等红测。
3. 接入对话首轮、卡片与同会话文字确认，关闭模型 confirmed 绕过。
4. 完成 PostgreSQL/SQLite migration、聚焦回归、独立安全复审。

## S4 · 研发任务分解

- [x] P0 pending confirmation 状态收口。
- [x] 只读工具假成功反向控制。
- [x] 多药解析与实际服量分栏。
- [x] owner-bound medication batch WriteIntent。
- [x] 原子 Medication/MedicationLog 执行与逐项 `write_receipts`。
- [x] 卡片/文字 confirm/dismiss、双向竞态和写后安全筛查。
- [x] `WriteIntent.decision_status`、条件唯一索引和 PostgreSQL/SQLite managed migration。
- [x] Agent namespaced `medication_batch_decision`、过期提交后崩溃恢复和跨端权威终态投影。
- [x] Backend/PostgreSQL、Mobile、Web、Mac 回归和 G3 裁决。

## S5 · 实现

- 服务端冻结 `medication_intake_batch` 计划；确认请求不接收 items，模型 `confirmed=true` 不再构成授权。
- `WriteIntent.status` 保存物理状态，nullable `decision_status` 保存逻辑终态：`executed/executed`、`dismissed/dismissed`、`dismissed/expired`。
- confirm/dismiss 均以条件更新竞争同一 intent；先完成者为权威，后完成者返回同一终态。若 confirm 胜出，取消请求也返回完整 `write_receipts`；若 dismiss 胜出，确认请求零写入。
- 过期授权物理关闭为 dismissed，并持久化 `decision_status=expired`；提交后响应中断或进程崩溃时，重试只重放 expired，不重新执行、不调用 LLM。
- 批次精确结果写入 `assistant.meta.medication_batch_decision`；顶层 `write_receipts` 和 `safety_alerts` 与同回合其他能力合并，避免互相覆盖。
- Mobile、Web、Mac 都按 `decision_status`、回执数量/类型/operation id 前缀收敛服务端终态，取消不伪造写回执；文字“确认/取消”的 `done.cards=[]` 也会立即关闭上一轮卡片，不等重载。
- 历史恢复优先消费 namespaced `medication_batch_decision.write_receipts/safety_alerts`；仅旧消息缺少嵌套字段时回退顶层兼容投影，避免同回合其他写入或告警污染用药卡。
- 本地实现已完成；尚未部署。主会话在最终验证和评审收口后只提交本任务文件，提交 SHA 由交付记录回填。

## G3 · 测试闸

- Backend 真实 PostgreSQL 聚焦套件：`103 passed, 6 warnings`；覆盖 migration 重入、唯一约束、并发认领、原子回滚、双向竞态、持久化过期与提交后崩溃恢复。
- Backend CI 模式增量合跑（`DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai`）：`304 passed, 6 warnings`。
- Web：`50 files / 290 passed`；`npx tsc --noEmit` 通过；Next build `74/74` 页面通过。
- Mobile：相关 `7 suites / 238 tests passed`；TypeScript、design check 通过；ESLint `0 errors`（仅既有 warnings）。
- Mac：Medication batch `24/24`；`HealthAgentMacCoreTests` 共 `445 tests, 1 skipped, 0 failures`；另补 namespaced live-event 旧协议回退红绿测试。
- 覆盖项：精确原句、query-only 假成功、confirmed 注入、IDOR/跨会话、双击/并发、confirm↔dismiss 双向竞态、同槽异量、第二项失败全回滚、时间冻结、完整安全告警、expired crash recovery。
- 已知无关基线红（未修改、未伪装为通过）：Mobile 全量仅 `mobile/app/__tests__/dietCapture.test.tsx` 2 例因 jsdom `window.dispatchEvent is not a function` 失败；Mac 全量仅 13 个既有 PNG snapshot 像素差异。相关功能闸和 Mac Core 均为绿。
- **裁决：PASS**。上述无关基线另行治理，不阻断本功能进入 G4；任何新的相关真红仍回 S5。

## G4 · 安全闸

- 已完成多轮 producer/reviewer 整改：回执合并、完整安全告警、双向 confirm/dismiss 竞态、严格客户端动作契约、持久化 expired、提交后崩溃重放、批次证据隔离和文字终态旧卡投影均已补测。
- Mobile 独立复审已 GO；Backend 最终独立复审已 GO（80/80 行为/API、4/4 PostgreSQL migration/race、8/8 隐私/安全预检）。
- Capstone 最终独立评审结论：**GO**，P0/P1 均为 0；Web `18/18`、Mobile medication `6/6`、Mac Core `445 tests, 1 skipped, 0 failures`，并确认 namespaced 精确证据、`cards=[]` 文字终态投影、intent 隔离、owner scope、原子写入、幂等/竞态/过期恢复均无阻断缺陷。
- 非阻断 P2：后续可加强 Web/Mac 回执 intent-prefix/唯一性校验，并减少 Mac dismiss 的 confirm-won 分支对历史重取的依赖。
- **裁决：PASS**。允许进入 G5，但 G5 仍须用户显式批准；未获批准不得部署。

## G5 · 部署健康闸

- **状态：PENDING（显式 STOP）**。实现完成但未部署；必须先取得用户明确发布批准，再从干净 main 部署、检查健康分和生产迁移/路由。

## G6 · 上线验证

- **状态：PENDING**。部署后使用生产单账号发送精确原句，验证首轮合并确认、两条 `write_receipts`、confirm/dismiss 权威终态、过期不可执行、重试不重复和完整安全提示。
