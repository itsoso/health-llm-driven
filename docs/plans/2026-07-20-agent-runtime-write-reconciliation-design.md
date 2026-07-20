# Agent Runtime Write Reconciliation Design

## 目标

让 Agent 管理的健康数据写入在 worker 退出、请求超时或响应丢失后可被安全核对：已经写入则重放可信回执，确定未写入则允许同一逻辑 operation 重试，无法判断则继续 fail closed。

## 非目标

- 不迁移 LangGraph、Temporal 或其他 Agent 框架。
- 不拆 Runtime 微服务，不做完整 Event Sourcing。
- 不改变 Mobile/Web/Mac 请求协议，也不改变 iPhone strict-local 路径。
- 不对尚未建立业务唯一键的资源自动重试。

## 选择

采用模块化单体内的 `Operation Reconciler Registry`：

1. `ToolSpec` 为具备事务幂等凭据的受管理写入声明 `resource_type`；首批仅 `health_record(diet create)`。
2. Runtime 在 dispatch 前创建稳定 `operation_id`，并持久化预期资源类型。
3. Executor 只在业务目标可证明时生成顺序无关的 logical key：饮食新增使用照片草稿 token，或“日期+餐次+规范化食物摘要+可选用餐时间”；修改/删除使用 record ID。Runtime 只保存该 key 的 SHA-256，不保存目标明文、参数或正文。
4. 饮食新增按“规范化日期+规范化餐次”进入不含食物措辞的稳定业务范围；缺省日期使用本轮用户时区的今天，缺省餐次与写入适配器一致使用加餐。相同范围内，只有同类型且明确不同的照片 token 或用餐时间才能证明是不同记录；区分器只在一边出现、类型改变、食物被模型重述或无法证明时拒绝第二笔。可选 `food_id` 不参与身份切换。
5. 饮食写入只有一个 canonical payload builder：顶层与 `data` 字段先合并，日期归一为 `YYYY-MM-DD`，餐次别名归一为枚举，用餐时间归一到业务库存储的 `HH:MM`，并剥离 `confirm/confirmed` 等会话控制字段。Runtime fingerprint、logical identity 和 HTTP dispatch 全部使用这份 payload，禁止三套归一逻辑漂移。
6. 饮食 API 不静默改写已通过 schema 的 `record_date`；历史补录按提交日期保存。任何日期策略必须在 Runtime identity 形成前完成，禁止业务接口在幂等身份生成后换日。
7. Executor 在当前 HTTP adapter 调用的局部 headers 中把 `operation_id` 下传为业务接口的 `Idempotency-Key`。
8. recovery 遇到租约过期写入时，按 `resource_type` 调用核对器。
9. 核对器只读取 owner-scoped 业务表，不把业务正文复制进 Runtime ledger。

## 状态语义

### 已确认写入

- 业务表存在 `(user_id, operation_id)` 对应记录。
- operation 变为 `succeeded`，只保存允许的 resource type/id。
- Run 变为可重试失败 `write_verified_reply_incomplete`。
- 同一 `client_turn_id` 重试时 operation replay 已验证回执，只补齐 Agent 回复，不再执行副作用。
- 同一 Run 有多笔写入时，只按各自 `logical_operation_key_hash` 重放，不能按工具名或资源类型模糊复用其他写入的回执。
- exact fingerprint 始终优先，用于兼容升级前 operation；新饮食 operation 的 fingerprint 基于实际 dispatch 的 canonical payload，餐次别名、ISO 日期形式、顶层/嵌套字段和秒级时间表达变化不会制造身份冲突，模型重排多笔调用也不会改变匹配结果。
- retry 出现既不能按 exact fingerprint、也不能按已证明业务目标匹配的新写入时，返回 `retry_plan_mismatch` 并阻止 dispatch，不允许模型在恢复阶段扩展副作用计划。
- operation 保存不可变的 `created_attempt_no`；retry 计划校验只看更早 attempt 创建的 operation，不会把当前 retry 内刚创建的第一笔写入误判为历史副作用。
- 同 attempt 中同一饮食范围的可选区分器若出现/消失或改变类型，视为不确定重复并 fail closed；仅同类型且两个摘要都明确不同时允许并存。

### 已确认未写入

- operation 已超过业务调用超时加安全宽限，业务表不存在对应记录。
- operation 变为 `failed`，错误码 `reconciled_no_effect`。
- Run 变为可重试失败；同一 operation 可再次 claim 并安全执行。

### 无法判断

- 旧 operation 没有预期资源类型、资源无核对器、数据库不可用或数据冲突。
- operation 与 Run 保持 `reconciliation_required`，circuit 保持暂停。
- 只能经显式、审计化的应用服务结算，不通过直接 SQL 修改。

## 幂等 transport

- 不使用进程全局、Executor 实例字段或 `ContextVar` 保存 operation ID。
- `_dispatch_tool_request` 只在当前受管理、可核对的 HTTP tool call 的局部 headers 中增加 `Idempotency-Key`。
- 现有非 Runtime 流量和非写工具不带该 header。
- 图片草稿 token 与 Runtime operation ID 合成为一个 opaque `client_action_id`，任一身份重试都复用同一条记录。
- 首批只自动核对新增的 `diet_record`；更新、删除和其他资源继续保留既有 fail-closed 行为，直到业务接口提供事务内 mutation receipt。

## 饮食更正路由

“晚餐只吃了四分之一”“没吃那么多”“实际只吃了一半”描述的是已有餐次的数量修正：

- Intent 为 `mutate/diet/update`，不是 `write/diet/create`。
- 需要餐次或可唯一解析的最近记录；目标不唯一时先查询/澄清，不创建新记录。
- fast route 选择 `health_manage`，复用既有先 list 后 verified update 流程。
- 更新成功时仍要求即时结构化回执；若 update 在回执前断流，本阶段不自动判定或重放，继续进入 reconciliation 并暂停 circuit。

## 安全与隐私

- Runtime 事件只记录有限 reason code，例如 `write_verified_reply_incomplete`、`reconciled_no_effect`。
- `logical_operation_key_hash`、`logical_operation_scope_hash` 和区分器字段只保存不可逆哈希及 `meal_time/photo_token` 类型标签；食物身份先规范化再单独哈希，Runtime 不保存食物名称、时间或照片 token。参数 SHA-256 继续保存在独立 `operation_fingerprint` 字段，不复用字段语义。
- migration 将旧 operation 的 lineage 回填为其原 fingerprint；新代码 exact-first 查找，保证升级前记录可安全重放，参数改变时则 fail closed。
- 旧 operation 的 `attempt_id` 可能已经被 retry 更新，migration 不据此猜测首次轮次；遗留行的 `created_attempt_no` 保持 `NULL`，按历史 operation 处理并 fail closed。
- 不记录用户句子、食物名称、营养数值、工具参数和工具返回正文。
- resolver 查询必须同时带 `user_id` 和 operation ID。
- 自动“未写入”判定需等待业务超时加宽限，避免与仍在执行的请求竞争。
- reconciliation 后系统不自动恢复 canary circuit。
- 所有 mutate/write 回合在模型轮次结束前缓冲正文；即使第一笔已有回执，第二笔失败前也不会先展示模型生成的成功措辞。

## 与 iPhone 分支的关系

- 变更限定在后端 Runtime、Agent 意图分类和服务端饮食 adapter。
- strict-local iPhone 不创建服务端 Run，不会进入该核对链路。
- API contract additive/unchanged，因此另一分支可正常 rebase；主要冲突风险仅来自同一后端文件的文本冲突，不是行为冲突。
