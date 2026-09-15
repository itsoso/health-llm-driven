# Feature Spec: 日常情境告知与回复恢复

> Status: implementing
> Owner: Reva backend / mobile
> Updated: 2026-09-15
> Related PRD: ../reva-product-governance-spec.md
> Related code: agent_executor.py, utterance_intent_classifier.py, useChatEngine.ts

## 1. Decision / Problem

恢复 Chat 主壳的基础理解：明确、纯粹的抵达/差旅入住告知应收到与原话绑定的简短确认，而不是加载全健康档案后被医疗建议校验整段撤回。连接恢复应与业务失败分开呈现。

## 2. Requirement Admission

```yaml
RequirementAdmission:
  request: 修复普通告知被医疗化与恢复状态干扰
  classification: bugfix
  first_user_fit: 高频差旅用户低负担更新执行环境
  core_loop_step: 情境输入与执行反馈
  first_class_objects: [ExecutionEvent, SafetyGuardian, WriteIntent]
  target_surface: backend shared Chat and Mobile
  source_of_truth: authenticated conversation and existing run lifecycle
  safety_level: medical_boundary
  prescription_or_causal_verdict: none
  autonomy_tier: none
  evidence_provenance: current user statement only
  claim_hedging: n/a
  verification_window: same turn and next turn
  success_metric: admitted statements have zero model/tool calls; preserved safety; accurate terminal state
  added_user_burden: none
  burden_justification: n/a
  non_goals: automatic location/health writes, medical gate relaxation, universal language classifier replacement
  smallest_end_to_end_slice: typed context statement -> durable acknowledgement -> terminal/replay
  stale_surface_to_remove_or_archive: red business-error treatment of transport recovery
  spec_required: yes
```

## 3. Contract and User Flow

Current unquoted first-person/present arrival with an exact city from the existing static weather catalog -> shared bounded semantic parser -> existing intent frame (`chat`, no write) -> deterministic acknowledgement persisted in the owned conversation -> ordinary request_persisted/token/done events. This admitted city path makes no model call, health context retrieval, tool dispatch, background extraction, or implicit profile update. The original message remains in ordinary history for subsequent explicit requests; no promise of perpetual memory is made.

Free-text hotel names are only `context_statement_candidate` hints, not trusted entities. They always retain the normal model/tool/safety pipeline. The common prompt now limits proactive analysis to the actual current task: neutral lodging updates get a brief acknowledgement, while symptoms, explicit actions and unresolved follow-ups keep their obligations. The prompt change is not an exemption from final medical validation.

One immutable parsed object supplies intent and deterministic eligibility. Unknown cities/compound grammar stay on the existing path. Recent user history uses positive admission (exact admitted cities or whole simple meal/water record phrases), not absence of symptom keywords; unrecognized history and assistant follow-up requests prevent the shortcut. The bounded history query examines the existing latest-eight-message window, not a claim that all historical clinical issues are resolved. Explicit writes and questions retain their existing authorization and task handlers. Attachments and structured entry context retain their full path.

Backend owns parsing, persistence and terminal truth for all streaming clients. Mobile only projects status and reconciles accepted turns against the server. A lost connection is neither successful work nor a failed write; no resubmission is allowed without existing server retry authorization.

## 4. Data / Safety

No API schema, database schema, native dependency or permission changes. Existing conversation metadata may carry an internal route/reason, not raw health payloads. No city registry lookup, geolocation request, permanent address, HealthEpisode, MemoryFact or health record is created by a plain acknowledgement. Authentication, conversation ownership, client-turn deduplication and failure propagation remain authoritative. Final medical checks on model replies remain unchanged; no exemption derived from a model-authored sentence.

## 5. Acceptance / Verification

- Admitted city phrases after a simple meal record: relevant acknowledgement, no medical disclaimer/citations, no model/health reads or writes, completed terminal. Free-text lodging remains model-validated, with current-task scope enforced in the prompt.
- Duplicate client_turn_id and owned history reload: same answer, no duplicate messages; foreign conversation remains denied.
- Negation, quotation, future/hypothetical travel, additional symptoms/advice/write/read clauses, attachments, structured continuation and recent medical context do not enter the shortcut.
- Explicit event recording, diet correction, sleep+Garmin reads and unsafe medical generation retain existing behavior.
- Mobile accepted stream loss uses neutral recovery, later authoritative terminal clears the notice, stale old-turn responses cannot replace a new conversation.
- Run focused unit/stream/PostgreSQL tests, existing guidance and policy regressions, mobile Jest and TypeScript, LLM change gate and required live gate, fixed-diff safety review, git diff --check.

## 6. Rollout / Rollback / Non-Goals

Backend and mobile changes can ship independently after their gates. No deployment claimed by local tests. Revert owned code changes for rollback; no migration required. Broad free-form task planning, universal claim-level rendering and end-to-end server recovery redesign remain separate work; this slice fixes the observed confirmed mechanisms without weakening their boundaries.

## 7. Changelog

| Date | Change | Reason |
| --- | --- | --- |
| 2026-09-15 | Accepted bounded context and recovery repair | User screenshot and source-bound reproduction |
