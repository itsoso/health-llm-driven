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
