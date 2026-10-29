# Daily planning scope and diet record latency

| 字段 | 值 |
|---|---|
| slug | daily-planning-and-diet-record-latency |
| Controller | health-harness-orchestrator |
| Overlay | safety-gate |
| 当前阶段 | G5 exact-SHA CI |
| 状态 | independent G4 GO; pending exact-SHA CI and backend release |

## G1 准入

裁决：PASS。修复两个已发生的对话问题：混合“运动、饮食和补剂”日程请求被错误扩展为个人记录查询并产生本人权限拒绝；明确饮食记录在已经编译成精确写目标后仍经历两轮外层模型调用，导致长时间停留在“正在理解”。不增加个人数据读取范围，不自动创建计划，不改变饮食写入授权、营养估算、Gateway 或回执核验。

## Incident evidence

- 生产脱敏日志证明，日程请求被分类为低置信度未知补剂请求，路由模型超时后又提出个人读取、补剂指南和知识检索；本人查询被 owner scope 拒绝，最终以错误状态结束。根因是本地通用日程闭合语法只覆盖饮食、运动和睡眠，未覆盖补剂。
- 明确桃子记录被编译为 `write/diet/create`，写工具取得可验证回执并完成；截图中的等待不是未写入。该回合仍经过写前外层模型、营养估算和写后外层模型，总耗时约 22 秒，反馈体验不合格。
- 生产调查只读取脱敏运行元数据、工具决策、耗时和部署 revision；没有输出或修改真实健康载荷。

## Implementation

- 日程闭合语法增加补剂领域，同时继续要求整句完全消费。第三方、否定、引用、追加个人记录读取、保存计划和用药混入仍不得进入本地通用回答。
- 本地回答明确未查询个人记录、未保存计划；补剂段不读取个人补剂记录，不安排产品、剂量、频次或时间，也不建议开始、继续、停用或调整补剂，只提示向医生或药师核对已确认方案。
- 语音渠道的精确 `simple_health_record` 饮食创建目标在首轮直接形成服务端工具提议，仍依次经过营养补全、参数校验、Tool Gateway、实际写入和回执 postcondition。只有回执覆盖目标时才用确定性文案收口；失败、不确定回执和补全失败继续显式失败，禁止冒充完成。聊天渠道保留既有模型提供完整结构化营养时跳过二次估算的路径。
- 快速路径还要求完整匹配“记录下来，吃了一粒桃子”这一类单一份量、无残余子句的明确记录句；多食物语音继续走既有结构化模型，保留食物分隔和完整营养的优先级。图片、附件、危机语义、只读轮次、待确认工具、运行时写阻断或既有失败/不确定写入均不进入快速路径。
- 首个固定提交 `2edface101769bb8687143d11523fe9c77a49813` 的独立 G4 判为 NO-GO：旧资格正则仍会把追加查询、心率写、具体药品或补剂名吞进 `food_items`，且可从追加的“昨天”污染目标日期；补剂文案也把“今天”请求写成“明天的执行要求”。该提交未推送、未部署。
- 修复后的快速路径把份量和食物名作为一个闭合片段验证；食物名必须命中现有的受限餐食名词集合，未知实体不进入快路径；同时拒绝追加动作、日期、指标信号，并在任何直接饮食写之前复用药品引用和补剂实体词典。运行时还要求闭合食物片段与 GoalSpec 的 `food_items` 完全一致，且 GoalSpec 日期等于本轮上下文日期；任一条件不满足都会回到常规模型和安全策略路径。补剂说明改为无错误时段的“核对已确认方案的执行要求”。
- 第二个固定提交 `d74b33cb42ff827bd56042d2bf66c1b59ae88e9d` 的 fresh G4 仍为 NO-GO：首轮入口已闭合，但模型返回无工具后的既有 deterministic fallback 没有复用资格证明，未知实体仍可经营养补全取得有效合成回执并完成。原负测通过抛异常表达“不得调用”，异常被执行器作为普通失败捕获，因而出现假绿。该提交同样未推送、未部署。
- 第二次修复把 source message、当前日期和完整 GoalSpec 闭合校验下沉到 `_build_preplanned_simple_diet_tool_call`；两个入口及未来调用者缺任一证明都只能得到 `None`。负测改用有效营养和有效写回执，并分别覆盖空、非空的模型 stop/no-tools；测试直接断言 estimator 与 dispatcher 调用次数均为零，不再依赖异常传播。
- 精确主干 CI `40910140319` 暴露了该次下沉的真实兼容性回归：`backend-test-balanced-14` 中 5 项失败，明确晚餐多食物、明确晚餐干枣及营养补全失败边界都被单食语音资格误拦截；其余已完成作业保持原始结果，整次运行按失败保留且不重跑。修复把“首轮跳过外层模型”的单食语音资格与“模型无工具后”的闭合餐次兜底分开；后者仍完整绑定当前 GoalSpec 的 owner 侧目标、日期、餐次和食物文本，并拒绝追加查询/写入、药品和补剂，不扩大到一般自由文本。
- 该兼容修复的首次独立 G4 仍为 NO-GO：宽泛 food 捕获加残余词黑名单会把“给妈妈”“和妈妈吃的苹果”“并查血脂”“多少卡”与食物一起吞入 GoalSpec，并可在模型 stop/no-tools 后写入当前认证用户，造成第三方归属污染和复合查询误写。最终修复删除该黑名单授权方式；闭合餐次兜底只接受受限食物名、明确份量和受限分隔符构成的正向餐食项序列，其他自由文本继续留在模型及共享安全策略路径。

## Verification evidence

- RED：新增的补剂混合日程正向用例及其多组闭合边界在旧实现失败；明确语音桃子记录测试禁止外层模型调用时在旧实现失败。
- 首轮 GREEN：日程规划与边界共 74 项通过；明确语音记录取得单一验证回执，外层模型轮次为 0。
- 饮食营养与进度/幂等邻近回归 8 项通过；服务端营养估算仍执行一次，写入只分发一次，重复 `client_turn_id` 复用原回执。新增多食物语音 RED 先复现分隔丢失，收窄后单一食物快速路径与多食物既有路径 2 项共同通过。
- 当前输入建议与执行器完成状态扩大回归：318 passed。先前路径过宽时有 4 个失败，其中 3 个证明聊天渠道完整营养/分隔/修复路径发生真实退化；收窄后同一 318 项全部通过。
- G4 NO-GO 后新增 RED：追加“查看昨天的饮食”、追加“记录心率80”、具体药品“布洛芬”、具体补剂“钙片”、合成未知实体、GoalSpec 日期/食物不一致，以及“今天”补剂文案错误时段均在旧候选失败。第二轮 G4 进一步用有效回执复现 10/10 负测失败。将资格证明下沉后，两个 stop/no-tools 变体及全部五类危险输入均不调用营养补全或分发写，聚焦正反例 18 passed；日程、当前输入、执行器、症状邻近路径与共享写意图合并回归 812 passed。
- 离线 LLM Gate：invariants 12/12、health agent core 50/50、trajectory contract 12/12、goldens 9/9 通过，无模型费用。
- 实时 LLM Gate 的 5 个 orchestrator 用例全部被隐私层以 `recipient_not_disclosed` 阻断，未取得评分，不能计为通过；脱敏 JSON SHA-256 为 `357fc74b78ed69809a5ad614e68286dd1a44d9cf4421356cd78d0f31cf5be1c5`。用户此前已明确授权一次性豁免和部署，豁免须在固定提交后绑定精确 SHA。
- 修复后离线 LLM Gate 再次通过：invariants 12/12、health agent core 50/50、trajectory contract 12/12、goldens 9/9。`py_compile` 与 `git diff --check` 通过；Dossier、System Map、skill governance 和精确 SHA CI 等证据在下游 Gate 完成后追加。
- 最终正向餐食序列修复后，原失败文件及全部相关日程、当前输入、执行器、症状、共享写意图回归共 844 passed；聚焦 48 项通过。执行器级负测向 estimator 和 dispatcher 提供可成功的合成实现，直接确认追加饮食查询、追加心率写、给妈妈、妈妈所吃食物、血脂查询、热量查询、否定、引用、布洛芬、钙片及未知实体均为零营养估算、零分发。离线 LLM Gate 仍为 12/12、50/50、12/12、9/9；System Map、Dossier 一致性、skill governance、`py_compile` 和 `git diff --check` 通过。该工作树增量仍待新的固定提交独立 G4 和新的精确 SHA 完整 CI，不能用失败运行的其他绿色作业替代。

## Safety boundaries

- 不把补剂安排转成具体摄入指令，不推断用户已有补剂方案或健康状况。
- 不因快速路径绕过认证用户隔离、写 intent、营养完整性、Gateway、回执或 Goal postcondition。
- 测试只使用合成用户、内存数据库和固定工具结果；不操作设备或真实健康数据。
- 本次只有后端行为变更，不触发 OTA、原生包或 App Store 重传。

## Gate status

- G1: PASS
- G2: PASS，复用现有闭合 advice scope、GoalSpec、营养补全、Gateway 和 postcondition。
- G3: PASS
- G4: GO on the final positive food-sequence remediation; prior `2edface1`, `d74b33c` and the first compatibility remediation NO-GO findings are retained above
- G5: PENDING exact-main CI and trusted backend release
- G6: PENDING production receipt, revision, health and anonymous-auth probes
