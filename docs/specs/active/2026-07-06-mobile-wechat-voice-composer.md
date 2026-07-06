# Feature Spec: Mobile WeChat-Style Voice Composer

> Status: implementing
> Owner: Codex
> Updated: 2026-07-06
> Related PRD/PDD: docs/specs/reva-product-governance-spec.md
> Related code: mobile/components/chat/ChatInputBar.tsx, mobile/hooks/useVoiceRecording.ts, mobile/hooks/useRealtimeDictation.ts

## 1. Decision

Change the Mobile chat composer to a WeChat-style voice-first input bar with a left hold-to-talk entry, a microphone inside the text field, and realtime dictation into the text input.

## 2. Problem

The current Mobile chat composer hides voice input behind long-pressing the empty text field. That keeps the surface compact, but it is not discoverable enough for high-frequency health capture. The user explicitly wants the input box to match the WeChat mental model: a visible left voice icon, a text field, and a right-side microphone control inside the field.

## 3. Requirement Admission

```yaml
RequirementAdmission:
  request: "Mobile input box mirrors WeChat voice/text composer with left speaker, right mic, slide voice gesture, and realtime speech-to-text."
  classification: product_change
  first_user_fit: high-intensity mobile user needing low-friction daily capture and chat input
  core_loop_step: Mobile Capture -> user text/voice intent -> existing chat routing and safety gates
  first_class_objects: [ExecutionEvent]
  target_surface: Mobile chat composer
  source_of_truth: mobile/components/chat/ChatInputBar.tsx
  safety_level: privacy_sensitive
  prescription_or_causal_verdict: none
  autonomy_tier: none
  evidence_provenance: user-triggered microphone input only
  claim_hedging: n/a
  verification_window: immediate UI interaction and focused tests
  success_metric: user can start voice input from a visible left icon or realtime dictation from the right mic, then submit typed/transcribed text with Enter
  added_user_burden: low
  burden_justification: makes voice input more visible while preserving text input and attachment menu
  non_goals: no new health-write path, no automatic medical action, no Rokid or voice-chat page change, no native dependency change
  smallest_end_to_end_slice: ChatInputBar UI + realtime dictation hook + focused Jest tests
  stale_surface_to_remove_or_archive: previous empty-field long-press is superseded by the visible left voice button
  spec_required: yes
```

## 4. Non-Goals

- Do not send raw audio messages.
- Do not bypass existing chat or health-record safety behavior.
- Do not change `voice-chat` continuous assistant conversations.
- Do not add native modules or modify iOS permissions.
- Do not remove the attachment menu.

## 5. Product Object Mapping

| Object | Change |
|---|---|
| `ExecutionEvent` | User-triggered voice input becomes a clearer capture event before existing chat submission. |

## 6. User Flow

```text
open Mobile chat
  -> tap/hold the left speaker icon for voice input
  -> slide left to cancel or slide right to keep transcript as editable text
  -> or tap the microphone inside the text field for realtime dictation
  -> transcribed text appears in the composer
  -> press Enter to submit through the existing chat pipeline
```

## 7. Surface Contract

| Surface | Responsibility | Contract |
|---|---|---|
| Mobile | Owns visible composer controls and dictation state. | Left icon starts hold-to-talk; right mic toggles realtime dictation; Enter submits current text. |
| Backend | Keeps existing chat and safety behavior. | No API contract change. Existing `/chat/transcribe` remains used for hold-to-talk file transcription. |

## 8. Data Contract

```yaml
apis: no new API
events: no new persisted event in this slice
models: no change
fields: no change
enums: no change
backward_compatibility: existing typed text, attachment, image, and Enter submit behavior must keep working
migration: none
```

## 9. Safety, Privacy, And Medical Boundary

This feature handles microphone input, so it is privacy-sensitive. Microphone activation must be explicit and visible, must stop on cleanup, and must release the audio session after stop or error. The composer only produces user text; existing backend safety gates still decide whether any health write or advice is allowed.

## 10. AI Behavior

No new LLM behavior is introduced. Realtime dictation only fills the text input. Submitted text continues through the existing chat route and safety behavior.

## 11. Acceptance Criteria

```gherkin
Given the Mobile chat composer is empty
When it renders
Then the left speaker voice button is visible
And the text field contains a microphone button on the right

Given the user taps the right microphone
When speech recognition returns partial text
Then the composer input updates with that text in realtime

Given the composer has dictated text
When Enter is pressed
Then the existing onSend callback receives the dictated text

Given the user holds the left voice button
When they slide left
Then recording is cancelled

Given the user holds the left voice button
When they slide right and release
Then recording is transcribed into editable text rather than auto-sent
```

## 12. Verification Plan

```bash
cd mobile && npm test -- --runInBand --runTestsByPath components/chat/__tests__/ChatInputBar.test.tsx hooks/__tests__/useRealtimeDictation.test.ts hooks/__tests__/useVoiceRecording.test.ts
git diff --check
```

## 13. Rollout And Rollback

This is a pure Mobile JS/TS/UI change and can ship by commit plus Mobile OTA after focused verification. Rollback is reverting the composer and hook changes; no backend or schema rollback is needed.

## 14. Open Questions

- Whether raw audio-message sending is ever needed remains out of scope for this slice.
- Whether to log a client event for microphone activation can be decided in a later observability slice.

## 15. Changelog

| Date | Change | Reason |
|---|---|---|
| 2026-07-06 | Initial spec | Admit WeChat-style Mobile voice composer as a narrow Mobile Capture improvement. |
