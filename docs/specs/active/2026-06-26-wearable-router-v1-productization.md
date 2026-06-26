# Feature Spec: Wearable Router v1 Productization

> Status: draft
> Owner: Reva / Personal Health OS
> Updated: 2026-06-26
> Related PRD/PDD: docs/prd/reva-personal-health-os-prd.md · docs/prd/2026-06-15-global-product-requirements.md · docs/plans/2026-06-15-multi-wearable-health-router-roadmap.md · docs/plans/2026-06-26-reva-global-product-architecture-plan.md
> Related code: backend/app/services/device_source_priority.py · backend/app/services/device_comparison_service.py · backend/app/services/recovery_decision.py · backend/app/services/agenda_service.py · backend/app/models/daily_health.py

## 1. Decision

Productize the existing multi-source wearable utilities into a minimal backend `WearableRouter` service that emits metric-level `winning_source`, freshness, agreement, confidence, and data-quality issues for recovery, training, and sleep decisions.

## 2. Problem

The repo already has good pieces:

- `GarminData.data_source` stores Apple Watch / Garmin / RingConn / other daily rows side-by-side.
- `device_source_priority.py` knows which source should win by metric.
- `device_comparison_service.py` computes multi-device agreement.
- `recovery_decision.py` uses agreement to adjust training confidence.

But the product contract is still implicit. Surfaces cannot ask, "Which device did we trust for HRV?", "Is this data stale?", or "Should the user see a data-quality agenda item?" without reimplementing local logic.

If this remains implicit, Reva will keep looking like multiple wearable dashboards rather than one Health OS state engine.

## 3. Requirement Admission

```yaml
RequirementAdmission:
  request: Continue global architecture implementation with Wearable Router v1
  classification: product_change
  first_user_fit: yes - the first wedge uses Apple Watch, Garmin, RingConn, and lab/wearable data together
  core_loop_step: Health Twin / Safety Gate / Agenda top action / verification
  first_class_objects:
    - WearableRouter
    - HealthAgendaItem
    - SafetyGuardian
    - HealthTwin
    - ExecutionEvent
  target_surface: Backend source of truth -> Agenda data-quality item -> Mobile/Watch/Mac/Rokid explanation later
  source_of_truth: backend wearable_router service using existing GarminData multi-source rows
  safety_level: low
  prescription_or_causal_verdict: none
  autonomy_tier: none
  evidence_provenance: wearable rows with source labels + deterministic source-priority rules
  claim_hedging: n/a
  verification_window: same-day focused backend tests
  success_metric: key wearable metrics expose source/freshness/confidence and stale/conflict items reach Agenda
  added_user_burden: none unless a data-quality issue is shown
  burden_justification: issue appears only when existing data is stale/conflicting, not for brand-new users with no wearable history
  non_goals:
    - no new device integration
    - no medical diagnosis or red-flag clearance
    - no database migration
    - no client UI migration
    - no replacement of SafetyGuardian
  smallest_end_to_end_slice: service snapshot -> data_quality issue -> Agenda item
  stale_surface_to_remove_or_archive: none in this slice
  spec_required: yes
```

## 4. Non-Goals

- Do not add Oura/WHOOP/CGM ingestion.
- Do not replace `recovery_decision.py`.
- Do not average conflicting devices.
- Do not generate data-quality nags for users with no wearable history.
- Do not use LLMs to choose a winning source.
- Do not make any diagnosis from wearable metrics.

## 5. Product Object Mapping

| Object | Change |
|---|---|
| `WearableRouter` | New service-level contract for metric source arbitration and freshness/confidence. |
| `HealthAgendaItem` | Stale/conflicting wearable data can become a `data_quality` agenda item. |
| `SafetyGuardian` | Safety-sensitive metrics keep safety policy metadata, but no safety rule changes in this slice. |
| `HealthTwin` | Future consumer of router confidence; not modified in this slice. |
| `ExecutionEvent` | No storage change; future data-quality dismissal/confirmation can use the existing lifecycle. |

## 6. User Flow

```text
wearable rows from GarminData
  -> WearableRouter chooses winning source per metric
  -> router computes freshness / agreement / confidence / safety policy
  -> stale or conflicting key metrics create data_quality issues
  -> Agenda shows a low-burden data_quality item
  -> user can sync/check device before trusting a high-confidence action
```

## 7. Surface Contract

| Surface | Responsibility | Contract |
|---|---|---|
| Mobile | Daily explanation | Show data-quality item and later source details. |
| Watch | Low-friction execution | May show freshness warning, not detailed debugging. |
| Mac | Workbench | Later can inspect router snapshot and source disagreement. |
| Backend | Source of truth | Own metric arbitration, freshness, confidence, and issue generation. |

## 8. Data Contract

```yaml
apis:
  changed:
    - GET /api/v1/agenda/today may include data_quality items from wearable_router
events: none
models:
  no_new_tables: true
fields:
  router.metric.value: selected metric value
  router.metric.winning_source: chosen source label
  router.metric.source_reason: why this source won
  router.metric.freshness_hours: approximate hours since metric date
  router.metric.reliability: high | medium | low
  router.metric.agreement_score: 0..1 | null
  router.metric.confidence: high | medium | low | missing
  router.metric.safety_policy: normal | worst_value | clinician_ground_truth
  router.data_quality_issues[].kind: stale | conflict
backward_compatibility: existing GarminData and agenda fields remain unchanged
migration: none
```

## 9. Safety, Privacy, And Medical Boundary

This slice reads health wearable data and exposes source metadata. It does not create diagnosis, treatment advice, medication changes, or red-flag clearance. SpO2 and other safety-sensitive metric semantics are inherited from deterministic source-priority rules; SafetyGuardian remains the only place for escalation decisions.

## 10. AI Behavior

LLMs may summarize the router explanation. They must not override `winning_source`, remove stale/conflict caveats, or claim that wearable conflicts prove a disease state.

## 11. Acceptance Criteria

```gherkin
Given same-day RingConn and Garmin HRV rows
When the router builds a snapshot
Then HRV uses RingConn as winning_source and reports agreement/confidence metadata

Given only stale wearable data for a key recovery metric
When Agenda is built
Then a data_quality item explains the stale metric instead of silently using high confidence

Given conflicting HRV values from two sources
When the router builds data-quality issues
Then it creates a conflict issue and does not average the sources into a fake value
```

## 12. Verification Plan

```bash
cd backend
DATABASE_URL=sqlite:///:memory: venv/bin/python -m pytest tests/test_wearable_router.py tests/test_agenda.py tests/test_agenda_contract.py -q --no-cov

python3 -m compileall -q backend/app/services/wearable_router.py backend/app/services/agenda_service.py

git diff --check
```

## 13. Rollout And Rollback

Roll out as additive backend logic. If stale/conflict items are too noisy, rollback by removing the `wearable_router` agenda projection; the router service can remain for diagnostics.

## 14. Open Questions

- Should a later endpoint expose full router snapshots to Mac/Web for diagnostics?
- Should expected wearable sources be user-configurable before missing-source issues are enabled?
- Should the Twin consume router confidence directly in the next slice?

## 15. Changelog

| Date | Change | Reason |
|---|---|---|
| 2026-06-26 | Initial draft | Continue Phase 0 global product spine implementation. |
