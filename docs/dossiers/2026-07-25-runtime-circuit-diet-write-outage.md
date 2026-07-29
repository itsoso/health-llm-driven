# Runtime Circuit Diet Write Outage

| 字段 | 值 |
|---|---|
| date | 2026-07-25 |
| status | complete |
| current_stage | S8 complete |
| owner_surface | Agent Runtime / health writes |

## Incident

Production Agent turns could read health data but could not record diet or
other health writes. The write tool was rejected before business dispatch, so
the diet database and diet API were not the failing layer.

## Root Cause

The Agent Runtime rollout circuit was paused after an older
`draft_aigc_media` operation entered `reconciliation_required`. New turns were
therefore admitted outside Runtime with `control_reason=circuit_paused`, and
the shared write boundary correctly failed writes closed.

The incident remained hard to see because a structured pre-dispatch rejection
(`success=false`, `dispatch_started=false`) was emitted as a successful
`agent.tool_result` when it occurred before ToolGateway had produced a policy
decision.

## Safety Decision

The circuit remains fail-closed. We explicitly rejected a broad fallback that
would have allowed every dynamic write while Runtime was paused.

Production recovery instead uses the existing audited administrator `resume`
transition after verifying:

1. the only unresolved operation is a media confirmation draft, not a health
   write;
2. current main recognizes a persisted media confirmation as a verified
   receipt;
3. resume acknowledges the reviewed reconciliation generation.

## Change

- Classify only hard structured failures independently of a ToolGateway
  decision; normal `pending` read states are not failures.
- Build and verify write receipts before generic failure classification, so a
  persisted AIGC confirmation or health record cannot be added to recovery
  state after already proving success.
- Require `expected_reconciliation_generation` on manual Runtime resume. The
  locked generation must match or the API returns `409` and remains paused.
- Expose only content-free current/acknowledged reconciliation generations in
  the administrator rollout status.
- Add regression coverage for pre-dispatch Runtime rejection, verified write
  replay, AIGC pending confirmation, health-record receipt, read pending state,
  and stale-generation recovery.

No health-record payload, write policy, idempotency rule, or circuit admission
rule is relaxed.

## Gates

### G1 Product Admission: GO

**裁决**: PASS

Restores an existing core capability. No new user behavior or data category.

### G2 Feasibility and Risk: GO

**裁决**: PASS

Root cause is reproduced from aggregate production control-plane evidence.
The repair is limited to telemetry; recovery uses an existing audited Runtime
transition.

### G3 Tests: GO

**裁决**: PASS

The related Runtime, ToolGateway, write receipt, management API and PostgreSQL
concurrency suite passes: 181 passed, 3 skipped. Targeted tests first
reproduced both receipt-priority failures and the stale-generation resume race.

### G4 Safety Review: GO

**裁决**: PASS

The first review returned NO-GO because verified receipts could be marked as
failures and manual resume acknowledged an unreviewed generation. Both findings
are now covered by regression tests and remediated. The second review found
that request coercion still accepted boolean and floating-point generations;
the API now requires a strict integer, the service rejects non-exact integers,
and stale-generation rejection is covered in both paused and active states.

The independent re-review returned GO after confirming strict generation
validation, paused/active stale-generation coverage, receipt-priority
classification, content-free telemetry, and unchanged fail-closed write
boundaries. Production resume must stop on `409`; it must not automatically
adopt and retry a newer generation.

### G5 Deployment Health: GO

**裁决**: PASS

Backend commit `9d49567c0` was deployed through `deploy.sh -b`. The database
backup, 231-table restore rehearsal, encrypted offsite archive verification,
managed migration check, service restart, `60/60` health score, `22/22` skills
manifest check, and exact remote SHA verification all passed.

### G6 Production Verification: GO

**裁决**: PASS

After explicit authorization, the audited resume transition acknowledged exact
generation `2`. Runtime is active with acknowledged generation `2`. A
production Agent turn using the App Store review account created a test diet
record, persisted exactly one verified `diet_record` receipt, exposed the
record through the authenticated diet API, and then deleted it. Cleanup was
verified by a second list query. The verification created no reconciliation;
the only unresolved operation remains the pre-existing non-health
`draft_aigc_media` confirmation.
