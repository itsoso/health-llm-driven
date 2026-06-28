# System KB Next Stage Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Push the LLM Wiki V2 system knowledge base from a working serving slice into a production-quality knowledge operating system: broader reviewed corpus, stronger evidence enforcement, mobile-first evidence UX, and automated lifecycle governance.

**Architecture:** Keep authoring and serving separated. Course/book material is compiled offline into reviewed JSONL artifacts, imported into PostgreSQL for serving, attached to specialist findings as `evidence_refs`, and displayed on mobile through a unified claim/entity evidence sheet. User conversations never write directly into the system KB; only reviewed artifacts and multi-user crystallized candidates can enter.

**Tech Stack:** FastAPI, SQLAlchemy, PostgreSQL in production, SQLite only for focused tests, React Native/Expo mobile, Celery scheduled tasks, deterministic Dedao ingest CLI, existing `kb_documents` / `kb_edges` / `kb_audit` schema.

---

## Current Baseline

Latest relevant implementation pass: 2026-05-17 system KB governance/retrieval update.

Already done:

- System KB tables and artifact import path are live.
- Reviewed artifacts contain `508 documents, 2715 edges` (`52 pages / 99 entities / 357 claims / 2715 relations`) and are imported on backend deploy.
- `/api/v1/knowledge/entity/...`, `/claim/...`, `/search`, `/lookup_for_twin` exist.
- `/api/v1/admin/knowledge/lint_report` exists and now flags orphan, invalid condition, stale claim, invalid review status, contradiction.
- `/api/v1/admin/knowledge/coverage_report` exists for evidence coverage and unsupported findings.
- Deterministic Dedao ingest exists via `backend/scripts/ingest_course.py` and older `backend/scripts/ingest_dedao_system_kb.py`.
- Artifact review promotion exists via `promote_artifact_review_status`.
- Crystallized claim candidate drafting exists in `backend/app/services/system_knowledge_crystallize.py` and runs draft-only from the weekly `system-kb-lifecycle` Celery job.
- Privacy isolation guard exists in `find_private_source_violations(...)`; ingestion scanner excludes private-looking paths without reading their contents.
- `/knowledge/search` now returns local BM25 lexical, PostgreSQL `tsvector` FTS-compatible, semantic alias, and graph channels in a stable response shape.
- Phase 2 corpus breadth target is complete: the compiler scanned 46 health-relevant Dedao/book source directories and promoted 314 generated claims, 83 entities, 46 pages, and 2566 relations to reviewed status across reviewed passes.
- Dedao graph association now emits entity-to-entity `contextualizes` relations from claim context, making graph traversal useful for linking biomarkers, conditions, interventions, and safety boundaries.
- Weekly Advisor action-card generation now reuses Orchestrator system-KB evidence attachment and planner evidence policy before persisting fallback specialist findings.

Main remaining gaps:

- Specialist evidence is attached and measured as a product contract through `evidence_refs`, `unsupported`, and coverage-rate metrics.
- Orchestrator Planner now filters unsupported actionable findings before synthesis when a same-domain KB-supported finding exists; safety alerts and data gaps are preserved.
- Mobile evidence UI now has reusable `EvidenceRefsRow` / `ClaimSheet` / `EntityCard`; chat cards, action cards, genetic report, today plan, knowledge entity, and the standalone diet/movement related-card surfaces expose system KB evidence refs.
- Admin has `/api/v1/admin/knowledge/operations_dashboard`, which aggregates coverage, lint, latest lifecycle report, and action items for KB governance.
- External second-source evidence exists for selected high-risk claim templates (`MTHFR`, `APOE`, statin boundary, diabetes 8-12 week loop), and coverage report now exposes `external_evidence` metrics by claim count, source kind, target rate, and `meets_target`.
- Direct PushScheduler wearable health alerts carry the KB V2 safety-alert evidence contract. Celery notification surfaces now tag trend summaries, morning briefings, weekly review invites, action-card followups, agent-loop pushes, and outcome-grader pushes with notification evidence metadata. Push-log evidence coverage is exposed in the admin coverage dashboard and operations action items. Search now uses local BM25 and PostgreSQL `tsvector` FTS in production; remaining gap is real vector retrieval beyond the deterministic alias stream.

---

## Phase 1: Source-Of-Truth Docs And Metrics Lock

**Intent:** Make current state unambiguous before expanding the corpus.

### Task 1: Update KB Architecture Docs

**Files:**
- Modify: `docs/AGENT_NATIVE_KB_PLAN.md`
- Modify: `docs/architecture/dedao-system-knowledge-sync.md`
- Modify: `docs/architecture/system-knowledge-kb-phase0.md`

**Step 1: Write doc status checklist**

Update each doc with a dated `2026-05-17 Current State` section:

```markdown
## 2026-05-17 Current State

- Reviewed artifacts: 508 docs / 2715 edges.
- Ingest authoring CLI: `backend/scripts/ingest_course.py`.
- Review promotion: `promote_artifact_review_status`.
- Admin lint: contradiction + invalid review status included.
- Admin coverage: `/api/v1/admin/knowledge/coverage_report`.
- Crystallize: draft-only service exists and is called by weekly `system-kb-lifecycle` Celery task.
```

**Step 2: Verify no stale status remains**

Run:

```bash
rg -n "145 claims|未完成|缺 contradiction|缺.*crystallize|缺.*review" docs/AGENT_NATIVE_KB_PLAN.md docs/architecture
```

Expected: any hits are either updated to current state or explicitly listed as still open.

**Step 3: Commit**

```bash
git add docs/AGENT_NATIVE_KB_PLAN.md docs/architecture/dedao-system-knowledge-sync.md docs/architecture/system-knowledge-kb-phase0.md
git commit -m "docs(kb): align system knowledge current state"
```

---

## Phase 2: Corpus Expansion To Reviewed 300+ Claims

**Intent:** Expand breadth without violating copyright or review boundaries.

**Status 2026-05-18:** Complete. Reviewed corpus now exceeds the target with `99 entities / 357 claims / 2715 relations`. The expansion manifest remains as the target contract for future ingestion rounds.

### Task 2: Add A Corpus Expansion Manifest

**Files:**
- Create: `backend/data/system_kb_v2_seed/expansion_manifest.json`
- Test: `backend/tests/test_system_knowledge_ingest.py`

**Step 1: Write failing test**

Add a test that asserts the manifest exists and contains priority courses:

```python
def test_system_kb_expansion_manifest_lists_priority_courses():
    path = Path("backend/data/system_kb_v2_seed/expansion_manifest.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["target_counts"]["claims"] >= 300
    assert "仇子龙·基因科学20讲" in payload["priority_courses"]
    assert "王家伟·日常用药健康课" in payload["priority_courses"]
```

**Step 2: Run test to verify it fails**

Run:

```bash
DATABASE_URL=sqlite:///./test_kb_manifest.db PYTHONPATH=backend backend/venv/bin/python -m pytest backend/tests/test_system_knowledge_ingest.py::test_system_kb_expansion_manifest_lists_priority_courses -q
```

Expected: FAIL because file is missing.

**Step 3: Add manifest**

Create JSON:

```json
{
  "version": "2026-05-17",
  "target_counts": {"entities": 80, "claims": 300, "relations": 800},
  "priority_courses": [
    "仇子龙·基因科学20讲",
    "仝卿·营养科学20讲",
    "王家伟·日常用药健康课",
    "冯雪·高血压医学课",
    "冯雪·高血脂医学课",
    "冯雪·高血糖医学课",
    "冯雪·高尿酸医学课",
    "给忙碌者的糖尿病医学课",
    "薄世宁·医学通识50讲",
    "怎样获得高质量睡眠"
  ],
  "copyright_policy": "Only transformed short claims and source references are stored; no paid-course long text is served.",
  "review_policy": "All generated artifacts remain draft until promoted by human reviewer."
}
```

**Step 4: Run test to verify it passes**

Run the same pytest command. Expected: PASS.

### Task 3: Expand Deterministic Claim Templates

**Files:**
- Modify: `backend/app/services/system_knowledge_ingest.py`
- Test: `backend/tests/test_system_knowledge_ingest.py`

**Step 1: Add failing tests for four domains**

Add tests proving the compiler can produce claims for:

- `gene_pharmacogenomics_boundary`
- `sleep_regular_window`
- `diabetes_recheck_8_12_weeks`
- `drug_interaction_review`

Expected doc IDs should start with `claim:c_dedao_...`.

**Step 2: Run tests to verify failure**

Run:

```bash
DATABASE_URL=sqlite:///./test_kb_templates.db PYTHONPATH=backend backend/venv/bin/python -m pytest backend/tests/test_system_knowledge_ingest.py -q
```

Expected: new tests fail because templates are missing.

**Step 3: Add minimal `ClaimTemplate` entries**

Add templates only when the topic can be detected by stable keywords in local course titles/text. Keep summaries short, transformed, and non-diagnostic.

**Step 4: Run tests**

Expected: PASS.

### Task 4: Generate Reviewed Expansion Artifacts

**Files:**
- Modify: `backend/data/system_kb_v2_seed/*.jsonl`
- Modify: `backend/data/system_kb_v2_seed/manifest.json`
- Create or update: `backend/data/system_kb_v2_seed/review_manifest.json`

**Step 1: Dry run**

Run:

```bash
backend/venv/bin/python backend/scripts/ingest_course.py \
  --course '仇子龙·基因科学20讲' \
  --course '仝卿·营养科学20讲' \
  --course '王家伟·日常用药健康课' \
  --course '冯雪·高血压医学课' \
  --course '冯雪·高血脂医学课' \
  --course '冯雪·高血糖医学课' \
  --course '冯雪·高尿酸医学课' \
  --course '给忙碌者的糖尿病医学课' \
  --course '薄世宁·医学通识50讲' \
  --course '怎样获得高质量睡眠' \
  --max-lessons-per-course 60
```

Expected: PR-style diff only; no files mutated.

**Step 2: Review diff manually**

Reject changes that:

- contain long paid-course text,
- sound like diagnosis/treatment/prescription,
- lack health management boundary,
- duplicate reviewed claims without candidate duplicate metadata.

**Step 3: Write and promote**

Run:

```bash
backend/venv/bin/python backend/scripts/ingest_course.py \
  --write \
  --promote-reviewed \
  --reviewer "owner-reviewed-2026-05-17" \
  --course '仇子龙·基因科学20讲' \
  --course '仝卿·营养科学20讲' \
  --course '王家伟·日常用药健康课' \
  --course '冯雪·高血压医学课' \
  --course '冯雪·高血脂医学课' \
  --course '冯雪·高血糖医学课' \
  --course '冯雪·高尿酸医学课' \
  --course '给忙碌者的糖尿病医学课' \
  --course '薄世宁·医学通识50讲' \
  --course '怎样获得高质量睡眠' \
  --max-lessons-per-course 60
```

**Step 4: Verify counts**

Run:

```bash
python - <<'PY'
import json, pathlib
root = pathlib.Path("backend/data/system_kb_v2_seed")
for name in ["entities.jsonl", "claims.jsonl", "relations.jsonl"]:
    print(name, sum(1 for _ in (root / name).open()))
print(json.loads((root / "manifest.json").read_text())["ingest"]["review_status"])
PY
```

Expected: claims move toward or exceed 300, review status is `reviewed`.

---

## Phase 3: Evidence Contract For Specialist Findings

**Intent:** Move from “audit unsupported” to “planner knows whether a recommendation is supported.”

### Task 5: Add Evidence Coverage Contract Tests

**Files:**
- Modify: `backend/tests/test_orchestrator_evidence_audit.py`
- Modify: `backend/tests/test_system_knowledge_v2_pipeline.py`
- Modify: `backend/app/orchestrator/orchestrator.py`

**Step 1: Write failing test**

Add test:

```python
def test_supported_recommendations_include_evidence_contract_fields():
    snapshot = _specialist_audit_snapshot([...])
    assert snapshot[0]["support_status"] == "supported"
    assert snapshot[0]["evidence_ref_count"] == 1
```

Unsupported findings should get:

```python
assert snapshot[0]["support_status"] == "model_inference"
assert snapshot[0]["unsupported_reason"] == "missing_system_kb_evidence_refs"
```

**Step 2: Run red test**

Run:

```bash
PYTHONPATH=backend backend/venv/bin/python -m pytest backend/tests/test_orchestrator_evidence_audit.py -q
```

Expected: FAIL because fields are missing.

**Step 3: Implement minimal fields**

Update `_specialist_audit_snapshot` to include:

- `support_status`
- `evidence_ref_count`
- `unsupported_reason`

Do not block user-facing answers yet.

**Step 4: Run tests**

Expected: PASS.

### Task 6: Specialist Coverage Gate In Admin Report

**Files:**
- Modify: `backend/app/services/system_knowledge_service.py`
- Modify: `backend/tests/test_system_knowledge_phase0.py`

**Step 1: Add test for threshold**

Admin coverage report should include:

```python
assert payload["specialist_findings"]["target_evidence_ref_rate"] == 0.85
assert payload["specialist_findings"]["meets_target"] is False
```

**Step 2: Implement**

Add target fields to `_aggregate_specialist_evidence_coverage`.

**Step 3: Verify**

Run:

```bash
DATABASE_URL=sqlite:///./test_kb_coverage_gate.db PYTHONPATH=backend backend/venv/bin/python -m pytest backend/tests/test_system_knowledge_phase0.py::test_admin_coverage_report_counts_evidence_refs_unsupported_and_feedback -q
```

Expected: PASS.

---

## Phase 4: Mobile-First Evidence UX

**Intent:** Make evidence inspectable from every recommendation surface, not just chat markdown.

**Status 2026-06-28:** Unified `mobile/components/knowledge/EvidenceRefsRow.tsx`, `ClaimSheet.tsx`, and `EntityCard.tsx` are live. This pass also closes the remaining standalone plan-page gap: diet and movement plan `related_cards` now receive backend `evidence_refs`, render `EvidenceRefsRow`, and preserve refs in follow-up Agent context.

### Task 7: Build Unified Evidence Components

**Files:**
- Create: `mobile/components/knowledge/EvidenceRefsRow.tsx` if not already present, otherwise consolidate existing implementation.
- Create: `mobile/components/knowledge/ClaimSheet.tsx`
- Create: `mobile/components/knowledge/EntityCard.tsx`
- Modify: existing assistant/recommendation cards using `evidence_refs`.
- Test: relevant mobile component tests under `mobile/components/**/__tests__/`.

**Step 1: Write component tests**

Test expected behavior:

- one evidence ref renders compact chip,
- multiple refs show count,
- tapping opens claim sheet,
- feedback button calls `/api/v1/knowledge/claim/{claim_id}/feedback`.

**Step 2: Run red tests**

Run:

```bash
cd mobile && npm test -- EvidenceRefsRow ClaimSheet
```

Expected: FAIL before components are implemented.

**Step 3: Implement components**

Use existing app visual language. Keep rows dense and mobile-first. Do not expose long course text.

**Step 4: Run tests**

Expected: PASS.

### Task 8: Wire Evidence Components Into Four Surfaces

**Files:**
- Modify: mobile supplement recommendation card.
- Modify: mobile food/fuel recommendation card.
- Modify: mobile movement/training recommendation card.
- Modify: mobile genetics/gene detail screen.

**Step 1: Add tests or snapshot checks for each surface**

Each surface must render `EvidenceRefsRow` when `evidence_refs.length > 0`.

**Step 2: Implement minimal wiring**

Do not redesign the whole page. Only add consistent evidence entry points.

**Step 3: Manual verification**

Run Expo locally and inspect:

```bash
cd mobile && npm run start
```

Expected: evidence chips visible and tap opens claim details.

---

## Phase 5: System KB Lifecycle Automation

**Intent:** Create a dedicated lifecycle path for global system KB, separate from user memory lifecycle.

### Task 9: Add System KB Lifecycle Task

**Files:**
- Create: `backend/app/tasks/system_knowledge_lifecycle.py`
- Modify: `backend/app/celery_app.py`
- Test: `backend/tests/test_system_knowledge_lifecycle.py`

**Step 1: Write failing test**

Test task helper returns:

```python
{
  "lint": {"summary": ...},
  "decay": {"processed": ...},
  "crystallize": {"draft_candidates": ...}
}
```

**Step 2: Run red test**

Run:

```bash
DATABASE_URL=sqlite:///./test_kb_lifecycle.db PYTHONPATH=backend backend/venv/bin/python -m pytest backend/tests/test_system_knowledge_lifecycle.py -q
```

Expected: FAIL because module is missing.

**Step 3: Implement helper and Celery task**

Task should:

1. run `lint_knowledge_base`,
2. run `apply_confidence_decay`,
3. run `draft_crystallized_claim_candidates(min_count=100)`,
4. write `KBAudit(op="lifecycle_report")`.

Do not auto-import crystallized drafts.

**Step 4: Add Celery schedule**

In `backend/app/celery_app.py` add weekly schedule, not daily:

```python
"system-kb-lifecycle": {
    "task": "app.tasks.system_knowledge_lifecycle.run_system_kb_lifecycle",
    "schedule": crontab(hour=4, minute=30, day_of_week=1),
},
```

**Step 5: Verify**

Run tests and lint.

---

## Phase 6: External Evidence Upgrade For High-Risk Claims

**Intent:** Improve evidence level without turning the system into unreviewed web RAG.

### Task 10: Add External Source Slot To Artifacts

**Files:**
- Modify: `backend/app/services/system_knowledge_ingest.py`
- Modify: `backend/data/system_kb_v2_seed/claims.jsonl`
- Test: `backend/tests/test_system_knowledge_ingest.py`

**Step 1: Add failing test**

Claims with high-risk entities should allow:

```json
"external_sources": [
  {"type": "pubmed", "id": "19033271", "title": "...", "review_status": "reviewed"}
]
```

**Step 2: Implement metadata support**

Keep `sources` backward-compatible. Store external sources in `metadata.external_sources`.

**Step 3: Add first reviewed external refs**

Start with only 5 high-value claims:

- MTHFR / Hcy / folate boundary
- APOE / lipid risk boundary
- statin / medication review boundary
- diabetes / 8-12 week recheck
- sleep apnea / doctor handoff boundary

Use only source IDs and short transformed summaries.

**Step 4: Verify evidence levels**

Run tests and inspect import output.

---

## Final Verification Batch

Before any final commit:

```bash
backend/venv/bin/python -m ruff check \
  backend/app/api/system_knowledge.py \
  backend/app/services/system_knowledge_ingest.py \
  backend/app/services/system_knowledge_service.py \
  backend/app/services/system_knowledge_crystallize.py \
  backend/app/tasks/system_knowledge_lifecycle.py \
  backend/scripts/ingest_course.py \
  backend/tests/test_system_knowledge_phase0.py \
  backend/tests/test_system_knowledge_ingest.py \
  backend/tests/test_system_knowledge_crystallize.py \
  backend/tests/test_system_knowledge_lifecycle.py
```

```bash
DATABASE_URL=sqlite:///./test_kb_next_stage.db \
PYTHONPATH=backend \
backend/venv/bin/python -m pytest \
  backend/tests/test_system_knowledge_phase0.py \
  backend/tests/test_system_knowledge_ingest.py \
  backend/tests/test_system_knowledge_crystallize.py \
  backend/tests/test_system_knowledge_lifecycle.py \
  backend/tests/test_orchestrator_evidence_audit.py \
  -q
```

If mobile files changed:

```bash
cd mobile && npm test -- EvidenceRefsRow ClaimSheet
```

Then:

```bash
git add <changed files>
git commit -m "feat(kb): advance system knowledge operations"
git push origin main
./deploy.sh -b
```

For mobile JS-only changes:

```bash
scripts/mobile-ota.sh production "System KB evidence UX"
```

If native dependencies/config changed, use EAS build + TestFlight instead of OTA.

---

## Acceptance Criteria

The next stage is complete when:

- Reviewed corpus reaches at least `80 entities / 300 claims`, or the expansion manifest explains why a course was skipped. Completed 2026-05-18 with `99 entities / 357 claims`.
- Admin `coverage_report` includes target rate and current evidence rate.
- Specialist audit snapshots expose `support_status`.
- Mobile has one reusable evidence sheet path for claim details and feedback.
- System KB lifecycle produces weekly lint/decay/crystallize audit reports.
- Weekly Advisor fallback action cards apply the same planner evidence policy as Orchestrator.
- No full paid-course text is stored in serving DB or displayed in mobile.
- User-private memory remains outside system KB.
