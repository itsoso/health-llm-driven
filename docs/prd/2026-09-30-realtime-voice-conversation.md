# PRD: Realtime Voice Conversation

## Outcome

Make Mobile voice-chat feel continuous and interruptible without creating a second health-agent path. Users see words while speaking, only the finalized transcript is sent, assistant speech starts from incremental phrase output, and tapping to speak over an answer stops both audio generation and the matching backend run.

## Scope

- Replace voice-chat's Apple recognition with the existing Qwen realtime ASR WebSocket.
- Preserve the existing Agent Kernel and cloud/iOS TTS selection.
- Stream cloud TTS through an authenticated backend WebSocket and play transient
  24 kHz mono PCM from memory in a native iOS module.
- Give every voice request a stable client turn ID and retain its Agent Run ID.
- Make barge-in cancel PCM playback, cloud TTS, the local Agent transport, and the server runtime.
- Cancel microphone capture on reset, authorization invalidation, and unmount.

## Safety And Privacy

The feature does not add medical authority or a new write route. Voice remains a lossy input channel, so existing confirmation requirements continue to apply. Microphone PCM and synthesized PCM stay transient and must never enter logs, analytics, or durable storage. Cancellation failure is visible and must not silently open a competing microphone/Agent turn. Streaming TTS does not receive tool calls or bypass Agent confirmation semantics; it only renders already-approved assistant text.

## Success Criteria

- Partial transcript latency uses the existing realtime ASR stream rather than waiting for native final recognition.
- Exactly one Agent request is created per finalized utterance.
- A user interruption results in an authenticated cancellation request for the active owner-scoped run.
- The first complete phrase can start synthesis before the Agent turn ends; playback waits for
  native drain and creates no temporary audio file.
- Existing direct briefing playback, conversation loading, and cleanup continue to pass tests.

## Deferred

Full-duplex audio, acoustic echo cancellation, direct speech-to-speech models, wake words, and background listening require a later native/audio architecture slice.
