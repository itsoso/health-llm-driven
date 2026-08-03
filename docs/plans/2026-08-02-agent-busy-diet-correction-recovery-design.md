# Agent Busy And Diet Correction Recovery Design

## Decision

Implement the user-approved complete recovery option across Mobile and Backend:

- treat `POST /api/v1/agent/stream` HTTP 409 as an admitted-state conflict, not
  as a network outage;
- keep text-only follow-up turns in the existing Mobile FIFO queue and retry the
  same `client_turn_id` with bounded backoff;
- support numeric meal fractions such as `1/2` in explicit diet corrections;
- deterministically update a unique matching meal, including meals that do not
  yet have scalable nutrition fields; and
- stop an ambiguous correction after the first lookup and ask the user to pick
  the intended record instead of spending additional model/tool rounds.

This is a reliability repair of the existing chat and diet-record contracts. It
does not add a server-side durable queue or new autonomous health behavior.

## Production Evidence And Root Cause

The screenshot was captured while an earlier agent turn was still running.
Production request logs show this sequence:

```text
POST /api/v1/agent/stream                         -> 409 Conflict
GET  /api/v1/agent/turns/<new-turn-id>/status     -> 404 Not Found
POST /api/v1/agent/stream                         -> 409 Conflict
```

The Backend correctly returned `上一条消息仍在处理，请稍后重试`. Mobile's XHR
stream adapter did not reject non-2xx responses, so the ordinary JSON error body
was treated as an empty SSE stream. Turn-status reconciliation then queried a
turn that had never been admitted, received 404, and reduced the whole sequence
to the generic `发送失败，请检查网络` alert.

When the same diet correction was eventually admitted, a second issue appeared:
the explicit correction parser recognized Chinese fraction phrases but not
`1/2`. A unique record without nutrition fields also produced an unresolved
state that was fed back through repeated model/tool rounds before a final
refusal. The user therefore saw both transport misinformation and delayed write
failure in one interaction.

## Alternatives Considered

1. **Only improve the error copy and require manual retry.** Small, but it makes
   the user supervise a conflict the client can safely recover from. Rejected.
2. **Add a durable queue to the Backend.** Useful for broader multi-device
   scheduling, but it changes admission, persistence and worker coordination.
   Rejected for this focused production repair.
3. **Reuse the Mobile FIFO queue and complete deterministic diet correction.**
   Chosen. It closes the observed flow with bounded surface and preserves the
   Backend as the source of truth for whether a turn was actually admitted.

## Mobile Transport Contract

`streamChat` will fail loudly for every non-2xx HTTP response with a typed,
sanitized error containing the status and safe API detail. It will never parse
an ordinary error document as SSE. The error type must not retain request
headers, auth tokens, images or prompt content.

The chat engine classifies the known busy response (`409`, with the current
busy detail) separately from network, authentication and server failures:

```text
send text turn
  -> 2xx: consume stream normally
  -> 409 busy: retain optimistic turn, enqueue same client_turn_id
               show "上一条仍在处理，本条已排队。"
               retry FIFO with bounded backoff
  -> other failure: existing reconciliation and explicit failure path
```

Retries use the original `client_turn_id`, conversation ID and local message
IDs. The Backend's idempotency contract therefore prevents duplicate durable
turns if the response was lost around admission.

Backoff starts at 1 second, grows through 2, 4, 8 and 15 seconds, and is capped
at 30 seconds. A queued item expires after ten minutes. Only one timer and one
queue pump may exist per mounted chat engine. A busy requeue suppresses the
immediate `finally` pump, preventing a tight loop. Foregrounding or completion
of the active stream may wake the pump earlier, but FIFO order remains intact.

Text-only busy turns count as locally accepted so `ChatInputBar` does not show
the false network alert. Image turns continue to clear their draft only after
server admission; a busy image turn stays visibly pending and retains its image
payload in memory for the bounded retry window. If the retry window expires,
the optimistic turn becomes explicitly failed/retryable rather than silently
disappearing.

This slice intentionally keeps the queue process-local. Closing the app may
discard a turn that the Backend never admitted; durable cross-restart delivery
belongs to a separate runtime-control feature.

## Backend Diet-Correction Contract

The deterministic parser will accept numeric fractions matching
`numerator/denominator` when the request contains a partial-consumption signal.
It rejects a zero denominator and fractions outside `(0, 1]`. The normalized
correction retains both the numeric multiplier and a canonical display label,
so `1/2` remains a truthful user-facing portion marker.

After the first owner-scoped date/meal lookup:

- **one record with nutrition values:** scale each available numeric nutrition
  field exactly once and update that record;
- **one record without scalable nutrition:** preserve its food description,
  replace any prior generated actual-portion suffix, and append
  `（按实际食用1/2计）`; do not synthesize calories or nutrients;
- **no record:** return a direct not-found clarification;
- **multiple records:** return a direct selection clarification identifying
  only safe distinguishing information already available to the user.

An unresolved lookup becomes a terminal deterministic response in the current
turn. It must not return to the model for another identical list/update cycle,
and it must never claim that a write succeeded.

## Data, Safety And Privacy Invariants

- Every diet lookup and update remains scoped to the authenticated user.
- Stored health values retain their source precision; only the requested
  fraction transformation changes existing numeric values.
- Missing nutrition is never guessed, inferred or backfilled by the LLM.
- A write receipt is emitted only after the update tool reports success.
- Logs and telemetry may include status, turn ID, retry count and unresolved
  reason, but never the health prompt, meal description, images or auth data.
- The queue copy is operational state, not a medical claim.

## Test Strategy

Start with failing regression tests that reproduce the two production chains:

1. a 409 JSON response from the stream endpoint raises the typed Mobile error;
2. the chat engine requeues the same turn ID, avoids the generic network alert,
   backs off, and succeeds exactly once after the active turn clears;
3. `晚餐只吃了 1/2 修改记录` parses as a fraction correction rather than a food
   replacement;
4. a unique meal with nutrition scales the available values;
5. a unique meal without nutrition preserves its food and records the actual
   fraction without invented values;
6. multiple candidates produce one immediate clarification and no repeated
   model/tool round.

Then run the focused Mobile and Backend suites, TypeScript, Backend compile and
lint checks, repository drift checks and `git diff --check`. Because this path
writes health data, an independent G4 safety review is required before release.

## Rollout And Rollback

Deploy the Backend first and verify health plus focused owner-scoped correction
behavior without exposing real meal content in logs. Publish the pure TS/JS
Mobile change through the production OTA script only after Backend G5 passes.

No database migration is required. Backend rollback restores the previous
parser/update behavior; Mobile rollback restores the prior bundle. The two
changes are backward compatible: an updated Mobile still receives the existing
409, and an updated Backend still accepts older clients. If OTA publication is
blocked, report the Backend and Mobile rollout states separately and do not
claim end-to-end completion.
