# Feature Spec: Health Record Write Outcome Reliability

> Status: approved
> Owner: Codex
> Updated: 2026-07-31
> Related code: `backend/app/services/agent_executor.py`, `backend/app/services/agent_kernel/goal_spec.py`, `mobile/services/chat.ts`, `mobile/utils/agentTurnState.ts`
>
> **Current release override (2026-08-12):** no backend/frontend production deploy and no OTA
> channel write is authorized. EAS channel→branch mapping may drift or be shared, so preview and
> development are frozen too. Use only local tests/Metro/iOS Simulator and read-only proof;
> `npm run ios` uses the Simulator wrapper, callers may not append npm/Expo `--device`, and the
> wrapper pins an exact available Simulator UDID; physical iOS repo CLI is frozen;
> archive/export/signing/provisioning is frozen. The release
> Gate is BLOCK/STOP pending a new dossier, repo-external root-owned launcher, canonical
> repo-external tree, recovery proof and new independent G4.

## 1. Decision

Make the backend authoritative for health-write outcomes and retry safety, preserve the user's target date through persistence, and prevent Mobile from offering a blind retry after a write may have been dispatched.

## 2. Problem

Mobile currently renders several distinct write outcomes as “记录信息暂时不可用”. A write-tool intermediate event can also make the client terminal before the backend's durable `done` event arrives. This hides actionable validation errors and can expose a retry button after a write may already have committed.

The production incident at 2026-08-01 09:57 +08:00 is the anchor case: user 52 requested a 1200 ml record for the previous day, water row `#705` committed to the current day, the date conflict invalidated the receipt, and the runtime operation ended as `reconciliation_required / missing_receipt`.

## 3. Requirement Admission

```yaml
RequirementAdmission:
  request: eliminate recurring generic record-unavailable failures and unsafe retries
  classification: bugfix
  first_user_fit: manual health capture is part of the primary Mobile daily flow
  core_loop_step: Mobile execution -> ExecutionEvent -> HealthTwin
  first_class_objects: [ExecutionEvent, WriteIntent, HealthTwin]
  target_surface: [Backend, Mobile]
  source_of_truth: Backend Agent Runtime and verified write receipt
  safety_level: privacy_sensitive
  prescription_or_causal_verdict: none
  autonomy_tier: unchanged
  evidence_provenance: production runtime ledger plus persisted water row
  claim_hedging: n/a
  verification_window: immediate turn completion and persisted record lookup
  success_metric: no blind retry for uncertain writes; target date equals persisted date; specific outcome labels replace generic unavailable
  added_user_burden: none
  burden_justification: n/a
  non_goals: [new record types, new medical advice, autonomy elevation, database schema migration]
  smallest_end_to_end_slice: historical water record plus typed SSE outcome plus Mobile terminal handling
  stale_surface_to_remove_or_archive: generic write-failure interpretation in Mobile
  spec_required: yes
```

## 4. Non-Goals

- Do not change medication, dose, diagnosis, or clinical advice behavior.
- Do not add a new database table or migrate every record adapter in this slice.
- Do not auto-correct existing production health rows.
- Do not make uncertain writes retryable.
- Do not change the existing fast-record autonomy tier.

## 5. Product Object Mapping

| Object | Change |
|---|---|
| `ExecutionEvent` | A write is completed only with a verified durable receipt. |
| `WriteIntent` | Retry safety is derived from dispatch facts, not client inference. |
| `HealthTwin` | Historical water records retain the user-owned target date. |

## 6. User Flow

```text
user says “昨天…补充记录 1200 毫升”
  -> deterministic intent/goal resolves amount and target date
  -> backend persists that exact date
  -> backend classifies verified/rejected/uncertain/failed once
  -> SSE carries the typed outcome and receipt facts
  -> Mobile waits for authoritative terminal state
  -> retry is shown only when the backend supplies a safe retry-source action
```

## 7. Surface Contract

| Surface | Responsibility | Contract |
|---|---|---|
| Mobile | Present progress and terminal recovery action | Tool results are intermediate; no blind retry for unverified writes. |
| Backend | Own write classification, persistence date, and retry safety | Emit typed write facts and authoritative terminal retry metadata. |

## 8. Data Contract

```yaml
apis: no route changes
events:
  tool_result:
    additive_fields: [write_outcome, dispatch_started, resubmit_safe, error_code]
  done:
    existing_authority: [completion_status, turn_outcome, recovery_action]
models: no schema changes
fields:
  record_date: user-owned ISO date carried into water persistence and receipt
enums:
  write_outcome: [verified, rejected, failed, uncertain]
backward_compatibility: legacy success/write_completed fields remain
migration: none
```

## 9. Safety, Privacy, And Medical Boundary

- All record lookup and persistence remain owner-scoped by `user_id`.
- SSE outcome fields contain no raw health values.
- A write with `dispatch_started != false` and no verified receipt is never resubmitted automatically or through the generic retry button.
- Existing production data correction is a separate, explicitly authorized operation.

## 10. AI Behavior

- The LLM may propose a tool call, but deterministic goal parsing owns unambiguous amount/date facts.
- The LLM must not decide whether a write succeeded or whether it is safe to retry.
- Receipt and runtime facts override model prose.

## 11. Acceptance Criteria

```gherkin
Given the user says “昨天喝水很多 补充记录 1200 毫升”
When the Agent records the water intake
Then one 1200 ml row is persisted on yesterday's date and a verified receipt is emitted

Given a local validation rejection before dispatch
When Mobile receives the tool result
Then it shows a specific non-terminal state and waits for the backend terminal outcome

Given a write completed without a verified receipt
When Mobile receives tool_result and done
Then the turn is non-retryable and no generic Retry button is shown

Given the backend exposes an active retry_source_turn action
When the user taps Retry
Then Mobile sends the retry confirmation path instead of resubmitting the original write as a new turn

Given the backend accepted a turn but the Mobile stream was interrupted
When the client is waiting for history reconciliation
Then the turn remains recoverable in storage but no user resubmit action is exposed
```

## 12. Verification Plan

```bash
cd backend && PYTHONDONTWRITEBYTECODE=1 venv/bin/python -m pytest -q --no-cov -p no:cacheprovider tests/test_agent_goal_spec.py tests/test_health_record_amount_regression.py tests/test_agent_stream_no_false_record_claim.py tests/test_agent_executor_completion_status.py tests/test_agent_turn_outcome.py
cd mobile && npm test -- --runInBand services/__tests__/chatStream.test.ts utils/__tests__/agentTurnState.test.ts hooks/__tests__/useChatEngine.test.ts app/'(tabs)'/__tests__/chat.test.tsx
git diff --check
```

## 13. Rollout And Rollback

- Validate backend compatibility and Mobile JS/TS locally; do not deploy either surface.
- All OTA/rollback channels and all server/production native writers are frozen. Record the manual
  release Gate as BLOCK; an existing candidate is read-only and cannot authorize selection/distribution.
- Local regressions return to implementation. There is no current production rollout or rollback action.

## 14. Open Questions

- Production row `#705` remains unchanged until an explicit data-correction approval is recorded.

## 15. Changelog

| Date | Change | Reason |
|---|---|---|
| 2026-07-31 | Initial approved spec | Production incident and recurring generic Mobile failure state |
