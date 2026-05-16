# LLM Wiki V2 System Knowledge Base Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a system-level LLM Wiki V2 knowledge base from `/Users/liqiuhua/work/personal/down-dedao`, then publish governed health knowledge into `health-llm-driven` so every Mobile First Agent Native user can receive evidence-enhanced guidance grounded in genetics and personal health data.

**Architecture:** Keep `/Users/liqiuhua/work/personal/down-dedao` as the offline wiki compiler and source curation workspace. Extend `health-llm-driven` into the serving plane: system corpus, typed health knowledge graph, lifecycle metadata, hybrid retrieval, safety policy, and Mobile Agent citation surfaces.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy, PostgreSQL in production, ChromaDB vector store, BM25/hybrid search, Celery, Expo React Native, Markdown/YAML wiki artifacts.

---

## 1. Product Framing

This is not a generic RAG upload feature. It is the system knowledge layer for a Personal Health Trajectory Agent.

The Agent should answer using three bounded knowledge sources:

1. **System Wiki:** curated health knowledge compiled from legally obtained course notes and source materials under `/Users/liqiuhua/work/personal/down-dedao`.
2. **User Twin:** private user data including genotype, labs, wearable data, diet, movement, sleep, medications, symptoms, and goals.
3. **Safety Rules:** deterministic clinical boundaries, red flags, drug/supplement interactions, and "not diagnosis / not treatment" constraints.

System Wiki must be shared by all users. User Twin must remain private per user. Anonymous aggregate feedback may strengthen system knowledge only after de-identification and review.

## 2. Current State

`/Users/liqiuhua/work/personal/down-dedao` already has the right shape for V2:

- ~14,478 files and ~625 directories.
- Health-relevant course directories:
  - `冯雪·家庭健康管理100讲`
  - `冯雪·科学减肥16讲`
  - `冯雪·高血压医学课`
  - `冯雪·高血糖医学课`
  - `冯雪·高血脂医学课`
  - `冯雪·高尿酸医学课`
  - `仝卿·营养科学20讲`
  - `仇子龙·基因科学20讲`
  - `薄世宁·医学通识50讲`
  - `王家伟·日常用药健康课`
  - `前沿课·人体微生物组9讲`
- Existing V2-like workspace:
  - `wiki/`
  - `wiki/concepts/`
  - `wiki/courses/`
  - `wiki/articles/`
  - `pipeline/compiler.py`
  - `pipeline/sync.py`
  - `pipeline/export_graph.py`
  - `pipeline/lint.py`
  - `artifacts/*.json`

`health-llm-driven` already has:

- `backend/app/services/knowledge/vectorstore.py`
- `backend/app/services/knowledge/rag_pipeline.py`
- `backend/app/api/knowledge.py`
- `backend/app/services/knowledge_evidence.py`
- Diet and supplement advice using first-pass `knowledge_evidence`.
- Agent architecture with Digital Health Twin, specialists, Safety Guardian, and advice ledger.

The gap is that the current pipeline is closer to "original LLM Wiki + some sync" than true V2 production serving.

## 3. Target Architecture

```mermaid
flowchart TD
    A["down-dedao raw course dirs"] --> B["V2 compiler: ingest + normalize"]
    B --> C["Wiki markdown: concepts / courses / articles"]
    C --> D["Artifacts JSONL: claims, pages, chunks, entities, relations"]
    D --> E["Sync API: system knowledge publish"]

    E --> F["PostgreSQL metadata tables"]
    E --> G["Chroma vector chunks"]
    E --> H["BM25 index"]
    E --> I["Typed health KG"]

    J["User Health Twin"] --> K["Agent Retrieval Policy"]
    F --> K
    G --> K
    H --> K
    I --> K
    L["Safety Guardian"] --> K

    K --> M["Specialists: fuel, recovery, movement, chronic, genetics"]
    M --> N["Mobile Agent response"]
    N --> O["Citation + boundary + user action"]
    O --> P["Outcome feedback"]
    P --> Q["De-identified aggregate feedback"]
    Q --> B
```

### Boundary Between Workspaces

`down-dedao` is the authoring/compiler plane:

- Reads raw files.
- Maintains wiki pages.
- Extracts entities and typed relations.
- Produces structured artifacts.
- Runs lint and quality checks.

`health-llm-driven` is the serving plane:

- Stores system knowledge metadata in PostgreSQL.
- Stores retrievable chunks in Chroma/BM25.
- Stores typed health KG in relational tables.
- Injects evidence into Agent prompts.
- Enforces privacy, claim boundaries, advice ledger, and safety rules.

## 4. V2 Knowledge Model

### 4.1 Scopes

| Scope | Meaning | Examples | Served To |
|---|---|---|---|
| `system_shared` | Curated knowledge usable by all users | general metabolic health, hypertension basics, nutrition principles | all users |
| `system_condition` | Shared but condition-specific | hypertension, hyperlipidemia, gout, OSA | users with matching risk/context |
| `system_gene` | Shared genotype interpretation rules | APOE, MTHFR, ALDH2, CYP2C19 boundaries | users with matching variants |
| `system_safety` | Deterministic safety and boundary knowledge | red flags, contraindications, drug/supplement cautions | all users |
| `user_private` | Private user facts | labs, genotype, wearables, medication | only the owning user |
| `aggregate_feedback` | De-identified outcome evidence | completion rate, response patterns | system review only |

### 4.2 Lifecycle Tiers

| Tier | Description | Storage | Promotion Rule |
|---|---|---|---|
| Working | Newly observed source chunks, import logs, raw LLM extraction | compiler artifacts + import job | successful parse + minimum quality |
| Episodic | Lesson summaries and session digests | wiki pages + `knowledge_pages` | reviewed or source-backed |
| Semantic | Stable claims and concept pages | `knowledge_claims`, KG entities/relations | multi-source support or high authority |
| Procedural | Action patterns and workflows | `knowledge_protocols` | repeated evidence + safety review |

### 4.3 Claim Contract

Every retrievable claim must carry:

```json
{
  "claim_id": "akbp_claim_...",
  "scope": "system_shared",
  "domain": "metabolic_health",
  "claim_text": "Protein intake during weight loss should be sufficient to preserve lean mass.",
  "evidence_level": "expert_opinion|guideline|rct|meta_analysis|course_synthesis",
  "confidence_score": 0.72,
  "source_count": 2,
  "last_confirmed_at": "2026-05-16T00:00:00Z",
  "decay_rate": 0.01,
  "superseded_by": null,
  "contradicts": [],
  "claim_boundary": "Health management guidance only; not diagnosis, prescription, or treatment."
}
```

Health advice may cite claims. It must not cite raw paid course text as if it were a clinical guideline.

## 5. Governance and Copyright Policy

This system can use course knowledge internally only if the content is legally obtained and usage is within the allowed private/internal scope.

Rules:

- Never expose full course text to end users.
- Store source metadata and short excerpts only for citations.
- Use transformed claims, summaries, and action patterns rather than raw course reproduction.
- Mark every artifact with `license_scope`.
- System serving may show:
  - course title
  - author
  - lesson title
  - one short excerpt
  - synthesized claim
  - boundary statement
- System serving must not show:
  - whole lessons
  - large contiguous excerpts
  - bulk exports of paid content
  - "downloadable course summaries" that substitute for the course

## 6. Data Model in `health-llm-driven`

### Task 1: Add System Knowledge Metadata Tables

**Files:**
- Create: `backend/app/models/system_knowledge.py`
- Create: `backend/migrations/20260516_200000_create_system_knowledge_tables.sql`
- Modify: `backend/main.py`
- Test: `backend/tests/test_system_knowledge_models.py`

**Tables:**

```sql
CREATE TABLE IF NOT EXISTS system_knowledge_sources (
    id SERIAL PRIMARY KEY,
    source_key VARCHAR(200) UNIQUE NOT NULL,
    title VARCHAR(500) NOT NULL,
    author VARCHAR(200),
    platform VARCHAR(100),
    source_type VARCHAR(80) NOT NULL,
    license_scope VARCHAR(80) NOT NULL DEFAULT 'internal',
    raw_root_path TEXT,
    content_hash VARCHAR(128),
    version VARCHAR(80),
    imported_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS system_knowledge_claims (
    id SERIAL PRIMARY KEY,
    claim_key VARCHAR(240) UNIQUE NOT NULL,
    source_key VARCHAR(200) REFERENCES system_knowledge_sources(source_key),
    scope VARCHAR(80) NOT NULL,
    domain VARCHAR(120) NOT NULL,
    category VARCHAR(120),
    claim_text TEXT NOT NULL,
    evidence_level VARCHAR(80) NOT NULL,
    confidence_score DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    source_count INTEGER NOT NULL DEFAULT 1,
    last_confirmed_at TIMESTAMP WITH TIME ZONE,
    decay_rate DOUBLE PRECISION NOT NULL DEFAULT 0.02,
    superseded_by VARCHAR(240),
    contradicts JSONB DEFAULT '[]'::jsonb,
    claim_boundary TEXT NOT NULL,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS idx_system_claims_domain ON system_knowledge_claims(domain);
CREATE INDEX IF NOT EXISTS idx_system_claims_scope ON system_knowledge_claims(scope);
CREATE INDEX IF NOT EXISTS idx_system_claims_active ON system_knowledge_claims(is_active);
```

### Task 2: Add Typed Health KG Tables

**Files:**
- Modify: `backend/app/models/system_knowledge.py`
- Modify: `backend/migrations/20260516_200000_create_system_knowledge_tables.sql`
- Test: `backend/tests/test_system_knowledge_kg.py`

**Entity types:**

- `condition`
- `lab_marker`
- `gene_variant`
- `medication`
- `supplement`
- `nutrient`
- `food_pattern`
- `exercise_pattern`
- `sleep_pattern`
- `risk_factor`
- `intervention`
- `safety_boundary`

**Relation predicates:**

- `improves`
- `worsens`
- `associated_with`
- `contraindicates`
- `interacts_with`
- `requires_monitoring`
- `supports`
- `supersedes`
- `contradicts`
- `applies_to`
- `depends_on`

### Task 3: Add Import Job and Audit Tables

**Files:**
- Modify: `backend/app/models/system_knowledge.py`
- Modify: migration file above
- Test: `backend/tests/test_system_knowledge_import_jobs.py`

Fields:

- `job_id`
- `source_root`
- `artifact_version`
- `total_files`
- `total_claims`
- `total_chunks`
- `total_entities`
- `total_relations`
- `status`
- `errors`
- `started_at`
- `finished_at`

Audit events:

- `import_started`
- `source_upserted`
- `claim_upserted`
- `chunk_uploaded`
- `relation_upserted`
- `supersession_created`
- `claim_deactivated`
- `retrieval_used`

## 7. Artifact Format from `down-dedao`

The compiler should output JSONL, not only one JSON file per article.

### Required Artifacts

```
artifacts/v2/
├── manifest.json
├── pages.jsonl
├── chunks.jsonl
├── claims.jsonl
├── entities.jsonl
├── relations.jsonl
├── supersessions.jsonl
├── quality_report.json
└── rejected.jsonl
```

### `manifest.json`

```json
{
  "protocol": "akbp",
  "version": "2.0",
  "compiled_at": "2026-05-16T00:00:00Z",
  "source_root": "/Users/liqiuhua/work/personal/down-dedao",
  "wiki_commit": "git-sha",
  "content_hash": "sha256",
  "counts": {
    "pages": 120,
    "chunks": 1800,
    "claims": 900,
    "entities": 320,
    "relations": 740
  }
}
```

### `claims.jsonl`

Each line:

```json
{
  "claim_key": "dedao:fengxue_weight_loss:protein_preserves_lean_mass",
  "page_id": "courses/fengxue_weight_loss",
  "chunk_id": "chunk_...",
  "source_key": "dedao:fengxue_scientific_weight_loss",
  "scope": "system_shared",
  "domain": "metabolic_health",
  "category": "nutrition",
  "claim_text": "Weight-loss plans should preserve protein intake to reduce lean-mass loss risk.",
  "evidence_level": "course_synthesis",
  "confidence_score": 0.65,
  "source_count": 1,
  "conditions": ["weight_loss", "metabolic_risk"],
  "genes": [],
  "labs": ["weight", "waist", "albumin", "eGFR"],
  "safety_tags": ["kidney_disease_check"],
  "claim_boundary": "General health management; not individualized medical nutrition therapy.",
  "short_excerpt": "减重阶段应关注蛋白质和肌肉量...",
  "citation": {
    "title": "冯雪·科学减肥16讲",
    "author": "冯雪",
    "platform": "得到",
    "lesson": "蛋白质与减重"
  }
}
```

## 8. Compiler Design in `down-dedao`

### Task 4: Build V2 Course Scanner

**Workspace:** `/Users/liqiuhua/work/personal/down-dedao`

**Files:**
- Create: `pipeline/v2/scanner.py`
- Create: `pipeline/v2/manifest.py`
- Test: `tests/test_v2_scanner.py`

Inputs:

- top-level course directories
- `PDF/`
- `MD/`
- `MP3/`
- existing `wiki/`
- optional `course.yaml`

Skip:

- `.git`
- `.obsidian`
- `.compile-cache`
- `pipeline/`
- `artifacts/`
- `output/`
- `agents/`
- `__pycache__`
- `.ok`
- images unless referenced

Output:

- normalized file inventory with hash, course metadata, lesson order, and parse status.

### Task 5: Build Health Domain Classifier

**Files:**
- Create: `pipeline/v2/health_classifier.py`
- Test: `tests/test_v2_health_classifier.py`

Prioritized health domains:

1. `metabolic_health`
2. `cardiovascular`
3. `nutrition`
4. `genetics`
5. `medication_safety`
6. `sleep_recovery`
7. `movement`
8. `mental_health`
9. `respiratory_allergy`
10. `microbiome`
11. `longevity`
12. `general_wellness`

Non-health courses should not enter the serving corpus by default.

### Task 6: Build Claim Extractor

**Files:**
- Create: `pipeline/v2/claim_extractor.py`
- Test: `tests/test_v2_claim_extractor.py`

Use deterministic extraction first:

- headings
- bullet claims
- tables
- "适用/禁忌/风险/建议/复查/医生" sections

Use LLM extraction only after deterministic pass, with a strict schema.

Claim extraction prompt must require:

- no diagnosis
- no prescription
- no unsupported certainty
- evidence level
- boundary
- source citation
- safety tags

### Task 7: Build Entity and Relation Extractor

**Files:**
- Create: `pipeline/v2/kg_extractor.py`
- Test: `tests/test_v2_kg_extractor.py`

Examples:

- `APOE` `associated_with` `LDL-C`
- `ALDH2 deficiency` `requires_monitoring` `alcohol exposure`
- `high sodium diet` `worsens` `blood pressure`
- `protein intake` `supports` `lean mass preservation`
- `kidney disease` `contraindicates` `unsupervised high protein`
- `grapefruit` `interacts_with` `some statins`

### Task 8: Build V2 Compiler

**Files:**
- Create: `pipeline/v2/compiler.py`
- Modify: `pipeline/run.sh`
- Test: `tests/test_v2_compiler.py`

Command:

```bash
cd /Users/liqiuhua/work/personal/down-dedao
python3 -m pipeline.v2.compiler \
  --root /Users/liqiuhua/work/personal/down-dedao \
  --health-only \
  --out artifacts/v2
```

Expected:

- generates all V2 artifacts
- skips unchanged files by content hash
- writes rejected items with reasons
- produces quality report

## 9. Sync Design

### Task 9: Add System Knowledge Publish API

**Files:**
- Create: `backend/app/api/system_knowledge.py`
- Modify: `backend/app/api/main.py`
- Test: `backend/tests/test_system_knowledge_api.py`

Endpoints:

```http
POST /api/v1/system-knowledge/imports
POST /api/v1/system-knowledge/imports/{job_id}/sources
POST /api/v1/system-knowledge/imports/{job_id}/claims
POST /api/v1/system-knowledge/imports/{job_id}/chunks
POST /api/v1/system-knowledge/imports/{job_id}/entities
POST /api/v1/system-knowledge/imports/{job_id}/relations
POST /api/v1/system-knowledge/imports/{job_id}/finalize
GET  /api/v1/system-knowledge/imports/{job_id}
GET  /api/v1/system-knowledge/stats
```

Security:

- admin only
- request size limits
- audit every batch
- idempotent by `claim_key`, `chunk_id`, `entity_key`, `relation_key`
- no raw full-course export endpoint

### Task 10: Add V2 Sync Client in `down-dedao`

**Files:**
- Create: `/Users/liqiuhua/work/personal/down-dedao/pipeline/v2/sync.py`
- Test: `/Users/liqiuhua/work/personal/down-dedao/tests/test_v2_sync.py`

Command:

```bash
cd /Users/liqiuhua/work/personal/down-dedao
HEALTH_API_URL=https://health-api.executor.life \
HEALTH_API_TOKEN=... \
python3 -m pipeline.v2.sync --artifacts artifacts/v2
```

Behavior:

- create import job
- batch upload sources
- batch upload claims
- batch upload chunks to vector store
- batch upload entities/relations
- finalize job
- print stats and failed rows

## 10. Retrieval Design

### Task 11: Add Hybrid Retriever

**Files:**
- Create: `backend/app/services/system_knowledge_retriever.py`
- Modify: `backend/app/services/knowledge_evidence.py`
- Test: `backend/tests/test_system_knowledge_retriever.py`

Streams:

1. BM25 exact retrieval over title, claim text, aliases, tags.
2. Vector retrieval over chunks.
3. Graph traversal from detected entities in user context.

Fusion:

- Reciprocal Rank Fusion with `k=60`.
- Hard filters:
  - `is_active = true`
  - `superseded_by IS NULL`
  - `scope in allowed scopes`
  - condition/gene match where required
- Soft boosts:
  - higher confidence
  - recent confirmation
  - matching user goal
  - matching abnormal lab
  - matching gene variant

### Task 12: Add Retrieval Policy for Health Agent

**Files:**
- Create: `backend/app/services/agent_knowledge_policy.py`
- Modify: `backend/app/orchestrator/orchestrator.py`
- Modify: `backend/app/services/diet_plan.py`
- Modify: `backend/app/services/supplement_recommendation.py`
- Test: `backend/tests/test_agent_knowledge_policy.py`

Policy:

```text
If user asks diet/supplement/metabolic question:
  retrieve nutrition + metabolic + safety claims
  include user labs and genotype only from private twin
  include contraindication checks

If user asks medication question:
  retrieve medication_safety + gene_drug + red flag rules
  never suggest dose changes without doctor boundary

If user asks genetics question:
  retrieve gene interpretation claims
  require confidence and population limitation language

If user asks red-flag symptom:
  Safety Guardian overrides knowledge retrieval
```

## 11. Mobile First Agent Native UX

### Task 13: Add Evidence Capsule UI

**Files:**
- Create: `mobile/components/agent/EvidenceCapsule.tsx`
- Modify: `mobile/app/(tabs)/chat.tsx`
- Test: `mobile/components/agent/__tests__/EvidenceCapsule.test.tsx`

Mobile response should show compact evidence:

```text
依据
1. 系统知识库 · 冯雪·科学减肥16讲 · 蛋白质与减重
2. 你的数据 · 近7日体重/腰围趋势
3. 安全边界 · 肾功能异常或孕产状态需医生/营养师确认
```

Tap behavior:

- expands short excerpt
- shows confidence
- shows "为什么这条适用于我"
- does not show full source text

### Task 14: Add "Why This Advice" Agent Trace

**Files:**
- Create: `mobile/components/agent/AdviceTraceSheet.tsx`
- Modify: relevant chat/action-card components
- Test: `mobile/components/agent/__tests__/AdviceTraceSheet.test.tsx`

Trace sections:

- `系统知识`
- `个人数据`
- `基因/体检锚点`
- `安全规则`
- `不确定性`
- `下一步行动`

## 12. Lifecycle Jobs

### Task 15: Add Knowledge Lifecycle Celery Tasks

**Files:**
- Create: `backend/app/tasks/system_knowledge.py`
- Test: `backend/tests/test_system_knowledge_lifecycle.py`

Jobs:

- `decay_system_claim_confidence`
- `detect_system_claim_contradictions`
- `recompute_system_knowledge_stats`
- `rebuild_system_bm25_index`
- `sample_retrieval_quality`
- `deactivate_stale_low_quality_claims`

Schedule:

- daily 04:30: confidence decay and contradiction scan
- weekly Monday 04:00: BM25/vector rebuild
- weekly: quality sample report

## 13. Quality Gates

### Import Quality

Reject if:

- no title
- no source
- no domain
- no claim boundary
- confidence below `0.35`
- raw excerpt too long
- probable PII/secrets detected
- medical recommendation lacks boundary
- supplement claim lacks contraindication review tag

### Retrieval Quality

Every agent-facing retrieval result must include:

- source title
- evidence level
- confidence score
- scope
- claim boundary
- applicability explanation

### Advice Quality

Every user-facing answer that uses system knowledge must include:

- what is from system knowledge
- what is from user data
- what is uncertain
- what requires clinician confirmation

## 14. First Health Corpus Cut

Do not compile all 14k files first. Build a focused health corpus:

1. `冯雪·科学减肥16讲`
2. `冯雪·家庭健康管理100讲`
3. `冯雪·高血压医学课`
4. `冯雪·高血糖医学课`
5. `冯雪·高血脂医学课`
6. `冯雪·高尿酸医学课`
7. `仝卿·营养科学20讲`
8. `仇子龙·基因科学20讲`
9. `薄世宁·医学通识50讲`
10. `王家伟·日常用药健康课`
11. `怎样获得高质量睡眠`
12. `怎样成为精力管理的高手`
13. `前沿课·人体微生物组9讲`

Target first batch:

- 13 courses
- 150-300 pages
- 1,500-3,000 chunks
- 700-1,500 claims
- 300-700 entities
- 600-1,500 relations

## 15. Testing Strategy

### Backend Tests

Run:

```bash
cd backend
./venv/bin/pytest \
  tests/test_system_knowledge_models.py \
  tests/test_system_knowledge_api.py \
  tests/test_system_knowledge_retriever.py \
  tests/test_agent_knowledge_policy.py \
  tests/test_knowledge_evidence.py \
  -q
```

### Compiler Tests

Run:

```bash
cd /Users/liqiuhua/work/personal/down-dedao
python3 -m pytest tests/test_v2_scanner.py tests/test_v2_compiler.py tests/test_v2_sync.py -q
```

### End-to-End Smoke

Queries:

1. "我有 MTHFR TT，应该补叶酸吗？"
2. "最近腰围没降，饮食先改什么？"
3. "APOE 风险和 LDL 偏高，我该怎么吃？"
4. "我在吃他汀，还能吃葡萄柚吗？"
5. "减肥期蛋白质目标为什么是这个数？"

Expected:

- retrieval returns system claims + user context
- no raw course dump
- safety boundary present
- gene claims are conservative
- medication questions defer to clinician where appropriate

## 16. Rollout Plan

### Phase 0: Design and Governance

- Write this plan.
- Review paid-content policy.
- Define health domains and claim schema.
- Decide first 13-course corpus.

### Phase 1: Offline V2 Compiler

- scanner
- manifest
- classifier
- claim extractor
- KG extractor
- artifact writer
- quality report

### Phase 2: Serving Plane

- Postgres tables
- import APIs
- vector/BM25/KG storage
- audit logs
- stats endpoint

### Phase 3: Agent Integration

- hybrid retriever
- knowledge policy
- diet/supplement/genetic/medication injection
- safety override
- advice trace contract

### Phase 4: Mobile UX

- evidence capsule
- why-this-advice sheet
- source boundary display
- no raw-course leak

### Phase 5: Lifecycle Automation

- decay
- contradiction detection
- supersession
- quality sampling
- feedback crystallization

## 17. Definition of Done

The V2 system is done when:

- `/Users/liqiuhua/work/personal/down-dedao` can compile the first health corpus into V2 artifacts.
- `health-llm-driven` can import those artifacts idempotently.
- All imported knowledge is marked `system_shared` or `system_condition`, never `user_private`.
- User Agent queries retrieve system knowledge plus private user twin separately.
- Mobile shows evidence and boundaries without exposing raw paid content.
- Claims have confidence, source count, lifecycle fields, and supersession support.
- Retrieval ignores stale/superseded claims by default.
- Every import and retrieval is auditable.
- Tests cover import, retrieval, policy, and mobile evidence rendering.

## 18. Immediate Next Step

Start with Phase 1 and Phase 2 in parallel only if using separate work scopes:

- Worker A: `down-dedao/pipeline/v2/*` compiler artifacts.
- Worker B: `health-llm-driven/backend/app/models/system_knowledge.py` plus migration and import API.

If done sequentially, build backend data model first, then compiler output can target the exact schema.

