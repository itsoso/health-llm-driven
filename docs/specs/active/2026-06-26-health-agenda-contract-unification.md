# Feature Spec: Health Agenda Contract Unification

> Status: draft
> Owner: Reva / Personal Health OS
> Updated: 2026-06-26
> Related PRD/PDD: docs/prd/reva-personal-health-os-prd.md · docs/prd/2026-06-15-global-product-requirements.md · docs/specs/active/2026-06-22-time-driven-health-management.md · docs/plans/2026-06-26-reva-global-product-architecture-plan.md
> Related code: backend/app/services/agenda_service.py · backend/app/services/timeline_agenda_service.py · backend/app/models/health_event.py · backend/app/schemas/device_observation.py

## 1. Decision

Create a backend-owned `HealthAgendaItem` contract layer that defines canonical item statuses, execution event statuses, source references, and surface routing for Mobile, Watch, Mac, Rokid, Web, and external agents.

## 2. Problem

Reva already has Agenda, Smart Agenda, Timeline HealthEvent lifecycle, Watch actions, device observations, and Rokid execution flows. The behavior is mostly present, but the contract is spread across service dictionaries and comments:

- item statuses differ by source (`pending`, `due`, `overdue`, `completed`, `done`, `info`, `expired`);
- `ExecutionEvent` has been reconciled into `HealthEvent`, but client-facing event vocabulary is not centralized;
- source references are required by the PRD, but the allowed object types are not named in one place;
- surface routing exists inside `agenda_service`, so mobile/Mac/Watch/Rokid cannot confidently reuse the same rule.

If this stays fragmented, each new wearable or capture flow will make its own interpretation of "complete", "skip", "show on Watch", "open on Mac", or "safe for voice", and cross-device state will drift.

## 3. Requirement Admission

```yaml
RequirementAdmission:
  request: Start implementing the global product architecture by landing the first Phase 0 Agenda contract slice
  classification: product_change
  first_user_fit: yes - high-intensity users need one source of truth for daily execution across phone, Mac, Watch, and Rokid
  core_loop_step: Agenda top action / execution / review
  first_class_objects:
    - HealthAgendaItem
    - ExecutionEvent
    - HealthProtocol
    - HealthProblem
    - WriteIntent
  target_surface: Backend contract -> Mobile daily execution -> Watch/Rokid low-friction execution -> Mac review/import
  source_of_truth: backend agenda/timeline services
  safety_level: low
  prescription_or_causal_verdict: none
  autonomy_tier: manual_confirm for writes; suggest-only for projection metadata
  evidence_provenance: existing PRD/specs + current agenda/timeline implementation
  claim_hedging: n/a
  verification_window: same-day contract tests; later cross-surface UI tests
  success_metric: all surfaces can consume a stable agenda contract without duplicating status/source/surface logic
  added_user_burden: none
  burden_justification: internal contract only
  non_goals:
    - no new medical claims
    - no new autonomous write path
    - no database migration in the first slice
    - no client UI migration in the first slice
  smallest_end_to_end_slice: backend contract module + Smart Agenda contract metadata + regression tests
  stale_surface_to_remove_or_archive: none in this slice; later mobile/Mac/Watch local enums should be replaced by this contract
  spec_required: yes
```

## 4. Non-Goals

- Do not create a new `ExecutionEvent` table. The current `HealthEvent` agenda lifecycle remains the execution spine.
- Do not change medication, supplement, protocol, or review completion semantics.
- Do not add client UI work yet.
- Do not make Rokid voice completion more permissive.
- Do not infer that a health action worked; this only describes item/event state.

## 5. Product Object Mapping

| Object | Change |
|---|---|
| `HealthAgendaItem` | Centralize item status, terminal state, source reference, and surface routing contract. |
| `ExecutionEvent` | Centralize client-facing execution event vocabulary while keeping storage in `HealthEvent`. |
| `HealthProtocol` | Continues as a major source object for executable agenda items. |
| `HealthProblem` | Continues as a source object for checkup/follow-up agenda items. |
| `WriteIntent` | Remains the manual-confirm write boundary for future external actions; not changed in this slice. |

## 6. User Flow

```text
Agenda source object
  -> backend projection creates HealthAgendaItem
  -> contract normalizes status/source/surface metadata
  -> Mobile/Watch/Mac/Rokid render the same item semantics
  -> user completes/skips/snoozes/adjusts where allowed
  -> HealthEvent agenda lifecycle records the execution fact
  -> Review reads the same execution vocabulary
```

## 7. Surface Contract

| Surface | Responsibility | Contract |
|---|---|---|
| Watch | Low-friction execution | Read `surface.primary == watch` or alternates, show confirm/skip only when item capabilities allow. |
| Mobile | Primary daily product | Render full Agenda and Smart Agenda; call existing complete endpoints. |
| Mac | Workbench | Import/review/debug items where `mac` is an alternate or primary surface. |
| Web | Historical/admin | May render the same contract for compatibility, not the primary daily loop. |
| Backend | Source of truth | Own status, source, event, surface, and voice-safety decisions. |
| External agents | Controlled extension | Must preserve source refs and use manual-confirm write paths. |

## 8. Data Contract

```yaml
apis:
  changed:
    - GET /api/v1/agenda/today adds contract metadata on regular items
    - GET /api/v1/agenda/today?mode=smart adds contract metadata on smart items
events:
  execution_statuses:
    - done
    - skipped
    - snoozed
    - adjusted
    - auto_observed
    - confirmed
    - failed
models:
  no_new_tables: true
fields:
  item.status_canonical: canonical HealthAgendaItem status
  item.is_terminal: whether the item should disappear from active execution
  item.contract.version: health_agenda_contract_v1
  smart_item.status_canonical: same canonical status on Smart Agenda items
  smart_item.is_terminal: same terminal flag on Smart Agenda items
  smart_item.contract.version: health_agenda_contract_v1
enums:
  item_statuses:
    - pending
    - due
    - overdue
    - info
    - completed
    - skipped
    - snoozed
    - adjusted
    - auto_observed
    - expired
    - cancelled
    - blocked
backward_compatibility: existing status/source/surface fields remain unchanged
migration: none
```

## 9. Safety, Privacy, And Medical Boundary

This contract touches health action metadata but does not add health claims, diagnosis, medication dose changes, or red-flag clearance. Medication and supplement completion remains gated by existing source-specific write logic. Voice completion stays denied for medical-grade writers and checkup/follow-up items. User ownership stays enforced by existing authenticated Agenda/Timeline endpoints and source lookups.

## 10. AI Behavior

LLMs may explain agenda items and ask for missing context. They must not invent source references, mark an item complete, bypass deterministic safety gates, or reinterpret medical-grade source models as voice-actionable.

## 11. Acceptance Criteria

```gherkin
Given an agenda item with legacy status "done"
When the backend builds the contract metadata
Then the canonical item status is "completed" and the item is terminal

Given a Smart Agenda movement item
When it is converted to a smart item
Then the surface contract routes it primarily to Watch with Mobile and Rokid as alternates

Given a medication or supplement source model
When voice_actionable is computed
Then it remains false

Given the backend exports execution event vocabulary
When client code reads it
Then done/skipped/snoozed/adjusted/auto_observed/confirmed/failed are present
```

## 12. Verification Plan

```bash
cd backend
venv/bin/python -m pytest tests/test_agenda_contract.py tests/test_agenda.py -q --no-cov

python3 -m compileall -q backend/app/services/agenda_contract.py backend/app/services/agenda_service.py

git diff --check
```

## 13. Rollout And Rollback

Roll out as an additive backend contract. Existing clients keep consuming old fields. Rollback is safe by removing the added metadata and module import; no data migration is involved.

## 14. Open Questions

- Should clients later generate TypeScript/Swift enums from this backend contract?
- Should snooze/adjust be routed through `/agenda/complete` or a future `/agenda/items/{id}/events` endpoint?

## 15. Changelog

| Date | Change | Reason |
|---|---|---|
| 2026-06-26 | Initial draft | Start Phase 0 implementation from global product architecture plan. |
