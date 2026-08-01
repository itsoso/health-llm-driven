# Dossier: 小巴正确理解并记录医生来源的健康事实

| 字段 | 值 |
|---|---|
| slug | `clinician-attributed-context` |
| 创建日期 | 2026-07-30 |
| 当前阶段 | S4 研发任务分解 |
| 状态 | building |
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
- 已完成 Task 1A：typed primitives、span/order invariants。
- Task 1B：v2 最终 HEAD `2a8f57b07` 通过规格、未通过质量 Gate；正在按
  v3 authorization-proof correction 重做，不能作为 Task 1C 输入。

## G3 · 测试闸

- 基线：CI 模式相关测试 `158 passed`。
- 增量 / 集成闸：待实现后填写。
- main CI 真实色：待部署前检查。
- 裁决：待定。

## G4 · 安全闸

- 触发：医疗来源文本 + 新健康写路径。
- 评审：实现 commit 后执行 safety-gate。
- 裁决：待定。

## S6 · 部署

- 路由：backend-deploy。
- 部署 SHA / 回滚点：待定。

## G5 · 部署健康闸

- 健康分 / prod smoke：待定。
- 裁决：待定。

## S7 · 上线验证

- 用原始截图语句验证正常理解且无写入。
- 用“请记录医生诊断：……”验证医生反馈回执与后续召回。

## G6 · 验证闸

- 待用户真机确认。

## S8 · 沉淀

- 待实现后判断是否需同步 Agent 行为文档或 system map 生成物。
