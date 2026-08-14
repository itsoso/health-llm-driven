# Feature Spec: Mobile Agent Reliability Kernel

> Status: approved
> Owner: Codex
> Updated: 2026-07-09
> Related PRD/PDD: `docs/prd/2026-07-09-mobile-agent-reliability-kernel.md`
> Related code: `mobile/hooks/useChatEngine.ts`, `mobile/components/chat/ChatInputBar.tsx`, `mobile/services/chatCardActions.ts`, `backend/app/services/agent_executor.py`
>
> **Current release override (2026-08-12):** all repo-contained automatic remote/vendor release
> entrypoints, local signing/install/automatic-provisioning entrypoints and every OTA/rollback
> channel are frozen. EAS channel→branch mapping can drift or be shared, so preview/development is not an
> isolated exception. Production network observation and release plan/validate are also frozen.
> Current delivery stops at local validation, offline evidence and public unauthenticated HTTPS;
> none forms G5/G6. Manual Gate is
> BLOCK pending a new repo-external trust-root dossier and independent G4.

## 1. Decision

Introduce explicit Mobile `AgentTurn`, `WriteReceipt`, and `ComposerState` contracts, then make Chat rendering and lifecycle behavior derive from those contracts instead of independent booleans and natural-language success claims.

## 2. Problem

Mobile Chat already supports streaming, cards, two voice paths, attachments, history and write confirmation. The features are individually capable but do not share one lifecycle. Background transitions, duplicate taps, missing resource IDs and audio-session races can therefore produce states that look complete without a durable fact or leave the UI active after the operation ended.

## 3. Requirement Admission

```yaml
RequirementAdmission:
  request: "形成详细的规划，按照规划和优先级，逐个做完"
  classification: product_change
  first_user_fit: high-intensity Mobile user using voice/photo capture and daily Agent execution
  core_loop_step: Capture -> Agent/tool -> WriteIntent or ExecutionEvent -> Today/Review
  first_class_objects: [ExecutionEvent, WriteIntent, HealthAgendaItem]
  target_surface: Mobile Chat, additive backend stream contract
  source_of_truth: backend domain record or WriteIntent.executed_ref; message history for turn presentation
  safety_level: privacy_sensitive
  prescription_or_causal_verdict: none
  autonomy_tier: manual_confirm
  evidence_provenance: deterministic API/tool result only
  claim_hedging: n/a
  verification_window: immediate operation completion plus next screen/history reload
  success_metric: all confirmed writes have a verified receipt and all input/turn states recover deterministically
  added_user_burden: lower
  burden_justification: removes repeated confirmation and manual checking
  non_goals: no autonomous clinical write, no new diagnosis, no background microphone, no new database model
  smallest_end_to_end_slice: one Agent turn with recoverable lifecycle and a verified diet/card receipt
  stale_surface_to_remove_or_archive: fixed four-action reply grid and duplicated boolean state
  spec_required: yes
```

## 4. Non-Goals

- No new health domain endpoint.
- No arbitrary endpoint or card execution.
- No raw audio-message storage.
- No object-storage vendor migration.
- No Mac, Web or Watch UI change in the first release.

## 5. Product Object Mapping

| Object | Change |
|---|---|
| `ExecutionEvent` | Mobile surfaces execution progress and terminal outcome consistently. |
| `WriteIntent` | Confirmation result exposes `executed_ref` as a verified receipt. |
| `HealthAgendaItem` | Completion action returns a resource/operation reference and remains idempotent. |

## 6. User Flow

```text
explicit user input
  -> ComposerState validates one active input mode
  -> AgentTurn starts and is snapshotted locally
  -> backend emits deterministic progress
  -> write action remains manual-confirm
  -> backend/API returns resource identity
  -> WriteReceipt marks verified success
  -> caches/history refresh
  -> terminal turn survives navigation or foreground recovery
```

## 7. Surface Contract

| Surface | Responsibility | Contract |
|---|---|---|
| Mobile | Own input, local turn lifecycle, draft recovery and receipt presentation. | No success without verified receipt for write actions. |
| Backend | Own domain facts, write safety, tool execution and message history. | Additive `tool_result.data.receipt`; existing clients may ignore it. |

## 8. Data Contract

```yaml
events:
  AgentTurnEvent: submit | accepted | status | tool_started | tool_finished | done | fail | interrupt | recover
models:
  AgentTurnState:
    phase: idle | submitted | running | writing | verifying | completed | failed | interrupted
    turn_id: client-generated stable string
    conversation_id: optional integer
    message_id: optional integer
    started_at: epoch milliseconds
    updated_at: epoch milliseconds
    label: optional user-facing text
    error_code: optional stable code
    recoverable: boolean
  WriteReceipt:
    operation_id: stable action/tool identifier
    status: verified | failed | dismissed | opened
    resource_type: optional string
    resource_id: optional string
    executed_ref: optional string
    completed_at: ISO timestamp
    verified: boolean
  ComposerState:
    mode: text | hold
    phase: idle | hold_starting | hold_recording | hold_transcribing | live_dictating | submitting | error
    dictation_enabled: boolean
    gesture: send | text | cancel | null
apis:
  POST /agent/stream: additive tool_result.data.receipt only
backward_compatibility:
  old clients ignore receipt; old history without receipt renders existing content
migration: none
```

Receipt verification rules:

- `diet_record.create`: verified only when response has a numeric record ID.
- `write_intent.confirm`: verified only when response status is terminal and `executed_ref` is present.
- `agenda.complete`: verified when the API returns an execution/domain reference; otherwise it remains unverified and the client does not show durable success.
- `route.open` and inline UI patches are not writes; they use `opened`/local completion without a resource receipt.
- Agent `health_record` receipt comes from parsed tool API output, never from assistant prose.

## 9. Safety, Privacy, And Medical Boundary

- Write actions remain manual-confirm and user-scoped through existing authenticated APIs.
- Medication/supplement writes keep existing confirmation and safety behavior.
- A receipt proves persistence, not clinical correctness or a causal health result.
- Audio activation is explicit and stops on background, submit, error and unmount.
- Draft images stay in the App private directory; logs contain only counts/state, never base64 or health content.

## 10. AI Behavior

- LLM may select allowlisted tools and explain results.
- LLM text cannot create a receipt or override failed/unverified state.
- If a record intent executes no write tool, the existing fail-closed response remains authoritative.
- If a tool returns no verifiable resource identity, UI says the operation could not be verified and offers retry/edit.

## 11. Acceptance Criteria

```gherkin
Given a user submits a message
When SSE status and done events arrive
Then AgentTurn reaches completed with the authoritative conversation and message IDs

Given the App backgrounds during a running turn
When it becomes active again
Then the client restores from server history without replacing a newer local stream with partial history

Given a write action returns no resource ID or executed_ref
When the dispatcher handles the response
Then it throws a stable missing-receipt error and the card remains retryable

Given realtime dictation is active
When the user submits, changes to hold mode, or backgrounds the App
Then dictation stops and the audio session is released

Given an unsent text/image draft exists
When Chat remounts
Then the draft is restored from private local storage

Given an Agent reply has a server card or completed health_record tool
When it renders
Then no generic Generate Record action is shown
```

## 12. Verification Plan

```bash
cd mobile && npm test -- --runInBand --runTestsByPath \
  utils/__tests__/agentTurnState.test.ts \
  components/chat/__tests__/ChatInputBar.test.tsx \
  hooks/__tests__/useRealtimeDictation.test.ts \
  hooks/__tests__/useVoiceRecording.test.ts \
  hooks/__tests__/useChatEngine.test.ts \
  services/__tests__/chatCardActions.test.ts \
  components/chat/__tests__/ChatBubbleStructuredSummary.test.tsx

cd mobile && npx tsc --noEmit --pretty false

backend/.venv/bin/python -m pytest backend/tests/test_agent_executor_fast_routing.py -q

python3 scripts/check_doc_drift.py
git diff --check
```

Simulator matrix: text send, hold send, hold-to-text, cancel, realtime start/stop, submit stops mic, background stops mic, image draft restore, stream background/resume, verified and failed card writes.

## 13. Rollout And Rollback

- Validate the additive backend receipt and Mobile JS/TS locally through G3/G4 and iOS Simulator;
  `npm run ios` uses the Simulator wrapper, callers may not append npm/Expo `--device`, and the
  wrapper pins an exact available Simulator UDID. Do not connect/install physical iOS, deploy either
  surface or build/sign a binary.
- All OTA/rollback channels and production native writers remain frozen. The manual release Gate is
  BLOCK regardless of existing candidate visibility; no production rollback writer is active.
- Existing WeChat composer spec remains active; this spec replaces only its internal state ownership.

## 14. Open Questions

- Moving chat image storage from server disk to OSS is a separate infrastructure feature.
- Cross-device turn resumption is out of scope; this release restores within Mobile from server history.

## 15. Changelog

| Date | Change | Reason |
|---|---|---|
| 2026-07-09 | Initial approved spec | Consolidate reliability work into one testable contract. |
