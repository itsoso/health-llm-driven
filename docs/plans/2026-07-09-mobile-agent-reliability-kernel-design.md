# Mobile Agent Reliability Kernel Design

## Outcome

Mobile Chat becomes a transaction-oriented Agent surface. A turn is complete only when its response is terminal and every claimed write has a deterministic receipt. Input, audio, attachments and foreground recovery are explicit states rather than loosely related booleans.

## Chosen Approach

Use three small reducers/contracts around the existing implementation:

1. `AgentTurnState` owns request lifecycle and recovery.
2. `WriteReceipt` owns the difference between UI completion and durable persistence.
3. `ComposerState` owns text/hold/dictation/submission mutual exclusion.

This keeps current SSE, React Query, card registry, WriteIntent and voice hooks. No new global state library, database table or native module is required.

## Architecture

```text
ChatInputBar
  └─ ComposerState reducer
       ├─ useVoiceRecording (hold path)
       ├─ useRealtimeDictation (live text path)
       └─ useMediaPicker + private draft storage

useChatEngine
  └─ AgentTurn reducer + persisted active snapshot
       ├─ streamChat(status/tool/card/token/done/error)
       ├─ restoreMessagesFromHistory
       └─ foreground reconciliation

ChatBubble / card registry
  └─ dispatchChatCardAction
       └─ WriteReceipt (verified resource identity)

Backend AgentExecutor
  └─ tool_result.data.receipt (additive deterministic metadata)
```

## State Machines

### AgentTurn

```text
idle -> submitted -> running -> writing -> verifying -> completed
                      |           |          |
                      +-----------+----------+-> failed
                      |
                      +-> interrupted -> recover -> running/completed/failed
```

Terminal states are `completed`, `failed`, and `interrupted`. `interrupted` is recoverable while its snapshot is fresh; a server history reconciliation decides the next state.

### Composer

```text
text.idle <-> hold.idle
text.idle -> live_dictating -> text.idle
hold.idle -> hold_starting -> hold_recording -> hold_transcribing -> text.idle or submit
any active audio -> background/submit/error -> idle + release audio session
text.idle -> submitting -> text.idle
```

The reducer rejects conflicting transitions. UI effects perform native start/stop only after the state transition is accepted.

## Write Receipt

A card button's runtime state is presentation-only. Durable success requires:

```text
manual confirm
  -> authenticated domain API
  -> response with resource ID or executed_ref
  -> normalized WriteReceipt(verified=true)
  -> card done + cache invalidation
```

Missing identity throws a stable error. The card keeps its draft/action payload and enters retryable `error`; it does not silently downgrade to success.

## Attachments And Drafts

- Text draft: AsyncStorage, short debounce, clear only after send starts successfully.
- Image draft: copy source bytes into an App-private draft directory; AsyncStorage stores only URI/type metadata.
- Send: read base64 from the private URI when needed and use the existing Agent API.
- History: continue using backend-uploaded URLs stored in `AgentMessage.image_url`.
- Cleanup: delete private draft files after acknowledged send or explicit removal; age-based cleanup handles abandoned drafts.

## Presentation

- Today Focus remains fully visible only before conversation activity and while the keyboard is hidden. During active conversation it becomes a one-line strip.
- Streaming shows one human-readable current stage; technical trace remains collapsed.
- Remove the fixed four-action grid from every response. Server cards/actions are authoritative. Generic copy/share/speech remain secondary affordances.
- XiaoBa avatar and name stay stable; personality is conveyed by concise language and context continuity, not decorative surface area.

## Error Handling

- Network before request: keep draft, show offline failure.
- Stream interruption: preserve received content and mark turn recoverable.
- Background: stop audio immediately; do not abort a server turn solely because Chat unmounted.
- Write without receipt: fail loud with retry/edit; never show completed.
- Attachment unavailable: keep text, mark only the missing attachment failed, offer remove/reselect.

## Testing

- Pure reducers receive table-driven transition tests.
- Hook/component tests cover native effect ordering and AppState transitions.
- Service tests cover resource identity extraction and missing-receipt failure.
- Backend helper tests cover valid/malformed/soft-failure tool results.
- Simulator is the final interaction oracle for keyboard geometry, voice gestures and background recovery.
