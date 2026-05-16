# System Knowledge KB Phase 0

Date: 2026-05-16

This document records the implemented vertical slice for the LLM Wiki v2 system knowledge base.

## Scope

Phase 0 makes reviewed system knowledge addressable by structured entity and claim IDs. The follow-on Phase 1a extension adds a reviewed JSONL artifact import path and expands the seed corpus across metabolic health, nutrition, sleep/recovery, movement, blood pressure, lipids, blood sugar, uric acid, and medication safety. Phase 1b adds DB-backed search, claim detail, admin lint/reindex, confidence decay, specialist `evidence_refs`, and an `aging_hallmark` taxonomy layer. Phase 1c adds the deterministic Dedao ingest pipeline, PR-style diff review flow, conflict/supersession guardrails, and the first scaled Dedao corpus expansion. User conversations remain outside the system KB.

## Data Flow

```mermaid
flowchart TD
  Raw["down-dedao raw sources"] --> Wiki["down-dedao/wiki entities + claims"]
  Wiki --> Seed["backend/scripts/seed_system_kb_phase0.py"]
  RawScan["down-dedao source scanner"] --> Artifact["backend/data/system_kb_v2_seed/*.jsonl"]
  Artifact --> Importer["backend/scripts/import_system_kb_v2_artifacts.py"]
  Seed --> DB["kb_documents / kb_edges / kb_audit"]
  Importer --> DB
  Twin["Twin summary genetics/labs"] --> Lookup["POST /api/v1/knowledge/lookup_for_twin"]
  DB --> Lookup
  DB --> Entity["GET /api/v1/knowledge/entity/{type}/{id}"]
  DB --> Claim["GET /api/v1/knowledge/claim/{claim_id}"]
  DB --> Search["GET /api/v1/knowledge/search"]
  DB --> Admin["GET/POST /api/v1/admin/knowledge/*"]
  Lookup --> Agent["Agent prompt / SSE card descriptor"]
  Entity --> Agent
  Claim --> Mobile
  Search --> Agent
  Admin --> Ops["lint / reindex / decay ops"]
  Agent --> Mobile["mobile system_knowledge_evidence card"]
```

## Backend Components

- `app.models.system_knowledge.KBDocument`: entity, claim, and article metadata.
- `app.models.system_knowledge.KBEdge`: typed graph edges between documents.
- `app.models.system_knowledge.KBAudit`: query and lookup audit trail.
- `app.services.system_knowledge_service`: deterministic entity bundle, claim detail, DB-backed search, Twin lookup, confidence decay, lint, reindex, and specialist evidence attachment.
- `app.api.system_knowledge`: authenticated `/knowledge/entity/...`, `/knowledge/claim/...`, `/knowledge/claim/{claim_id}/feedback`, `/knowledge/search`, `/knowledge/lookup_for_twin`, plus admin `/admin/knowledge/lint_report` and `/admin/knowledge/reindex`.
- `migrations/managed/20260516_200000_create_system_knowledge_tables.*.sql`: PostgreSQL production and SQLite test migrations.
- `app.services.system_knowledge_pipeline`: deterministic source scanner and health-domain classifier for `/Users/liqiuhua/work/personal/down-dedao`.
- `app.services.system_knowledge_ingest`: deterministic Dedao course ingest, transformed claim mining, duplicate/conflict handling, supersession guardrails, entity/claim/page/relation artifact generation, and PR-style diff rendering.
- `app.services.system_knowledge_importer`: imports reviewed `manifest.json` plus `entities.jsonl`, `claims.jsonl`, `pages.jsonl`, and `relations.jsonl`.
- `scripts/ingest_dedao_system_kb.py`: dry-run or `--write` CLI for expanding reviewed artifacts from selected Dedao courses.
- `scripts/import_system_kb_v2_artifacts.py`: deployment-safe import entrypoint for reviewed artifacts.
- `scripts/scan_system_kb_sources.py`: local inspection tool for expanding course/book coverage without publishing raw paid content.
- `scripts/lint_system_kb.py`: CLI lint report for orphan/stale/invalid KB content.
- `scripts/reindex_system_kb.py`: refreshes `tsv` search text and `content_hash`.
- `scripts/decay_system_kb_confidence.py`: applies lifecycle confidence decay to stale claims.

## Mobile Function Map

```mermaid
flowchart LR
  ServerCard["SSE cards[] / message card"] --> Registry["components/chat/cards/registry.tsx"]
  Registry --> Evidence["SystemKnowledgeEvidenceCard"]
  Evidence --> User["Evidence level, confidence, source chips, medical boundary"]
```

Card type: `system_knowledge_evidence`

Minimal payload:

```json
{
  "type": "system_knowledge_evidence",
  "data": {
    "entity": { "title": "MTHFR", "entity_id": "MTHFR" },
    "claims": [
      {
        "title": "MTHFR C677T 与叶酸转化边界",
        "evidence_level": "B",
        "confidence": 0.82,
        "sources": ["dedao:qiuzilong-genetics-07", "pubmed:19033271"]
      }
    ],
    "claim_boundary": "仅用于健康管理和风险沟通，不替代医生诊断、治疗或用药决策。"
  }
}
```

## Phase 0 Seed Coverage

- Genes: `MTHFR`, `APOE`, `FTO`, `ACTN3`, `ALDH2`
- Biomarker: `Hcy`
- Supplement: `5-MTHF`
- Claims: five reviewed seed claims, one per gene.

## Phase 1a Expanded Coverage

The reviewed artifact seed adds:

- Priority course pages: 冯雪四高课程、科学减肥、仝卿营养、忙碌者营养/糖尿病、仇子龙基因、王家伟用药、睡眠课程、薄世宁医学通识。
- Entities: metabolic-health, hypertension-risk, dyslipidemia-risk, glycemic-risk, hyperuricemia-risk, sleep-recovery, weight/waist/HbA1c/LDL-C/TG/BP/uric-acid/eGFR and core interventions.
- Claims: 15 bounded action claims covering weight+waist tracking, protein, fiber, salt, home BP, LDL/ApoB, TG, HbA1c feedback loop, uric acid context, Zone 2 with recovery constraint, strength training, sleep window, medication-vs-supplement separation, interaction review, and medical boundary.

These artifacts are intentionally transformed summaries and short claims. They do not expose full paid lesson text and are imported only after review.

## Phase 1b Backend Closure

Current reviewed artifact counts:

- Pages: 16
- Entities: 45
- Claims: 145
- Relations: 550

New behavior:

- `GET /api/v1/knowledge/claim/{claim_id}` returns claim detail, graph neighbors, edges, and medical boundary.
- `POST /api/v1/knowledge/claim/{claim_id}/feedback` records `feedback_disagree` in `kb_audit` so mobile evidence feedback becomes a lifecycle signal.
- `GET /api/v1/knowledge/search` performs deterministic DB-only lexical scoring plus graph context. It is compatible with SQLite tests and production PostgreSQL; later FTS/vector/RRF can replace the scorer without changing response shape.
- `GET /api/v1/admin/knowledge/lint_report` reports orphan entities, orphan claims, invalid `applies_when`, and stale claims.
- `POST /api/v1/admin/knowledge/reindex` refreshes `kb_documents.tsv` and SHA-256 `content_hash`.
- `apply_confidence_decay(...)` and `scripts/decay_system_kb_confidence.py` implement the first lifecycle hook for stale claim confidence decay.
- Orchestrator attaches matched system KB claim IDs to specialist output as `evidence_refs`, so mobile can render evidence chips on non-gene cards in a later UI pass.
- KnowledgeLibrarian now prefers system KB V2 when a DB session is present, returning `system_knowledge_reference` findings and claim-level `evidence_refs`; the old Chroma wiki search remains fallback.

New taxonomy:

- `aging_hallmark:*` covers 14 aging hallmarks and extensions. The explicit product rule is: hallmark entities are a trajectory map and mechanism vocabulary, not a direct supplement recommendation table.

## Phase 1c Dedao Ingest Pipeline

New ingest behavior:

- `backend/scripts/ingest_dedao_system_kb.py` runs in dry-run mode by default and prints a PR-style diff without mutating `backend/data/system_kb_v2_seed`.
- `--write` merges generated pages, entities, claims, and graph edges into reviewed artifacts after human review.
- Claims are transformed short health-management facts with `applies_when`, `recommends_lookup`, evidence level, confidence, lifecycle fields, and a medical boundary.
- Raw paid-course bodies are not written to artifacts or serving DB.
- Existing reviewed claims are not superseded by draft ingest output; possible overlaps are marked as `candidate_duplicates`.
- Legacy or draft claims may be superseded with an explicit archived copy and metadata trail.

First scaled run:

- Source root: `/Users/liqiuhua/work/personal/down-dedao`
- Courses selected: 冯雪科学减肥、冯雪家庭健康管理、冯雪高血压/高血糖/高血脂/高尿酸、仝卿营养、仇子龙基因、王家伟用药、给忙碌者糖尿病、前沿人体微生物组、薄世宁医学通识、怎样获得高质量睡眠。
- Sources compiled: 13
- Claims added: 129
- Entities added: 9
- Pages added: 4
- Relations added: 503
- Claims superseded: 0

## Next Interfaces

Next work should keep widening the reviewed artifact corpus with more topic templates or a governed LLM extraction pass. The main remaining product work is stronger specialist evidence enforcement, deeper PostgreSQL FTS/vector hybrid search, private-vault cleanup for personal wiki pages, and reviewer workflows for claim approval/supersession.
