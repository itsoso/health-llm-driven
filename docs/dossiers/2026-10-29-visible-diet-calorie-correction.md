# Visible diet calorie correction

| 字段 | 值 |
|---|---|
| slug | visible-diet-calorie-correction |
| 当前阶段 | S5 独立安全审查 |
| 状态 | first G4 repaired; awaiting re-review |

## G1 准入

裁决: PASS。修复用户对当前可见、已记录的本人单餐热量做精确纠正时被误判为未授权读取的问题。不新增自动估算，不扩大到其他营养字段、其他日期、其他餐次或其他用户。

## Scope

截图中的当前对话先展示一张 `recorded=true` 的饮食记录卡，用户随后明确说“热量是 378 大卡，之前计算的热量不对”。系统没有把该卡投影为安全的可操作引用，也没有把该句编译为受约束的饮食修正任务，最终普通读取提议被权限层拒绝。

目标行为：仅在最近可见饮食卡恰好包含一条已记录餐食、用户给出唯一且合理的热量值、且句式明确表达纠正时，先按认证用户、卡片日期和餐次查询数据库中的唯一原记录，再只更新 `calories`，最后读回核验。卡片中的 `record_id`、`user_id`、图片地址和 action payload 不提供写权限。

## Safety boundaries

- 问句、假设、转述、第三方、否定或取消、多值、多餐及无当前可见单餐均不得获得写权限。
- 不从卡片直接取得写入 ID；必须先走 owner-scoped lookup，且更新 ID 必须来自该查询结果。
- 不修改蛋白质、碳水、脂肪、纤维、食物内容、日期或餐次。
- 不读取或写入生产健康数据；测试使用合成数据。

## Gate status

- G1: PASS
- G2: PASS，采用现有 `diet_recalculate_update` 查询、更新和读回合同的窄化分支。
- G3: PASS，任务拆分为安全引用投影、严格语法、能力绑定、执行器参数规范化和回归验证。
- G4: 首次 NO-GO 已修复，等待新提交复审。首次审查发现 capability policy 未放行最终 update，且 postcondition 未核对目标热量；两处均已补实现和正负测试。
- G5: pending
- G6: pending

## Implementation evidence

- `diet_draft` 只有在 `recorded=true` 时才会投影为可操作上下文，且投影会剥离记录 ID、用户 ID、私有图片地址与 action payload。
- 严格语法只接受当前可见单餐的单一明确热量纠正；问句、假设、转述、第三方、否定、多值、其他营养指标、无卡片和多餐场景均保持拒绝。
- 查询权限由服务端 GoalSpec 绑定到认证用户、卡片日期与餐次；模型提供的 ID 或跨域读写不会扩权。
- 唯一 owner-scoped 查询成功后，执行器只生成 `data={"calories": ...}`；即使模型提供其他字段或省略工具调用，也不会改变其他营养信息。
- 最终 capability policy 会再次核对精确 GoalSpec、认证用户、日期、餐次、唯一 owner-scoped 记录、记录 ID、唯一字段和目标值；原始 intent 即使为 `unknown` 也只能通过这一条服务端窄化授权。
- 更新后的 Goal postcondition 会把权威读回 `calories` 与目标数值严格比较；缺失、非数值、布尔值或不一致均不能宣称完成。

## Verification evidence

- RED：实现前新增用例产生 5 个预期失败，其余 2,635 项通过。
- 首次 G4 绑定提交 `27fc3a034c5b8331fe22b496b8381bdd8c62ff5c`，裁决 NO-GO；阻断项为最终 update capability 未授权和读回未比较热量，未推送、未部署。
- G4 修复 RED：目标 378 时，读回 284、缺失、布尔值或非数字的 4 个用例在旧实现上均错误通过；最终 capability 正向用例也由独立 reviewer 复现为 `ambiguous_intent_requires_clarification`。
- 修复后核心与邻近回归：2,867 passed，覆盖 actionable context、GoalSpec、最终 capability 正负决策、owner/date/meal 唯一 lookup、执行器规范化、数值 postcondition 与事件流。
- 新退化用例：模型省略工具调用时，由服务端基于唯一 owner-scoped lookup 生成只含 `calories` 的更新。
- 修复后实时 LLM Gate：invariants 12/12、health agent core 50/50、orchestrator 5/5（平均分 0.96）、trajectory contract 12/12、goldens 9/9；仅合成数据与 SQLite 内存库。脱敏日志 SHA-256：`93df6407196ad0ae68c8c3399f855cbcc001f21e25ff3527c6749016f449eb5b`。
- System Map、mobile navigation 和 doc drift 检查通过；`git diff --check`、修改文件 `py_compile`、新增规则的 `ISC004/FURB157` 检查通过。
- 全量后端回归首次因缺少锁定依赖在收集阶段失败；补齐依赖后执行 36,219 项，34,350 passed、157 skipped、1,704 failed、8 errors。失败分布在运行身份、工具投影缓存、同步、可穿戴、天气等非本变更区域，因此该结果保留为全量 NO-GO，不计作本修复通过证据。精确提交仍须依赖独立 G4 与目标 SHA 的 CI Gate。
