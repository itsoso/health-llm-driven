# Feature Spec: Mobile WeChat-Style Voice Composer

> Status: implementing
> Owner: Codex
> Updated: 2026-07-18
> Related PRD/PDD: docs/specs/reva-product-governance-spec.md
> Related code: mobile/components/chat/ChatInputBar.tsx, mobile/hooks/useRealtimeDictation.ts, mobile/hooks/useVoiceRecording.ts, mobile/services/cloudRealtimeAsr.ts, mobile/modules/reva-pcm-stream, backend/app/services/realtime_speech_transcription.py

## 1. Decision

Change the Mobile chat composer to a WeChat-style voice-first input bar. The default iOS path uses Speech.framework through the existing native voice module so short hold-to-talk phrases get local partial and final results without a network round-trip. The authenticated PCM/WebSocket Qwen path remains available as a bounded fallback/experiment and must not silently replace the local path without an ASR quality comparison.

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
  non_goals: no new health-write path, no automatic medical action, no Rokid or voice-chat page change
  smallest_end_to_end_slice: ChatInputBar UI + PCM capture module + authenticated realtime ASR proxy + focused tests
  stale_surface_to_remove_or_archive: previous empty-field long-press is superseded by the visible left voice button
  spec_required: yes
```

## 4. Non-Goals

- Do not send raw audio messages.
- Do not bypass existing chat or health-record safety behavior.
- Do not change `voice-chat` continuous assistant conversations.
- The default composer path may use the existing iPhone Speech.framework integration. Keep provider credentials on the backend for the cloud fallback, and do not make the mobile client depend on a DashScope key.
- Do not remove the attachment menu.

## 5. Product Object Mapping

| Object | Change |
|---|---|
| `ExecutionEvent` | User-triggered voice input becomes a clearer capture event before existing chat submission. |

## 6. User Flow

```text
open Mobile chat in default voice mode
  -> hold the center voice surface for voice input
  -> iOS first uses native realtime recognition; the authenticated mono 16 kHz PCM path is a bounded cloud fallback
  -> partial transcript wraps inside the recording panel while the user speaks
  -> slide left to cancel or slide right to keep transcript as editable text
  -> tap the icon-only keyboard switch to enter text mode
  -> optionally tap the microphone inside the text field for realtime dictation
  -> transcribed text appears in the composer
  -> press Enter to submit through the existing chat pipeline
```

## 7. Surface Contract

| Surface | Responsibility | Contract |
|---|---|---|
| Mobile | Owns visible composer controls, native realtime recognition, gestures and transcript presentation. | Default is hold-to-talk. The left icon switches to text input; right mic toggles native realtime dictation; Enter submits current text. |
| Backend | Authenticates the cloud fallback, holds provider credentials and proxies bounded audio. | `/chat/transcribe/realtime` accepts transient base64 PCM chunks over WebSocket and emits partial/final text; `/chat/transcribe` remains the file-based fallback. |
| DashScope | Performs cloud fallback speech recognition. | Qwen realtime ASR consumes mono 16 kHz PCM in manual commit mode when the native path is unavailable or explicitly enabled for comparison. |

## 8. Data Contract

```yaml
apis: authenticated WebSocket /chat/transcribe/realtime
events: no new persisted event in this slice
models: no change
fields: no change
enums: no change
backward_compatibility: existing typed text, attachment, image, and Enter submit behavior must keep working
migration: none
```

## 9. Safety, Privacy, And Medical Boundary

This feature handles microphone input, so it is privacy-sensitive. Microphone activation must be explicit and visible, must stop on cleanup, and must release the audio session after stop or error. Raw PCM stays in memory only for the active session, is size/time bounded, is never logged or persisted, and is cleared on finish/cancel/error. Provider credentials remain on the backend. The composer only produces user text; existing backend safety gates still decide whether any health write or advice is allowed.

## 10. AI Behavior

No new LLM behavior is introduced. Realtime dictation only fills the text input. Submitted text continues through the existing chat route and safety behavior.

## 11. Acceptance Criteria

```gherkin
Given the Mobile chat composer is empty
When it renders
Then hold-to-talk is the default mode
And the left control is a compact icon-only keyboard switch

Given the user holds the voice surface
When native speech recognition returns partial text
Then the transcript updates while speaking
And long text wraps without resizing or obscuring the controls

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
cd mobile && npm test -- --runInBand --runTestsByPath components/chat/__tests__/ChatInputBar.test.tsx hooks/__tests__/useRealtimeDictation.test.ts services/__tests__/cloudRealtimeAsr.test.ts modules/reva-pcm-stream/__tests__/revaPcmStreamIosSource.test.ts
cd backend && pytest -q tests/test_realtime_speech_transcription.py
cd mobile/ios && pod install
# Build the iOS simulator target to compile the local PCM module.
git diff --check
```

## 13. Rollout And Rollback

The backend WebSocket proxy must deploy before the cloud fallback is enabled. The native composer path is JavaScript-controlled and can be repaired by OTA; the PCM capture module still requires a new signed iOS build when it changes. Rollback switches the composer back to native-only and leaves no schema rollback requirement.

## 14. Open Questions

- Whether raw audio-message sending is ever needed remains out of scope for this slice.
- Whether to log a client event for microphone activation can be decided in a later observability slice.

## 15. Changelog

| Date | Change | Reason |
|---|---|---|
| 2026-07-06 | Initial spec | Admit WeChat-style Mobile voice composer as a narrow Mobile Capture improvement. |
| 2026-07-14 | Add bounded server-side ASR routing | Keep both voice entry paths available on DashScope while making any cross-provider fallback explicit and time-bounded. |
| 2026-07-16 | Make voice the default and use Qwen realtime ASR | Historical cloud-primary experiment; later quality review restored native-primary routing for short composer utterances. |
| 2026-07-18 | Restore native-primary composer ASR | Short utterances regain low-latency local partial/final results; cloud PCM/WebSocket remains a bounded fallback and comparison path. |
