# Prompt task completion

> Status: implementation
> Updated: 2026-10-02
> Controller: health-harness-orchestrator
> Dossier: ../../dossiers/2026-10-02-prompt-task-completion.md

## Decision and problem

Restore completion of explicitly authorized personal queries and corrections,
and add a manually confirmed, dated water backfill using existing WriteIntent.
Users currently repeat clear instructions because scope parsing or update
verification rejects them without a useful next step.

## Requirement admission

```yaml
RequirementAdmission:
  request: execute the production prompt improvement plan
  classification: reliability repair and bounded backfill
  first_user_fit: existing authenticated health-data user
  core_loop_step: observe, record, correct, verify
  first_class_objects: [WriteIntent, ExecutionEvent]
  target_surface: existing chat across Mobile, Web and Mac
  source_of_truth: owner-scoped records and verified server receipts
  safety_level: health-data read and write boundaries
  prescription_or_causal_verdict: none
  autonomy_tier: manual_confirm for batch backfill
  evidence_provenance: authenticated data and source-bound user instruction
  claim_hedging: report missing data or failed writes explicitly
  verification_window: same request or next explicit confirmation
  success_metric: verified task completion without no-progress retry
  added_user_burden: one dated batch preview or explicit target selection
  burden_justification: prevents wrong-day, duplicate and wrong-record writes
  non_goals: inferred clinical recovery, automatic medication changes, new devices
  smallest_end_to_end_slice: one owned read, one meal correction, one water batch
  stale_surface_to_remove_or_archive: none
  spec_required: yes
```

## Flow and contracts

Personal reads bind the authenticated principal and one canonical date/domain
scope. Requests outside supported authority receive a specific clarification;
neither model arguments nor prior unrelated turns widen the scope.

Meal corrections use the original baseline, one current owner-scoped record and
the user's absolute consumed fraction. Ambiguous candidates are presented for
selection. A prior meal receipt may resolve an immediate follow-up only when it
is server-owned, verified, fresh and belongs to the same conversation. Repeating
a correction must not multiply the fraction or create another meal.

Water backfill renders dated totals before confirmation. A lower bound does not
become an exact observed measurement. Dates, quantity and existing totals must be
resolved before creating an executable intent. Confirmation revalidates owner,
source, expiry, plan and unchanged baselines; writes are atomic and receipts
survive replay. Failure preserves an actionable state and never reports success.

Short read/format continuations use the latest server-bound owned read task,
with unchanged dates and domains. They do not resume writes or sync dispatch.

Existing chat text and existing intent confirmation interfaces carry the flow.
No native dependency or public API schema change is intended. A new intent kind
requires consistent server validation and clients must not mistake it for a
medication action. There is no schema migration in the planned slice.

## Safety and verification

- Negative cases: foreign owner, changed context owner, cancelled/quoted acts,
  unparsed restrictions, stale/forged references, arbitrary record IDs, concurrent
  baseline change, replay and partial failures.
- Use PostgreSQL for transaction/locking behavior; SQLite only for fast tests.
- Golden scenarios contain synthetic utterances and records, no raw production
  messages or health values. Measure verified outcomes rather than model finish.
- Independent fixed-commit safety review, exact CI, deployment health and real
  acceptance remain separate gates. No existing production record is changed
  merely to test a code repair.
