# Feature Spec: Agent Busy And Diet Correction Recovery

> Status: approved
> Owner: Reva / Personal Health OS
> Updated: 2026-08-02
> Related PRD/PDD: docs/specs/active/2026-07-17-xiaoba-agent-kernel.md · docs/specs/active/2026-07-25-agent-meal-capture-session.md
> Related code: mobile/services/chat.ts · mobile/hooks/useChatEngine.ts · backend/app/services/agent_executor.py
>
> **Current release override (2026-08-12):** all repo-contained automatic remote/vendor release
> entrypoints, local signing/install/automatic-provisioning entrypoints and every OTA/rollback
> channel are frozen; preview/development is not isolated by name because EAS channel→branch mapping may
> drift or be shared. Production network observation and release plan/validate are also frozen. Use
> local validation, offline evidence and public unauthenticated HTTPS only; none forms G5/G6.
> Release Gate is BLOCK/STOP pending
> a new repo-external trust root and independent G4.

## 1. Decision

Recover follow-up chat turns from Backend busy conflicts in Mobile and make
explicit numeric-fraction diet corrections complete deterministically without
inventing missing nutrition.

## 2. Problem

When a user sends a follow-up while the previous agent turn is still running,
the Backend returns a truthful 409 busy response. Mobile currently parses the
JSON response as an empty event stream, polls a never-admitted turn, and shows a
false network-failure alert. The user's draft appears to fail even though the
real condition is temporary serialization.

The observed follow-up also uses `1/2`, which the explicit diet-correction
parser does not recognize. A unique meal without scalable nutrition then loops
through repeated model/tool rounds before refusing the update. If unchanged,
users cannot trust either chat delivery state or diet correction outcomes.

## 3. Requirement Admission

```yaml
RequirementAdmission:
  request: Continue fixing the false send-failure and incomplete 1/2 diet correction shown in the production screenshot
  classification: reliability bugfix + deterministic health-record correction
  first_user_fit: yes - conversational diet capture is an existing daily first-user loop
  core_loop_step: Act -> WriteIntent -> ExecutionEvent -> Review
  first_class_objects:
    - WriteIntent
    - ExecutionEvent
  target_surface: Mobile chat with Backend agent runtime source of truth
  source_of_truth: backend turn admission state and owner-scoped diet record
  safety_level: health_data_write
  prescription_or_causal_verdict: none
  autonomy_tier: user-authored correction only; no autonomous health recommendation
  evidence_provenance: production HTTP logs, screenshot, and deterministic parser/tool traces
  claim_hedging: operational and write-result statements are factual; no health interpretation is added
  verification_window: immediate queue state followed by persisted record confirmation in the same turn
  success_metric: busy follow-ups are queued without a false network alert; one accepted correction produces at most one owner-scoped write or one immediate clarification
  added_user_burden: none for temporary busy state; one selection only when records are genuinely ambiguous
  burden_justification: selecting the target is required to avoid changing the wrong health record
  non_goals:
    - backend durable or cross-device turn queue
    - new nutrition inference
    - automatic meal selection when multiple records match
    - changes to medical guidance
    - Web or Mac queue redesign
  smallest_end_to_end_slice: Mobile busy response -> local FIFO retry with same turn ID -> backend numeric-fraction correction -> truthful write receipt
  stale_surface_to_remove_or_archive: generic network alert for known server-busy responses
  spec_required: yes
```

## 4. Non-Goals

- Do not add a persistent Backend queue or cross-restart Mobile outbox.
- Do not infer calories, macros, food weights or serving sizes.
- Do not update an ambiguous meal record.
- Do not change Web, Mac or Watch behavior in this slice.
- Do not change medical analysis, diagnosis or treatment behavior.

## 5. Product Object Mapping

| Object | Change |
|---|---|
| `WriteIntent` | A user-authored partial-meal correction retains one stable client turn ID across temporary busy retries. |
| `ExecutionEvent` | A successful owner-scoped diet update remains the only source for a write-success receipt. |

## 6. User Flow

```text
user submits follow-up diet correction
  -> Backend reports previous turn busy
  -> Mobile displays queued state and retries the same turn ID in FIFO order
  -> Backend admits the turn after the active turn completes
  -> deterministic parser reads the requested fraction
  -> owner-scoped meal lookup returns zero, one or multiple candidates
  -> one candidate is updated; otherwise one immediate clarification is shown
  -> persisted write result is reported to the user
```

## 7. Surface Contract

| Surface | Responsibility | Contract |
|---|---|---|
| Mobile | Primary chat delivery state | Distinguish 409 busy from network failure, queue text turns, retry one stable turn ID with bounded backoff, and expose exhaustion as retryable failure. |
| Backend | Admission and health-write truth | Serialize active turns, parse numeric fractions, scope record access by user, perform at most one unambiguous correction, and terminate unresolved corrections promptly. |

## 8. Data Contract

```yaml
apis:
  preserved:
    - POST /api/v1/agent/stream
    - GET /api/v1/agent/turns/{client_turn_id}/status
  busy_response: existing HTTP 409 detail remains backward compatible
events: no new durable event type
models: no schema change
fields:
  client_turn_id: reused unchanged across local retries
  consumed_fraction: normalized number in (0, 1]
  consumed_fraction_label: canonical user-facing fraction label
backward_compatibility: old clients continue receiving 409; old diet phrases remain supported
migration: none
```

## 9. Safety, Privacy, And Medical Boundary

This feature changes an owner-scoped diet health record. It may scale only
numeric nutrition already stored on the selected record. If those values are
missing, it records the user-stated portion against the existing food text and
does not invent nutrition. Ambiguity fails closed to clarification. Prompt,
meal text, images, credentials and tokens must not enter operational logs.

## 10. AI Behavior

The LLM may explain a completed correction or ask the deterministic
clarification supplied by the runtime. It must not select among ambiguous
records, infer missing nutrition or claim success without a successful update
tool result. Once the deterministic correction path is unresolved, the current
turn terminates rather than re-entering the model/tool loop.

## 11. Acceptance Criteria

```gherkin
Given an earlier agent turn is still active
When a user submits a text-only follow-up and the Backend returns 409 busy
Then Mobile shows that the turn is queued, retries the same client turn ID with bounded backoff, and does not show a network-failure alert

Given a queued follow-up is later admitted
When the response stream completes
Then exactly one durable turn is represented and the pending queue state clears

Given the user says a matching meal was only eaten 1/2
When exactly one owner-scoped record has nutrition values
Then each available numeric nutrition value is scaled once by 0.5

Given exactly one matching record has no nutrition values
When the same correction is processed
Then its food description is preserved with an actual-portion marker and no nutrition value is invented

Given multiple meal records match
When the correction is processed
Then no record is changed and one immediate selection clarification ends the turn
```

## 12. Verification Plan

```bash
# Backend focused correction and runtime tests
cd backend
venv/bin/python -m pytest tests/test_health_manage_date_normalize.py <focused-runtime-test> -q --no-cov
venv/bin/python -m compileall -q app/services/agent_executor.py

# Mobile transport and queue tests
cd ../mobile
npx jest --runInBand --runTestsByPath services/__tests__/chatStream.test.ts hooks/__tests__/useChatEngine.test.ts
npx tsc --noEmit

# Repository gates
cd ..
python3 backend/scripts/check_dossier_consistency.py
python3 scripts/check_system_map_drift.py
git diff --check
```

The implementation plan will replace `<focused-runtime-test>` with the exact
existing test path after the relevant harness is selected.

## 13. Rollout And Rollback

Validate Backend and Mobile locally, including the deterministic correction contract and iOS
Simulator behavior. `npm run ios` uses the Simulator wrapper; do not append npm/Expo `--device`.
The wrapper pins an exact available Simulator UDID. Do not connect/install physical iOS, deploy
Backend, build/sign a binary, or
call any OTA/rollback channel. No migration or feature flag is required. The release Gate remains
BLOCKED regardless of existing candidate
visibility; preserve the current production state and report local evidence only.

## 14. Open Questions

- A durable cross-restart outbox may be designed under the agent runtime control
  plane later; it does not block this bounded local recovery.

## 15. Changelog

| Date | Change | Reason |
|---|---|---|
| 2026-08-02 | Approved complete recovery option A | Fix the production busy-turn misclassification and finish numeric-fraction diet correction. |
