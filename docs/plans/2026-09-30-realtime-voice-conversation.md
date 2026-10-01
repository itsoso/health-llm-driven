# Plan: Realtime Voice Conversation

## Slice 1 — Agent identity and cancellation

1. Extend Mobile SSE parsing to expose `run_id` on persisted and done events.
2. Add an authenticated Mobile helper for the existing Agent Run cancel endpoint.
3. Cover parsing, ownership-safe URL construction, success, and failure behavior in service tests.

## Slice 2 — Realtime voice Hook

1. Replace Apple Voice listeners with `createCloudRealtimeAsrSession`.
2. Keep partial text display-only; on stop/silence await the final result and submit once.
3. Pass a stable voice client turn ID into `streamChat` and capture its run ID.
4. On barge-in, stop playback, abort XHR, cancel the backend run, then start the next ASR session.
5. Cancel ASR on reset, consent invalidation, and unmount.

## Slice 3 — Verification and gates

1. Run focused RED/GREEN tests for the hook and service.
2. Run cloud ASR regression and Mobile typecheck.
3. Run diff/secret/governance checks appropriate to the touched files.
4. Request independent safety review only after a reviewable commit is authorized; do not push or release without separate authorization.

## Slice 4 — Streaming speech output

1. Add a consent-gated authenticated `/tts/stream` WebSocket that bridges bounded text
   fragments to CosyVoice streaming input and returns transient 24 kHz mono PCM chunks.
2. Add an iOS Expo PCM player backed by `AVAudioEngine` / `AVAudioPlayerNode`; keep audio
   in memory and expose explicit finish/drain/stop semantics.
3. Replace cloud MP3 file synthesis in voice-chat with one streaming TTS session per
   assistant turn; begin on phrase boundaries and await native playback drain.
4. Make barge-in/reset/consent invalidation/unmount cancel PCM playback and the TTS session
   before opening the next realtime ASR session.
5. Verify focused protocol, native-source, hook, privacy, type, and repository governance
   gates. Record that the native change requires a signed iOS build and is not OTA-safe.
