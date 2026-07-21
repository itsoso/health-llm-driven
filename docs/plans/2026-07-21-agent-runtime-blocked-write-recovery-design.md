# Agent Runtime Blocked Write Recovery Design

## Problem

An advice turn can occasionally make a model-generated write tool call. The
Agent Kernel correctly blocks that call before dispatch, but the blocked result
is currently classified as an uncertain external write. The executor then
replaces the requested advice with a missing-receipt error and marks the Run as
failed. A client replay can display the same terminal result again.

## Design

Use structured execution facts as the primary contract between ToolGateway and
the write outcome classifier. A policy-blocked tool returns `status=rejected`
and `dispatch_started=false`; legacy `[NEEDS_CLARIFICATION]` text remains
recognized during rollout. Rejected tool calls stay available to the model as
recovery context and the next round is forced to synthesize without tools, so a
read/advice turn still answers the original request.

Only results that may have crossed the external write boundary can become
`uncertain`. Verified writes still require a resource receipt. Confirmation
gates remain non-successful but are not treated as unknown writes.

The model prompt must not create the bad call in the common case. A pure
"starting sleep now" statement can remain an event write, but a statement that
also asks for advice, analysis, or an answer is read-only unless the user also
explicitly asks to record it.

Structured rejections are consumed consistently by every direct execution
surface: chat, voice commands, Telegram, procedure replay, and post-record
quality processing. No surface may convert a rejected result into a success
message.

## Client Behavior

Server replay remains idempotent. Mobile must merge a replayed durable turn by
`client_turn_id` instead of appending a second optimistic user/assistant pair.
Terminal failed state must replace the persisted-progress banner.

## Verification

- Unit-test structured and legacy policy rejections.
- Integration-test an advice turn whose model requests `health_record`.
- Contract-test the sleep-advice prompt distinction.
- Prove the write adapter is never called and the final answer is normal advice.
- Preserve tests for remote timeout uncertainty and verified receipts.
- Cover voice, Telegram, procedure replay, and post-record quality consumers.
- Cover mobile replay merge behavior without weakening retry recovery.
