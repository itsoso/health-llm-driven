# Agent record completion contracts

Status: implemented and locally verified; not released. Updated: 2026-10-31.

## Decision and admission

Keep official Pi. Separate a user's record obligation from domain classification,
resolve supported actions through one executable capability contract, and verify
persistence before completing the task. This bugfix strengthens ExecutionEvent,
WriteIntent and HealthTwin on the shared backend; clients keep their existing
completion_status/turn_outcome contract. Source of truth is authenticated storage.
It adds no medical advice, diagnosis or prescription changes. Explicit typed
self-reports of a completed low-risk behavior authorize that record only; no
proactive autonomy or new clinical write authority is introduced.

## Scope and flow

Current user text -> completion obligation -> bound capability -> Pi proposal ->
existing gateway and write checkpoint -> authenticated API -> owner/event/value
readback -> task outcome. Unsupported explicit record requests retain an unmet
obligation and cannot report successful chat. An obligation is never authority.
The first capability is nasal washing, using the existing daily health checkin
fields. Its schema, parser, endpoint and receipt resource are declared together.
Existing record domains retain their domain guards and verification contracts.
Supported coordinated record requests carry every bound target. Their completion
requires distinct receipts matching each target's values in both the dispatched
arguments and persisted response, including explicit owner and date. Partial completion is projected into streamed text, stored text and outcome consistently; it cannot retain a model claim that every item succeeded. Unsupported coordinated targets cannot be
silently dropped. Postfix record requests, descriptive symptom conjunctions and
analysis adjuncts do not invent extra write obligations.

## Data and safety contract

nasal_wash uses count, optional volume_ml/solution, and record_date. Absent facts
remain absent. The endpoint also requires a stable event_id: Agent derives it from the source turn, while clients generate it once and reuse it for retries.
The current user row serializes event append; same event ID plus identical facts
is a replay, conflicting facts fail. Readback binds owner, day, event and values.
Readback also checks the event operation type. Automatic Agent recording is restricted to the typed channel; media and other channels do not inherit authority. No schema migration is required. Existing HealthCheckinResponse is reused; the
new endpoint has a strict input schema. Quoted, third-party, negated, hypothetical,
future and compound unbound text grants no capability. Model fields cannot grant
consent, alter owner, expand facts, or substitute a generic memory record.

## Client and recovery behavior

Web and Mobile append individual events instead of overwriting a cached daily
aggregate. Manual time and wash/soak selection remain supported. Undo targets one
event and retains a tombstone, so a late retry cannot restore it. The legacy daily
endpoint rejects changes to canonical events before mutating other fields.
Clients preserve the pending event identity during an in-component retry; this
change does not add a durable offline queue across app restarts.

Uncertain Agent writes remain reconciliation_required and are not dispatched
again automatically. Generic runtime reconciliation does not verify health
checkins merely by row existence; automatic background reconciliation for this
new event capability is outside this change.

## Acceptance and verification

- Unknown explicit record intent with zero writes is not complete, in ordinary
  and panel paths. Asking whether a record exists is not a new write obligation.
- Nasal self-report reaches real Pi, gateway, authenticated API and isolated PG;
  saved count, optional volume and fluid equal the user request.
- Same client turn/event replay does not duplicate; concurrent distinct events
  accumulate; another user's event is inaccessible; changed payload is rejected.
- Failure/unknown dispatch remains failure/reconciliation; unrelated receipts
  cannot satisfy the bound capability.
- Focused regression, PostgreSQL E2E, system-map drift and independent safety
  review are required. Scripted provider E2E is distinguished from live-model
  evidence. No production mutation is part of this implementation task.

## Rollback and changelog

Revert code to remove capability exposure; existing checkin records remain valid.
2026-10-31: accepted architectural bugfix following observed zero-write success.
