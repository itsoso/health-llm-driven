# Dossier: Agent Trajectory Intelligence

| 字段 | 值 |
|---|---|
| slug | `agent-trajectory-intelligence` |
| 创建日期 | 2026-07-24 |
| 当前阶段 | S6 已验证 / G5 待部署 |
| 状态 | ready_for_deploy |
| 负责 | Codex |
| 反馈环 | intent corpus / stateful trajectory eval / backend pytest / production trace |

## S0 · 用户需求

> Agent 还是太弱，如何评测、优化和提升智能水平；按顺序实施。

直接事故：用户在已展示今日饮食卡片后说“重新估算和写入早午两餐”，Agent
没有关联上一张卡片，也没有查询既有记录，而是把它降级为缺少“记录类型和值”的
普通新增请求。

## S1 · Discovery

- Agent Runtime 已具备统一 Run、会话串行化、工具幂等、写入回执和恢复能力，不需要换框架。
- `TurnSnapshot` 只保存本轮文本、时间、媒体和粗粒度 `IntentFrame`，没有保存用户当前
  可见卡片中的可操作对象。
- `AgentConversationService.build_messages()` 只返回 `role/content`，`AgentMessage.meta.cards`
  不进入模型上下文；历史中的 `reva-ui` 块又会被替换为占位符，模型无法引用卡片对象。
- 现有意图语料覆盖单轮饮食 CRUD，但没有“基于上一张卡片重算并批量更新”的多轮轨迹。
- 现有饮食纠正护栏只覆盖单餐替换或按比例缩放，不覆盖“读取多个既有餐次、重新估算、
  更新并读回验证”的复合目标。

## G1 · 准入

```yaml
RequirementAdmission:
  classification: product_change
  first_user_fit: 高频饮食记录用户需要可靠修正和批量更新
  core_loop_step: Capture -> WriteIntent -> ExecutionEvent -> verified record
  first_class_objects: [WriteIntent, ExecutionEvent, HealthTwin]
  target_surface: Backend Agent; Mobile/Mac/Web 共享结果
  source_of_truth: PostgreSQL diet_records + Agent Runtime receipts
  safety_level: privacy_sensitive
  autonomy_tier: manual_confirm_for_ambiguous; execute_for_explicit_existing-record-update
  prescription_or_causal_verdict: none
  verification_window: same turn
  success_metric: first-pass trajectory success and exact DB delta
```

裁决：**PASS**。该改造提升 Health OS 写入闭环，不引入新的医疗判断。

## S2 · Spec

### 用户不变量

1. 用户说“这两餐/上面的记录/早午两餐”时，Agent 必须先解析当前可见的结构化对象，
   不得要求用户重复输入已经在卡片里的信息。
2. “重新估算并写入”只能更新既有饮食记录，不得静默新增重复记录。
3. 写入成功必须有每条记录的 verified receipt；缺少回执不得宣称完成。
4. 同一 `client_turn_id` 的重试不得重复产生副作用。
5. 目标不唯一时先查询数据库；查询后仍不唯一才做最小澄清。
6. 评测以工具轨迹和最终数据库状态为准，不以回复措辞为准。

### 目标轨迹

```text
resolve visible card / open task
  -> list today's diet records
  -> select breakfast and lunch records
  -> recalculate nutrition from existing food_items
  -> update exact record IDs
  -> read back
  -> emit verified receipts and concise summary
```

## S3 · 规划

- Implementation Plan:
  [`docs/plans/2026-07-24-agent-trajectory-intelligence.md`](../plans/2026-07-24-agent-trajectory-intelligence.md)
- P0: stateful golden cases, exact incident reproduction, DB-delta scorer.
- P0: safe actionable-card projection into `TurnSnapshot`.
- P0: typed `GoalSpec` for multi-record diet recalculation/update.
- P0: deterministic first lookup and no-create guard.
- P1: postcondition verifier and minimal clarification policy.
- P1: production incident -> eval case pipeline and model-routing comparison.

## G2 · 可行性与风险

- 采用 additive typed fields 和 safe projection，不改变移动端协议。
- 只投影记录 ID、日期、餐次、食物和营养字段；不把整段健康正文写入运行日志。
- 复用现有 `health_manage(list/update)`、ToolGateway、Runtime 幂等和 receipt。
- 第一阶段不做微调、不迁移框架、不引入新服务。

裁决：**PASS，带约束**。生产逻辑必须测试先行，且批量更新必须保留 fail-closed 和读回验证。

## S4 · 研发任务

- [x] T0 添加多轮轨迹 Golden Cases、盲测评分器和失败基线。
- [x] T1 添加卡片可操作对象安全投影，并固定最新卡片优先。
- [x] T2 添加 `GoalSpec` 和复合饮食目标识别。
- [x] T3 添加确定性首次查询、目标记录 ID 白名单和禁止重复新增。
- [x] T4 添加批量更新后的读回验证。
- [x] T5 加入 Agent 回归 Gate 和不含健康正文的目标进度指标。

## S5 · 实现摘要

- `TurnSnapshot` 新增安全投影后的 `ActionableReference` 与类型化 `GoalSpec`。
- 当前轮可引用最近饮食卡，但卡片只用于指代解析；所有写入仍必须先查 PostgreSQL。
- “重新估算和写入早午两餐”固定执行：
  查询当天记录 → 解析目标餐次唯一 ID → 更新原记录 → 再查询 → 回执核验。
- 查询前的 update、任何 diet create、以及查询结果之外的 record ID 都被写前护栏拦截。
- 没有覆盖全部目标餐次的写入回执和读回结果时，最终回复不得宣称完成。
- 离线轨迹评分以工具顺序、副作用、回执、读回和诚实完成声明为硬指标；
  匿名候选先按正确率排名，延迟和成本只用于同正确率时排序。

## S6 · 验证证据

- 目标模块 RED/GREEN：`GoalSpec`、卡片投影、后置条件、轨迹评分器、ID 白名单、
  多卡最新优先、目标进度遥测均先观察失败后实现。
- Agent 扩大回归：`280 passed`。
- 多模型路径：`8 passed`。
- 默认离线回归 Gate：
  - synthesis invariants `12/12`
  - health agent core `50/50`
  - trajectory contracts `5/5`
- Python 编译检查通过。
- system-map 重新生成并通过漂移检查。
- 遥测只记录 goal kind、目标数量、已验证数量和原因码，不记录餐次名称、食物或健康正文。

## Gate 记录

| Gate | 状态 | 证据 |
|---|---|---|
| G1 准入 | PASS | 直接增强饮食写入闭环和用户体验 |
| G2 可行性/风险 | PASS | additive、复用现有 Runtime 和 ToolGateway |
| G3 测试 | PASS | 280 项 Agent 回归 + 8 项多模型 + 62 项离线不变量 + 5 项轨迹契约 |
| G4 评审 | PASS | 补齐目标 ID 白名单、多卡最新优先、fail-closed 和隐私遥测 |
| G5 部署健康 | PENDING | 等待 backend deploy |
| G6 上线验证 | PENDING | 等待真实会话 trace 和数据库核对 |
