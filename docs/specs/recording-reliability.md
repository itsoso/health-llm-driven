# Feature Spec: Mixed recording reliability

> Status: implementation
> Updated: 2026-10-24
> Dossier: ../dossiers/2026-10-24-recording-reliability.md

## Decision and problem

Parse explicitly stated intake facts once, authorize each fact, and present the verified result of each write. Current fixed-order parsing rejects ordinary word order; a verified sibling and a failed action can produce contradictory status. Replaying the original mixed request risks duplicate writes.

## Requirement Admission

```yaml
RequirementAdmission:
  request: Improve mixed records, safe partial recovery, and truthful status
  classification: existing core-loop reliability
  first_user_fit: users recording their own completed intake
  core_loop_step: record and verify
  first_class_objects: [WriteIntent, ExecutionEvent]
  target_surface: mobile conversation and backend gateway
  source_of_truth: authenticated persistence receipts and durable checkpoints
  safety_level: health write
  prescription_or_causal_verdict: none
  autonomy_tier: explicit user-requested write and retry
  evidence_provenance: current-turn facts and owner-scoped execution evidence
  claim_hedging: no saved claim without verified receipt
  verification_window: same source turn; bounded retry validity
  success_metric: all supported explicit facts persisted once; zero unauthorized writes
  added_user_burden: clarification only for incomplete or ambiguous facts
  burden_justification: prevent inferred quantities and duplicate writes
  non_goals: [new supplement vocabulary, dosage advice, inferred intake dates, real health data evaluation]
  smallest_end_to_end_slice: explicit mixed supplement and drink records with per-item evidence
  stale_surface_to_remove_or_archive: whole-turn unexecuted label when a sibling is verified
  spec_required: yes
```

## Product objects and flow

| Object | Contract |
|---|---|
| WriteIntent | Complete bounded parse; exact owner, item, amount, unit and date authorization |
| ExecutionEvent | Per-operation verified, definite failure, or reconciliation required |

User records explicit facts → complete typed plan → authenticated single-item gateway → durable checkpoint and receipt → truthful per-item result → explicit retry of proven unwritten items only.

## Surface contract

Backend owns authorization, idempotency, outcome and recovery binding. Mobile preserves the server terminal state and projects verified receipts from that same turn. A success receipt never proves all items complete. Unknown dispatch disables replay. Historical message restoration uses the same projection as streaming completion.

## Safety and scope

The first grammar retains the established name vocabulary, rejects unconsumed text, negation, other people, duplicate names and more than eight items. No batching, quantity inference or unit/strength conversion is authorized. Recovery must revalidate source ownership and original time context; missing evidence is not proof of no write. Logs and recovery metadata contain identifiers and hashes, not duplicated health text.

A complete single supplement fact also controls routing before meal-goal
compilation: the optional category label cannot change the record type. Explicit
vitamin subtypes remain part of the product identity, without inferred alias
equivalence or dosage conversion. Authorization, repair and persistence consume
that same identity; model-selected diet tools cannot override it.

## Acceptance and delivery

Tests cover changed word order, oral connectors, multiple items, exact quantities, unknown residue, malicious extra arguments, other owners, partial and uncertain writes, replay and historical UI. PostgreSQL verifies persistence semantics. Independent safety review, full CI, applicable live synthetic model validation, production receipt and compatible OTA are separate gates. Infrastructure optimization follows this behavioral repair in a separate reviewed change.
