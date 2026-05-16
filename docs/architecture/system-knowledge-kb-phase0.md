# System Knowledge KB Phase 0

Date: 2026-05-16

This document records the implemented vertical slice for the LLM Wiki v2 system knowledge base.

## Scope

Phase 0 makes reviewed system knowledge addressable by structured entity and claim IDs. The follow-on Phase 1a extension adds a reviewed JSONL artifact import path and expands the seed corpus across metabolic health, nutrition, sleep/recovery, movement, blood pressure, lipids, blood sugar, uric acid, and medication safety. User conversations remain outside the system KB.

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
  Lookup --> Agent["Agent prompt / SSE card descriptor"]
  Entity --> Agent
  Agent --> Mobile["mobile system_knowledge_evidence card"]
```

## Backend Components

- `app.models.system_knowledge.KBDocument`: entity, claim, and article metadata.
- `app.models.system_knowledge.KBEdge`: typed graph edges between documents.
- `app.models.system_knowledge.KBAudit`: query and lookup audit trail.
- `app.services.system_knowledge_service`: deterministic entity bundle and Twin lookup.
- `app.api.system_knowledge`: authenticated `/knowledge/entity/...` and `/knowledge/lookup_for_twin` endpoints.
- `migrations/managed/20260516_200000_create_system_knowledge_tables.*.sql`: PostgreSQL production and SQLite test migrations.
- `app.services.system_knowledge_pipeline`: deterministic source scanner and health-domain classifier for `/Users/liqiuhua/work/personal/down-dedao`.
- `app.services.system_knowledge_importer`: imports reviewed `manifest.json` plus `entities.jsonl`, `claims.jsonl`, `pages.jsonl`, and `relations.jsonl`.
- `scripts/import_system_kb_v2_artifacts.py`: deployment-safe import entrypoint for reviewed artifacts.
- `scripts/scan_system_kb_sources.py`: local inspection tool for expanding course/book coverage without publishing raw paid content.

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

## Next Interfaces

Phase 1 should keep widening the reviewed artifact corpus and add PR-diff ingest for new courses/books. Phase 2 should make planners and specialist agents emit `evidence_refs` and card descriptors from these `claim:*` IDs, instead of relying only on direct gene-question cards.
