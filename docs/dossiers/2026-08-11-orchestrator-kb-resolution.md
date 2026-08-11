# Dossier: Orchestrator 单轮知识解析复用

| 字段 | 值 |
|---|---|
| slug | `orchestrator-kb-resolution` |
| 创建日期 | 2026-08-11 |
| 当前阶段 | G4 独立复评 GO；等待提交与集成 |
| 状态 | building |
| 负责 | Codex |
| 反馈环 | Backend focused tests → integration gates → guarded rollout |

## Correct Course

- [x] 2026-08-11 设计复核修正
  - 触发:只读 reviewer 发现 `precomputed` truthiness、cross-review 异常/空结果混淆，以及 parallel synthesis 未共享 fallback 的风险。
  - 旧基线:空 KB 结果可能被当成未计算；空 cross-review 同时表示无冲突和异常。
  - 新基线:`None` 才表示未计算；有效空结果不重查；cross-review `None / "" / block` 三态贯穿 mega、parallel、shadow；异常路径保留一次受控 fallback。
  - 回退阶段:S3。
  - 需重跑 Gate:G2、G3、G4。
  - 用户确认:用户已于 2026-08-11 批准增量方案，修正不扩大 scope，只补失败语义。
- [x] 2026-08-11 事务所有权修正
  - 触发:最终 reviewer 指出 catch-all retry 对 caller Session 执行 rollback 可能丢弃调用方 pending unit-of-work；后续复核又发现全局 `SessionLocal` 会绕过 caller bind。
  - 旧基线:首次查询异常后 rollback caller；临时独立 Session 固定绑定全局 Engine；mapper/import 不在 fail-soft 范围。
  - 新基线:每次 lookup 在 caller Engine 上创建独立事务 Session，复制或回退 tenant id；失败只 rollback 自有 Session并始终 close；import/mapper 失败为 `lookup_count=0 / lookup_ok=false`，整轮继续。
  - 回退阶段:S5 → G4 → S5。
  - 需重跑 Gate:G3、G4。
  - 验证:先观察 caller rollback / bind / mapper 用例 RED，再修复到 GREEN；两名只读 reviewer 最终均无 Critical/Important。

## S0 · 用户需求（逐字）

> “现在是主动将Context塞入到Prompts给到模型，而不是模型基于用户的原始Prompts，主动寻找应该把哪些Context或者知识库放到到Prompts，以及在拿到大模型的结果之后再做二次RAG，分析当前系统架构，是否还有更好的架构？”
>
> “分析业界，github上，是否有更好的最佳实践，做一下调研，并且继续改进系统架构，目标是能更快”
>
> “分析其他两个session执行情况，确保不要冲突”

- 谁用 / 解决什么:健康 Agent 用户需要更快的综合回答，同时不得因 Agentic 检索遗漏药物、过敏、红线等必选安全上下文。
- 当前痛点:Orchestrator 对同一 Twin 在 finding 绑定和 synthesis prompt 中执行重复系统知识查询；健康无冲突路径重复 cross-review；关键阶段缺少可归因耗时。
- 锚点用户相关性:更低等待时间、更一致的证据快照和不降低医疗安全边界。

## S1 · Discovery（现状勘察）

- 已读系统入口:`docs/system-map/INDEX.md`、产品治理、流程契约与项目 skill binding。
- 已有可复用:
  - Orchestrator 的 lite fast path、specialist 并行、parallel synthesis shadow、perf audit。
  - `lookup_for_twin` 的结构化条件匹配与 claim ref 选择。
  - Prompt cache、连接复用、确定性 query reply、history compaction。
- 主要发现:
  - 外层 `pre_llm` p50 约 217ms，不是当前首要瓶颈。
  - 系统 KB 在多个 applicable findings 上形成 N 次 lookup，prompt 再查一次。
  - cross-review 已计算无冲突时仍因空串触发 fallback 再查。
  - `twin.meta.build_ms` 不能代表本轮 cache-hit wall time。
  - IQS 对非-lite 路径可能贡献尾延迟，但本切片只补观测，不改触发行为。
- 业界/GitHub 调研结论:
  - 最佳实践是确定性必选安全上下文 + 可选按需检索 + 条件式 corrective RAG。
  - 默认路径应是 `NO_RAG | ONE_SHOT | CORRECTIVE` 三档，而不是全 Agentic 或无条件二次 RAG。
  - Haystack/LangGraph/LlamaIndex/DSPy/pgvector 的并发、状态机、压缩、离线优化模式可借鉴，不需要为本切片引入框架。
- 性能基线:相关 Orchestrator/System KB/Cross-review 测试 87 passed（2026-08-11，改动前）。

## G1 · 准入裁决

- first_class_objects:无新增产品对象；内部 `_TurnKBResolution` 是一次请求内的工程快照。
- core_loop_step:Health Twin → specialist evidence → synthesis。
- target_surface / safety_level / autonomy_tier:Backend / medical_boundary / 现有自治等级不变。
- spec_required:否。属于既有核心循环的性能与一致性维护，不新增用户行为、跨端契约或自治能力；走 Quick Flow 技术设计 + Dossier。
- smallest_end_to_end_slice:单轮 KB snapshot 同时供 findings 与 prompt 使用；cross-review 三态；四段 wall-time 指标。
- stale_surface_to_remove:无用户 surface；移除内部重复查询。
- **裁决**:PASS。
- 用户确认:2026-08-11 “可以”。

## S2 · PRD

- 链接:不新建 PRD；产品行为不变。
- 权威需求:本 Dossier S0 + `docs/plans/2026-08-11-orchestrator-kb-resolution-design.md`。
- 边界（不做）:不改 Agent Kernel/Executor、Context 路由、IQS 资格、LLM 次数、模型选择、输出文案或二次 RAG。
- 验收 Gate:健康路径单轮一次 KB lookup；证据/Prompt 同源；cross-review 无冲突不重跑、异常有 fallback；stream/nonstream 指标一致；现有安全测试全绿。

## S3 · 规划

- 设计:`docs/plans/2026-08-11-orchestrator-kb-resolution-design.md`。
- 实施计划:`docs/plans/2026-08-11-orchestrator-kb-resolution.md`。
- 反馈环:TDD RED → EvidenceResolver GREEN → formatter GREEN → cross-review 三态 GREEN → nonstream/stream 集成 → focused regression → independent review。
- 长杆:stream background Session 测试、parallel synthesis 的冲突块一致性、完整 coverage 报告耗时。

## G2 · 可行性 + 安全压测

- 可行性证据:现有函数边界已支持在 Orchestrator 内集中构建 Twin payload；formatter 可纯函数化；所有变更可向后兼容。
- 安全硬约束:
  - `lite_mode` 继续按 `not specialists`。
  - 空结果以 `is None` 区分，零命中不重查。
  - lookup 失败不生成 refs；最多一次受控异常重试。
  - cross-review 检测失败不能伪装成“无冲突”。
  - mega/parallel/shadow 使用同一最终 conflict block。
  - 指标禁止健康内容。
- 性能硬约束:健康 non-lite 路径 `lookup_for_twin` 恰好一次；lite 为零；不增加在线 LLM 调用。
- 评审:主 Agent + 独立只读 reviewer；两处失败路径风险已回到 S3 修正。
- **裁决**:PASS —— 正常路径不降低医疗安全；失败路径已有明确恢复策略与测试要求。

## S4 · 研发任务分解

- [x] T1 EvidenceResolver 单批懒加载一次 + precomputed seam。
- [x] T2 纯 System KB result formatter。
- [x] T3 cross-review 三态与异常 fallback。
- [x] T4 nonstream turn-scoped KB snapshot + metrics。
- [x] T5 stream parity + SSE/audit metrics。
- [x] T6 focused/integration/static/doc gates + independent review。
- 并发检查:
  - Session `semantic-illness-query` 独占 Agent Kernel/Executor；本切片不触碰其文件。
  - Session `ios-1-3-3-app-store-release` 已完成并释放 release/EAS/production lock；复查状态为 idle。
  - `semantic-illness-query` 最新仍在独立 worktree 处理 `agent_kernel/capability_policy.py`、`agent_kernel/health_semantics.py` 及其 eval/test；与本切片文件交集为 0。
  - 开放 PR 与本切片目标文件无重叠。
  - 分支:`codex/orchestrator-kb-resolution`；worktree 从 `origin/main@506eb23bb` 创建，基线一致。

## S5 · 实现

- 当前状态:completed locally，尚未提交/集成。
- 已实现:
  - EvidenceResolver 对一批 applicable findings 懒加载一次，并接受 precomputed falsey 结果，不把 `{}` 当成未计算。
  - System KB prompt formatter 从 DB wrapper 中拆为纯 result formatter；findings 与 prompt 共享同一轮快照。
  - Orchestrator 的 nonstream/stream 都建立 `_TurnKBResolution`，正常 non-lite 一次 lookup，lite 为零，异常最多一次重试。
  - 每次 lookup 使用 caller bind 上的独立事务 Session；不提交/回滚 caller，失败清理自有 Session；mapper/import/formatter 均 fail-soft。
  - cross-review 采用 `None / "" / block` 三态；同一最终 block 供 mega、parallel、shadow 使用。
  - 新增 Twin wall、KB、cross-review、IQS 指标；stream audit 与 `done.perf` 同源。
- 修改范围:
  - `backend/app/services/evidence_resolver.py`
  - `backend/app/services/system_knowledge_service.py`
  - `backend/app/orchestrator/orchestrator.py`
  - `backend/tests/test_orchestrator_context_reuse.py`
  - `backend/tests/test_orchestrator_stream_persistent.py`
  - `backend/tests/test_system_knowledge_v2_pipeline.py`
  - 本 Dossier 与两份设计/实施文档。
- implementation commit:`3bb70ad67`（`perf(orchestrator): reuse turn-scoped knowledge`）。

## G3 · 测试闸

- 改动前基线:87 passed，17 warnings，165.01s。
- TDD RED/GREEN:
  - EvidenceResolver:先观察两个 applicable findings 发生 2 次 lookup、precomputed 参数缺失；修复后选定 3 项 GREEN。
  - pure formatter:先观察 import 缺失；修复后等价/截断用例 GREEN。
  - cross-review:先观察空 block 重算、异常折叠为空串、resolver 缺失；三态及 mega/parallel 共享用例 GREEN。
  - nonstream/stream:先观察一轮 2 次 KB lookup 与指标缺失；集中快照后 GREEN。
  - 事务/bind:先观察 caller rollback、全局 Engine 与 mapper 异常外泄；caller-bind 独立 Session、双失败 cleanup、真实 committed claim、mapper zero-session 用例 GREEN。
  - falsey/retry metrics:先观察 avoided-count helper 缺失；`{}` 与 retry-aware 公式 GREEN。
- focused regression（最终代码）:175 passed，17 warnings，21.98s，`--no-cov`。
- coverage 模式（最终代码）:175 passed，17 warnings，88.70s；该 focused 组合对全仓 `app` 的总体覆盖为 25%，不把局部组合误报为全仓 80% Gate。
- backward compatibility:通知 evidence policy、agent loop notification、push scheduler、specialist backfill 均包含在最终 175 项回归内。
- static/doc gates:
  - `compileall`:PASS。
  - Ruff `F821,F822,E9`:PASS。
  - `git diff --check`:PASS。
  - `scripts/check_doc_drift.py`:PASS。
  - `backend/scripts/check_dossier_consistency.py`:PASS（更新前 102 份；本次更新后再次执行）。
- **裁决**:PASS。

## G4 · 安全闸

- 触发:医疗证据绑定与 specialist 冲突裁决属于 safety-sensitive 路径。
- 评审关注:refs 等价、零命中/异常语义、parallel/mega 一致、跨用户隔离、日志隐私。
- 独立最终评审:
  - reviewer 1 首轮提出 caller rollback Important；修复后最终批准，无 Critical/Important。
  - reviewer 2 提出双失败事务清理、falsey 测试、retry metric、mapper fail-soft 与 caller bind Important/Minor；逐项修复后最终批准，无 Critical/Important。
  - 非阻塞观察项:生产关注独立 lookup Session 的池等待；`Connection` bind 分支未单独造 mock，但生产 `SessionLocal` 与真实 committed-claim 测试覆盖 Engine bind 主路径。
- **裁决**:PASS。

## S6 · 部署

- 路由:Backend-only；无 DB migration、无 Mobile/Web 变更。
- 当前限制:release lock 已释放；语义 Session 仍活跃但文件交集为 0。为遵守隔离约束，先提交本 feature branch，再由集成选择决定 merge/PR/deploy。
- 回滚:回滚代码 revision 即可，无数据回滚。

## G5 · 部署健康闸

- 健康分:pending。
- 生产 revision / 日志指标:pending。
- **裁决**:pending。

## S7 · 上线验证

- 计划:使用无敏感内容的合成健康分析请求，对比 `kb_lookup_count`、`kb_lookup_reuse_count`、stage wall-time、引用覆盖与最终安全输出。
- 结果:pending。

## G6 · 验证闸

- 延迟/查询目标在 production 真成立?:pending。
- 安全与引用无回归?:pending。
- **裁决**:pending。

## S8 · 沉淀

- 已沉淀:
  - 单轮 snapshot 的 `None` 与有效 falsey 结果必须分离。
  - retry 必须拥有自己的事务边界，不能 rollback caller；独立 Session 必须继承 caller bind/tenant。
  - `kb_lookup_reuse_count = legacy potential attempts - actual lookup attempts`。
  - 后续 ContextPlan/三档 RAG 路线记录于设计文档，等 `semantic-illness-query` 释放 Agent Kernel/Executor ownership 后再实施。
- 状态:local design + implementation complete；production latency feedback pending G5/G6。
