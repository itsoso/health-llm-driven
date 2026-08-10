# Provider Stream Total Deadline Design

## Decision

Add a server-side wall-clock deadline to every streaming LLM provider attempt.
The selected provider and the existing stable fallback each receive an independent
120-second total budget. This repairs the observed production stall without
changing the Mobile protocol, rebuilding the iOS binary, publishing an OTA, or
changing health-data write semantics.

## Production Evidence And Root Cause

The Build 256 photo turn was admitted and durably stored with its image. Vision
processing completed, the selected streaming provider returned HTTP 200, but the
provider stream never produced a terminal event. The run stayed active until the
outer Agent runtime deadline expired roughly five minutes later. A later send was
correctly rejected with HTTP 409 because the first run still owned the
conversation.

The provider HTTP client already has a 120-second read timeout. That timeout only
bounds the idle interval between response bytes. A server can keep the connection
alive with reasoning, empty, or keepalive chunks indefinitely, so the read timeout
does not bound the total time spent iterating the stream. `AgentExecutor` currently
has no wall-clock limit around `provider.chat_stream(...)`; the much larger outer
runtime deadline is therefore the first effective stop.

The stored user message and image prove this is not an upload or persistence
failure. The missing terminal assistant response and the repeated 409s are
downstream effects of the stalled provider stream.

## Alternatives Considered

1. **Per-provider stream deadline with existing failover — chosen.** Bound each
   streaming attempt at 120 seconds, then reuse the existing stable-provider
   fallback and partial-output rules. This fixes the failed boundary directly.
2. **Shorten the entire Agent runtime deadline.** Simpler, but it would also cut
   off legitimate multi-tool health turns and still would not isolate the failing
   provider attempt. Rejected.
3. **Retry or special-case the conflict only in Mobile.** This would mask the
   server stall, keep the conversation occupied, and increase duplicate/queueing
   risk. Rejected for this incident.

## Runtime Contract

Introduce one module-level constant in `agent_executor.py`:

```python
_LLM_STREAM_ATTEMPT_TIMEOUT_S = 120.0
```

A small async-generator helper will iterate `provider.chat_stream(...)` inside
`asyncio.timeout(_LLM_STREAM_ATTEMPT_TIMEOUT_S)`. The timeout starts when the
provider stream is entered and covers the complete iteration, including reasoning
and keepalive chunks. It is separate from the HTTP client's per-read timeout.

The helper is used for both streaming boundaries:

- the initially selected streaming provider in `_call_llm_stream`; and
- a streaming stable fallback in `_stream_via_stable_fallback`.

Each attempt gets its own deadline. A primary timeout with no user-visible content
therefore leaves enough time for one stable fallback while remaining below the
outer Agent runtime budget. A fallback timeout emits the existing error finish
event so the runtime releases the conversation instead of waiting for the outer
deadline.

Non-streaming bridge calls are unchanged. They do not iterate a keepalive stream
and remain protected by the provider HTTP timeout.

## Partial Output And Failure Semantics

Preserve the current no-duplicate invariant:

- If the selected provider times out before any user-visible `content` event, mark
  that provider dead for the applicable scope and invoke the existing stable
  fallback.
- If user-visible content was already emitted, do not invoke another provider.
  Emit an error finish event and close the turn gracefully, preventing duplicated
  or contradictory answers.
- Reasoning/keepalive events are not user-visible answer content. A timeout after
  only those events is still eligible for fallback.
- If the stable fallback also times out or fails, emit one error finish event and
  release the run. Never report a health write as successful without the existing
  verified receipt path.

Timeout logs will include only operational context such as the configured budget
and provider/model identifier already used by the executor. They must not include
the prompt, image, health content, credentials, or tokens.

## Test Strategy

Add focused asynchronous regressions to
`backend/tests/test_agent_executor_failover_gate.py` using a very short monkeypatched
deadline:

1. A selected provider emits non-content reasoning events forever. Verify the
   deadline cancels it, the stable fallback is invoked exactly once, and the turn
   receives fallback content plus a terminal finish event.
2. A selected provider emits user-visible content and then stalls. Verify the
   deadline produces an error finish without invoking the fallback or duplicating
   content.
3. The selected provider fails and a streaming fallback also emits only
   non-terminal events forever. Verify the fallback deadline yields one error
   finish and returns promptly.
4. Keep the existing successful streaming and non-streaming bridge tests green.

Run the new tests red before implementation, then the focused failover suite and
the relevant Backend gate after implementation. No real provider, health record,
or user content is required for these tests.

## Rollout And Verification

This is a Backend-only deployment with no database migration and no Mobile
release. After focused and integration gates pass:

1. deploy the clean pushed `main` revision through the repository deployment
   script;
2. verify Backend health, deployed revision, and sanitized timeout/failover logs;
3. reset the App Review fixture through the supported release workflow;
4. repeat the Build 256 photo meal flow on the connected physical iPhone;
5. verify the conversation receives a terminal response and no repeated 409 loop;
6. continue the remaining physical-device release checklist only after this item
   is green.

App Review submission remains blocked until all existing G5/G6 items pass.
Production OTA remains frozen.

## Rollback

Rollback restores the prior Backend revision. No data or schema rollback is
needed because this change only bounds provider-stream execution. The persisted
user message/image and existing run-recovery contracts remain unchanged.
