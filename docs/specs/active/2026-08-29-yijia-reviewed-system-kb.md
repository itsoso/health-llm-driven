# Feature Spec: 益家知研受审 System KB 上线

> Status: accepted
> Owner: Codex / product owner
> Updated: 2026-08-29
> Related PRD/PDD: `docs/prd/2026-08-29-yijia-reviewed-system-kb.md`
> Related code: `backend/app/services/system_knowledge_service.py`, `backend/app/services/agent_executor.py`

## 1. Decision

Publish a minimal, source-scoped, reviewed claim pack for the “益家知研 / 皮皮妈妈”
aliases without exposing the unreviewed legacy Markdown corpus.

## 2. Requirement Admission

```yaml
RequirementAdmission:
  request: make the named knowledge source actually searchable
  classification: product_change
  first_user_fit: health questions involving supplements and chronic-risk context
  core_loop_step: evidence retrieval -> SafetyGuardian boundary -> synthesis
  first_class_objects: [SafetyGuardian, HealthTwin]
  target_surface: backend Agent chat
  source_of_truth: reviewed System KB artifacts and PostgreSQL serving tables
  safety_level: medical_boundary
  prescription_or_causal_verdict: none
  autonomy_tier: none
  evidence_provenance: transformed local source plus current official guidance
  claim_hedging: hedged
  verification_window: immediate production replay
  success_metric: named query returns only matching reviewed collection documents
  added_user_burden: none
  burden_justification: n/a
  non_goals: raw corpus serving, diagnosis, treatment or dose generation
  smallest_end_to_end_slice: two reviewed claims and source-scoped retrieval
  stale_surface_to_remove_or_archive: supersede not_released alias after release
  spec_required: yes
```

## 3. Data Contract

```yaml
apis: no public HTTP schema change
events: none
models: no database schema change
fields:
  KBDocument.metadata.source_collections: list[str]
  KBDocument.metadata.named_collection_only: true for documents hidden from generic search
  search_knowledge.source_collection: optional exact canonical collection id
enums:
  yijia_reviewed: canonical collection id
backward_compatibility: absent source_collection preserves prior generic ranking and excludes named-only documents
migration: none
```

## 4. Medical Boundary

- The legacy source is discovery input, not medical authority.
- Released claims require current official-source calibration and transformed text.
- The runtime must not prescribe supplements, antipyretics, or antivirals, and must
  not generate individualized doses.
- Acute COVID answers should prioritize red flags, severe-risk assessment, symptom
  onset and timely clinician/pharmacist review over supplement selection.
- Collection filtering is TIGHTEN-only: errors or zero hits never widen to generic KB.

## 5. Acceptance Criteria

```gherkin
Given reviewed yijia_reviewed and unrelated reviewed documents exist
When source-scoped search is called for yijia_reviewed
Then every returned document belongs to yijia_reviewed

Given a user specifies 益家知研 after asking about COVID fever supplements
When the Agent executes knowledge_search
Then it searches yijia_reviewed and returns released source receipt plus a reviewed claim

Given the named collection has no matching reviewed document
When retrieval completes
Then the response states a named-source zero hit and never substitutes generic results

Given a generic knowledge_search call
When no knowledge_source is specified
Then named-only documents are excluded and existing reviewed System KB ranking is unchanged
```

## 6. Verification

Run focused System KB and Agent tests, the full artifact release gate, relevant wider
regression, LLM change gate, independent safety review, CI, deploy health, and a
read-only production replay of the anchor query.

## 7. Rollout And Rollback

Backend deploy imports the reviewed artifacts through the existing content-addressed
System KB transaction. Roll back the code/artifact commit to restore `not_released`.

## 8. Changelog

| Date | Change | Reason |
|---|---|---|
| 2026-08-29 | Accepted minimal reviewed source collection | Complete the named-source user loop safely |
