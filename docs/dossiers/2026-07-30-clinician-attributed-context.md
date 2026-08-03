# Dossier: 小巴正确理解并记录医生来源的健康事实

| 字段 | 值 |
|---|---|
| slug | `clinician-attributed-context` |
| 创建日期 | 2026-07-30 |
| 当前阶段 | S5 上线召回修正 / 发布闸复验 |
| 状态 | verifying |
| 负责 | Codex |
| 反馈环 | backend deploy |

## Correct Course

- [x] Correction Block
  - 触发：T1 连续三轮实现后，独立质量评审仍发现同类动作主体误判。
  - 证据：“医生告诉我是……”被判为 read；医生转述的 update/delete/sync
    被升级为用户 mutation；多分句“先转述、再保存”被误拒。
  - 根因：全句先聚合动作关键词，再为个别动作修补主体；属于结构问题而非
    marker 覆盖问题。
  - 回退决策：停止第四轮关键词/位置补丁，重新进入定义环。
  - 新方案：raw text 先分句，生成 source/action/actor/object 的私有
    clause frame，再 fail-closed 归并到现有 `IntentFrame`。
  - 用户裁决：2026-07-31 批准 clause-level provenance 方案、组件边界、
    失败策略和测试矩阵。
- [x] Correction Block 2
  - 触发：clause-level frame 完成三轮结构修正后，独立质量评审仍发现
    quoted action 获得用户授权、delete 被误判 create、mutation 撤销失效。
  - 证据：同一标点段内“我想记录…但医生说要保存…”的多个 action
    共用 frame actor；save 与 mutation 使用不同粒度的解析和 stance。
  - 根因：真实授权主体属于 action occurrence，不属于整句或 clause。
  - 回退决策：停止第四轮 clause-frame 补丁，重新进入定义环。
  - 新方案：独立 ActionEvidence 模块；每个动作拥有自己的
    actor/target/polarity/modality/span；所有动作家族共用 target-aware
    reducer；clinician-bearing 输入禁止 raw whole-text 授权。
  - 用户裁决：2026-07-31 批准 ActionEvidence 方案、组件边界、失败策略和
    属性测试矩阵。
- [x] Correction Block 3
  - 触发：Task 1B 最终补丁虽然 `601 passed`，但独立规格评审仍拒绝：
    same-region 第二个明确用户动作被判 clinician；evidence 扩展词污染
    legacy classifier；所有 create verb 被 target 跨家族改写；read 候选和
    property tests 仍有第二套手写子集。
  - 证据：`医生说要保存诊断但请记录今天腰痛6分` 得到
    clinician/clinician；`删除用药记录么`、`勿删除用药记录`、
    `不再删除用药记录` 的公共分类在 Task 1C 前已改变；`设置康复计划`、
    `制作复查提醒`、`创建康复图片` 获得了原词典没有的能力。
  - 根因：候选先被压成 generic create 再按 target 任意重写；actor 仍按每个
    动作向后猜测而不是维护线性所有权 scope；“共享词典”没有区分 legacy
    兼容视图和 evidence 安全扩展视图。
  - 回退决策：Task 1B 规格 Gate 失败，不进入质量审查或 Task 1C；停止继续
    添加 marker 例外，保留 Task 1A，重做 Task 1B 两个内部抽象。
  - 新方案：candidate 携带其原有 `allowed_families`，target 只能在集合内
    解析，空交集 fail closed；actor 用一次左到右 scope pass，provider-owned
    quote 优先，只有引语外的顶层 transition + 明确用户 cue 才能从已消费的
    clinician action 切回 user；legacy classifier 和 evidence lexicon 分层但
    共处单一模块。
  - 裁决：G2 仍 PASS，产品语义与安全边界不变；Task 1B v2 必须重新通过
    spec + quality 双审后才能进入 reducer。
- [x] Correction Block 4
  - 触发：Task 1B v2 最终通过规格闸，但独立质量评审报告 6 Critical /
    4 Important，不能作为授权 reducer 的输入。
  - 证据：外层 `医生说` 被内层 clinician basis 覆盖成 user；未收录的
    `应不应该/不得/拒绝/曾` 默认 positive command；读取“删除前/删除历史”
    产生 mutation；basis modifier 换成“写成的/整理的/开具的”即选错目标；
    并列目标冲突被 separator/provider filter 隐藏；重复扫描呈明显非线性。
  - 根因：v2 仍以“未命中反例词 = command”为默认；provider 只保存最近一层；
    action role 和 target modifier 依赖有限 marker，而不是授权级结构证明。
  - 回退决策：不再扩充问题/否定/relative/modifier 词表；保留 Task 1A 和
    `allowed_families`，替换 v2 actor/stance/action-role/target internals。
  - 新方案：单次 lexical index + nested provider/quote scopes +
    structural command proof + governor/embedded action roles + target
    head/coordination conflict；未知结构默认不授权。词典属性测试之外新增一份
    不由实现常量生成的固定安全语料。
  - 裁决：G2 仍 PASS，产品语义、显式写入和 fail-closed 边界不变；
    Task 1B v3 必须重新通过 fresh spec + fresh quality 双审。
- [x] Correction Block 5
  - 触发：Task 1B v3 最终通过规格闸，但 fresh quality review 仍报告
    4 Critical / 3 Important；通用中文授权 parser 再次出现 scope、后置
    stance、协调继承、target 跨段污染和性能计量盲区。
  - 证据：`医生建议休息然后请保存诊断记录` 被授权 user write；
    `删除用药记录是否合适`、`查看删除和保存的诊断记录`、
    `请删除或不保存用药记录` 仍产生可授权动作；无关 provider/target
    还能污染前一动作。
  - 根因：产品只需要安全识别医生转述和一个明确写能力，却试图构建通用
    中文动作授权语法；其语言覆盖、安全证明和维护成本远超需求。
  - 回退决策：停止 Task 1B 通用 ActionEvidence 路线，不再修 parser；删除
    未上线的 parser 和 evidence-only 词典，回到最小端到端产品边界。
  - 新方案：`ClinicianProvenanceGuard` 只判断医生来源、建议问题和窄格式的
    `记录/保存 + 医生诊断/意见/反馈/结论 + 非空内容`；裸转述只理解，
    混合/歧义操作全部非写并提示拆分；非医生输入继续走 legacy classifier。
  - 用户裁决：2026-08-01 批准窄授权、强理解方案及复杂混合操作 fail-closed。
  - 新设计：`docs/plans/2026-08-01-clinician-provenance-guard-design.md`。
- [x] Correction Block 6
  - 触发：Task 2 独立质量评审要求保留 `根据/依据/按照医生意见 + 用户操作`
    的 legacy mutation；连续对抗复审证明，纯字符级 guard 无法同时支持任意
    非空 target，并完备排除尾随否定、拆词和第二个医疗动作。
  - 证据：`根据医生诊断删除昨天用药记录，停药`、`依据医生意见调整剂量并
    换药`、`...拒绝执行` 可被放行为写；收紧到 target 词典又误伤午餐、
    体重、心率、药物和复合记录等合法目标。
  - 根因：clinician provenance guard 被迫承担开放域中文 mutation 授权解析，
    再次超出产品所需的窄授权边界；有限否定/连接词/target 枚举不能形成安全
    证明。
  - 裁决：撤销评审期间新增的 clinician-basis → legacy 豁免。任何
    `根据/依据/按照 + clinician basis + mutation` 统一非写并提示用户把操作
    单独重述；独立 mutation 和显式 doctor-feedback save 语义不变。
  - 用户裁决：2026-08-01 明确批准上述安全收紧。
- [x] Correction Block 7
  - 触发：窄 guard 首轮端到端实现后，独立复审发现“已保存但不代表 Reva
    诊断”仍能掩盖虚假写入声明，且敬语、条件句和硬分句后的 clinician-basis
    mutation 可绕过 fail-closed。
  - 根因：授权判断仍依赖外层句式枚举，false-save backstop 只看局部模板；
    未形成统一的语义优先级和 turn-level 写入事实源。
  - 修正：引入 clause-local canonical representation；clinician guard 先于
    legacy classifier，typed receipt 成为唯一成功事实源；stream token、落库
    assistant message 和 done message 共用同一条 false-save backstop。
  - 裁决：裸医生陈述和普通咨询保持只读；clinician-basis mutation 统一要求
    用户另发独立操作命令。
- [x] Correction Block 8
  - 触发：Unicode 安全复审发现控制符、私用区和未分配码点可插入来源词或
    outer command/object；同时有效显式保存正文被二次混淆扫描误拒。
  - 根因：canonical view 采用黑名单过滤，且“写入信封”和用户提供的医疗正文
    没有先后分层。
  - 修正：NFKC 后 canonical view 只保留 Unicode `L*`/`N*`，其余字符作为
    gap 并保留 raw offset；只有 outer envelope 完整证明后，保存正文才对通用
    混淆扫描不透明，outer command/object 和复合动作仍 fail-closed。
  - 裁决：`97f26b55f` 经独立规格与质量双审均 GO，Critical 0、Important 0。
- [x] Correction Block 9
  - 触发：首轮生产上线验证中，显式保存成功，但新会话询问“刚才记录的医生
    诊断是什么？”被 guard 判为 `ambiguous_clinician_action`，返回“没有执行
    操作”，G6 因此 FAIL 并停止宣告完成。
  - 根因：guard 在问句裁决前扫描到 legacy `记录/保存` 动作词；没有区分
    “记录医生诊断”命令与“记录的医生诊断”这一名词性历史召回结构。
  - 修正：新增窄格式、单分句的 clinician-feedback recall envelope，只接受
    来源对象 + `的` + 明确回忆问法；返回只读 `clinician_feedback_recall`。
    executor 对该 reason 强制零工具，并要求只从最近医生反馈上下文回答，未
    找到时明确说不知道。删除、调整、同步及角色反转问句继续 fail-closed。
  - 安全边界：修正不扩大任何写授权；召回仍由 owner-scoped doctor source
    上下文提供，不能用模型猜测补全。
- [x] Correction Block 10
  - 触发：`431ea2d10` 第二轮生产验证中，guard 已正确识别 recall 且强制
    tools `[]`，但新会话回答“看不到最近医生反馈”，G6 再次未通过。
  - 根因：typed clinician recall 之后，system prompt 仍把原句交给通用个人
    上下文预算分类器；“是什么/有哪些”命中纯知识题，预算降成 MINIMAL，而
    L3 医生反馈按隐私设计只在 FULL 注入。两套分类器的决策没有串联。
  - 修正：executor 将 server-owned `clinician_feedback_recall` 决策显式传给
    system prompt，强制本回合使用 FULL 个人上下文；其他查询仍沿用原有
    FULL/MINIMAL 分类，不新增关键词，也不开放工具。
  - TDD：跨层测试先证明 run-stream 未传 full-context 信号、prompt 缺少 owner
    医生反馈；修正后两项均通过。
- [x] Correction Block 11
  - 触发：上下文修正候选 `3c83612d7` 推送后，main CI run
    `30803354084` 的 `type-drift` 失败，其余 43 个 jobs 成功；发布闸因此
    停止，未部署该候选。
  - 根因：并发合入的饮食份量修正 API 新增内部请求头
    `X-Reva-Internal-Diet-Portion-Signature`，后端 OpenAPI 已更新，但 Mobile
    与 Frontend 派生类型尚未同步。该漂移与 clinician recall 业务逻辑无关，
    但属于接口契约 Gate，不能带红发布。
  - 修正：使用 CI 同版 Python 3.12、`requirements.lock`（FastAPI 0.139.2、
    Pydantic 2.9.2、Starlette 1.3.1）和
    `openapi-typescript@7.13.0` 重新生成两端类型；最终差异仅为两端各新增
    该请求头，复跑前后 SHA-256 均为
    `18f69d6114bc108503dcd7bcb35a67332b8d290471507914d9d7d33bec10b96e`。
  - 一次性 `HARNESS_LIVE_LLM_EVAL_CONFIRMED` 已在 `backend-quality` 成功读取
    后删除，并验证远端返回 `not found`。

## S0 · 用户需求（逐字）

> 修复代码 从架构上分析智能程度不高的原因 并进行改进

- 谁用 / 解决什么 / 现在怎么绕过（四问 Q1）：
  - Mobile 小巴用户在转述医生诊断或康复评估时，需要得到符合语义的理解和回应。
  - 当前包含“痛”等词的医生结论会被误判成普通症状写入；写入提取又失败，最终返回要求补类型和值的通用兜底。
  - 用户只能改写成问题，或进入“医生回路”页面手工填写医生反馈。
- 锚点用户相关性：医生结论是 Health OS 长期管理中的高价值证据，直接影响伤病限制、行动建议和复诊沟通。

## S1 · Discovery（现状勘察）

- 已有可复用：
  - `backend/app/services/utterance_intent_classifier.py`：统一意图帧，但 `SYMPTOM_TERMS` 中的宽泛“痛”先把医生转述归入 symptom。
  - `backend/app/services/agent_executor.py`：fast-record 在零写入回执时使用 `_record_intent_needs_detail_message`，其文案与截图逐字一致。
  - `backend/app/services/doctor_report_service.py:record_doctor_feedback`：已有医生反馈写入，落在 `ClinicalJournalEntry(created_by="doctor")`。
  - `backend/app/api/doctor_report.py` 与 `mobile/app/doctor-loop.tsx`：已有受用户身份约束的医生反馈 API 和人工录入页面。
  - `backend/app/services/agent_kernel/tool_registry.py` 与 `capability_policy.py`：已有写工具回执、能力准入和显式写意图承重墙。
- 缺什么：
  - 意图层没有 clinician-attributed semantic frame。
  - Agent 工具层没有医生反馈写能力。
  - 后续 Agent 上下文没有明确注入最近的医生来源事实。
- 根因链：
  - 医生结论中的“痛” → symptom/write → fast-record → 症状提取器拒绝报告/医生来源 → 零工具回执 → 通用补字段兜底 → turn 标为未完成 → Mobile 展示重试条。
- 硬约束 / 平台·安全边界：
  - 裸陈述不能自动持久化临床事实。
  - 只有用户明确“记录/保存”才写入，自治档永久为 `manual_confirm`。
  - 医生意见必须保持来源归属，不能被模型改写成 Reva 自己的诊断。
  - 不从自由文本自动创建或升级 `HealthProblem` 风险等级。
- 并发检查：2026-07-30 检查开放 PR，未发现同范围实现。

## G1 · 准入裁决（governance §8 RequirementAdmission）

- first_class_objects：`HealthProblem`（医生证据输入，不自动改状态）、`WriteIntent`（显式保存语义）
- core_loop_step：symptoms / clinician evidence → health context → safe action reasoning
- target_surface / safety_level / autonomy_tier：Backend Agent Kernel + Mobile chat / medical_boundary / manual_confirm
- spec_required：yes（新用户可见行为 + 新健康写路径）
- smallest_end_to_end_slice：正确分类医生来源陈述；显式保存复用 Clinical Journal；最近医生反馈进入后续完整健康上下文。
- stale_surface_to_remove：无；保留“医生回路”人工页面作为精细编辑入口。
- **裁决**：PASS —— 复用现有对象，不新建数据库模型，不让 LLM 诊断。
- 用户确认：2026-07-30 已确认“裸陈述只理解，明确保存才入档”。

## S2 · PRD / Feature Spec

- 链接：`docs/specs/active/2026-07-30-clinician-attributed-context.md`
- 引用的权威 R 号：R10 Agent 受控入口、R13 HealthProblem 医生结论与随访证据
- 边界：不自动诊断、不自动建 HealthProblem、不自动生成康复处方、不改 Mobile UI。
- 验收 Gate：分类、能力策略、持久化回执、上下文召回和原始截图语句的端到端回归。
- 未决问题：无。

## S3 · 规划

- 当前设计：`docs/plans/2026-08-01-clinician-provenance-guard-design.md`
- 历史设计：`docs/plans/2026-07-30-clinician-attributed-context-design.md`
- 当前实施计划：`docs/plans/2026-08-01-clinician-provenance-guard.md`
- 历史实施计划：`docs/plans/2026-07-30-clinician-attributed-context.md`
- 已废止的 T1 parser 计划：`docs/plans/2026-07-31-clinician-action-evidence.md`
- 分阶段：意图帧 → Agent 写工具与回执 → 上下文召回 → 回归与安全验证。
- 反馈环路由：后端改动，验证通过后走 backend deploy；无 Mobile OTA。

## G2 · 可行性 + 安全压测

- 评审方式：Codex challenge
- 已焊进设计的硬约束：
  - clinician provenance guard 先于全句 read/write/mutation keyword。
  - clinician-bearing 输入绝不回 raw whole-text authorizer。
  - 只有窄格式的 clinician-feedback save envelope 可以产生写意图；复杂混合
    动作统一 fail-closed 并提示拆分。
  - clinician-basis mutation 也属于复杂混合动作；必须先移除医生依据从句，
    再以单独明确命令重述，系统才交给 legacy mutation 路径。
  - 保存必须有显式写意图并产生可验证回执。
  - 上下文标明“用户转述的医生意见”，禁止把来源升级成系统诊断。
  - 不新增表、不迁移、不自动变更 HealthProblem。
- 待拍板分叉：无。
- **裁决**：PASS（2026-08-01 第三次重新裁决）—— 用户已批准窄授权
  provenance guard；持久化、来源标记和安全边界不变。

## S4 · 研发任务分解

- T1：删除未上线的通用 ActionEvidence parser；实现窄
  ClinicianProvenanceGuard、显式 feedback save envelope、legacy 分类器与
  fast-record choke point 接入。
- T2：模型可见工具、Kernel registry、回执契约与 capability policy。
- T3：owner-scoped 写入 adapter、校验、回滚与敏感日志测试。
- T4：完整上下文中的来源标记召回、长度限制与 cache invalidation。
- T5：提示词契约与原始截图语句端到端 streaming 回归。
- T6：system map 生成、集成 Gate、独立 G4 安全评审与 Dossier 证据。
- 并发检查：已完成。

## S5 · 实现

- 分支：`codex/clinical-context-intelligence`，从 `origin/main@b8164308f` 创建。
- Health Harness Run Ledger：`docs/_generated/harness-runs/57c7b7e8a387.jsonl`
  （本地运行追踪，不提交原始 JSONL）。
- T1 已完成：`ClinicianProvenanceGuard` 在宽泛 symptom/mutation classifier
  前裁决医生来源语义；裸陈述只理解，显式反馈保存走窄 typed envelope，
  clinician-basis mutation 要求另发独立命令。
- T2 已完成：注册 `record_doctor_feedback`、capability gate、tool registry 与
  verified `clinical_journal_entry` receipt；每 turn 最多一次 typed write。
- T3 已完成：owner-scoped adapter、候选集/快照一致性验证、rollback 和不含
  原始医疗文本的日志契约。
- T4 已完成：最近医生反馈以“用户转述的医生意见”进入完整 health context；
  cache invalidation 避免成功写入后召回旧上下文。
- T5 已完成：提示词、streaming、持久化 assistant message 与 done message
  使用同一写入事实；无 verified receipt 时禁止宣称已记录。
- T6 已完成：截图原句、显式保存、普通咨询、复合动作、Unicode gap、owner
  isolation、rollback、receipt freshness 与 Health Evidence 优先级均有回归覆盖。
- 上线召回修正已完成：窄 recall envelope、零工具执行约束及正反例回归已
  实现。第二轮生产暴露上下文预算断链后，typed recall → FULL context 的跨层
  修正也已实现；当前正在修复并复验并发 API 类型契约 Gate，尚未进入第三轮
  部署。
- 上下文预算修正提交：`a410e80c4`；当前发布候选记录提交：`3c83612d7`。
  药物 Health Evidence 域未扩张；正式 golden
  pack 仍只覆盖既有 low-back 场景，药物风险问题走可靠普通分析路径。
- 发布前再次无冲突合并 `origin/main@0e2f05252`；当前合并提交
  `e218c3ac57cf`。
- 独立审查：规格 reviewer GO（Critical 0 / Important 0，`1986 passed`）；
  医疗质量 reviewer GO（Critical 0 / Important 0，相关套件合计
  `2030 passed`）。

## G3 · 测试闸

- 基线：CI 模式相关测试 `158 passed`。
- 实现 HEAD `97f26b55f`：扩展相关回归 `1986 passed, 7 warnings`；独立质量
  reviewer 分组复核合计 `2030 passed`。
- Ruff、`py_compile`、fixture JSON、`git diff --check`、pre-commit：通过。
- 最终主干合并后集成回归：`2031 passed, 7 warnings`；system-map 生成/校验、
  `py_compile`、fixture JSON、doc drift、Dossier consistency、diff-check 和
  全变更 pre-commit：通过。
- 最终头 offline Health Harness：invariants `12/12`、health-agent-core
  `50/50`、trajectory contract `12/12`、trajectory goldens `9/9`；
  path-sensitive confirmation：通过。
- 最终头 live Harness 首轮 orchestrator `4/5`（平均分 `0.91`），因此停止发布
  并按 systematic-debugging 复查；同 SHA 逐 case 诊断重放 `5/5`（平均分
  `0.90`），所有 keywords 与 LLM judge 均通过。此前合并头 live 为 `5/5`
  （平均分 `0.94`）。本分支未修改 orchestrator、judge 或其 dataset；合成路径
  `temperature=0.3`，裁定为 live 模型方差而非确定性代码回归。失败与重放证据
  均保留，不以静默重试掩盖。
- 上线召回修正相关套件：`1580 passed, 7 warnings`；Ruff、`py_compile`、
  `git diff --check` 通过。新增召回正例先按 TDD 在旧实现上失败，修正后与
  删除/调整/同步/角色反转反例共同通过。
- 修正后 live Harness：最初误用了生产角色连接本地库，随后改为本地
  `health_db`，又因该开发库 `llm_usage_logs` 缺列而被配额保护正确阻止；两次
  均是环境失败且未产生成功 TokenPlan 调用。最终切换到结构最新的隔离
  `health_test` 后通过：invariants `12/12`、health-agent-core `50/50`、
  orchestrator `5/5`（平均分 `0.94`）、trajectory contract `12/12`、
  trajectory goldens `9/9`。未绕过配额保护，也未用失败回退结果冒充成功。
- 第二次生产失败后的上下文修正 TDD：新增 2 项跨层回归，修正前均失败
  （缺少 `force_full_personal_context` 信号 / prompt 不接受该参数），修正后
  `2 passed, 7 warnings`。
- 上下文修正与并发饮食链合并后组合回归：前 1154 项通过，`test_diet.py`
  55 项因误载生产 `.env`、本机管理员角色被生产数据库角色闸正确拒绝而在
  TestClient 启动阶段报错；显式 `APP_ENV=test` 后该文件全部 `59 passed,
  7 warnings`。这是测试环境配置失败，无业务断言失败，且安全闸未被绕过。
- 最新合并头 live Harness 再次通过：invariants `12/12`、health-agent-core
  `50/50`、orchestrator `5/5`（平均分 `0.90`）、trajectory contract `12/12`、
  trajectory goldens `9/9`。结构闸、变更文件 Ruff、`py_compile`、diff-check
  同时通过。
- main CI 真实色：曾在 `508624f7f` 因 OpenAPI 派生类型漂移失败；按 CI 同版
  Python 3.12、`requirements.lock` 和 `openapi-typescript@7.13.0` 精确复现并
  生成修复。后续主干已同步同一类型结果，完成的 `e966281cd` 与
  `d19c53603` CI 均 success；最新 `0e2f05252` 为 docs-only，检查仍在运行。
- 当前发布候选 CI run `30803354084`：43 jobs success，唯一失败为
  `type-drift`。精确复现确认是并发饮食 API 新请求头未同步到两端派生类型；
  固定依赖重生成后仅产生两端各 `4 +++-` 的同一请求头差异，连续两次生成
  SHA-256 不变，`git diff --check` 通过。
- 裁决：本功能与合并后本地 Gate PASS；远端接口契约 Gate 已在本地修复，
  待重新推送并取得全绿后才能部署。

## G4 · 安全闸

- 触发：医疗来源文本 + 新健康写路径。
- 独立规格评审：GO（Critical 0、Important 0）。
- 独立医疗质量/隐私评审：GO（Critical 0、Important 0）。
- 已验证边界：只有明确保存才写入；普通陈述/咨询零写入；原始 assessment
  保留、来源不升级为 Reva 诊断；owner isolation、rollback、verified receipt、
  日志隐私与 false-save backstop 均通过。
- 裁决：PASS（2026-08-01，HEAD `97f26b55f`）。

## S6 · 部署

- 路由：backend-deploy。
- 首轮部署 SHA：`c78b5b1ef419ddec92346bb1e0b7372ca4cd182c`；从与
  `origin/main` 完全一致的临时干净 main 部署。
- 首轮回滚点：`e966281cd50b45bbf98bd623923705b9b2cce2c0`。
- 生产数据库备份：
  `/var/backups/health-app/database/health_db_2026-08-03_15-52-23_1617541.sql.gz`
  （恢复演练通过，237 tables）；生产 `.env` 备份：
  `/var/backups/health-app/env/.env.20260803_155911`。
- 首轮 main CI：run `30788287172` attempt 2 全绿。一次性
  `HARNESS_LIVE_LLM_EVAL_CONFIRMED` 变量在 CI 后已删除并验证不存在。
- 第二轮部署 SHA：`431ea2d10394a37cf00888f69fb33b8bffdc3511`；CI run
  `30798444883` 全部 44 jobs 成功。一次性 live-eval 变量在
  `backend-quality` success 后删除并验证 `not found`。
- 第二轮回滚点：`c78b5b1ef419ddec92346bb1e0b7372ca4cd182c`；数据库
  备份 `/var/backups/health-app/database/health_db_2026-08-03_17-07-25_1679893.sql.gz`
  恢复演练 237 tables，异地加密归档哈希/HMAC 通过；env 备份
  `/var/backups/health-app/env/.env.20260803_171352`。
- 部署启动后 `origin/main` 被并发推进到 `96e10374f`；事务保持锁定、生产只
  安装已验证 `431ea2d10`，未混入并发提交。后续修正须先合并最新主干并重新
  通过 CI，不能直接追部署未知提交。
- 并发饮食功能随后独立完成其 Gate 并把生产推进到
  `96e10374f6a600fe8401abb5b7fb9360b963b911`；本任务只读复查 backend active、
  `/api/v1/health` healthy。上下文修正已合并该主干及其 docs-only 收尾提交，
  第三轮发布必须以新的远端 main 精确 SHA 为准。
- 第三轮候选 `3c83612d7` 的 CI 因 `type-drift` 失败，已按 Gate 停止，未部署；
  精确类型同步完成后待新候选全绿再部署。

## G5 · 部署健康闸

- 首轮部署健康分：`60/60 PASS`；远端 SHA 与部署 SHA 完全一致；运行时 KB
  guard、skills 对齐、schema probe 与发布事务终态均通过。
- 第二轮部署健康分三次 `60/60 PASS`；远端 SHA 精确为 `431ea2d10`；schema
  probe、runtime-only KB guard/staged、skills `22 = 22` 和事务 finalize 通过。
- 裁决：首轮与第二轮 G5 PASS；第三轮修正部署待复验。

## S7 · 上线验证

- 原始截图语句经生产 API 得到语义理解，并明确“不自动保存”；医生反馈计数
  `0 -> 0`、tools `[]`、error `null`。本地 smoke 仅因过度精确断言期待字面
  “未保存”而退出 1，产品行为本身通过。
- 显式保存生产 smoke 成功，创建唯一测试反馈 ID `206`，回执工具为
  `record_doctor_feedback`。随后新会话召回失败，触发 Correction Block 9。
- 测试会话均已删除；ID `206` 通过 `id + user_id + created_by + release marker`
  精确删除并复查计数为 0，生产无合成医疗数据残留。
- 第二轮生产 smoke：显式保存成功，tools
  `["record_doctor_feedback"]`，创建唯一测试反馈 ID `207`；新会话 guard
  正确保持 tools `[]`，但因 FULL/MINIMAL 预算断链未拿到反馈，触发
  Correction Block 10。会话 `1826` / `1827` 均删除成功；ID `207` 按
  `id + user_id + created_by + release marker` 精确清理，标记复查计数 `0`。
- 第三轮仍执行相同闭环，并要求回读正文包含“大腿 / 臀部 / 腰肌”。

## G6 · 验证闸

- 首轮历史结果：**FAIL** —— 裸陈述与显式保存通过，但新会话召回错误；已停止
  完成声明并回到 S5 修正。
- 第二轮历史结果：**FAIL** —— recall 只读语义正确，但个人上下文预算误降级；
  已停止完成声明并再次回到 S5 修正。
- 当前状态：上下文预算修正已完成；第三轮首个发布候选因接口类型漂移被 CI
  拒绝且未部署，漂移已本地精确修复。待新候选 CI、部署与生产 smoke 后作出
  新裁决。

## S8 · 沉淀

- 待实现后判断是否需同步 Agent 行为文档或 system map 生成物。
