# Dossier: Mobile 回答依据说明组件重设计

| 字段 | 值 |
|---|---|
| slug | `mobile-answer-evidence-panel` |
| 创建日期 | 2026-08-30 |
| 当前阶段 | G5 发布准备；后端先行、Mobile OTA 待后端健康检查 |
| 状态 | release_authorized |
| 负责 | Codex / 用户确认 |
| 反馈环 | Mobile Jest + TypeScript + iOS Simulator；发布另行授权 |

## S0 · 用户需求（逐字）

> 依据和过程 UI和内容都很丑 要想办法优化

- 谁用 / 解决什么 / 现在怎么绕过：Mobile 对话用户需要快速判断回答用了哪些个人数据、做了哪些处理、是否值得信任；当前只能在一块密集的调试面板里辨认来源、状态、耗时、轮次、模型和工具名。
- 锚点用户相关性：健康建议的依据必须容易找到，但主回答之后不应再出现一块工程日志式信息墙。

## S1 · Discovery（现状勘察）

- 已有可复用：
  - `mobile/components/chat/ChatBubble.tsx:2915` 已用 `AssistantUtilityPanel` 合并回答依据、分享和复制动作。
  - `mobile/components/chat/ChatBubble.tsx:2936` 已采用默认折叠，展开后依次展示技术摘要、来源、思考步骤和执行细节。
  - `mobile/components/chat/AttributionChips.tsx:22` 已按记忆、化验、用药、趋势、记录、知识库分类来源，并保留记忆来源跳转。
  - `mobile/utils/chatTransparency.ts:74` 已把耗时、成本、模型、轮次、数据源和工具调用整理成稳定 profile，无需修改服务端契约。
  - 邻近 Jest 已覆盖抽屉展开/收起、来源入口、工具成功/失败语义和分享动作。
- 当前缺口：
  - 展开面第一行直接显示 `约¥… · 6.1s · 2轮 · qwen…`，用户价值低、工程感强。
  - “思考过程”在完成态仍显示“正在思考 / 正在查询 / 整理回复中”，时态冲突，也容易被理解为暴露模型内部推理。
  - “使用数据 / 思考过程 / 执行过程”三段视觉权重接近，来源证据没有成为第一层。
  - 工具名、Token、run id、逐轮耗时与用户可理解的回答依据混排。
  - 整块仅靠小标题和密集文本分区，缺少摘要、层次、留白和二级技术详情。
- 硬约束 / 平台与安全边界：
  - 医疗引用与个人数据来源必须继续容易找到，不能以美化为由隐藏或删除。
  - 只展示可公开的状态摘要，不展示 chain-of-thought、原始 prompt、完整健康载荷或错误堆栈。
  - 不改变健康结论、模型路由、数据查询、写入、分享和记忆跳转语义。
  - 纯 React Native JS/TS；不新增依赖和原生能力，满足 OTA 边界，但本需求不自动授权发布。
- System Map：该单文件 selector 当前未被索引，已按规则回到源码与邻近测试验证，不以地图缺失阻断局部勘察。
- 并发：当前 `main == origin/main`；现有开放 PR 未触及该 Mobile 对话组件。

## G1 · 准入裁决（governance §8 RequirementAdmission）

- request：重设计 Mobile 完成态的回答依据说明组件。
- classification：`product_change`。
- first_user_fit：需要快速理解健康建议依据、又不希望阅读工程日志的 Mobile 用户。
- core_loop_step：`personal data -> HealthTwin / SafetyGuardian context -> answer -> evidence review -> safer action`。
- first_class_objects：`HealthTwin`（数据与不确定性来源）、`SafetyGuardian`（安全依据的可见性）。
- target_surface / source_of_truth：Mobile / 既有消息 `sourcesUsed`、`thinkingSteps`、`llmUsage`、`perf` 元数据。
- safety_level：`medical_boundary`（只改变证据呈现，不改变健康主张）。
- prescription_or_causal_verdict：`none`。
- autonomy_tier：`none`。
- evidence_provenance：保留现有来源标签、医疗引用卡和失败语义；技术遥测继续来自后端完成事件。
- claim_hedging：`n/a`，不新增医学主张。
- verification_window：实现后同轮运行 Jest / TypeScript / Simulator 展开与折叠视觉验收。
- success_metric：3 秒内能看懂“参考了什么、完成了什么”；技术信息不再占据首层；来源、错误和失败工具调用无丢失。
- added_user_burden：零；仍是一键展开，技术详情再按需展开。
- burden_justification：不适用。
- non_goals：不改回答正文、医疗引用内容、模型路由、Agent 执行链、后端 schema、分享入口和数据权限。
- smallest_end_to_end_slice：把首层重排为“回答依据 + 数据来源 + 处理摘要”，将耗时/成本/模型/Token/逐轮细节收进二级“技术详情”；完成态步骤改成完成时态并去重。
- stale_surface_to_remove_or_archive：删除完成态的“思考过程”命名、顶部裸技术串和扁平调试日志布局。
- spec_required：`yes`，属于新的用户可见信息层级；采用 Quick Flow，在一页 tech-spec 中合并 PRD 与计划。
- **裁决：PASS。** 范围限定为单一 Mobile 展示组件，无跨端契约、数据写入或健康语义变化。
- 用户确认：☒（2026-08-30，用户回复“可以”）

## S2 / S3 · Quick Flow 规格与规划

- 一页式 feature spec：`docs/specs/active/2026-08-30-mobile-answer-evidence-panel.md`。
- 设计方向：refined clinical notebook；先回答“参考了什么、做了什么”，技术遥测二次展开。
- 数据流：既有完成事件 → `buildAgentTransparency` → `AnswerEvidencePanel` → 来源 / 处理摘要 / 技术详情。
- 改动范围：从 `ChatBubble.tsx` 提取单独组件，修改邻近 Jest；不改 Backend / API / schema。
- 反馈环：Mobile Jest / TypeScript / ESLint → iOS Simulator；发布另行授权。

## G2 · 可行性与安全压测

- 平台可行性：既有消息和 transparency profile 已包含全部数据；无需新 API、依赖、原生模块或迁移。
- 安全边界：来源与失败必须保留；缺失/不可用步骤不能显示成功勾；技术详情默认收起但仍可访问；禁止展示内部推理和完整健康载荷。
- 范围分叉：无。用户已经确认“用户依据优先、技术信息二级折叠”的推荐方向。
- **裁决：PASS。** 用户确认：☒

## S4 · 研发任务分解

- [x] T1 以失败测试锁定新标题、完成时态、警示步骤和二级技术详情。
- [x] T2 新建 `AnswerEvidencePanel.tsx` 并从超大 `ChatBubble.tsx` 提取旧组件。
- [x] T3 保留来源跳转、分享、复制、错误和工具调用语义。
- [x] T4 跑定向测试、TypeScript、ESLint、diff check 与模拟器视觉验收。
- 跨端 API 契约：无变化。
- 发布路由：纯 Mobile JS/TS，后续如获授权走 OTA。

## S5 · 实现与 TDD 证据

- 从 `ChatBubble.tsx` 提取 `AnswerEvidencePanel.tsx`，形成“回答依据 → 参考的数据 / 处理摘要 → 技术详情”的两级披露。
- 首层不再出现模型、成本、Token、run id、工具名或逐轮耗时；这些信息仍完整保留在二级“技术详情”。
- warning 与 complete 分别计数；warning 不再被计入“已完成”，顶部改用 caution 语义。
- 原始 `error_message` 不再进入 UI，只保留失败次数与安全错误码；医疗引用仍独立展示在证据组件之前。
- 来源标签取消行数上限，记忆入口无障碍名称包含完整来源；44pt 交互目标由邻近测试锁定。
- 将“已取得健康数据”归一为中性动作“检查健康数据”，避免与“数据缺失”正文形成假成功冲突。
- 当回答含证据面板时，外层消息不再合并 VoiceOver 子节点；正文、回答依据、分享、复制和技术详情均可独立聚焦。
- TDD RED 记录：新入口文案、原始错误脱敏、warning 计数、长来源换行、健康数据中性动作和消息容器无障碍分组均先观察到失败断言，再做最小实现。

## G3 · 本地工程验证

- 定向 Mobile Jest：6 suites / 134 tests 全部通过；TypeScript、设计 token 闸、`git diff --check` 与 120 份 Dossier 一致性闸通过。
- ESLint 仅保留 `mobile/utils/chatTransparency.ts:91` 的既有 `Array<T>` 风格 warning，本 diff 未引入 error。
- iOS Debug 原生构建：0 error；既有 Xcode / Pods warning 不影响安装。

## G4 · 安全与独立复审

- 独立 reviewer 曾两次给出 NO-GO：warning 假计完成、长来源截断、旧集成断言；均已修复并回归。
- 当前边界：无新增医学主张、数据写入、权限、模型路由或后端契约；不展示 chain-of-thought、原始 prompt、完整健康载荷或错误堆栈。
- 最终 reviewer 裁决：**GO**。两个既有阻断、原生无障碍焦点问题与测试 Gate 均已关闭；未发现新增隐私、医疗语义或数据权限风险。
- 非阻断债务：VoiceOver 下消息长按菜单中的“朗读 / 更多操作”仍不是独立 AX action，后续应将正文操作显式暴露为无障碍动作。

## G5 / G6 · 发布与验收

- G5 已授权：2026-08-31 用户明确要求“搞定之后，进行 OTA”；纯 Mobile JS/TS 变更按 `scripts/mobile-ota.sh production` 执行，不使用 dirty escape hatch。
- G6 本地模拟器已验证：折叠态不抢正文；首层只显示来源与处理动作；技术数据须二次展开；原生无障碍树可分别聚焦回答依据、微信、小红书、复制和技术详情，并正确暴露 expanded 状态。
- Dynamic Type 已切到最大辅助字号做压力检查并恢复原 `large`；来源 `Text` 无行数截断，整体对话在最大字号下仍依赖纵向滚动（既有页面行为）。

## Correction Block · 2026-08-31 二阶段证据语义升级

- 触发：用户验收反馈“处理摘要都是通用表达，没有足够的信息”。
- 旧基线：假设 `sourcesUsed + thinkingSteps` 足以支撑用户理解回答依据，并将范围限制为 Mobile 单组件重排。
- 新证据：
  - `AnswerEvidencePanel` 的首层模型只有 `label + tone`，摘要只能统计来源数和步骤数。
  - 普通 Agent 路径曾把“用户哪些表有数据”直接加入 `sources_used`，并不证明本轮回答实际使用了这些数据。
  - 后端已有可确定性复用的工具结果、Health Evidence 本轮选中证据、freshness 与恢复数据质量闸，但未形成 Mobile 可消费的统一契约。
- 新基线：首层必须展示“本轮实际观察到什么、该数据用于什么、哪些数据不足以及如何处理”；查询/检查/整理只属于二级技术记录。
- 回退阶段：S2/S3 Quick Flow 规格与规划。
- 范围变化：升级为 Backend + Mobile 跨端只读展示契约；不新增 LLM 调用、不改变健康结论和写路径。
- 安全边界：只从本轮真实工具结果或本轮选中的 Health Evidence 编译；禁止从全部已填充数据表推断“本轮已使用”；禁止暴露 prompt、chain-of-thought、工具参数、完整载荷或未约束对象。
- G1：**PASS**。仍映射 HealthTwin / SafetyGuardian 的证据复核闭环；用户于 2026-08-31 回复“可以的”确认继续。
- G2：**PASS**。已有确定性表格构建器和 Health Evidence packet 可复用，无需额外模型调用；新增 `safety` overlay，历史重放与失败路径必须 fail closed。
- 待重跑：G3 前后端契约/持久化/撤权/类型/UI 测试；G4 独立安全复审；G5/G6 发布与真机验收不沿用上一轮结论。
- Harness run：`docs/_generated/harness-runs/1b873181e9f6.jsonl`（本地生成，不提交）。

### 二阶段实现与验证记录

- Backend：新增确定性 `answer_evidence.v1` 编译器；只接收本轮执行的受支持只读查询结果或 Health Evidence 已选 `PersonalEvidencePacket`，最多 4 条依据与 3 条限制，不接收模型散文、对象或数组原始载荷。
- Truthfulness：普通 Agent 路径停止用 `_inspect_user_data_sources` 枚举所有已填充表；`sources_used` 只保留本轮实际工具/知识来源。结构化依据写入 done 与 assistant `message.meta`，并用 SHA-256 绑定持久化投影。
- Replay：所有 assistant 历史投影都在健康意图早退前规范化并校验 `answer_evidence_sha256`；普通查询缺少/不匹配摘要、健康证据撤权或 verification 失效时均移除结构化依据。
- Mobile：新增严格归一化；done 与历史恢复共用同一校验。结构化消息首层显示“关键依据 / 数据限制”，通用查询、检查、整理步骤只进入技术详情；旧消息继续走原兼容展示。
- 2026-08-31 fresh checks：
  - Backend 定向全集：`346 passed`（编译、Agent done/meta、Health Evidence、普通与健康历史摘要校验、撤权与摘要篡改）。
  - Mobile：ChatBubble/stream/history/normalizer `167 passed`；`tsc --noEmit` 与 `expo lint --quiet` 均 exit 0。
  - `git diff --check` 与 changed Python `py_compile` 均 exit 0。
  - `./scripts/system-map-check.sh`：PASS；生成物已同步，`service_files` 由代码生成更新为 415。
  - 扩展 Backend 452 项：446 passed、2 failed、4 errors。4 个 error 均在测试应用启动时因本机 PostgreSQL 缺少 `health_app_runtime` role；2 个 failure 分别是多药确认轮次与 LangBridge 原图输入断言，本任务未修改对应逻辑，当前不将扩展套件记为全绿。
  - Live-LLM gate：BLOCK。确定性 invariants 12/12、health core 50/50、trajectory goldens 9/9 通过；真实 orchestrator 评测因预算守卫/数据库环境不可用与上游 429 无额度失败（0/5）。不得设置 `HARNESS_LIVE_LLM_EVAL_CONFIRMED=1`，不得进入发布。
- G3：本任务定向契约与 UI Gate **PASS**；扩展套件环境/非目标失败如上保留为 Unknown/未清零。
- G4 初审：**NO-GO**。独立安全 reviewer 复现了三项阻断：嵌套工具对象被字符串化进入 observation；stale/low-confidence/conflicts/failed partitions/truncated 未形成限制；普通历史消息可绕过摘要完整性校验。
- G4 修复：容器化工具字段让整条依据 fail closed；过期/低可信、来源冲突和加载/截断分别生成用户可见限制，冲突私有 detail 不透传；所有 assistant meta 统一在历史投影入口校验规范化结果和 64 位 digest。
- G4 复审：**GO**。原 reviewer 使用上一轮 batch/diet 攻击样例、陈旧/冲突 packet、普通历史 valid/missing/tampered digest 重新验证，三项阻断均关闭；owner 隔离与撤权清理保持成立。该 GO 只覆盖当前未提交 diff，不构成 commit、push、deploy 或 release 授权。
- 发布前 live LLM gate 使用一次性本地额度账本完成真实调用：invariants 12/12、health core 50/50、orchestrator 5/5（平均分 0.94）、trajectory contract 12/12、goldens 9/9，**PASS**。
- Release preflight：主干 CI 基线 `0160b0bfb` 为 green；secret scan、System Map/doc drift、Dossier 一致性、API 类型漂移、23 个 release invariant 与 Mobile changed-file 345/345 全部通过。
- 固定候选提交 `330aedbda` 的发布前独立复审为 **NO-GO**：长按通用菜单仍允许复制流式/中断/失败的半截回答。三类 RED 回归已复现该旁路；菜单与复制/分享/播报 handler 均已改为仅允许完整终态，定向 33/33 通过，等待修复后固定提交复审。
- 修复提交 `14078c987` 的独立复审为 **GO**：三类非完整状态均无复制/分享/播报入口，handler 具备二次终态检查；完整 assistant 与 user 操作保持，相关 Mobile 7 个套件 174/174 通过。
- G5：2026-08-31 用户在本轮明确回复“发布”，授权本批变更 commit、push、后端 deploy 与随后 Mobile OTA；仍按后端健康检查通过后再发 OTA 的顺序执行。
- G6：待真实发布回执、production revision 读回和 OTA update group / iOS update ID。
