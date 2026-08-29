# Feature Spec: Named knowledge-source retrieval integrity

> Status: accepted bugfix
> Owner: Codex
> Updated: 2026-08-29
> Related PRD/PDD: `docs/specs/reva-product-governance-spec.md`
> Related code: `backend/app/services/agent_executor.py`, `backend/app/services/tool_schema_registry.py`

## 1. Decision

When a user explicitly asks Reva to answer from a named knowledge source, the
backend must deterministically carry that source into `knowledge_search` and
must not substitute the reviewed System KB, an unrelated retrieval result, or
an unreviewed legacy asset while claiming the named source was searched.

## 2. Problem

The production conversation on 2026-08-29 exposed two failures. A request to
use the "皮皮妈妈" knowledge base completed without a retrieval call. A follow-up
that named "益家知研" called generic `knowledge_search` twice, but the tool contract
could not carry a source name and the answer speculated about upload or keyword
problems. The repository contains a legacy supplement asset with those labels,
but it is not released into the reviewed System KB serving plane.

## 3. Requirement Admission

```yaml
RequirementAdmission:
  request: 修复指定知识库没有被真正搜索且回答误报成功的问题
  classification: bugfix
  first_user_fit: users asking Reva to ground health answers in an owned knowledge source
  core_loop_step: Health Twin -> evidence retrieval -> safe synthesis
  first_class_objects: [HealthTwin, SafetyGuardian]
  target_surface: Backend agent chat
  source_of_truth: reviewed System KB plus an explicit source-resolution contract
  safety_level: medical_boundary
  prescription_or_causal_verdict: none
  autonomy_tier: none
  evidence_provenance: requested source and resolved serving source must be explicit
  claim_hedging: hedged
  verification_window: same chat turn
  success_metric: named-source requests always retrieve or return an explicit unavailable boundary
  added_user_burden: none
  burden_justification: n/a
  non_goals: importing or medically approving the legacy supplement guide
  smallest_end_to_end_slice: named request -> deterministic tool call -> source-aware result -> honest synthesis
  stale_surface_to_remove_or_archive: none
  spec_required: yes
```

## 4. Non-Goals

- Do not promote `backend/knowledge/supplement_knowledge.md` into reviewed
  medical evidence.
- Do not add a database migration or a new user knowledge-store product.
- Do not use raw Dedao, MyKnowledge, Obsidian, or Chroma content as runtime
  medical authority.
- Do not provide a COVID supplement treatment or personalized dose.

## 5. Product Object Mapping

| Object | Change |
|---|---|
| `HealthTwin` | Named-source retrieval remains evidence context and does not mutate the Twin. |
| `SafetyGuardian` | Unreviewed or unknown sources fail closed before medical synthesis. |

## 6. User Flow

```text
explicit named-source request or immediate correction
  -> resolve source alias and recover the preceding health question
  -> call knowledge_search with query + knowledge_source
  -> reviewed source: retrieve; unreviewed/unknown source: return explicit boundary
  -> strong-model synthesis without source substitution
  -> same-turn verification in tool metadata
```

## 7. Surface Contract

| Surface | Responsibility | Contract |
|---|---|---|
| Backend | Retrieval authority | Carry source identity into the tool call and fail honestly. |
| Mobile/Mac/Web | Presentation | No API change; render the returned answer and existing source metadata. |

## 8. Data Contract

```yaml
apis: no HTTP contract change
events: existing tool events; knowledge_search remains read-only
models: none
fields: knowledge_search.knowledge_source is optional and backward compatible
enums: none
backward_compatibility: generic knowledge_search continues to query reviewed System KB
migration: none
```

## 9. Safety, Privacy, And Medical Boundary

Named-source resolution is deterministic and contains no user health data.
The health query still passes through the retrieval privacy guard. A legacy or
unknown source must not be queried as medical authority and must not be silently
replaced by generic results. The result must instruct synthesis not to claim an
upload, sync, keyword, or content failure that was not observed.

## 10. AI Behavior

The model may synthesize only after the deterministic source result. It must
not decide whether a named source exists, invent a source mapping, or claim it
searched one source when the tool resolved another. Immediate follow-ups may
reuse the nearest preceding user health question; unrelated older turns must
not be folded in.

## 11. Acceptance Criteria

```gherkin
Given a user asks "基于皮皮妈妈的一家之言的知识库作答" after a health question
When the first model round returns prose without a tool call
Then the backend executes one knowledge_search call with the recovered health question and named source

Given a user corrects "益家知研 这个在我知识库中"
When the preceding turn was a named-source discussion
Then the backend resolves the alias without losing the preceding health question

Given the resolved source is the legacy unreviewed supplement asset
When knowledge_search executes
Then it does not call raw or reviewed retrieval as a substitute and returns an explicit not-released boundary

Given no source is specified
When knowledge_search executes
Then existing reviewed System KB behavior is unchanged
```

## 12. Verification Plan

```bash
cd backend && venv/bin/pytest -q tests/test_knowledge_search_merge.py tests/test_agent_executor_status_events.py --no-cov
python3 scripts/harness_llm_change_gate.py
python3.12 scripts/check_doc_drift.py
python3.12 backend/scripts/check_dossier_consistency.py
git diff --check
```

## 13. Rollout And Rollback

Backend-only release through `deploy.sh -b`; no migration. Rollback is a code
revision rollback. Production validation replays the three-turn interaction
with no personal identifiers and checks the tool/source receipt.

## 14. Open Questions

- A future reviewed import may map the legacy label to released claims. That is
  a separate medical-content review and is not required for this incident fix.

## 15. Changelog

| Date | Change | Reason |
|---|---|---|
| 2026-08-29 | Initial accepted bugfix spec | Production named-KB retrieval incident. |
