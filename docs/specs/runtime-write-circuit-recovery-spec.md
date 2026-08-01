# Feature Spec: Runtime Write Circuit Recovery

> Status: approved
> Owner: Codex
> Updated: 2026-08-01
> Related PRD/PDD: `docs/plans/2026-08-01-runtime-write-circuit-recovery-design.md`
> Related code: `backend/app/services/agent_runtime_rollout.py`, `backend/app/services/agent_executor.py`, `backend/app/services/agent_kernel/goal_spec.py`

## 1. Decision

Restore reliable natural-language health writes by terminalizing pre-dispatch Runtime blocks,
scoping a single reconciliation to its affected user, and compiling diet records without an
explicit meal label through the existing local-time inference rule.

## 2. Problem

All managed users currently lose write capability when one Runtime write requires
reconciliation. During that pause, the Agent keeps asking models to reinterpret a typed
control failure and produces an incorrect generic reply. The UI reports the attempted tool
as “调用 Skill”. A common diet phrase without an explicit meal label also misses the bounded
simple-record goal.

If unchanged, one unresolved operation can cause an indefinite global write outage and make
users distrust whether health data was recorded.

## 3. Requirement Admission

```yaml
RequirementAdmission:
  request: restore ordinary health recording and fix the design that removed it globally
  classification: reliability bugfix
  first_user_fit: natural-language health capture is a primary daily action
  core_loop_step: user action -> WriteIntent -> ExecutionEvent -> verification
  first_class_objects: [WriteIntent, ExecutionEvent, HealthTwin]
  target_surface: [Backend, Mac, Mobile, Web]
  source_of_truth: Agent Runtime state plus verified write receipt
  safety_level: privacy_sensitive_write_path
  prescription_or_causal_verdict: none
  autonomy_tier: unchanged
  evidence_provenance: production content-free Runtime logs, rollout state, and prior reconciliation dossier
  claim_hedging: n/a
  verification_window: immediate terminal turn plus persisted owner-scoped lookup
  success_metric: exact anchor phrases write once with a verified receipt; one reconciliation no longer blocks unrelated users
  added_user_burden: none during normal operation
  burden_justification: n/a
  non_goals: [clinical advice changes, blind replay, production health-row mutation, new record types]
  smallest_end_to_end_slice: diet intent -> scoped Runtime admission -> one tool outcome -> receipt-backed terminal UI
  stale_surface_to_remove_or_archive: generic detail prompt after typed circuit failure
  spec_required: yes
```

## 4. Non-Goals

- Do not auto-replay or mutate the unresolved production write.
- Do not lower verified-receipt requirements or nutrition validation.
- Do not add clinical recommendations or raise autonomy.
- Do not replace the durable Runtime control plane.
- Do not introduce a scoped-circuit database migration in the active recovery slice.

## 5. Product Object Mapping

| Object | Change |
|---|---|
| `WriteIntent` | Common diet wording compiles to one bounded create intent. |
| `ExecutionEvent` | Pre-dispatch circuit rejection becomes an explicit terminal event. |
| `HealthTwin` | Changes only after a verified receipt; blocked turns make no mutation. |

## 6. User Flow

```text
record request
  -> deterministic goal and meal inference
  -> scoped Runtime admission
  -> write tool gateway
  -> verified receipt OR deterministic terminal block
  -> truthful cross-surface presentation
  -> immediate owner-scoped verification
```

## 7. Surface Contract

| Surface | Responsibility | Contract |
|---|---|---|
| Mobile | Render terminal text and execution transparency | Failed completion labels tools as attempted; no unsafe retry. |
| Mac | Render terminal text and execution transparency | Failed completion labels tools as attempted. |
| Web | Render terminal text and execution transparency | Failed completion labels tools as attempted. |
| Backend | Own intent, admission, dispatch, receipt, and terminal truth | Never ask the model to reinterpret a Runtime control block. |
| External agents | Continue through the shared Runtime facade | Same scoped admission and receipt rules. |

## 8. Data Contract

```yaml
apis: no route changes
events:
  done.turn_outcome:
    new_category: service_unavailable
    reason_code: runtime_control_unavailable
models: no schema changes
fields: no health payload added to telemetry
enums:
  runtime_terminal_category: additive service_unavailable
backward_compatibility: tools_used and existing SSE fields remain; old clients render terminal text
migration: none
```

Internal configuration adds a bounded reconciliation threshold; setting it to `1` restores
the previous global fail-closed behavior.

## 9. Safety, Privacy, And Medical Boundary

- The change touches health writes but not medical advice.
- Owner isolation remains enforced by the existing Runtime and record queries.
- Admission scope queries only the durable generation/ack counters plus content-free
  reconciliation event and owner metadata, not health values or tool arguments.
- Acknowledged historical owners and already resolved Runs do not count toward a later
  incident; an incomplete event ledger cannot prove scope and remains globally fail-closed.
- Uncertain writes remain non-retryable and require reconciliation.
- Runtime-control failure is pre-dispatch and must state that no write was sent.
- Existing audit and rollout event records remain authoritative.

## 10. AI Behavior

- The LLM may estimate bounded nutrition for an explicit food phrase.
- Deterministic code owns meal inference, control-state interpretation, dispatch facts, and
  success claims.
- The LLM must not convert `runtime_control_unavailable` into missing user details, a health
  disclaimer, or a success claim.
- Failure degrades to deterministic terminal copy after one attempted write.

## 11. Acceptance Criteria

```gherkin
Given local time is 21:05 and the user says “记录吃了一个桃子”
When the goal is compiled
Then it is one diet create for snack with food_items “一个桃子”

Given a write is blocked by a paused Runtime before dispatch
When the Agent receives runtime_control_unavailable
Then it stops after that tool result and emits completion_status error with service_unavailable

Given one user owns one currently unacknowledged reconciliation and the systemic threshold is not reached
When an unrelated user starts a write turn
Then that user receives a managed Runtime run and can reach the normal receipt path

Given older reconciliation owners were acknowledged before the current incident
When admission derives the current reconciliation scope
Then those historical owners are excluded from the systemic threshold

Given a reconciliation event is current but its Run has already been resolved
When admission derives the current reconciliation scope
Then that Run owner is excluded from isolation and the systemic threshold

Given the reconciliation event ledger disagrees with the durable generation
When any user starts a write turn
Then the circuit remains globally fail-closed

Given the reconciliation threshold is reached or the circuit pause is manual/systemic
When any managed user starts a write turn
Then the global fail-closed block remains

Given a failed turn attempted health_record without a receipt or confirmation
When dynamic cards and transparency are rendered
Then no verified-write suppression is inferred and the Skill is labeled as attempted
```

## 12. Verification Plan

```bash
cd backend
PYTHONDONTWRITEBYTECODE=1 ../backend/venv/bin/python -m pytest -q --no-cov -p no:cacheprovider \
  tests/test_agent_goal_spec.py \
  tests/test_agent_runtime_rollout.py \
  tests/test_agent_runtime_concurrency.py \
  tests/test_agent_executor_completion_status.py \
  tests/test_agent_turn_outcome.py \
  tests/test_agent_conversations_api.py

cd ../mobile && npm test -- --runInBand components/chat/__tests__/ChatBubbleToolsUsed.test.tsx utils/__tests__/chatTransparency.test.ts
cd ../frontend && npm test -- --run src/components/assistant/chatTransparency.test.ts
cd ../apps/mac && swift test
cd ../.. && git diff --check && python3 scripts/check_doc_drift.py
```

Exact commands may be narrowed while driving individual red/green tests, but the integrated
Gate may not pipe test output through `tail`.

## 13. Rollout And Rollback

- Acknowledge only the exact reviewed reconciliation generation; never replay the uncertain
  write.
- Deploy backend before any client release.
- Use existing backend deploy health scoring and production smoke checks.
- Use Mobile OTA only if Mobile code changes; use the Mac release route only if a packaged
  client update is required.
- Roll back backend code to the recorded pre-deploy SHA on Gate failure.
- Set reconciliation threshold to `1` for immediate policy rollback.

## 14. Open Questions

None blocking the approved slice. A normalized scoped-circuit table remains a future option
only if admission-time scoping proves operationally insufficient.

## 15. Changelog

| Date | Change | Reason |
|---|---|---|
| 2026-08-01 | Initial approved spec | Production global write outage and exact diet-record failures |
