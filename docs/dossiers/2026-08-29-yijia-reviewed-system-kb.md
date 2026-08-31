# Dossier: 益家知研受审 System KB 上线

| 字段 | 值 |
|---|---|
| slug | `yijia-reviewed-system-kb` |
| 创建日期 | 2026-08-29 |
| 当前阶段 | G6 上线验证完成 |
| 状态 | shipped |
| 负责 | Codex |
| 反馈环 | source discovery -> reviewed claim pack -> source-scoped retrieval -> backend deploy -> production replay |

## S0 · 用户需求（逐字）

> 帮我搞定

- 上下文目标：让小巴真正检索“益家知研 / 皮皮妈妈”指定知识源，而不只返回
  `not_released`。
- 锚点场景：用户在急性新冠/发烧和既往胃溃疡、脂肪肝语境下询问补剂。

## S1 · Discovery

- MyKnowledge 可读目录共 7 个，均非健康知识库；所有目录 `qaPairCount=0`。
- 私有 KBase `system-kb/export` 可访问，但当前导出为 0 entities / 0 claims /
  0 pages / 0 relations。
- 本地旧资产包括 `backend/knowledge_base/pipi_mama/*.md` 和
  `backend/knowledge/supplement_knowledge.md`；它们缺少逐条权威出处，并混有儿童
  退烧药剂量、高剂量补剂和泛化功效断言，不满足运行时医疗依据发布标准。
- 可复用发布面：reviewed JSONL artifacts -> `system_knowledge_importer` ->
  `kb_documents` -> `system_knowledge_service.search_knowledge`。
- 现有命名来源完整性修复已把该别名 fail-closed 为 `not_released`，可在受审内容
  真正存在后切换为 released source collection。

## G1 · 准入裁决

- classification: `product_change`。
- first_class_objects: `SafetyGuardian`, `HealthTwin` evidence boundary。
- core_loop_step: health question -> reviewed evidence -> safety-gated synthesis。
- target_surface: Backend Agent chat。
- source_of_truth: reviewed System KB artifacts and PostgreSQL serving tables。
- safety_level: `medical_boundary`; autonomy_tier: `none`。
- smallest_end_to_end_slice: 两条受审急性 COVID claim + 一个 source-scoped
  retrieval contract；不发布旧文全文或自动剂量。
- spec_required: yes。
- stale surface: `not_released` alias mapping is superseded only after the pack is
  present and release gates pass。
- **裁决：PASS。** 用户在已获知需走医学审核和 System KB 入库后明确要求“帮我搞定”，
  视为对安全转化切片的范围确认，不视为允许原文整包直发。

## S2 · PRD

- `docs/prd/2026-08-29-yijia-reviewed-system-kb.md`
- 权威约束：全局 PRD §2 确定性优先、§7 医疗安全；治理 Spec §6.6/§6.12。

## S3 · 规划

- `docs/plans/2026-08-29-yijia-reviewed-system-kb.md`

## G2 · 可行性与安全压测

- 原文整包发布：**BLOCK**。缺少逐条出处且含剂量/治疗性断言。
- 把通用 System KB 结果标成益家知研：**BLOCK**。违反来源完整性。
- 受审转化 claim pack + source collection 精确过滤：可行。
- 受审内容只允许说明补剂证据不足、及时治疗评估窗口、药物/肝肾相互作用核对；
  不允许生成补剂或处方剂量。
- 命名来源零命中必须返回“已检索但无匹配受审内容”，不得通用回退。
- **裁决：PASS。** 无待拍板分叉；安全路径是唯一可上线实现。

## S4 · 研发任务分解

- [x] T1 RED：source collection 只返回属于该来源的 reviewed documents。
- [x] T2 RED：益家知研别名执行真实 source-scoped retrieval。
- [x] T3 RED：急性 COVID/补剂查询命中受审边界，零命中不通用回退。
- [x] T4 GREEN：最小服务与 Agent 接线。
- [x] T5 更新受审 artifacts、manifest 与发布 eval。
- [ ] T6 G3 测试、G4 独立安全评审、CI。
- [ ] T7 后端部署和真实路径回放。
- 并发检查：已 fetch `origin/main` 并检查开放 PR；未发现同一命名知识源实现。

## Gate ledger

| Gate | Status | Evidence |
|---|---|---|
| G1 | PASS | Safe reviewed subset admitted; raw legacy promotion rejected. |
| G2 | PASS | Source-scoped reviewed retrieval is feasible and fail-closed. |
| G3 | PASS | 35 named-source/health interaction tests; System KB release gate 69/69; live LLM 5/5 plus deterministic suites all pass. |
| G4 | PASS | Independent reviewer GO; no Critical/Important findings. Minor negative-guard gap remediated with executable dose/raw-fragment assertions. |
| G5 | PASS | CI `33257262576` 全绿；生产部署 SHA `78ba65a60f43`，健康度 60/60。 |
| G6 | PASS | 生产只读回放命中精确两条受审 claim；通用检索零泄漏，来源回执与剂量负向护栏通过。 |

## Rollback

Revert source-collection code and reviewed artifact rows, redeploy backend, and return
the aliases to `not_released`. No schema migration is planned.

## G3 · 测试证据

- TDD RED：`search_knowledge(..., source_collection=...)` 最初以未识别参数失败；新增
  `named_collection_only` 测试最初证明条目会泄漏到通用检索。
- GREEN：相关服务、Agent 和健康证据运行时回归 `35 passed`。
- Artifact release gate：JSONL/manifest/import/lint 全通过，69/69 eval 通过；益家用例
  两条 claim 排名第 1/2，既有睡眠补剂用例恢复到第 12，证明未污染通用排序。
- Seed integrity：462 claims / 248 entities / 3320 relations，无孤儿 claim/entity。
- System Map、mobile nav、doc drift 全通过。
- 真实 TokenPlan `MiniMax-M2.5` 回归：invariants 12/12、health agent 50/50、
  orchestrator 5/5（平均 0.96）、trajectory contract 12/12、goldens 9/9。
- 非生产内存 SQLite 缺 `llm_usage_logs` 仅产生旁路告警；模型调用、裁判与闸门均成功。

## G4 · 独立安全评审

- 审查提交：`f2bef65f`；裁决：**GO**。
- Critical / Important：0 / 0。
- reviewer 独立复核 CDC、NIH ODS、NCCIH 原始页面，确认两条 claim 未超出
  补剂证据不足、尽早治疗评估、相互作用和肝肾限制核对边界。
- reviewer 独立验证 35 项测试、69/69 release eval、895 documents / 3320 edges、
  Ruff、py_compile 和 diff check 均通过。
- Minor：`must_not_include` 不是当前 eval runner 的可执行字段。本次已在 artifact 测试中
  增加剂量单位模式与旧配方片段扫描，并固定 `named_collection_only=true`，作为本知识包的
  可执行负向护栏；不借机改变全局 eval 语义。

## G5 · 主干 CI 反馈环

- 首次主干 CI：`33256739791`，结论 **FAIL**，因此未部署。
- 失败定位：两组 sealed runtime-only 契约测试通过 `authority_packs[0]` 构造漂移场景；
  新命名来源 pack 被插入首位后，这些场景不再命中既有 low-back runtime pack。
- 修复：保留原有 runtime pack 为首项，将 `named_generic_system_kb` pack 排在其后；
  runtime-only 策略代码仍按 `serving_scope=health_evidence_runtime` 精确过滤，未放宽安全契约。
- 本地复验：`test_kb_rollback_quarantine.py` 与 `test_runtime_only_kb_contract.py`
  共 38 passed / 1 skipped。
- 修复后主干 CI：`33257262576`，结论 **SUCCESS**；PostgreSQL 语义、发布/回滚契约、
  backend quality、完整后端测试聚合均通过。临时 `HARNESS_LIVE_LLM_EVAL_CONFIRMED`
  仓库变量在 CI 结束后已删除并验证不存在。

## G5 · 生产部署

- 部署提交：`78ba65a60f434a89a5d3f0234062a5ab2293391f`，与 `origin/main` 和远端
  `/opt/health-app` 精确一致。
- 数据库发布前备份 43MB；恢复演练覆盖 237 张表；站外加密归档 SHA-256 与 HMAC
  真实性校验通过。
- System KB 导入：895 documents / 3320 edges；重建后 910 dense vectors，
  backend=`pgvector:text-embedding-v4`。
- 部署后健康度两次 `60/60 PASS`；runtime-only guard/staged 契约均通过，
  generic exposure=0；事务 finalize 成功。

## G6 · 生产只读回放

- 查询：`我有胃溃疡和脂肪肝，新冠发烧时补剂怎么选？`
- `source_collection=yijia_reviewed` 精确返回：
  `claim:c_yijia_covid_supplement_evidence_boundary`、
  `claim:c_yijia_covid_early_treatment_assessment`。
- 同查询走通用 System KB 时，上述两个 `named_collection_only` claim 均未出现。
- `AgentExecutor` 生产回执：`requested_source=益家知研`、
  `resolved_source=yijia_reviewed`、`source_status=released`；数值剂量模式未命中。
