# Runtime Write Circuit Recovery Design

> Status: approved by user on 2026-08-01
> Related incident: `run_e272f2a009f44346`, `run_a36355c055424ad4`
> Related prior work: `docs/specs/record-write-outcome-reliability-spec.md`

## 1. Outcome

Restore ordinary health-record writes without weakening receipt safety, and make every
surface tell the truth when the write control plane blocks a request.

The concrete anchor phrases are:

- `记录吃了一个桃子`
- `记录加餐，我吃了一个桃子`

Both must either produce one verified diet receipt or terminate after the first blocked
write attempt with an explicit protection-state response. They must never spend more LLM
rounds rewriting a control-plane failure into “请补充详情”.

## 2. What Failed

The incident is a composition failure across four otherwise reasonable mechanisms:

1. A previous write finished without a trustworthy receipt, so the Runtime circuit
   entered `paused / reconciliation_detected`.
2. The circuit is a singleton. One unresolved run therefore disabled dynamic writes for
   every managed user, even though the uncertain operation itself was already isolated by
   run identity and write fingerprint.
3. `AgentExecutor` returned a typed pre-dispatch failure
   (`runtime_control_unavailable`, `dispatch_started=false`) but treated it like ordinary
   tool feedback. The model continued for four to nine rounds and finally replaced the
   real failure with a generic record-detail prompt.
4. `tools_used` records attempted tools, while all clients label it “调用 Skill”. A blocked
   attempt therefore looked like a completed capability invocation. The API wrapper also
   suppressed draft cards from the attempted tool name instead of a verified receipt or
   pending confirmation.

There is a separate capture gap: the deterministic diet goal compiler requires an
explicit meal label. It does not reuse the repository's existing local-time meal inference,
so the first anchor phrase falls back to a generic write while the second gets a bounded
`simple_health_record` goal.

The first production smoke after that recovery found a deeper ownership gap: the goal
contract owned food, meal, and date, but still delegated all required nutrition fields to
the first tool-selection model. That model emitted the correct canonical diet write without
nutrition. The validator rejected it as designed; repeated model rounds could not change
the already canonical operation safely, so the user received another failure with no write.

## 3. Safety Invariants

- A write is successful only when a verified durable receipt exists.
- An uncertain post-dispatch write is never retried automatically or through a generic
  retry action.
- A pre-dispatch circuit block performs zero health-data mutation.
- The Runtime ledger and user-visible control telemetry contain no food text or other
  health values.
- A single unresolved write quarantines the affected user/run. It may not remove write
  capability from unrelated users unless the configured systemic threshold is reached.
- Stale leases, control-plane unavailability, manual pause, and systemic failure rate stay
  globally fail-closed.
- Existing finalized client turns retain their idempotent replay semantics.

## 4. Options Considered

### A. Manually resume the circuit only

This restores service fastest but preserves the global blast radius and misleading model
loop. The same shape of incident would recur. Rejected.

### B. Ignore reconciliation pauses

This keeps writes available but discards the safety signal that detects potentially
duplicated writes. Rejected.

### C. Add a new scoped-circuit schema before recovery

A fully normalized circuit table keyed by user/capability is architecturally clean, but it
adds migration and rollback risk to an active production outage. Deferred until operational
evidence shows the admission-time scope policy is insufficient.

### D. Keep the durable global event, scope admission, and terminalize the typed block

Chosen. The existing singleton continues to record and expose the incident. Admission
derives the current unresolved window from the durable generation-minus-acknowledgment
delta, the newest content-free reconciliation events, and the Runs that still require
reconciliation. Below the systemic threshold, only users owning an unresolved
reconciliation in that current window are blocked; acknowledged historical and already
resolved owners are excluded, and unrelated users still receive managed Runtime runs.
At or above the threshold, for any non-reconciliation pause reason, or when the event ledger
cannot prove the generation window, the global block remains. The Executor turns a
pre-dispatch control rejection into one deterministic terminal outcome.

This is the smallest safe change that reduces blast radius without bypassing the durable
Runtime or introducing a production migration during recovery.

## 5. Architecture

```text
user record text
  -> deterministic intent + goal compiler
       -> explicit meal, or existing local-time meal inference
  -> Runtime admission
       -> active: managed run
       -> reconciliation pause, below threshold:
            affected user -> managed=false + circuit_paused write block
            unrelated user -> managed run + scoped_reconciliation_admission
       -> systemic/manual/stale/unavailable: global write block
  -> simple diet numeric enrichment (only after admission is available)
       -> existing text estimator, once
       -> sanitize + bound calories/protein/carbs/fat/fiber
       -> preserve canonical food/meal/date
  -> ToolGateway / AgentExecutor
       -> verified receipt -> success
       -> pre-dispatch runtime_control_unavailable
            -> emit tool_result once
            -> deterministic terminal response
            -> done.completion_status=error
            -> done.turn_outcome=service_unavailable
       -> post-dispatch uncertain -> reconciliation_required, never retry
```

## 6. Component Changes

### Deterministic capture

`goal_spec` accepts an explicit diet meal when present. When absent but the current turn is
an unambiguous diet create, it extracts the food phrase and calls the existing
`diet_voice_parser.infer_meal_type(text, local_hour)`. The inferred meal remains a bounded
goal fact; nutrition estimation and the verified receipt gate remain unchanged.

### Runtime admission scope

Add a bounded configuration value for the number of currently unacknowledged
reconciliation owners that escalates to a global block. While the state reason is
`reconciliation_detected`:

- affected user with a still-unresolved reconciliation in the
  generation-minus-acknowledgment event window: block writes;
- unrelated user below threshold: create a normal managed run;
- threshold reached: block globally.

The event ledger is content-free. A generation/event-count mismatch cannot establish a
trustworthy window and therefore remains globally fail-closed. Acknowledged historical or
already resolved Runs may retain their audit event without contaminating future incident
scope.

The check executes while holding the existing rollout-state lock, so circuit admission and
run creation remain linearized. No raw operation payload is queried.

### Executor terminal semantics

The write outcome classifier already proves the block happened before dispatch. Capture
`runtime_control_unavailable` as a dedicated terminal fact, stop the tool/model loop after
the first occurrence, and construct the final response from deterministic text. Do not set
`record_intent_no_tool`; the tool was attempted and truthfully rejected.

The terminal outcome is:

```json
{
  "category": "service_unavailable",
  "reason_code": "runtime_control_unavailable",
  "retryable": false,
  "refusal_detected": false
}
```

`retryable=false` prevents reconnects or generic retry UI from hammering a still-paused
circuit. The user can send a new turn after recovery.

### Server-owned diet enrichment

After the goal guard has replaced model-authored identity fields with the current turn's
canonical food, meal, and date, inspect the five nutrition fields. If they are incomplete,
invoke the existing text-nutrition estimator at most once, sanitize per-food results, bound
all totals, and add numeric fields only. The enriched call still passes through the normal
validator, ToolGateway, write checkpoint, and verified-receipt boundary.

Do not invoke the estimator while Runtime has already blocked writes. Do not accept an
incomplete, non-finite, negative, or unbounded result. Failure leaves the original call to
the hard validator, which fails closed without a health mutation.

### Cards and transparency

Draft-card suppression is derived from verified `write_receipts`, explicit existing cards,
or server-owned pending confirmations. A mere attempted `health_record` name is not enough.

The historical `tools_used` field stays backward compatible, but clients label it
“尝试调用 Skill” for any explicit non-complete terminal state. Successful turns keep
“调用 Skill”, and legacy rows without a status retain their existing presentation. No new
client API field is required.

### Operations

Before resuming production, use the existing documented evidence for the prior missing
receipt, never replay it, and acknowledge exactly the current reconciliation generation.
Deploy from a clean integration point. Production verification must include the two anchor
phrases, a content-free Runtime state check, a receipt-backed record lookup owned by the
requesting user, and an error-log scan.

## 7. Rollout and Rollback

1. Land backend capture, terminal semantics, scoped admission, and tests.
2. Land additive client wording changes; old clients remain compatible.
3. Acknowledge/resume only the exact observed circuit generation.
4. Deploy backend, then publish client updates using their project release routes only if
   client files changed.
5. If backend health fails, roll back the deployed SHA. The old circuit behavior remains
   fail-closed; no schema rollback is required.
6. If scoped admission is unsafe in production, set the threshold to `1` to recover the old
   global-pause behavior without a code rollback.

## 8. Success Criteria

- Both anchor phrases compile to `simple_health_record / diet / create`; at 21:05 local time
  the phrase without a meal label resolves to `snack`.
- If the first tool model omits nutrition, the server enriches the canonical diet call once,
  preserves food/meal/date, and dispatches exactly one validated write.
- Estimator failure or invalid totals cannot bypass the nutrition validator; a Runtime block
  prevents the estimator call entirely.
- A simulated paused circuit produces one `health_record` attempt, zero dispatches, at most
  one LLM tool round, `completion_status=error`, and the typed service-unavailable outcome.
- No model-authored “need details” or health-analysis disclaimer replaces the typed block.
- A single user reconciliation blocks that user but admits an unrelated user's managed run.
- The configured threshold, manual pause, stale lease, failure rate, and unavailable control
  plane still block all relevant writes.
- Draft cards are not suppressed solely because a failed tool was attempted.
- Mac, Mobile, and Web distinguish attempted Skill display on failed turns.
- Production returns a verified receipt for the anchor phrases after recovery.
