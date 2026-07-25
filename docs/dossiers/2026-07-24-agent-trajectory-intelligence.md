# Dossier: Agent Trajectory Intelligence

| 字段 | 值 |
|---|---|
| slug | `agent-trajectory-intelligence` |
| 创建日期 | 2026-07-24 |
| 当前阶段 | S7 已部署 / 简单记录合同 G4 已通过、待部署 |
| 状态 | implemented_pending_deploy |
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
- [x] T6 将 Goal compiler、合同 prompt 和 postcondition verifier 改为静态注册机制。
- [x] T7 将明确饮水/症状写入纳入类型化合同、严格回执和一次性确定性兜底。

## S5 · 实现摘要

- `TurnSnapshot` 新增安全投影后的 `ActionableReference` 与类型化 `GoalSpec`。
- 当前轮可引用最近饮食卡，但卡片只用于指代解析；所有写入仍必须先查 PostgreSQL。
- “重新估算和写入早午两餐”固定执行：
  查询当天记录 → 解析目标餐次唯一 ID → 更新原记录 → 再查询 → 回执核验。
- 查询前的 update、任何 diet create、以及查询结果之外的 record ID 都被写前护栏拦截。
- 没有覆盖全部目标餐次的写入回执和读回结果时，最终回复不得宣称完成。
- 离线轨迹评分以工具顺序、副作用、回执、读回和诚实完成声明为硬指标；
  匿名候选先按正确率排名，延迟和成本只用于同正确率时排序。

### P1 快速增强

- 用户显式说“昨天/前天/具体日期”时，用户日期优先于当前可见卡片日期，避免把历史
  修正写到今天。
- 支持“重新算/再估/补回/补上”等真实口语，不再降级成缺少类型和值的通用写入。
- 每个目标餐次必须在查询结果中恰好对应一个记录 ID；目标缺失或存在重复记录时整批
  停止写入。
- 目标无法唯一确定时，工具结果向模型注入确定性停止条件，要求指出具体餐次并请用户
  选择或补充，不允许反复查询、误写或宣称完成。
- 轨迹评分新增目标日期、查询结果唯一性和“更新 ID 必须来自权威查询”三个硬约束。

### Goal Contract Registry

- 新增不可变 `GoalCompilerRegistry`、`GoalPromptRegistry` 和
  `GoalVerifierRegistry`，为后续症状、饮水、提醒和用药任务合同提供稳定扩展点。
- compiler 按声明顺序确定性匹配，prompt/verifier 按精确 goal kind 分派；重复名称或
  kind 在注册表构造时直接失败。
- 保留 `compile_goal_spec()`、`format_goal_contract_prompt()` 和
  `verify_goal_postconditions()` 三个公共 facade，Executor 和客户端协议无需迁移。
- 当前饮食重估编译、合同 prompt、写入回执及权威读回规则原样迁移到注册表。
- 任何 `requires_verification=True` 但没有 verifier 的新任务继续 fail-closed，
  返回 `unsupported_goal_verifier`，不得由 Executor 自行推断成功。
- 注册表只含任务类型和函数引用，不记录用户健康正文；iPhone 本地闭环和 Runtime
  持久化协议未改变。

### 简单健康记录合同

- 明确的饮水创建和症状观察现在编译为 `simple_health_record`，合同保存目标记录类型
  以及当前消息中的服务端权威参数：饮水保存标准化毫升数，症状保存原始描述和受控
  body-part 枚举。
- 中文数字和阿拉伯数字均在服务端解析，当前只接受 `1..5000ml`；问句、否定句、缺少
  明确数量和带附件的输入不会进入确定性饮水写入；覆盖“五百毫升”“半升”
  “1千毫升”等常见表达。
- 模型只输出“已记录”而没有调用工具时，normal 和 multi-model 两条执行路径都会从
  类型化目标合成一次 `health_record`；执行仍经过既有 ToolGateway、确认策略、
  Runtime operation fingerprint、写入 checkpoint 和 receipt 提取。
- 模型提供的写入类型、数值和症状描述不再拥有写入权威；写前统一替换为 Goal 中的
  canonical payload。模型同轮发出多个等价写入时会得到相同 operation fingerprint，
  Runtime 只执行一次并复用结果。
- 无法构造 canonical payload 的损坏 Goal 会 fail-closed：模型写调用被删除，不会回退
  到模型自填参数。
- `simple_health_record` 只有在恰好一个回执 `verified=true`、资源 ID 有效且资源类型与
  目标完全一致时才通过后置条件；错误类型和额外回执都不能被误判为完成。
- 多模型路径取得简单记录结果后立即终止，不再进入 perspective/synthesis；成功使用
  服务端确定性确认文案，失败使用确定性未完成文案，综合模型不能覆盖真实回执状态。
- 症状继续复用已有的当前轮窄授权检查，没有放宽第三方描述、问句、否定句或附件写入
  权限。
- Goal 遥测仍只记录 kind、计数和原因码；标准化饮水量与症状正文不会进入 Kernel trace。

## 历史失败回溯与 Pi-style 架构裁决

### 失败类型

| 失败类型 | 历史表现 | 当前控制 | 剩余缺口 |
|---|---|---|---|
| 上下文对象丢失 | 已显示饮食卡，下一轮仍要求用户重述 | `ActionableReference` 投影进入 `TurnSnapshot` | 只覆盖已注册卡片类型 |
| 意图与目标混淆 | 查询被误写、明确修改被当作普通新增 | `IntentFrame` + `GoalSpec` + `CapabilityPolicy` | `GoalSpec` 目前只对少数复合任务有专用合同 |
| 工具调用退化 | 模型输出裸 `tool_code`、文本工具名或不调用工具 | textual recovery 只负责解析，执行仍经 `ToolGateway` | 恢复和确定性 fallback 仍散落在大 Executor |
| 写入假成功/假失败 | 先提示失败后显示成功，或成功后要求再提交 | Run/Operation ledger、幂等键、verified receipt、reconcile | 后置核验尚未完全收口进 `ToolGateway` |
| 重复执行/重复卡片 | 重试或断流造成重复消息、重复记录和重复卡片 | canonical Run、会话串行化、operation fingerprint、客户端回放 | 仍需持续跑真实断流和跨端回放用例 |
| 时间与指代错误 | 昨天写成今天、沿用旧卡片日期 | 冻结 `ExecutionContext`，用户显式日期优先 | 自然语言时间范围仍需扩充 |
| 模型可用但任务失败 | 模型会回答，却不能完成“查找→修改→读回” | stateful trajectory eval + deterministic task contract | 评测域仍偏饮食，症状/用药/提醒需同样合同化 |

### 架构裁决

当前实现是 **Pi-style Kernel + Reva durable Runtime**，不是直接采用 Pi 框架，也还不是
完全解耦的 Pi Harness：

- 已完成：`AgentEnvelope -> ExecutionContext -> IntentFrame -> TurnSnapshot` 的稳定边界；
  工具注册、能力策略、统一 `ToolGateway` 派发；Run/Attempt/Operation/Event 持久化；
  会话串行化、取消、租约恢复、幂等与可验证回执。
- 部分完成：provider 上下文转换、compaction、tool postflight、任务后置条件和模型 fallback
  仍有较多逻辑留在 `AgentExecutor`。
- 未完成：通用 `GoalSpec`/Verifier 注册表、独立的无状态 Run Executor、由生产事故自动晋级
  Golden Case 的评测闭环。

因此下一阶段不迁移框架，继续按 Pi 的边界原则拆分：

1. 将任务合同扩为按域注册的 `GoalCompiler + PostconditionVerifier`，先覆盖饮食、症状、
   饮水、提醒和用药修改。
2. 将 receipt、post-safety 和 postcondition 收口到 `ToolGateway` 的 postflight，禁止
   Executor 自行判定成功。
3. 将 provider message transform、tool loop 和 fallback 从超大 Executor 中拆为无状态
   `RunExecutor` 阶段，并保留现有 durable Runtime 作为控制面。
4. 把重复提交、错误指代、工具泄漏、时间错误、假成功/假失败和断流恢复全部纳入同一
   stateful trajectory regression gate。

## S6 · 验证证据

- 目标模块 RED/GREEN：`GoalSpec`、卡片投影、后置条件、轨迹评分器、ID 白名单、
  多卡最新优先、目标进度遥测均先观察失败后实现。
- Agent 扩大回归：`280 passed`。
- 多模型路径：`8 passed`。
- 默认离线回归 Gate：
  - synthesis invariants `12/12`
  - health agent core `50/50`
  - trajectory contracts `7/7`
- P1 核心回归：`123 passed`。
- Goal registry RED/GREEN 聚焦回归：`14 passed`。
- Agent Kernel、ToolGateway 和 stateful trajectory 回归：`110 passed`。
- Executor 完成状态、工具门禁、写入授权/回执、工具恢复和 Runtime operation
  集成回归：`152 passed`。
- Goal registry 改造后的离线 Gate：
  - synthesis invariants `12/12`
  - health agent core `50/50`
  - trajectory contracts `7/7`
- 简单健康记录合同 RED/GREEN：
  - 合同、注册表、回执、Intent 和 TurnSnapshot `37/37`
  - 无虚假记录完整流式路径 `10/10`
  - 写入授权、写入结果、CapabilityPolicy、ToolGateway 和 Tool Registry `79/79`
  - fast routing 与 tool-round routing `83/83`
  - multi-model 路径 `8/8`
  - LLM 回归 Gate 自测 `5/5`
- 权威写入加固复审：
  - 错误饮水量、错误记录类型、错误症状语义、重复调用、损坏 Goal 和额外回执反例通过
  - 多模型 verified receipt 终止路径通过，确认未调用 perspective/synthesis
  - 附件输入不生成简单记录 Goal
  - 独立代码复审两轮：首轮发现 6 项风险并全部整改；终审 `44 passed`、无剩余 finding
- 更新后的零成本离线 Gate：
  - synthesis invariants `12/12`
  - health agent core `50/50`
  - trajectory contracts `11/11`
- Python 编译、`git diff --check` 和文档漂移检查通过。
- 扩大 Agent 回归：`662 passed`；15 项因本地沙箱禁止连接 PostgreSQL 而未执行，
  9 项批量化验失败隔离复测后 `9/9 passed`；另 1 项为旧模型名断言与当前 Qwen
  路由配置不一致，和本次改动无关。
- Python 编译检查通过。
- system-map 重新生成并通过漂移检查。
- Goal registry 新增 Kernel service 后，system-map 由官方生成器重建并再次通过漂移检查。
- 遥测只记录 goal kind、目标数量、已验证数量和原因码，不记录餐次名称、食物或健康正文。

## Gate 记录

| Gate | 状态 | 证据 |
|---|---|---|
| G1 准入 | PASS | 直接增强饮食写入闭环和用户体验 |
| G2 可行性/风险 | PASS | additive、复用现有 Runtime 和 ToolGateway |
| G3 测试 | PASS | Agent 核心定向回归通过；62 项离线不变量 + 11 项轨迹契约通过；ruff、compileall、文档漂移和 diff 检查通过 |
| G4 评审 | PASS | 两轮独立复审；补齐 canonical 写入权威、单回执、多模型终止、损坏 Goal fail-closed 和附件反例 |
| G5 部署健康 | PASS | 精确提交 `069699d69378` 已部署；备份、231 张表恢复演练、站外归档、60/60 健康分和远端 SHA 核验通过 |
| G6 上线验证 | PENDING | 等待真实会话 trace 和数据库核对 |
