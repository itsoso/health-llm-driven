# Runtime Local Rejection False Reconciliation

| 字段 | 值 |
|---|---|
| date | 2026-07-26 |
| status | complete |
| current_stage | S8 complete |
| owner_surface | Agent Runtime / health writes |

## Incident

Production Agent turns could read health data but new health writes displayed
`记录信息不可用`. A text diet turn was persisted as an input message but did
not create a Run or assistant response because the Runtime rollout circuit was
already paused.

## Root Cause

An earlier medication turn failed local plan preflight before any business API
dispatch. The Executor returned human-readable error text, but the shared write
outcome classifier did not recognize that exact local failure. Runtime
therefore classified three operations as `write_uncertain`, moved them to
`reconciliation_required`, and correctly paused all subsequent writes.

The production timeline proves those three Runtime operations had no side
effect:

- all three operations completed within the local preflight interval;
- the journal records the local `InvalidMedicationIntakePlan` before each
  failed tool result and no downstream dispatch;
- the nearby persisted medication records belong to a separate confirmed
  write intent and were created after the uncertain operations completed.

This dossier intentionally records only content-free operation, Run, intent and
timestamp evidence. Medication names, doses and health payloads are excluded.

## Change

- Return structured local medication rejections with
  `status=rejected`, `success=false` and `dispatch_started=false`.
- Give each local rejection a stable error code.
- Keep a legacy classifier marker so in-flight or older workers returning the
  previous text format are also treated as pre-dispatch rejections.
- Add a managed Runtime regression proving local medication plan rejection
  finishes as `failed/tool_rejected`, never `reconciliation_required`.

The global circuit remains fail-closed. Remote errors, ambiguous receipts and
any result that may have crossed the dispatch boundary remain uncertain and
continue to require reconciliation.

## Recovery Plan

1. Deploy the classifier and structured-result repair.
2. Resolve only the three evidence-backed operations as
   `verified_no_effect` through the audited Runtime service.
3. Confirm that no newly unacknowledged reconciliation remains. The known
   2026-07-23 non-health `draft_aigc_media` operation stays unchanged.
4. Resume using the exact current reconciliation generation.
5. Verify Runtime is active, generations are acknowledged, production health
   is green and the deployed SHA matches main.

## Gates

### G1 Product Admission: GO

**裁决**: PASS

Restores an existing Agent-native health-write capability. No new behavior or
data category is introduced.

### G2 Feasibility and Risk: GO

**裁决**: PASS

The failure is reproduced from production control-plane evidence and targeted
tests. The fix narrows deterministic local outcomes without weakening the
uncertain-write boundary.

### G3 Tests: GO

**裁决**: PASS

- Runtime API: 39 passed.
- Runtime Facade: 16 passed.
- Combined Runtime operations, rollout, API, Facade and reconciliation:
  157 passed.
- Write outcome, observe-only probes and medication batch flow: 64 passed.
- Ruff and Python compilation pass for every changed file.

The first targeted run failed before implementation with a local rejection
classified as uncertain; the same regression now passes.

### G4 Safety Review: GO

**裁决**: PASS

No business write path, authorization rule, idempotency policy or global
fail-closed behavior is relaxed. Legacy compatibility is limited to an exact
local no-write marker.

### G5 Deployment Health: GO

**裁决**: PASS

Backend commit `f29be0c96` was deployed through `deploy.sh -b -y`. The
database backup, 234-table restore rehearsal, encrypted offsite archive
verification, managed migration check, service restart, `60/60` health score,
`22/22` skills manifest check and exact remote SHA verification all passed.

### G6 Production Verification: GO

**裁决**: PASS

All three incident operations were resolved through the administrator audit API
as `verified_no_effect`. The exact-generation resume changed Runtime to
`enforce + active`, with reconciliation generation `3` acknowledged at `3`.

The already-persisted user diet turn was then resumed using its original
`client_turn_id`, rather than creating a duplicate input. Its Run completed as
`succeeded`, executed exactly one `health_record` operation and obtained one
verified `diet_record` receipt. Runtime remained active and no new
reconciliation generation was created. The pre-existing acknowledged
non-health `draft_aigc_media` reconciliation remains unchanged.
