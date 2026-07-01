# 知识库可视化 + dedao-kbase 融合 —— 分阶段设计

> 2026-06-28 · 设计稿(待 founder 审)· A 可视化先做(纯读),B 跨源对账后做(改入库数据,走安全评审)
> 方法:4 路 map 精确核现状 + A/B 分别设计 + 综合。**核心结论:两件事都已建一半,真 gap 在「可见 + 对账」,不在「再建导入」。**

## 0. 现状(先对齐,别重造)

**System KB V2 = reviewed-only 运行时知识库**:`kb_documents`(863)/`kb_edges`(3314)/`kb_audit`;`models/system_knowledge.py` 的 `metadata_json` (JSONB) 已带**全量 provenance**(origin / license_scope / source_repo / source_commit / source_path / external_sources[]);edge 带 `source_claim_id`;有 `KBDocumentVector` 稀疏向量。

**融合路径其实已经通了** —— 两条 authoring→publish pipeline 都进**同一道 reviewed 门**:
- `down_dedao_wiki_bridge.py`(531 行,origin=`down-dedao-llm-wiki`,直接 reviewed)
- `dedao_kbase_export_importer.py`(265 行,origin=`dedao-kbase-export`,draft→人工 approve)
- 共享内核 `_import_system_kb_export` / `_ensure_relation_endpoint_entities` / `_load_existing_doc_ids` / `_load_existing_relation_keys`
- 外加 `owner_curated_*` claims + genetic-reanalysis

**reviewed-only serving 门已强制**:`_reviewed_document_filter` / `_serving_document_filters` 在 `lookup_for_twin` + `knowledge_librarian.run` + `search_knowledge` 三处 —— draft/needs_review/archived **永不进 Twin/Orchestrator**。**别碰、别重造。**

**加层不减层已正确**:跨源同名 claim 写 `metadata.candidate_duplicates`(暴露)+ **从不 supersede/merge**;`clear_candidate_duplicates` reviewer 动作已存在。

## 1. 真 gap(map 揪出来的,我原先没看到)

1. **可视化很薄**:`admin/knowledge/page.tsx`(584 行)只有 stats + review-queue 表 + claim review 表单 —— **无图视图、无跨源覆盖矩阵、无逐项 provenance lineage、无去重候选队列、无实体对齐**。
2. **对账的硬 gap**:去重键 `_claim_key = (entity_type, entity_id, title)` 是**纯 schema 级**。两条 pipeline 若发出不同 `entity_id`(`entity:bacterium:hp` vs `entity:condition:hp-infection`),文档**永远各存各的孤岛**,**真跨源重复(Hp / 幽门螺杆菌)连 `candidate_duplicates` 都进不去**。这是融合真正没解决的核心。
3. **kg_service 不能复用**:`match_entity`/`upsert_entity` 只作用于 user-scoped `HealthEntity`,**不能用于 kb_documents**。KB 侧需要**新的对齐器**。
4. **复杂度债**:`system_knowledge_service.py` 已 4062 行(8× 500 行预算)。**新代码一律进新子模块**,不许往它上堆。

---

## 2. Phase A — 可视化(纯读,先上,零 runtime/治理改动)

目标:**让融合可见** —— 人能看见 down-dedao 和 dedao-kbase 在哪重叠,**在改任何数据之前**。三个视图全是纯 SELECT,挂在现有 admin 页做 tab,复用**已在库里**的数据。

### View 1 —— 覆盖矩阵(先做,最便宜,回报最高)
唯一的「融合可见」屏。行 = 8 个 entity_type;列 = 各 `metadata.origin`(**动态渲染** —— origin 是自由串,绝不写死 3 列)。每格 = {doc_count, reviewed_count(色深), avg_confidence, evidence_level 分布}。纯 SQL `GROUP BY entity_type, metadata->>'origin'`。
- 后端:新子模块 `services/system_knowledge_coverage.py`,现有 `get_knowledge_coverage_report` 追加 `matrix` 字段(不改签名)。
- **两个 origin 同一 entity_type 都非空的格 = 重叠区 = Phase B 对账该瞄准的地方**。点格 → 深链到 View 2 / 审核队列(按 entity_type+origin 过滤)。

### View 2 —— 实体关系图(种子邻域,非全量 dump)
数据全在 kb_edges + kb_documents。新后端 `admin_expand_kb_neighborhood(db, seed_doc_id, hops≤2)`(新子模块 `services/system_knowledge_graph.py`,BFS over KBEdge,借 `kg_service.expand_neighborhood` 的 hop/方向语义但**读 system KB 表非 HealthEntity**)。返回 nodes{doc_id, doc_type, entity_type, title, review_status, origin, confidence} + edges{src, dst, relation, confidence, origin, source_claim_id}。
- 前端 `KnowledgeGraphView`(react-force-graph / Cytoscape —— **新 npm 依赖须过 CLAUDE.md 三问 + 精确 pin 非 alpha**);node 按 entity_type 上色、edge 按 origin 描边;种子选择器 + hops 1–2;点 node → 侧栏走现有 `get_entity_bundle`/`get_claim_bundle`。
- **硬默认**:仅种子 + hops≤2;服务端超 N 节点截断;不渲染全图。

### View 3 —— provenance 溯源 + 审核生命周期(近零后端)
`serialize_document` **已发** sources + 全 metadata。`ProvenancePanel`(图+队列共享侧栏)渲染 lineage 链:origin 徽章 → source_repo@commit → license_scope 标签 → external_sources[] → candidate_duplicates 计数(**只读展示,无 merge 按钮**)。`ReviewLifecycleFunnel`(reviewed/needs_review/draft/archived)吃现有 `review_queue.by_review_status`。队列行加 origin 徽章 + candidate_duplicates 列(数据已在 payload,纯前端)。

### 唯一一处故意的治理开口
`admin_expand_kb_neighborhood` + 覆盖矩阵**必须绕过** `_serving_document_filters()`,好让 reviewer 看见 draft/needs_review 节点(看不见就没法审)。这个 bypass **物理隔离在 admin 读路径** —— 绝不能被 lookup_for_twin/knowledge_librarian/search_knowledge 调用(它们保留 `_reviewed_document_filter`)。**用一条测试钉死**:图端点返回某 draft 节点,但同 doc_id 的 lookup_for_twin 仍返回空。source_path 只渲染 artifact 相对路径(绝不落文件系统绝对路径);down-dedao 的 private/ 笔记**结构上不进 kb_documents**(bridge 只导 reviewed artifact),泄不了。admin 读也写 KBAudit(op=admin_graph_view/admin_coverage_view)。

---

## 3. Phase B — 跨源对账(改入库 serving 数据,后上,**必过 safety-privacy-reviewer**)

架构:**「对账候选」旁路,只产建议**。detector + LLM-judge 只**写候选**;只有**人的 PATCH 决定**才改 serving metadata(R4)。**每次变更都是 additive,永不物理删除**。

### 数据模型 —— 方案 A(旁路表,推荐;kb_documents 保持干净 + 可回滚)
新 managed 迁移(pg+sqlite 双文件)建 `kb_reconciliation_candidate`:
`id, kind(entity_align|claim_overlap), left_doc_id, right_doc_id, entity_type, entity_id, relation_tag(agree|conflict|complementary|duplicate), score, signals JSONB(哪些 detector 触发:title_norm/alias_overlap/edge_overlap/vector_sim/judge_verdict + 逐源 confidence/evidence delta), status(open|approved|rejected|deferred), detected_at, reviewed_by, reviewed_at, decision JSONB`。
—— 这是 KBAudit 缺的「合并前可审状态」。**kb_documents/kb_edges 零结构改动**(Frozen Core),只往现有 metadata_json 写 additive 键:doc 上 `merged_into`/`aliases`/`provenance_lineage`/`conflict_status`;edge 上 `superseded_by_align`。KBAudit op 扩 `entity_align_approved`/`claim_conflict_flagged`/`claim_merge_source_folded`。

### 1. 实体对齐(Hp / 幽门螺杆菌 问题)
按 entity_type 分桶,桶内用 title/summary 归一 + aliases 重叠 + 共享 KBEdge 邻域 + 可选 KBDocumentVector 语义 NN 打分候选对(**新 KB 对齐器,非 kg_service**)。reviewer approve 后:loser doc 得 `metadata.merged_into=<canonical>` + `is_archived=True`(因非 reviewed-active 自动掉出 serving),aliases 折进 canonical,KBEdge 重指 canonical(旧 edge 得 `superseded_by_align`,**从不删**;重指复用 `_relation_key` 防重复边)。**同阶段必带反向 `unalign`**(误合必可撤)。

### 2. claim 重叠/冲突 —— 三态
复用现有 candidate_duplicates 作同名种子,扩成 agree|conflict|complementary(确定性 + LLM-judge 混合,复用 `system_knowledge_eval.py`)。**医嘱式 claim(饮食/用药/补剂剂量)无论 judge 判什么一律强制走 conflict-review**;judge 仅 advisory。

---

## 4. 治理硬边界(设计绝不可违)

1. **reviewed-only serving 门不可变**:两阶段都不改 health agent 服务的内容。
2. Phase A 的 admin bypass **物理隔离**在 admin 读路径 —— 测试钉死(图见 draft / lookup_for_twin 空)。
3. **加层不减层**:合并永不丢 claim,只 additive(merged_into/is_archived/superseded_by)。**count 不变量测试**:合并前后 doc 数相等(archived+active)。
4. **冲突必暴露**:relation_tag=conflict 恒进 review_queue,服务端**硬拒**对它的任何 merge(端点守卫,非仅 UI)。
5. **无自动 promote 到 reviewed、LLM 无不可逆动作(R4)**:detector/judge 只写候选,人 PATCH 才改,恒写 KBAudit。
6. **不泄原始笔记**:只读 kb_documents(已转换的 reviewed/draft 面);private/ 永不入库;source_path 只 artifact 相对路径。
7. **license 绝不静默放宽**:合并保留最严 license_scope,两个都记进 provenance_lineage。
8. **Frozen Core 不动**:Phase B 只加一张旁路表 + additive JSONB 键。

---

## 5. 分阶段(各自可独立上线)

| 阶段 | 内容 | 迁移 | 治理闸 |
|---|---|---|---|
| **P0** ⭐ | 覆盖矩阵 query(`system_knowledge_coverage.py` + 追加 matrix 字段)| 无 | 纯读,1 个 shape 测试 |
| P1 | 覆盖矩阵 tab + provenance 侧栏 + 生命周期漏斗(前端)| 无 | 纯读 |
| P2 | admin 邻域读端点 + 交互图(新 npm 依赖过三问)| 无 | **隔离测试**(draft 图见/twin 空)|
| P3 | 对账候选表 + detector + 扫描(只读,不改 serving)| **有** | detector 只写候选 |
| P4 | 实体对齐写路径(首个 mutation)+ unalign | 无 | **safety review** + count 不变量 |
| P5 | claim 折叠 + 冲突 flag(服务端守卫)+ provenance 并集 | 无 | **safety review** + 冲突硬拒合并 |
| P6 | 对账 tab + 并排详情 + provenance 徽章(前端)| 无 | 纯 UI |

## 6. 第一刀(P0):覆盖矩阵 query
- **为什么先**:最小改动兑现「让融合可见」的全部意义。纯 SELECT(`GROUP BY entity_type, metadata->>'origin'`),零 runtime/治理/schema 改动,无新 npm 依赖,一个 shape 测试。复用两个 importer 都已 stamp 的 `metadata.origin`,**无需 backfill**。它的输出(哪些 entity_type 两个 origin 都非空)**正是 Phase B 对账要瞄准的重叠区** —— 在写任何 B 代码前就给整个 B 阶段去了风险。图视图更好看但 5× 成本(新依赖/BFS/隔离测试),放后面。
- **具体**:`services/system_knowledge_coverage.py::build_coverage_matrix(db)` 跑上面那条 SQL(reviewed 计数用 `FILTER (WHERE metadata->>'review_status'='reviewed')`);`get_knowledge_coverage_report` 追加 `matrix`(动态 origin 键,绝不写死);`tests/test_system_knowledge_coverage.py` 断言矩阵 shape + 种子的 down-dedao 与 dedao-kbase doc 落在不同 origin 列的正确 entity_type 下。不改 API 签名、无迁移、暂无前端。

## 7. 待你拍板(founder decide)

1. **对齐权威策略**:down-dedao(reviewed)与 dedao-kbase(draft)描述同实体时,down-dedao **恒为 canonical 幸存者**,还是 confidence/evidence 投票?B4 前须定。
2. **对齐召回目标**:Hp/幽门螺杆菌 标注 fixture 上 detector 召回多少算够(0.8?0.9?);是否**每次对齐都要人确认**,还是高分可 auto-suggest 但仍需一键?
3. **LLM-judge 信任边界**:哪些 entity_type/predicate **无论 judge 都强制 conflict-review**?提议地板=一切医嘱式(饮食/用药/补剂剂量)—— 你确认清单。
4. **图 npm 依赖**:react-force-graph vs Cytoscape vs 纯 SVG 自绘;三问闸(现有为何不行/Snyk 干净/近半年更新)须先答。v1 值不值一个重交互库?
5. **对账数据模型**:确认方案 A(旁路表)优于方案 B(kb_documents 内联 JSONB)。旁路表更干净可回滚但多一张表。
6. **审核面合并**:dedao-kbase 的 draft→approve 流程与新对账队列**分开**,还是合成一个 review 面?(影响 B6 是否吞掉现有 draft_review)
7. **Phase A 审计范围**:每次 admin 图/覆盖**读**都写 KBAudit(全轨迹、更多行),还是只写 mutation?当前设计连读都写 —— 确认。

## 8. 风险

- **admin bypass 漏进 runtime**:`admin_expand_kb_neighborhood` 一旦被接进 lookup_for_twin,draft 进 Twin 破门 → **隔离子模块 + 隔离测试**。
- **对账召回低**:因 `_claim_key` 跨 entity_id 不碰撞,现有 candidate_duplicates 漏真跨源重复 → 新 detector 扛全部载荷,**先在标注 fixture 上测召回**再信;欠召回=静默留碎片。
- **实体误合有医疗后果**:对齐两个真不同实体会污染图 → 合并 additive(never delete)+ 同阶段发一等 unalign。
- **system_knowledge_service.py 4062 行**:新逻辑一律进新子模块。
- **图依赖风险**:重交互库对 admin-only 页可能不值 → v1 考虑静态 SVG。
- **provenance_lineage 无 FK**:loser doc 若被硬删,lineage doc_id 悬空 → never-hard-delete 不变量测试。
- **桶内 O(n²) 两两扫**:863 doc/8 类型下 OK,vector 相似须便宜预筛,KB 长大后 admin 扫描端点会慢。
- **origin 列基数漂移**:origin 自由串,新 pipeline 加新列 → 前端**动态渲染**,写死 3 源会静默藏第 4 源。

---

## 9. Phase B v2 —— 两个决定落定后的 auto-approve 契约(2026-07-01)

> A 线全上线(P0 覆盖矩阵 · P1 前端矩阵 · P2 邻域图,含治理隔离机械护栏)。B 线两个 §7 开放问题被 founder 拍板,本节据此把对账 auto-approve 设计到「越不了硬不变量」的粒度。方法:4 路对抗 lens(auto-approve 机制 / 不变量攻击者 / eval / canonical 幸存者)+ 综合,全部对真代码核过。
>
> **§7 状态更新**:Q1 → §9.1 定;Q2/Q3 → §9.2/§9.4 定;Q5(方案 A 旁路表)沿用;Q4(图依赖)已由 P2 纯 SVG 自绘解决;Q6/Q7 仍开(见 §9.6)。

### 9.0 两个已定决定
- **D1 down-dedao canonical 优先**:down-dedao(reviewed)与 dedao-kbase(draft)描述同实体/同 claim 时,down-dedao reviewed 侧**恒为 canonical 幸存者**,非 confidence/evidence 投票。
- **D2 LLM 判重自动 approve**:LLM 判重 judge 可对**重复**候选 auto-approve(置 status=approved 并触发合并),不必人 PATCH ——**仅限 dedup/merge 一种形状**。

### 9.1 canonical 选择(D1,确定性纯函数 `resolve_canonical`)
- 恰一侧 origin=`down-dedao-llm-wiki` ∧ reviewed ∧ 未 archived → 该侧 canonical。
- 两侧都 reviewed(down-dedao×down-dedao)→ 幸存者 = 三元组 MAX(evidence_level_rank {A:4,B:3,C:2,D:1} → active-edge degree → doc_id 升序),**approve 时事务内重算并写进 decision JSONB**(防检测态/审批态之间并发 import 改 degree 翻盘)。**v1 该同类 reviewed 对默认 DISABLE auto,走人**(archive 一个 reviewed 文档比折一个 draft 高危)。
- 两侧都不是 reviewed down-dedao(两个 dedao-kbase draft,或 down-dedao 未 reviewed)→ **auto-approve 硬拒(422 no reviewed canonical anchor),走人**。draft↔draft 判重永不 auto。
- **confidence/evidence delta 结构性排除出选择** → draft 再高的 importer 置信也压不过 reviewed down-dedao(杀掉「攻击 1」)。

### 9.2 auto-approve 契约 —— 单一服务端 choke-point `can_auto_approve(db, candidate)`
新模块 `backend/app/services/kb_reconciliation.py`(**绝不堆进 4062 行的 `system_knowledge_service.py`**)。该函数**重读 live DB 行**(origin/review_status/is_archived/entity_type/predicate)、**从 signals JSONB 重推** relation/conflict,**绝不信 judge 自报**;auto executor 与人的 reconcile-PATCH 端点**共用**它(I4 端点守卫非 UeI)。judge 只能**降级到人**,永不能把 conflict/prescriptive/draft 对升级成可自动合。全部 C1–C9 为真(AND)才 fire,任一假 → 候选留 `open` 入人工队列(fail-loud):

| 闸 | 条件 | 护的不变量 |
|---|---|---|
| C1 形状 | kind∈{entity_align,claim_overlap} ∧ relation_tag=='duplicate' | I3/I4(agree/complementary/conflict/novel 全排除出自动路) |
| C2 canonical 源 | 幸存者 origin=='down-dedao-llm-wiki' | D1 |
| C3 canonical 已在服务集 | 对幸存者 doc_id **fire 时重跑** `_serving_document_filters()` 通过 | I1/I2(只往**已服务**的 canonical 折,服务集**零新增**) |
| C4 loser 是未审 draft | loser origin=='dedao-kbase-export' ∧ review_status≠'reviewed' | I2(archive draft,绝不 promote) |
| C5 非医嘱式 | 两侧 entity_type ∧ claim predicate 均不在处方地板;复用 `is_clinician_gated_metric`(`intervention_priors.py:131`)**+ 新增 anchored 药名/补剂剂量 predicate allowlist**(见 R4 gap) | I4 |
| C6 无冲突信号 | signals 无任一 detector 的 conflict flag ∧ 确定性值/剂量/方案不匹配扫描为空 | I4(冲突覆盖 judge 的 duplicate) |
| C7 claim 同指称 | claim_overlap 需**共享 predicate ∧ object**,非仅共 subject/entity 锚 | 杀「攻击 4」(Hp→胃炎 vs Hp→MALToma 都挂 Hp 但 object 不同→走人) |
| C8 分数 ≥ τ | judge_score ≥ 每 entity_type 精度校准地板;**τ = gold 上 auto 切片零误合的最小分**,无 τ<1.0 满足则该 type auto **DISABLE**;τ 作 anchored 常量由 doc-drift 钉 | I3(误合=掉覆盖,宁拒不赌) |
| C9 可逆 | 已注册 unalign 反动作 + 记 `decision.reverse_action_id` | I5(**代码里今天无 unalign**,C9 是真闸——unalign 必与写路径同 PR) |
| 扇出帽 | edge 重指 > 4 条 → 硬拒走人 | 无人合并的爆炸半径 |

**fire 时的 mutation(与人 PATCH 字节同,不引入新 mutation kind,单事务)**:候选 status='approved'、`reviewed_by='llm_dedup_judge:v<N>'`(机器 actor,**永不用人名**)、decision JSONB 存 9 布尔快照 + `auto_approved:true` + reverse_action_id;**loser** 加 additive 键 `merged_into`/`is_archived=True`/`review_status='archived'`/`provenance_lineage`;**canonical** 加 additive `aliases`∪、`provenance_lineage`(两 repo@commit + 两 license)、`license_scope` 收到**两者最严**(I6,只收窄永不放宽),**其 review_status/body/summary/confidence 一字不改**(服务载荷字节不变);loser 关联 **KBEdge 重指** canonical(`_relation_key` 去重),旧边留 + `superseded_by_align`(**永不删**,端点原样存好让 unalign 重建);KBAudit op∈{entity_align_approved,claim_merge_source_folded}。

### 9.3 I2 证明(为什么 D2 不是漏未审内容的后门)
服务门 = is_archived==False ∧ review_status=='reviewed'。折后 loser **两个合取都失败**(archived + 'archived'),掉出服务、比之前**更紧**;canonical 本就 reviewed-served 且内容零改;服务集基数**严格 -1**(draft 走,无新增)。loser→canonical 唯一跨越的是 aliases + provenance + 更严 license(均非服务 claim 文本)。故 D2 下 draft 的归宿只有「archived(折)」或「留人工审」,**永无「served」**。等价于 I3 count 不变量(archived+active 恒定)。

### 9.4 §4 不变量 I5(修订)—— 有界 auto-approve,其余全人工门 + additive 可逆
改 serving metadata 的对账默认是人 PATCH。**单一窄形状**可被 LLM judge 无人 auto:kind∈{entity_align,claim_overlap} ∧ duplicate,`resolve_canonical` 出**已 reviewed 已服务**的 down-dedao canonical(D1),loser 是未审 dedao-kbase draft,C1–C9 服务端对 live 行全过,且**该 entity_type 的离线 eval 已认证零误合**。此开口**不碰** I1/I2(§9.3 证)/I3(additive)/I4(处方+冲突两路硬拒,人机同拒)/I6(最严 license + 未知=fail-closed 最严)/I7(机器 actor + reverse_action_id 全审计)。

### 9.5 eval 闸(auto-approve 开关的前置,权威验证)
新 `backend/app/services/kb_reconciliation_eval.py::run_dedup_judge_eval(db,*,tau,with_llm)` + CI wrapper `tests/test_kb_reconciliation_eval.py`(内存 SQLite,mock verdict,无需 LLM key),注册进 `eval/runner.py` 的 `reconciliation` suite。
- **gold v1 = 40 对 founder 签名标注**(12 真重复 / 14 对抗近似:HbA1c×空腹血糖生物标记归一、子串陷阱、基因型/亚型、他汀×他汀、反义对、Hp×胃溃疡相关非同 / 8 互补 / 6 冲突含≥3 处方),存为 reviewed eval_case KB doc(版本化,judge 输出永不覆盖)。
- **精度是发布闸,召回不是**:误合=不可逆掉服务覆盖(带医疗后果的 I3 破);漏判=只留个重复在人工队列(零丢数据)。**精度地板 = gold auto 切片上绝对零误合**(任何近似/互补/冲突对被判可自动 = 硬红 FAIL)。τ 每 type = FP==0 的最小分;无则该 type **DISABLE** 并 `auto_approve_disabled[type]`。
- eval 另跑 **6 条不变量断言**(真内存 DB / 每 gold 自动合):count 不变量、unalign 往返字节还原、**NO-UNREVIEWED-SERVED**(真查 lookup_for_twin/search/librarian:loser 缺、canonical 在)、canonical=down-dedao(即便 draft 置信更高)、处方硬拒、license 不放宽。
- **CI 硬闸**:确定性层(gold FP==0 + 6 断言绿)**阻断**任何 mutation PR;τ anchored 由 `check_doc_drift.py` 钉,悄悄调低即 CI 红。**auto-approve 对某 entity_type 保持 DISABLE 直到其过 eval 地板** —— 「开 D2」= 「该 type 过了 eval」。

### 9.6 修订分阶段(替代 §5 的 P3–P6)
| 阶段 | 内容 | 迁移 | 闸 | 现在能开工? |
|---|---|---|---|---|
| **P3** | `kb_reconciliation_candidate` 表 + 确定性 detector(写候选)+ 只读 admin 队列 | **有**(旁路表 pg+sqlite) | 纯 additive scaffolding,**零 mutation 零 auto** | ✅ **GO now**(I1–I7 平凡成立) |
| P4 | 单一服务端 merge(resolve_canonical + additive 折 + edge 重指 + provenance/license 并)走**人 PATCH** + **unalign 同 PR** | 无 | safety review + merge↔unalign 字节往返测 + count 不变量;端点对冲突/处方人机同硬拒 | 待 P3 |
| P5 | advisory judge + `can_auto_approve` 9 闸(调 P4 同一 merge)+ `kb_reconciliation_eval` | 无 | auto **ships DISABLED**,**逐 entity_type** 过零 FP eval 才开;entity_align 先开,claim_overlap 对 药/补剂/基因/方案 类 v1 恒人工 | 待 eval |
| P6 | 扩 gold(近似库 ~24+)+ 校准更多 type + **生产影子审计**(抽样重排 auto 合给人静默复核)+ 按 `llm_dedup_judge` actor 的**速率熔断** | 无 | 运行时监控(不闸 P3–P5) | 待 P5 |

### 9.7 残余风险(未被任何 build-time 闸完全关闭)
- **R1 互补被判重复**:两个非处方、共 predicate+object 表面形的互补 claim(如两套都写「幽门螺杆菌根除方案」)无剂量/值 token 触 C6/C7,judge 语义错对结构信号不可见。地板:临床相关 claim_overlap 类默认关自动、entity_align(命名)先开;**检测即撤(unalign)非预防**。
- **R2 judge 规模化漂移**:prompt/模型回归可批量吐「看着对其实错」的自动合,快过人工发现;扇出帽只限单合爆炸不限总速率 → 需 **P6 速率熔断 + 定期人工抽审**。
- **R3 D1 固化错的 reviewed 文档**:down-dedao reviewed 系课程材料机器转,若本身错,把纠正它的 dedao-kbase draft 折进去(loser archived)会**压掉纠正**。D1 让 reviewed 侧即便更差也赢——**刻意 tradeoff**,只能**记录(每次 loser body 与 canonical 实质分歧的 case 落日志待审)不能闸掉**。
- **R4 处方真源是生物标记形(已核实 gap)**:`is_clinician_gated_metric` 覆盖 lab/BP/激素 + 中英词表,**不覆盖药名/补剂剂量自由文本**。C5 依赖**新 anchored 药/补剂剂量 predicate allowlist**;未签发前**任何药/补剂 claim_overlap 类恒人工**。漏一个 predicate = I4 泄漏 → **开自动前最高优先**。
- **R5 gold 小样本**:12 真重复对证不了总体精度,地板是「标注对抗零 FP」,界不测。分布外近似族(跨语言别名撞、单位驱动假等)可过 eval 却生产误合 → 只能 gold 扩张 + 影子审计(都滞后)。
- **R6 license 格是手排,代码真相与 lens 假设冲突(已核实)**:dedao-kbase 默认 `internal_transformed_claims`(importer:25),down-dedao 同时发 `internal_transformed_claims` + `licensed_transformed_content`,**今天无排序函数**。若把前者排成最严,一个默认它的 draft 折进 `licensed_transformed_content` canonical 会**误收窄**canonical(可用性非安全残余)。**两 scope 严格序须 founder 批**;未知恒 fail-closed 最严。
- **R7 确定性/LLM CI 漂移**:CI 跑确定性 + mock verdict;真 judge `--with-llm` 是 admin 触发非每 PR → 模型/prompt 变可回归精度到下次 admin 跑才现;τ anchor 治配置漂移不治模型漂移。

### 9.8 仍待你拍板(gate P5 非 P3,记录默认建议)
1. **精度地板策略**:确认「gold 零误合」(建议)vs「τ=0.95 全局」;确认「某 type 无 τ<1.0 达 FP==0 即 DISABLE 自动」。**单点决定每 type 到底开不开自动**。
2. **v1 entity_type 范围**:建议 entity_align 对低危(condition/biomarker 命名)eval 过即开;claim_overlap 自动对 药/补剂/基因/方案 **v1 恒关**(即便 duplicate)。
3. **同类 reviewed 对**(down-dedao×down-dedao):建议 v1 **DISABLE 自动走人**(archive reviewed 高危,超出 D2「archive draft」范围)。
4. **处方 predicate allowlist**:批 anchored 药/补剂剂量清单(扩 `is_clinician_gated_metric`,anchored 非子串)。未签发前任何药/补剂 claim 类不自动。
5. **license 严格序**:批 `internal_transformed_claims` vs `licensed_transformed_content` vs `public_reference` 具体排名;确认未知→最严/fail-closed,会**放宽 canonical 的合并直接拒 + 审计**。
6. **gold 规模**:40 对(12/14/8/6)够签 v1,还是近似库扩到 ~24 再开自动?
7. **生产误合预算 + 影子审计率**:确认 ≤1/200 auto 合为熔断阈,重排抽样率(如 1/20 静默人工复核)。
8. **扇出帽 N**:确认 4(仓库既有原子操作帽)。
9. **机器 actor 串**:确认 `llm_dedup_judge:v<N>`(永非人 reviewer_id),让审计不被误认人工签、熔断可按 auto actor 圈定。
10. **CI 策略**:动 judge prompt/模型 的 PR 是否**阻断式**跑 `--with-llm` 真 judge eval(关 R7,代价 LLM-cost CI 步,仅 judge-touching diff)。

> **净结论**:**P3 现在可开工**(纯 additive、零 mutation、零 auto,I1–I7 平凡成立,还产出 gold/τ 校准需要的真候选分布)。三道硬前置在**开任一自动合之前**必须全绿:merge↔unalign 字节往返测、逐 type 零 FP eval、处方 anchored allowlist 扩展。
