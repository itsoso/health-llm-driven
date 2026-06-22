# Feature Spec: Smart Agenda

> Status: draft
> Owner: Reva
> Updated: 2026-06-22
> Related PRD/PDD: docs/prd/reva-personal-health-os-prd.md
> Related code: backend/app/api/agenda.py, backend/app/services/agenda_service.py

## 1. Decision

Build a backend `mode=smart` agenda projection that ranks today's health work into a small set of executable, verifiable items.

## 2. Problem

The current agenda tells the user what exists today, but it does not decide what deserves attention first, why now, where to execute it, or how the system will verify the result. For a middle-aged user trying to improve health over months, a flat calendar becomes another checklist instead of a behavior engine.

## 3. Requirement Admission

```yaml
RequirementAdmission:
  request: make calendar and planning more intelligent
  classification: behavior_execution
  first_user_fit: middle-aged health improvement with low daily cognitive load
  core_loop_step: decide_next_action
  first_class_objects: [HealthAgendaItem, LeverageAction, ExecutionEvent]
  target_surface: backend first, mobile/watch/rokid consumers later
  source_of_truth: existing agenda sources plus DailyOperatingPlan actions
  safety_level: behavior_guidance
  prescription_or_causal_verdict: no
  autonomy_tier: suggest_or_confirm
  evidence_provenance: source object and deterministic ranking fields
  claim_hedging: health-management guidance, not diagnosis or treatment
  verification_window: per item, default 1-14 days
  success_metric: smart top_items include why_now, do_now, verify_by, surface, replan_policy
  added_user_burden: low
  burden_justification: reduces daily decision burden by selecting top actions
  non_goals: no new reminders, no LLM planner, no persistence migration
  smallest_end_to_end_slice: GET /agenda/today?mode=smart
  stale_surface_to_remove_or_archive: none
  spec_required: yes
```

## 4. Non-Goals

- No new database table or migration in the first slice.
- No medical diagnosis, medication dose change, or causal verdict.
- No automatic execution without user confirmation.
- No replacement for existing `/agenda/today` default response.

## 5. Product Object Mapping

| Object | Change |
|---|---|
| `HealthAgendaItem` | Adds virtual smart projection fields for execution and verification. |
| `LeverageAction` | Daily Operating Plan actions can appear as smart agenda items. |
| `ExecutionEvent` | Future completion/skipping should route to source-specific events. |
| `HealthProblem` | Due and overdue followups rank high in smart agenda. |
| `HealthProtocol` | Due protocols remain source facts and can be ranked into smart agenda. |

## 6. User Flow

```text
open today's agenda
  -> backend builds regular agenda and Daily Plan actions
  -> deterministic ranking selects top actions
  -> target surface displays why_now and do_now
  -> user completes, snoozes, or skips
  -> source event verifies or replans
```

## 7. Surface Contract

| Surface | Responsibility | Contract |
|---|---|---|
| Mobile | Primary consumer for the first release. | Call `/agenda/today?mode=smart`, render `smart.top_items`. |
| Watch | Execute small movement, hydration, supplement, and reminder items later. | Use `surface.primary=watch` as routing hint. |
| Rokid | Ambient food and workout capture later. | Use `surface.alternates` until glasses paths are stable. |
| Backend | Own ranking and item contract. | Preserve regular agenda by default. |

## 8. Data Contract

```yaml
apis:
  - GET /api/v1/agenda/today?mode=smart&max_items=3
events: []
models: []
fields:
  smart.top_items:
    - id
    - source
    - why_now
    - do_now
    - verify_by
    - replan_policy
    - surface
    - autonomy_tier
backward_compatibility: /agenda/today without mode remains unchanged
migration: none
```

## 9. Safety, Privacy, And Medical Boundary

This feature touches personal health behavior data and follow-up reminders. It must not claim diagnosis, treatment, or medication changes. It only ranks already-authorized internal health objects and deterministic Daily Plan actions. User data isolation continues through the authenticated user id used by the agenda API.

## 10. AI Behavior

No LLM is used in the first slice. Future LLM planners may suggest item wording, but deterministic source facts, safety filters, and user confirmation must remain authoritative.

## 11. Acceptance Criteria

```gherkin
Given a user has protocols, due followups, and Daily Plan actions
When the client calls /agenda/today?mode=smart
Then the response includes ranked smart.top_items with why_now, do_now, verify_by, replan_policy, and surface.

Given an existing client calls /agenda/today without mode
When the request succeeds
Then the response remains the regular agenda response.
```

## 12. Verification Plan

```bash
cd backend && venv/bin/python -m pytest tests/test_agenda.py tests/test_agenda_range_complete.py tests/test_today_timeline.py -q --no-cov
cd backend && venv/bin/python -m compileall -q app/api/agenda.py app/services/agenda_service.py tests/test_agenda.py tests/test_agenda_range_complete.py
git diff --check
```

## 13. Rollout And Rollback

The feature is opt-in by query parameter. Rollback is removing or ignoring `mode=smart`; default agenda clients are unaffected.

## 14. Open Questions

- Should Mobile replace the regular agenda page with smart top items, or show both?
- Should Watch own hydration, supplements, and movement execution cards first?
- Should skipped smart items write `InterventionEvent` or source-specific events in the next slice?

## 15. Changelog

| Date | Change | Reason |
|---|---|---|
| 2026-06-22 | Initial draft | Define the first backend smart agenda slice. |
