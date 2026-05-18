# Agent Native 系统知识库建设计划

**日期**: 2026-05-16
**作者**: itsoso (产品 Owner) + Claude (技术合伙人)
**目标**: 用 Karpathy LLM Wiki v2 模式，把 `~/work/personal/down-dedao/` 已有的得到课程素材，编译成系统级（全平台用户共享）的健康知识库，为基因 + 个人健康信息驱动的 LLM 对话提供证据增强
**状态**: 已复核并进入执行；原 Claude 计划方向保留，但执行顺序调整为“治理与引用闭环优先，LLM 全量抽取后置”

> 本文档是项目级落地计划。Karpathy 原版 LLM Wiki 与 v2 (agentmemory 团队) 的设计原则不在此重复，请直接读 [docs/HARNESS.md](HARNESS.md) §LLM Wiki 概念映射，或仓库 `wiki/HOME.md` 的引用。本文档只写"在我们这个产品里怎么落"。

## 2026-05-18 Current State

- Reviewed artifacts: 508 docs / 2715 edges (`52 pages / 99 entities / 357 claims`); backend deploy imports them into serving DB.
- Ingest authoring CLI: `backend/scripts/ingest_course.py`.
- Review promotion: `promote_artifact_review_status`.
- Admin lint: contradiction + invalid review status included.
- Admin coverage: `/api/v1/admin/knowledge/coverage_report`.
- Crystallize: draft-only service exists and is called by weekly `system-kb-lifecycle` Celery task.
- Mobile evidence consumption: ordinary chat cards and genetic report cards render `evidence_refs` through a shared `ClaimSheet`/`EntityCard` detail surface with claim feedback and entity deep-link pages.
- Search serving: `/knowledge/search` now fuses local BM25 lexical ranking, PostgreSQL `tsvector` FTS, semantic alias retrieval, and one-hop graph expansion via deterministic reciprocal-rank fusion; admin reindex writes production `TSVECTOR` via `to_tsvector('simple', ...)`.
- Privacy isolation: source scanner excludes private-looking paths and `find_private_source_violations(...)` reports private material without reading content.
- External evidence: selected MTHFR/APOE/statin/diabetes claims include reviewed PubMed/guideline references in `metadata.external_sources`.
- Phase 2 corpus expansion: deterministic compiler scanned 46 health-relevant source directories and promoted 314 generated claims / 83 entities / 46 pages / 2566 relations to reviewed status across reviewed passes, exceeding the 300 claim / 80 entity target.
- Graph association: Dedao claim context now also emits entity-to-entity `contextualizes` edges, so an Agent can traverse from a condition/biomarker to related biomarkers, interventions, and safety boundaries without relying only on keyword search.
- Admin operations: `/api/v1/admin/knowledge/operations_dashboard` summarizes coverage, external evidence, lint, latest lifecycle report, and action items.
- Ingest reviewer queue: dry-run PR-style diffs prepend new draft claim count, missing external-evidence count, candidate duplicate count, and claim IDs needing reviewer attention.
- Planner enforcement: Orchestrator applies a deterministic evidence policy before synthesis; unsupported actionable findings are blocked when the same evidence domain already has KB-supported findings, while safety alerts and data gaps are preserved.
- Weekly Advisor enforcement: fallback weekly action cards now attach system KB evidence and reuse the same planner evidence policy before persistence.

---

## 1. 为什么要做（北极星 + 现状缺口）

### 1.1 北极星

让全平台用户在做"基因 + 个人健康"驱动的 LLM 对话时，每条建议（饮食、补剂、运动、用药提醒）都可以追溯到**系统级知识库**里的可信证据条目，而不是让 LLM 自由发挥。这是 [[project_action_card_compliance_2026_05_12]] 中 evidence_level 4 级体系真正能跑起来的前提。

WSCLA 北极星里的 "Safe" 这个字，依赖于知识库——没有结构化证据，安全闭环就退化成 LLM 自我背书。

### 1.2 现状（2026-05-16）

| 层 | 现状 | 问题 |
|---|---|---|
| 原始素材 | `~/work/personal/down-dedao/raw/` 已有 160+ 门课程、10000+ 课时（健康类约 30 门） | 全是叙事文本，无结构化抽取 |
| Wiki | `wiki/AK-INDEX.md` `wiki/domains/` `wiki/concepts/` `wiki/articles/` 已有骨架，303 篇 md | Serving plane 已用 reviewed JSONL artifacts 承接 entity/claim；scanner 会排除 private/personal/user-* 路径 |
| 后端检索 | `KnowledgeLibrarian` specialist + ChromaDB 一个 collection | 纯 keyword/embedding 模糊匹配，对 Twin 里的 `MTHFR_C677T = "TT"` 这种结构化事实没法精确反查 |
| 消费端 | Specialist 输出建议 + KnowledgeLibrarian 输出引用，**并排两份 finding**，由 LLM 合成时拼接 | 引用经常和具体建议对不上号；Mobile UI 没有"看证据"入口 |
| 隔离 | 私人 episode 不进入 system KB | `find_private_source_violations(...)` 可报告路径风险；用户对话只进 user memory/crystallize draft |

### 1.3 这次设计要解决的 4 件事

1. **隔离**：个人 working memory 与系统级 semantic memory 物理分离
2. **结构化**：从 page-first 改为 entity-first + claim-first，让 Twin 能直接反查
3. **生命周期**：confidence / supersession / decay 落到 claim frontmatter
4. **Agent Native 闭环**：Specialist 给的每条建议必须能 attach 到 claim_id；UI 上能展开看证据

---

## 2. 核心架构决策

### D1 — 个人 ≠ 系统，物理分离

| 类型 | 路径 | 是否进 git system KB | 是否参与 system 检索 |
|---|---|---|---|
| 系统级（适用所有用户） | `down-dedao/wiki/entities/` `claims/` `domains/` `concepts/` `courses/` `articles/` | 是 | 是 |
| 用户私人 episode | `~/.health-llm/private-vault/user-{id}/` 或后端 `user_episode_memory` 表 | 否 | 仅当前用户 |
| 多用户聚合洞见 | crystallize.py 自动产 system claim PR | 是（人工 review 后） | 是 |

**当前动作**：系统 KB 扫描器已经排除 `personal/private/私人/个人/用户/user-*` 路径；本地如再出现 `wiki/articles/personal-*.md`，先用 `find_private_source_violations(...)` 报告，再迁到 `~/.health-llm/private-vault/user-3/`。

### D2 — Entity-first，不是 page-first

| 实体类型 | 示例 | 来源 |
|---|---|---|
| `gene` | MTHFR / APOE / FTO / ACTN3 / COMT / ALDH2 / CYP2D6 / VDR / HFE | 仇子龙基因 20 讲；尹烨健康参考 |
| `snp` | rs1801133 / rs429358 / rs7412 / rs1815739 / rs4680 | 同上 + 用户 23andMe 报告字段 |
| `nutrient` | folate / vitamin-D / omega-3 / magnesium / B12 / 钾 | 仝卿营养 20 讲；忙碌者营养健康公开课 |
| `supplement` | 5-MTHF / MitoQ / 虾青素 / 鱼油 EPA-DHA / 镁甘氨酸 | 同上 + Examine.com（Phase 3） |
| `biomarker` | Hcy / LDL-C / HbA1c / ApoB / eGFR / 肝酶三联 / TIR | 冯雪医学课系列；薄世宁医学通识 |
| `condition` | hyperhomocysteinemia / MAFLD / OSAHS / 鼻炎 / 高血脂 | 同上 |
| `drug` | warfarin / statin / metformin / SSRI / GLP-1 | 王家伟日常用药课 |

每个 entity = 一个 markdown 文件，frontmatter 含 `entity_id` `aliases` `linked_claims`。Twin 里的字段直接映射到 entity_id，不靠 LLM 猜词。

### D3 — Claim 是一等公民，不是 entity 内嵌段落

每条原子事实独立一个 `wiki/claims/c_*.md` 文件，frontmatter 规范如下：

```yaml
---
claim_id: c_mthfr_677_folate
subject: snp:rs1801133
predicate: reduces_efficiency_of
object: nutrient:folate-conversion
confidence: 0.92                    # 0-1
evidence_level: B                   # A=RCT meta, B=cohort, C=科普源, D=anecdote
sources:
  - r_qiuzilong_jiyin_07
  - r_pubmed_19033271
last_confirmed: 2026-05-14
created: 2026-05-09
supersedes: []
superseded_by: null
decay_rate: slow                    # slow=架构级 | normal=临床 | fast=新闻/趋势
applies_when:                       # 结构化触发条件，Twin 反查用
  - twin.genetics.MTHFR_C677T in [CT, TT]
recommends_lookup:
  - entities/supplement/5-MTHF.md
  - entities/biomarker/Hcy.md
contraindicates: []
tags: [methylation, b-vitamins]
---

C677T 纯合会将 MTHFR 酶活性降至 ~30%，导致叶酸 → 5-MTHF 转化受限，血浆同型半胱氨酸 (Hcy) 升高...
```

`applies_when` 是相对 V2 增加的字段，让 Twin 能**结构化命中**而不是模糊匹配。这是把 "Protocol-first LLM-second" ([[project_agent_native_principles]]) 落到 KB 层。

### D4 — Agent 写 wiki，但要 review；用户对话不直接写

- LLM ingest 一篇得到课 → 生成 git PR diff（claims/entities 新增/修改/废弃）→ 人工 review merge
- 用户对话里的"洞见"只进 `user_episode_memory`，**不**进 system wiki
- 例外：`crystallize.py` 从聚合的 `agent_audit_log` 找出"被触发 100+ 次且 outcome 一致"的隐性规则 → 自动起草 claim PR（仍需人工 merge）

### D5 — Mobile First：证据 chip 是 RN 的一等组件

- Specialist 返回的每条建议 schema 加 `evidence_refs: [claim_id]`
- `mobile/components/assistant/SupplementCard.tsx` / `FuelCard.tsx` 默认折叠"📚 N 条证据 [evidence_level]"chip
- 点开侧滑展示 entity 卡 + claim 列表 + 来源链接
- Web 版滞后或不做（按 [[decision_react_native_only]]）

---

## 3. 目录结构最终态

```
~/work/personal/down-dedao/
├── raw/                              # 不动，immutable
│   ├── 仇子龙·基因科学20讲/
│   ├── 仝卿·营养科学20讲/
│   ├── 给忙碌者的营养健康公开课/
│   ├── 王家伟·日常用药健康课/
│   ├── 冯雪·高血脂/血压/血糖/尿酸医学课/
│   ├── 给忙碌者的{糖尿病,大脑,骨科,眼科,心脏,泌尿}医学课/
│   ├── 王立铭·{生命,脑,进化论}50讲/
│   ├── 薄世宁·医学通识50讲/
│   ├── 尹烨·健康参考/
│   └── external/                     # 新建，Phase 3 用
│       ├── pubmed/
│       └── examine/
│
├── wiki/
│   ├── WIKI_SCHEMA.md                # 新建：agent 行为宪法
│   ├── HOME.md / AK-INDEX.md / ak-log.md   # 已有，继续维护
│   ├── domains/                      # 已有，8 篇主题索引
│   ├── concepts/                     # 已有，59 篇概念
│   ├── courses/                      # 已有，按课程归档
│   ├── articles/                     # 移除 personal-* 后的长文
│   ├── entities/                     # 新建
│   │   ├── gene/        MTHFR.md APOE.md ...
│   │   ├── snp/         rs1801133.md ...
│   │   ├── nutrient/    folate.md ...
│   │   ├── supplement/  5-MTHF.md ...
│   │   ├── biomarker/   Hcy.md LDL-C.md ...
│   │   ├── condition/   hyperhomocysteinemia.md ...
│   │   └── drug/        warfarin.md ...
│   └── claims/                       # 新建，平铺
│       └── c_*.md
│
└── pipeline/
    ├── ingest_course.py              # 新：LLM-driven 课程抽 claim
    ├── lint.py                       # 新：orphan / stale / contradict 检查
    ├── decay.py                      # 新：confidence 时间衰减
    └── crystallize.py                # 新：audit_log → claim PR

~/.health-llm/private-vault/          # 本机，不入 git
└── user-3/
    ├── personal-fitness-progression.md
    ├── personal-rhinitis-management.md
    └── ...                           # 从 wiki/articles/ 迁出的 10 篇
```

---

## 4. WIKI_SCHEMA.md 大纲

这份文件是 Agent 行为宪法，必须在 Phase 0 第一周完稿。结构：

1. 实体七型定义 + frontmatter 必填字段
2. claim_id 命名规范（`c_<subject>_<predicate>_<object>` 蛇形）
3. predicate 词表（封闭枚举 ~30 个：reduces / increases / requires / contraindicates / synergizes_with / supersedes / ...）
4. evidence_level 评级标准（A/B/C/D 各举 3 个示例）
5. confidence 初值表 × decay 公式
6. ingest 流程 10 步（见 §5）
7. lint 触发条件 + 自动修复白名单
8. supersession 决策树（源权威 > 时间 > 样本数）
9. 私密 → 系统的 crystallization 阈值
10. PR review checklist（5 条以内）

---

## 5. Ingest 流程（V2 §automation 落地）

输入：`raw/仇子龙·基因科学20讲/07-MTHFR与一碳代谢.md`

| 步 | 动作 | 输出 |
|---|---|---|
| 1 Discuss | 与 user/agent 对谈关键点（可 dry-run 跳过） | 对话日志 |
| 2 Entity extract | 抽实体 + 别名 + 类型 | gene:MTHFR / snp:rs1801133 / nutrient:folate / ... |
| 3 Claim mining | 抽原子事实 (S-P-O 三元组) | `c_*.md` × N |
| 4 Conflict check | 对每条新 claim 在 BM25+vector 检索既有 claim | 冲突列表 |
| 5 Supersession | LLM 按"源权威 > 时间 > 样本数"判定旧 claim 是否被取代 | `supersedes` 链 |
| 6 Confidence | 初分 (A=0.9 / B=0.75 / C=0.6 / D=0.4) | claim frontmatter |
| 7 Update entity pages | 把 claim 插到对应 entity 页的"相关事实"区（连 claim_id） | entity md diff |
| 8 Update index | 重写 AK-INDEX.md 对应条目 | index diff |
| 9 Append log | `## [2026-05-16] ingest \| 仇子龙 #07` + diff stat | ak-log.md |
| 10 Emit PR | 生成 git diff 等 review | PR |

**反馈环目标**：本地 dry-run 一篇 < 60s，全量 6 门优先课重跑 < 10min，异步走 Celery（背景任务）。

---

## 6. 后端集成

### 6.1 新建 3 张表（PostgreSQL，写迁移 SQL）

```sql
-- 文档元数据（正文在 git wiki + ChromaDB）
CREATE TABLE kb_documents (
  doc_id          TEXT PRIMARY KEY,         -- entity:gene:MTHFR / claim:c_xxx
  doc_type        TEXT NOT NULL,            -- entity / claim / article
  entity_type     TEXT,                     -- gene/snp/nutrient/...
  entity_id       TEXT,
  title           TEXT,
  content_hash    TEXT,
  confidence      REAL,
  evidence_level  CHAR(1),
  applies_when    JSONB,
  sources         TEXT[],
  tsv             TSVECTOR,
  last_confirmed  TIMESTAMPTZ,
  decay_rate      TEXT,
  is_archived     BOOLEAN DEFAULT FALSE,
  created_at      TIMESTAMPTZ DEFAULT NOW(),
  updated_at      TIMESTAMPTZ
);
CREATE INDEX kb_doc_entity ON kb_documents(entity_type, entity_id);
CREATE INDEX kb_doc_tsv    ON kb_documents USING GIN(tsv);
CREATE INDEX kb_doc_apply  ON kb_documents USING GIN(applies_when);

-- 知识图谱边（V2 §typed relationships）
CREATE TABLE kb_edges (
  edge_id         BIGSERIAL PRIMARY KEY,
  src_doc_id      TEXT REFERENCES kb_documents(doc_id),
  dst_doc_id      TEXT REFERENCES kb_documents(doc_id),
  relation        TEXT NOT NULL,            -- uses / depends_on / contradicts / supersedes / recommends / synergizes_with
  confidence      REAL,
  source_claim_id TEXT
);
CREATE INDEX kb_edge_src ON kb_edges(src_doc_id, relation);

-- 审计（V2 §privacy and governance）
CREATE TABLE kb_audit (
  id        BIGSERIAL PRIMARY KEY,
  doc_id    TEXT,
  op        TEXT,                           -- ingest/edit/supersede/decay/query/feedback_disagree
  actor     TEXT,                           -- llm-claude-opus-4-7 / user:3
  diff      JSONB,
  ts        TIMESTAMPTZ DEFAULT NOW()
);
```

ChromaDB 拆 3 个 collection：`kb_entities` / `kb_claims` / `kb_articles`，分别 embed 对应 doc 的摘要文本。

### 6.2 API 端点（最小集，挂在 `/api/v1/knowledge`）

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/knowledge/entity/{type}/{id}` | 返回 entity page + linked claims + 反向引用 |
| GET | `/knowledge/claim/{claim_id}` | 单条 claim 详情（含 source 链接） |
| GET | `/knowledge/search?q=...&user_id=...` | hybrid 检索：BM25 + vector + graph，可按用户 Twin filter |
| POST | `/knowledge/lookup_for_twin` | Twin builder 调用：把 Twin 13 分区 → entity_id 清单 |
| POST | `/admin/knowledge/reindex` | 触发全量 reindex |
| GET | `/admin/knowledge/lint_report` | 最新 lint 报告（orphan / stale / contradict 计数） |

`/lookup_for_twin` 是 **Agent Native 核心**：跳过 LLM 自由提问，直接结构化匹配。

### 6.3 Twin Prompt Blob 注入

`twin_to_prompt_blob` 末尾追加：

```
## 系统知识库相关条目 (system KB v2026-05-16)
- gene:MTHFR (C677T-TT) [conf=0.92, B] → 叶酸转化受限，建议 5-MTHF 替代
  - 证据: c_mthfr_677_folate (得到-仇子龙基因20讲第7讲)
- biomarker:Hcy = 18 µmol/L (高) [conf=0.85, B] → 与 MTHFR-TT + B12 缺乏共现
  - 证据: c_hcy_b12_mthfr_synergy
- supplement:5-MTHF [conf=0.78, B] → 推荐剂量 400-800µg/d
  - 注意: c_5mthf_overdose_risk (>1mg/d 可能掩盖 B12 缺乏)
```

长度上限 1500 token，超过时按 `applies_when` 命中度排序截断。

### 6.4 改造现有 Specialist

- **SupplementAdvisor** / **FuelStrategist** / **MovementCoach**：每条 recommendation schema 加 `evidence_refs: [claim_id]`
- 没有 evidence_refs 的建议：confidence 降一级，UI 显示"💡 模型推断"而非"📚 证据"，audit_log 标 `unsupported=true`，作为 KB 覆盖率指标
- **KnowledgeLibrarian** 从纯 keyword 升级为 entity-first 图谱行走：
  1. 从 intent + Twin 抽 entity 清单
  2. 图上 BFS 2 跳收集邻居
  3. 按 confidence × applies_when 命中度排序
  4. 取 top-N 作为 finding

---

## 7. Mobile UI（Mobile First）

新建 `mobile/components/assistant/EvidenceChip.tsx` + `EntityCard.tsx` + `ClaimSheet.tsx`，复用到 SupplementCard / FuelCard / MovementCard。

```
┌─────────────────────────────────┐
│ 5-MTHF (活性叶酸) 400µg/d         │
│ ───                              │
│ 因为你是 MTHFR C677T-TT 纯合     │
│ 叶酸转化效率低 30%                │
│                                  │
│ 📚 3 条证据  [B级]  [展开]         │
└─────────────────────────────────┘
       ↓ tap
┌─────────────────────────────────┐
│ ← 5-MTHF                         │
│ 来源: 系统知识库                  │
│                                  │
│ ## 适用条件                       │
│ • MTHFR C677T 杂合/纯合           │
│ • Hcy ≥ 15 µmol/L                │
│                                  │
│ ## 证据                           │
│ A 级 (0): -                      │
│ B 级 (2): 仇子龙基因20讲#07,      │
│           PubMed 19033271        │
│ C 级 (1): 仝卿营养20讲#12         │
│                                  │
│ ## 注意                           │
│ ⚠ >1mg/d 可能掩盖 B12 缺乏       │
│                                  │
│ [👎 这条建议不对]                  │
└─────────────────────────────────┘
```

底部"这条建议不对"按钮写 `kb_audit.op=feedback_disagree`，作为 lint 阶段的冲突信号。

---

## 8. 实施分期（4 阶段，每阶段独立可上线）

### Phase 0 — 隔离 + Schema（**1 周**，立即开始）

- [ ] 写 `down-dedao/wiki/WIKI_SCHEMA.md`（agent 宪法，§4 大纲）
- [x] 增加 private/personal/user-* 扫描隔离和报告；本地当前未发现可迁出的 `personal-*` 文件
- [ ] 建 `wiki/entities/{gene,snp,nutrient,supplement,biomarker,condition,drug}/` 骨架，每型 1-2 个示范页
- [ ] 手写 5 条样板 claim：MTHFR / APOE / FTO / ACTN3 / ALDH2
- [ ] 后端 migration：建 `kb_documents` / `kb_edges` / `kb_audit` 三表
- [ ] 一次性同步脚本：把 5 条样板写入 `kb_documents`

**验收**：mobile chat 问"我 MTHFR-TT 该注意什么"，后端返回 entity page + 1 条 claim，UI 显示证据卡。

### Phase 1 — Ingest Pipeline（**2-3 周**）

- [ ] 写 `pipeline/ingest_course.py`，dry-run 输出 PR diff，不直接 commit
- [ ] 优先 ingest 6 门课（不全跑，避免噪音爆炸）：
  - 仇子龙·基因科学 20 讲
  - 仝卿·营养科学 20 讲
  - 给忙碌者的营养健康公开课
  - 王家伟·日常用药健康课
  - 冯雪·高血脂/血压/血糖/尿酸医学课（4 合 1）
  - 给忙碌者的糖尿病医学课
- [ ] 每门课产 PR，每周 review 1 次合并
- [ ] 写 `pipeline/lint.py`，跑全量找 orphan / contradict

**验收**：claim 表 ≥ 300 条，entity ≥ 80 个，覆盖 SupplementAdvisor 现有规则的 90%。

### Phase 2 — Agent 接入 + Mobile UI（**2 周**）

- [ ] `KnowledgeLibrarian` 改 entity-first 图谱行走
- [ ] `twin_to_prompt_blob` 加系统知识库段落
- [ ] `SupplementAdvisor` / `FuelStrategist` 每条建议绑 claim_id
- [ ] Mobile `EvidenceChip` + `EntityCard` + `ClaimSheet` 三组件落地
- [ ] API：`/knowledge/entity/...` + `/search` + `/lookup_for_twin` 上线

**验收**：SupplementAdvisor 输出建议 ≥ 80% 带 evidence_refs；Mobile 上能点开看到得到课/PubMed 来源；audit_log 里 `unsupported=true` 比例 < 20%。

### Phase 3 — Lifecycle + Self-healing（**持续**）

- [ ] Celery 周任务：confidence decay + 生成 lint report
- [ ] 写 `pipeline/crystallize.py`：从 `agent_audit_log` 找 100+ 次触发、outcome 一致的隐性规则 → 起草 claim PR
- [ ] 每条 claim 自评 + 人审；低分标 `needs_review`
- [ ] 接入 PubMed / Examine.com 第二源，提升 evidence_level 平均档位

**验收**：3 个月内 claim 平均 evidence_level 从 C 升到 B；orphan rate < 5%；用户"这条建议不对"反馈率 < 5%。

---

## 9. 与现有系统的关系

| 现有模块 | 关系 | 动作 |
|---|---|---|
| `KnowledgeLibrarian` specialist | 不删 | 改造为 entity-first 入口；旧 ChromaDB collection 保留作 fallback |
| `backend/data/knowledge_chromadb/` | 路径保留 | collection 重建为 `kb_entities` / `kb_claims` / `kb_articles` |
| [[project_action_card_compliance_2026_05_12]] 的 evidence_level | 直接复用 | A/B/C/D 4 级写入 claim frontmatter |
| [[project_agent_native_principles]] "Protocol-first LLM-second" | 在此体现 | claim.applies_when 是 protocol，Planner LLM 不能绕过 |
| [[feedback_data_before_analysis]] P-a/P-b 切分 | Phase 0 = P-a，Phase 2 = P-b | 数据先采全（claim 库），再做分析消费（specialist 改造） |
| `agent_audit_log` 表 | 复用 | crystallize.py 从这里挖隐性规则 |
| OpenClaw skills | 解耦 | skill 不直接读 KB，仍走 API |

---

## 10. Trade-off 与风险

| 项 | 决策 | 风险 | 对策 |
|---|---|---|---|
| 预抽 claim vs query 时抽 | **预抽**（offline） | LLM 抽错 → 永久污染 | PR review + supersession + audit |
| 得到 wiki 为主源 | **是**（Phase 0-2） | 科普级 evidence 上限 C | Phase 3 加 PubMed 升 B |
| 用户对话进 system KB | **不进** | 丢失 N=1 真实案例价值 | crystallize 聚合 100+ 用户后才入 |
| Mobile 显示证据 chip | **是** | 增加 UI 复杂度 | 默认折叠，点开才看 |
| 自动 supersede | **是**（保留 supersedes 链） | 新源不一定对 | UI 上保留历史版本可回退 |
| 系统 KB 公开所有用户 | **是** | 隐私泄漏（私事进了 ingest） | D1 物理隔离 + ingest 阶段 PII scrub |
| 一次跑全量 80 门课 | **不**，先跑 6 门 | 噪音爆炸 + review 队列堵塞 | 优先级队列 + 每周 review 节奏 |
| Web 端是否同步做证据 chip | **不做** | feature parity 不齐 | 按 [[decision_react_native_only]]，Web 滞后或不做 |

---

## 11. 度量

每周看板（写到 `admin/wscla` 现有看板里加一栏）：

| 指标 | 目标 (3 个月) |
|---|---|
| `kb_documents` 总数 | ≥ 800 (entity 100 + claim 700) |
| 平均 evidence_level | B (从 Phase 1 末的 C 升到 B) |
| Specialist 建议 evidence_refs 覆盖率 | ≥ 85% |
| `feedback_disagree` 比例 | < 5% |
| orphan rate | < 5% |
| ingest dry-run 时间 / 门课 | < 60s |
| Twin → KB lookup p95 | < 200ms |

---

## 12. 立即下一步（本周 5 个动作）

1. 写 `wiki/WIKI_SCHEMA.md`（Agent 宪法，1 天）
2. 运行 private source violation 检查；若发现 `wiki/articles/personal-*.md`，迁出到 private vault
3. 建 `wiki/entities/{7 子目录}/` + 每型 1 个示范页（半天）
4. 手写 5 条样板 claim（半天，亲自写以 calibrate Phase 1 的 LLM ingest prompt）
5. 后端 migration：3 表上线 + 一次性同步样板（1 天）

完成后启动 Phase 1。

---

## 13. 2026-05-16 独立复核结论与修订版路线

### 13.1 对 Claude 原计划的判断

Claude 的核心判断是合理的：系统知识库必须从“页面检索”升级为 `entity + claim + applies_when + evidence_refs`，否则 Agent 给出的饮食、补剂、运动和用药建议无法稳定追溯证据，也无法避免不同 specialist 给出互相冲突的建议。

但原计划有 3 个需要调整的点：

1. **不应先追求 LLM 全文抽取**  
   得到课程属于已授权但仍需克制使用的付费内容。线上系统不应保存或展示大段原文。当前 deterministic topic-template 抽取虽然覆盖率低，但版权边界、医学边界和 review 成本更可控。下一步应先把 claim 模板和人工 review 闭环跑顺，再引入受约束 LLM claim mining。

2. **authoring plane 与 serving plane 要分开验收**  
   `down-dedao/wiki` 是离线 authoring/compiler plane；`health-llm-driven/backend/data/system_kb_v2_seed` 和 PostgreSQL 是 serving plane。计划里的“建 wiki/entities/claims 文件树”有价值，但线上产品验收应以 artifacts、DB、API、Agent、Mobile 是否闭环为准。

3. **Phase 2 corpus breadth 已达标，下一步应转向质量和消费强约束**
   当前已有 357 条 claim 和 2715 条边。继续扩课的边际收益开始低于治理和消费质量；短期优先级应是“每条关键建议能看到 evidence_refs、可点开、可反馈不对”，并提高外部二次证据覆盖率。

### 13.2 当前真实进度

| 模块 | 当前状态 | 复核结论 |
|---|---|---|
| System KB tables | 已有 `kb_documents/kb_edges/kb_audit` | 完成 |
| Artifact import | 已有 reviewed JSONL import，部署自动导入 | 完成 |
| Dedao ingest | 已有 dry-run/`--write` deterministic pipeline；本轮扫描 46 个健康相关来源目录 | deterministic pipeline 完成，仍不是完整 LLM claim mining |
| Corpus coverage | 52 pages / 99 entities / 357 claims / 2715 relations | Phase 2 breadth 达标；新增 entity-to-entity contextual graph |
| KnowledgeLibrarian | 已改为有 DB 时优先 system KB V2，旧 Chroma fallback | 本轮补齐 |
| Prompt injection | `format_system_knowledge_for_prompt` 已接入 Orchestrator；`lookup_for_twin` 会沿 `contextualizes` 图谱边补充上下文 claim | 完成最小闭环 |
| Specialist evidence_refs | Orchestrator 可自动附着；Planner synthesis 前会过滤同域无证据 actionable 建议，安全告警和 data_gap 例外；Weekly Advisor fallback action card 也复用同一策略 | 基本完成，后续扩展到直接 push scheduler 通知面 |
| Mobile evidence UI | 已有 system evidence card、EvidenceRefsRow、统一 ClaimSheet/EntityCard、反馈入口、来源可信度解释和 entity 深链页面 | 基本完成，后续优化交互密度 |
| Lifecycle | 有 lint/reindex/decay 脚本，admin lint 已覆盖 contradiction + invalid review status；weekly `system-kb-lifecycle` 会跑 lint/decay/crystallize draft；admin operations dashboard 可看治理状态；PostgreSQL reindex 使用 `to_tsvector` 写入 `TSVECTOR` | 基本完成，后续是可视化页面 |
| Privacy isolation | scanner 排除 private/personal/user-*，并提供 violation report | 完成最小治理闭环 |

### 13.3 修订后的执行顺序

#### P0：治理收口（优先）

- 持续运行 private source violation 检查；如发现 `down-dedao/wiki/articles/personal-*.md`，迁到 private vault，系统 KB 不混入用户私人健康分析。
- 补齐 `down-dedao/wiki/entities/{snp,nutrient,condition,drug}` 骨架，但不要把它作为线上验收阻塞项。
- 给 reviewed artifacts 增加 review 状态统计：`draft/reviewed/needs_review/archived`。

#### P1：消费闭环（优先）

- KnowledgeLibrarian 优先走 system KB V2，旧 Chroma 只做 fallback。
- Specialist 输出如果没有 `evidence_refs`，记录 `unsupported=true`，先进入 audit，不立刻降低线上回答质量。
- Mobile 的 diet/supplement/workout 卡统一展示 `EvidenceRefsRow`，并补“这条证据不对”反馈入口，写 `kb_audit.op=feedback_disagree`。

#### P2：扩展知识库（中期）

- 已完成：从 148 claims 扩到 357 claims、45 entities 扩到 99 entities。
- 已覆盖：高血压、高血脂、高血糖、高尿酸、糖尿病、营养、用药安全、睡眠恢复、运动、微生物组、心脏、骨科、精力管理、正念和部分生命科学课程。
- 暂不追求 160+ 门全量课程，避免噪音和 review 队列失控。

#### P3：V2 生命周期（后置）

- contradiction lint：已进入 admin lint；下一步接入定期运维报告。
- reviewer workflow：CLI 已生成 diff + review queue + review manifest，并支持人工确认后从 draft 升为 reviewed。
- crystallize：已有 draft-only service；下一步接入 Celery 周期任务和 admin review 队列。
- PubMed/Examine 二源只用于提升高风险 claim 的 evidence level，不作为初期覆盖率任务。

### 13.4 新验收口径

短期不再用“课程数量”作为主指标，改用下面 5 个指标：

| 指标 | 下一阶段目标 |
|---|---|
| system KB lookup p95 | < 200ms |
| KnowledgeLibrarian system KB 命中优先率 | 明确 gene/biomarker 查询优先 system KB |
| Specialist finding evidence_refs 覆盖率 | 先达到 60%，再到 85% |
| Mobile evidence 可点击率 | diet/supplement/workout/genetic 四类卡都可点开 |
| KB lint | orphan/invalid/stale 为 0，新增 contradiction 报告 |

---

**版本历史**

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-05-16 | v0.1 | 初稿（draft） |
