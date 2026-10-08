# Feature Spec: Realtime Voice Conversation

> Status: phase 2 locally implemented; G4 safety review passed; G5 not authorized
> Owner: Codex
> Updated: 2026-10-01
> Related PRD: docs/prd/2026-09-30-realtime-voice-conversation.md
> Related code: mobile/hooks/useVoiceConversation.ts, mobile/services/cloudRealtimeAsr.ts, mobile/services/chat.ts

## 1. Decision

Upgrade the Mobile voice conversation page from Apple one-shot recognition to the existing authenticated cloud realtime ASR path, and stream Agent output into authenticated cloud TTS with in-memory PCM playback. A finalized transcript is submitted exactly once with a stable client turn ID. Starting a new utterance while the assistant is thinking or speaking stops playback, cancels the TTS session, aborts the local Agent stream, and requests cancellation of the matching server Agent Run before opening the next microphone session.

## 2. Requirement Admission

```yaml
RequirementAdmission:
  request: "执行类似 ChatGPT 的实时语音对话改造"
  classification: product_change
  first_user_fit: mobile user who prefers hands-free health conversation
  core_loop_step: Mobile Capture -> Agent chat -> safe response or confirmed action
  first_class_objects: [ExecutionEvent, WriteIntent]
  target_surface: Mobile voice-chat
  source_of_truth: mobile/hooks/useVoiceConversation.ts
  safety_level: privacy_sensitive
  prescription_or_causal_verdict: unchanged; existing Agent policy remains authoritative
  autonomy_tier: manual_confirm
  evidence_provenance: user-triggered microphone input and existing Agent evidence chain
  claim_hedging: unchanged
  verification_window: immediate interaction and focused automated tests
  success_metric: realtime partial transcript, one final submission, first-chunk PCM playback, and server-backed interruption
  added_user_burden: low
  burden_justification: explicit microphone control remains visible; no extra confirmation for ordinary questions
  non_goals: direct speech-to-speech model, full-duplex AEC, wake word, background listening, new medical-write authority
  smallest_end_to_end_slice: existing realtime ASR + Agent stream identity/cancel + streaming TTS + in-memory PCM playback
  stale_surface_to_remove_or_archive: Apple Speech recognition dependency from voice-chat hook
  spec_required: yes
```

## 3. User Flow

### Menu-only voice entry — 2026-10-04

Following user feedback that the green header voice capsule is too prominent,
remove the standalone header action. Keep history and more as compact neutral
header actions with 44-point touch targets; new chat remains in more. Use
Chat → 更多操作 → 实时语音对话 as the realtime voice entry, without a header or
above-composer shortcut, including after leaving message multi-selection.
The menu entry retains the existing microphone-ownership/navigation guard. Keep the
first-level conversation-history action and the separate transcription microphone.
Navigation opens `/voice-chat` without `autoStart`; the voice page's explicit
microphone and existing AI-consent gate remain authoritative. Active chat streaming
or composer capture/start/transcription/submission blocks entry with a visible
explanation, so opening the modal cannot create competing microphone ownership.
This is a reachability bugfix under the existing Capture/ExecutionEvent/WriteIntent
admission, not new medical-write authority, background listening or full duplex.

Acceptance: no prominent voice shortcut appears in the chat header or composer;
the more menu exposes one realtime voice entry and closes on successful navigation; active composer/Agent
work cannot navigate; history and transcription remain available; native simulator
verification and release gates are separate from mocked regression evidence.

Change note: this supersedes the 2026-10-03 prominent header-entry layout only;
voice-session behavior and safety boundaries are unchanged.

```text
tap microphone
  -> authenticated realtime ASR session starts
  -> partial transcript appears while speaking
  -> silence or explicit stop asks ASR for the authoritative final result
  -> non-empty final transcript is submitted exactly once to the existing Agent stream
  -> speakable phrases are appended to one authenticated streaming TTS session
  -> returned PCM chunks play immediately without temporary audio files
  -> tapping microphone during thinking/speaking stops PCM, cancels TTS, and cancels the matching Agent Run
  -> after cancellation succeeds, the next realtime ASR session starts
```

## 4. Contracts

| Surface | Contract |
| --- | --- |
| Mobile ASR | Reuse `/chat/transcribe/realtime`; partial text is display-only and final text is authoritative. |
| Mobile Agent client | Send a stable `client_turn_id`; resolve the owner-scoped local `run_id` through persisted events or turn status even when managed runtime storage is off; fail closed unless that run is terminal or its cancellation request succeeds. |
| Streaming TTS | `/tts/stream` accepts bounded incremental text and returns 24 kHz mono PCM chunks; it enforces 256 KiB per chunk, 180 seconds of PCM per session, a bounded event queue, an absolute session deadline, and provider cancellation on abnormal exit. Both directions remain transient and consent-gated. |
| Mobile playback | Native `AVAudioPlayerNode` queues PCM in memory, reports drain, stops synchronously on barge-in/reset/unmount, and applies 8-second/4-second high/low-water backpressure plus the same chunk/session byte ceilings. |
| Agent backend | Existing authentication, owner isolation, runtime cancellation, write gates, and terminal semantics remain authoritative. |
| Audio privacy | Mic activation is explicit; PCM is transient, bounded, not logged, and cancelled on reset, consent invalidation, or unmount. |

## 5. Acceptance Criteria

```gherkin
Given AI consent is valid
When the user starts listening
Then voice-chat starts the authenticated cloud realtime ASR session
And partial text is visible without being submitted

Given the ASR session has partial text
When silence is detected or the user stops listening
Then voice-chat waits for the final ASR result
And submits the non-empty final transcript exactly once

Given an Agent turn is running or TTS is speaking
When the user starts a new utterance
Then queued and active audio stops immediately
And the active streaming TTS session is cancelled
And the local Agent stream is aborted
And the server Agent Run receives a cancellation request before the next mic session opens

Given an active Agent turn has not yet exposed a cancellable owner-scoped run identity
When the user attempts to barge in
Then the next microphone session remains closed
And the UI reports that the previous turn could not be stopped safely

Given the TTS provider overruns an audio bound or the downstream socket disconnects
When PCM relay is active
Then the bridge terminates within its bounded deadline
And provider synthesis is cancelled
And queued audio cannot grow without a byte or playback-watermark bound

Given consent is invalidated, the screen unmounts, or reset is requested
When a realtime ASR session is active
Then capture is cancelled and cannot reopen after cleanup

Given a voice turn requests a health write
When existing Agent safety rules require confirmation
Then voice input does not bypass the existing confirmation or receipt path
```

## 6. Non-Goals And Rollback

- No full-duplex microphone/playback, acoustic echo cancellation, wake word, or background audio.
- ASR does not fall back to Apple Speech or a second cloud provider. TTS may fall back to
  local iOS speech only when the cloud session fails before any text reaches the provider;
  mid-stream failures never replay already-sent health guidance.
- No backend schema or health-data contract change.
- Phase 2 requires a new signed iOS build because it adds a native PCM player; it is not OTA-compatible.
- Rollback can disable the streaming TTS client and return to the existing authenticated MP3 endpoint; ASR and Agent endpoints remain compatible.

## 7. Verification

```bash
cd mobile && npm test -- --runInBand --runTestsByPath hooks/__tests__/useVoiceConversation.test.ts services/__tests__/chatStream.test.ts services/__tests__/cloudRealtimeAsr.test.ts
cd mobile && npx tsc --noEmit --pretty false
git diff --check
```
