# Daily planning scope and diet record latency

| 字段 | 值 |
|---|---|
| slug | daily-planning-and-diet-record-latency |
| Controller | health-harness-orchestrator |
| Overlay | safety-gate |
| 当前阶段 | G4 fresh safety review after dependency remediation |
| 状态 | backend behavior and typed safety review passed; exact-main CI exposed a new mobile dependency advisory, remediated locally and pending fresh fixed-commit review |

## G1 准入

裁决：PASS。修复两个已发生的对话问题：混合“运动、饮食和补剂”日程请求被错误扩展为个人记录查询并产生本人权限拒绝；明确饮食记录在已经编译成精确写目标后仍经历两轮外层模型调用，导致长时间停留在“正在理解”。不增加个人数据读取范围，不自动创建计划，不改变饮食写入授权、营养估算、Gateway 或回执核验。

## Incident evidence

- 生产脱敏日志证明，日程请求被分类为低置信度未知补剂请求，路由模型超时后又提出个人读取、补剂指南和知识检索；本人查询被 owner scope 拒绝，最终以错误状态结束。根因是本地通用日程闭合语法只覆盖饮食、运动和睡眠，未覆盖补剂。
- 明确桃子记录被编译为 `write/diet/create`，写工具取得可验证回执并完成；截图中的等待不是未写入。该回合仍经过写前外层模型、营养估算和写后外层模型，总耗时约 22 秒，反馈体验不合格。
- 生产调查只读取脱敏运行元数据、工具决策、耗时和部署 revision；没有输出或修改真实健康载荷。
- 2026-10-30 新截图对应生产 SHA `feb5d55a917e1f3281e0d6777fa421b568a85e58`。09:57 与 10:11 两次“记录一碗黑米粥”类请求都被识别为当前认证用户的 `write/diet/create`，但 `nutrition_estimate_ms` 和 `nutrition_model` 均为空，说明没有进入服务端营养补全。09:57 外层模型连续 8 轮产生不完整营养，反复缺少纤维或宏量营养；10:11 首轮同样被完整营养守门拒绝后停止。两次都没有写回执，现有安全守门正确阻止了不完整餐食数据落库。调查只读取脱敏日志元数据；未读取、修改或补写真实饮食记录。

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
- 新的直接份量语法覆盖 `记录一碗黑米粥`：GoalSpec 只在整句为明确记录动作、一个受限份量和受限食物名时编译当前用户、当天、单餐 `diet/create`；餐次继续按已有本地时间规则推断。受限食物集合增加黑米粥、小米粥、燕麦粥和白粥。
- 首轮服务端预规划只扩展到截图实际的 `typed` 与既有 `voice` 渠道。普通 `chat` 继续允许模型先提供完整结构化营养，避免覆盖已有高质量营养结果。所有渠道仍必须通过原有营养完整性、Tool Gateway、真实分发和回执 postcondition。
- 直接短句资格继续完整绑定 GoalSpec 食物、日期、当前用户和单次创建；布洛芬、钙片、追加昨日饮食查询、追加第三方归属均不能编译成该目标或进入营养估算/写分发。首个过宽实现导致 5 项邻近回归，已收窄渠道边界并修复一个依赖运行时钟的既有测试断言；失败证据保留，不作为通过。

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
- 黑米粥新增 RED 在旧实现稳定复现：GoalSpec 为一般 `write` 而非单一可验证目标，执行器未调用营养估算并进入外层模型。最小实现后聚焦正向、药物/补剂、追加查询和第三方归属共 11 项通过。随后 830 项扩大回归首次得到 825 passed / 5 failed；失败证明所有聊天渠道抢跑会覆盖模型完整营养，以及既有语音测试把动态餐次写死。边界收窄到 `typed`/`voice` 后，原 5 项和新增黑米粥路径共 6 项全部通过。完整扩大回归仍需 fresh rerun 后才能更新为 G3 PASS。
- 收窄后的 fresh 扩大回归为 834 passed；`py_compile`、`git diff --check` 与 agent-skill governance 均通过。该结果只证明本地增量，仍需固定提交上的独立 G4、LLM change gate、CI-mode 集成闸和精确主干 CI。
- 共享意图分类、能力策略、强制写工具和防假成功扩大回归 fresh 3278 passed。实时 LLM gate 的 invariants 12/12、health agent core 50/50、trajectory 12/12、goldens 9/9 通过；5 个 orchestrator 用例全部被隐私层以 `recipient_not_disclosed` 阻断并记为 errored，未取得评分，不能计为 live PASS。脱敏 JSON 位于 `/tmp/reva-black-rice-live-llm.json`，SHA-256 `3457cadbabc82a5fdea2b117a256b64a76e4fba7b5abeda73e83665b7cb40d4e`。任何豁免都必须在新提交固定后绑定该精确 SHA，不能复用旧候选的一次性变量。
- 固定提交 `9a9ab26a634542a3707c40b7094b7619d0b42c5f` 的独立 G4 判为 NO-GO。静态复核未发现新增越权路径，正向 typed 写已证明一次营养估算、一次分发、验证回执和零外层模型轮次；阻断点是测试证据没有让新增 typed 执行器入口实际承受药品、补剂、复合读取和第三方归属，也没有覆盖营养补全失败与回执缺失/错型后的防假成功和防重复分发。该候选未推送、未部署。
- 按复核要求新增真实 typed 执行器测试：布洛芬、钙片、追加昨日饮食查询和“给妈妈”四种输入均使用可成功的 estimator/dispatcher 作为陷阱，实际为零估算、零分发、零回执；营养补全返回空时只估算一次、零分发并显式返回完整营养失败；分发返回缺失身份或错误资源类型时均只分发一次、零验证回执、屏蔽模型“已经记录好了”，并进入 `write_reconciliation_required/missing_receipt`。新增及相邻正反路径 fresh 30 passed，待新的固定提交和 fresh 独立 G4。
- 固定提交 `b4e3f37dfe916e4629cbaec3d836d0d82a972de6` 的 fresh 独立 G4 为 GO；本地 CI-mode 发布集成闸退出码为 0，结果为 5638 passed / 67 skipped / 127 subtests。该提交推送后，精确主干 CI `40995174585` 的 32 个作业中只有 `mobile-typecheck` 失败；失败步骤为生产依赖 OSV 审计，新披露的 `GHSA-qr28-fpjm-wq7f` 将锁定的 `decode-uri-component@0.5.0` 判为 HIGH。该失败运行按原结论保留，未重跑，也没有把其他 31 个绿色作业冒充完整 CI 通过。
- 移动端依赖覆盖已从 `decode-uri-component@0.5.0` 升至上游首个修复版本 `0.5.1`，并同步 lockfile。安装树证明 `query-string@7.1.3` 实际解析到 `0.5.1`；实时 OSV gate、TypeScript、设计 token、签名回补测试、依赖兼容/图片解析 DoS 测试、OSV gate 自测均通过。移动端主 Jest 套件为 377 suites / 3846 passed / 1 skipped，四个隔离状态套件另有 84、80、34、7 项全部通过。该跨域依赖修复需在新的精确提交上重跑独立 G4、本地 CI-mode 与完整主干 CI，之后才能进入可信后端发布。

## Safety boundaries

- 不把补剂安排转成具体摄入指令，不推断用户已有补剂方案或健康状况。
- 不因快速路径绕过认证用户隔离、写 intent、营养完整性、Gateway、回执或 Goal postcondition。
- 测试只使用合成用户、内存数据库和固定工具结果；不操作设备或真实健康数据。
- 本次只有后端行为变更，不触发 OTA、原生包或 App Store 重传。

## Gate status

- G1: PASS
- G2: PASS，复用现有闭合 advice scope、GoalSpec、营养补全、Gateway 和 postcondition。
- G3: PASS, fresh 834-test focused expansion plus compile/diff/governance checks
- G4: PENDING fresh independent review of the final backend plus dependency-remediation commit; `b4e3f37` backend behavior review GO and earlier NO-GO evidence retained above
- G5: PENDING new fixed commit, exact-main CI and trusted backend release
- G6: PENDING production receipt, revision, health and anonymous-auth probes
