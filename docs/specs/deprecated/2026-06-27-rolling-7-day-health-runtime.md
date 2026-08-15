# Feature Spec: Rolling 7-Day Health Runtime

> Status: deprecated — superseded; do not implement
> Owner: Reva
> Updated: 2026-08-15
> Related PRD/PDD: docs/prd/reva-personal-health-os-prd.md, docs/prd/2026-06-27-code-derived-product-prd-and-10m-goal.md
> Related code: backend/app/api/agenda.py, backend/app/services/agenda_service.py, mobile/app/(tabs)/index.tsx, mobile/app/agenda.tsx, mobile/components/chat/cards/
> Superseded by: `docs/specs/active/2026-06-28-rolling-7-day-health-runtime.md` (shipped read-only runtime baseline). Health Day v2 convergence is owned by `docs/specs/active/2026-08-15-quiet-proactive-health-day.md`.

> ⚠️ 本文件保留为 2026-06-27 设计历史,不再是 active contract。不要从这里实现 `RollingHealthRuntimePlan`、Home IA 或 mutation;以两份 superseding specs 为准。

## 1. Decision

Make "滚动 7 天健康运行时编排" a first-class Reva capability: the system continuously compiles future health actions from real-time state and life context, while Home stays next-action-first.

## 2. Problem

Reva already has Agenda, Daily Plan, protocols, HealthKit, Watch, reminders, and Chat cards, but the user-facing information architecture can still degrade into a feature list, dashboard, or flat timeline. That creates too much cognitive load: users must decide which page matters, which metric matters, and what to do now.

The product goal is the opposite. Users should operate Reva with minimal effort:

- open Home and see the best next action;
- talk to Reva and receive contextual action cards;
- confirm, postpone, skip, ask why, or add one quick piece of context;
- let the system replan the next 7 days in the background.

If this is not specified before UI work, the Mobile redesign will likely become visually polished but structurally remain a function directory.

## 3. Requirement Admission

```yaml
RequirementAdmission:
  request: make Rolling 7-Day Health Runtime a first-class capability and use next-action-first UI
  classification: new_product_behavior
  first_user_fit: middle-aged health improvement users who want low cognitive load and daily execution help
  core_loop_step: decide_next_action_and_execute
  first_class_objects: [RollingHealthRuntimePlan, HealthAgendaItem, HealthProtocol, HealthProblem, ExecutionEvent, WriteIntent]
  target_surface: Mobile Home, Mobile Chat, Agenda drill-down, Watch execution, Backend planner/ranker
  source_of_truth: backend Agenda plus health runtime projection
  safety_level: medical_boundary
  prescription_or_causal_verdict: clinician_review_downgraded
  autonomy_tier: manual_confirm
  evidence_provenance: source object, wearable/source freshness, protocol, safety rule, calendar/location context
  claim_hedging: hedged
  verification_window: per action, default same-day to 7 days; program actions can point to 30/90 day review
  success_metric: Home renders one next action, Chat renders contextual action cards, skipped/completed events replan future items
  added_user_burden: low
  burden_justification: replaces feature navigation and manual planning with a small set of confirmations
  non_goals: no medication dose changes, no diagnosis, no automatic medical writes, no full timeline as Home primary UI
  smallest_end_to_end_slice: backend 7-day projection + mobile Home next-action card + Agenda drill-down + Chat card contract
  stale_surface_to_remove_or_archive: mobile pages that only duplicate function-directory access should be hidden, merged, or moved behind Agenda/Programs
  spec_required: yes
```

## 4. Non-Goals

- Do not turn Home into a full 7-day calendar.
- Do not create a generic reminder system detached from HealthTwin, Agenda, safety, and verification.
- Do not let LLMs freely generate arbitrary UI components; card types must be allowlisted.
- Do not infer medication ingestion from NFC or location alone.
- Do not change medication dose, prescribe drugs, diagnose disease, or clear red flags.
- Do not add proactive notifications outside the notification budget.

## 5. Product Object Mapping

| Object | Change |
|---|---|
| `RollingHealthRuntimePlan` | New product capability: rolling 7-day projection derived from Agenda, realtime state, calendar, location, devices, and Chat context. |
| `HealthAgendaItem` | Becomes the executable unit for next-action selection and 7-day drill-down. |
| `HealthProtocol` | Supplies repeatable routines such as hydration, meals, movement, medication, supplements, sleep, and measurement. |
| `HealthProblem` | Supplies chronic-risk priority, medication/follow-up constraints, red lines, and clinician escalation paths. |
| `HealthTwin` | Supplies current state, freshness, uncertainty, and missing data. |
| `SafetyGuardian` | Filters medication, symptom, training, supplement, and red-flag actions before display or write. |
| `ExecutionEvent` | Records completed, skipped, postponed, auto_observed, nearby_confirmed, user_confirmed, and uncertain outcomes. |
| `WriteIntent` | Handles calendar/reminder/external writes and any non-trivial action requiring confirmation. |

## 6. User Flow

```text
real-time state + agenda + protocol + calendar + location + chat context
  -> backend builds rolling 7-day health runtime projection
  -> deterministic safety and notification budget filters actions
  -> Home shows one next action
  -> Chat can generate contextual action cards
  -> user completes / postpones / skips / asks why / confirms with NFC or wearable
  -> ExecutionEvent or WriteIntent records the result
  -> future 7-day plan is recalculated
```

Example daily sequence:

```text
08:00 wake
  -> hydration card: warm water 200ml, derived from body weight, sleep, and morning state
08:05 medication window
  -> medication card: existing prescription name, purpose, safety note; NFC nearby + user confirm
08:10 movement window
  -> movement card: run / tai chi / ba duan jin / stretch based on age, HRV, sleep, weather, and existing plan
workday
  -> break, hydration, eye-rest, posture, lunch, nap, dinner, and wind-down cards based on calendar and state
```

## 7. Surface Contract

| Surface | Responsibility | Contract |
|---|---|---|
| Mobile Home | Primary next-action surface. | Render one next action, current state sentence, up to 3 evidence/freshness items, and 2-4 user participation items. |
| Mobile Chat | Contextual UI generator. | Convert user conversation into allowlisted action cards with explain/confirm/skip/replan actions. |
| Agenda | Full drill-down. | Show the rolling 7-day plan, grouped by day/time window, with source, safety, and replan reason. |
| Watch | Execution and passive capture. | Show next due item, confirm/later/skip, capture simple records, and mirror safety-limited summaries. |
| Backend | Source of truth. | Build projection, rank next action, apply safety and notification budgets, own event writes. |
| External agents | Controlled extension. | Read projection and propose changes only through WriteIntent/manual_confirm. |

## 8. Data Contract

```yaml
apis:
  - GET /api/v1/agenda/range?days=7&mode=runtime
  - GET /api/v1/agenda/today?mode=runtime
  - POST /api/v1/agenda/complete or equivalent source-specific completion
events:
  - runtime_action_impression
  - runtime_action_accepted
  - runtime_action_completed
  - runtime_action_postponed
  - runtime_action_skipped
  - runtime_plan_rebuilt
models:
  - no mandatory new table in first slice; projection can be virtual
fields:
  runtime_context:
    - current_state_summary
    - next_action
    - evidence
    - safety_boundary
    - freshness
    - surface
    - time_window
    - replan_reason
    - verification_window
  execution_event:
    - confirmation_mode: user_confirmed | nearby_confirmed | auto_observed | uncertain
enums:
  - skip_reason
  - confirmation_mode
backward_compatibility: default agenda endpoints remain unchanged unless mode=runtime is requested
migration: none for first slice
```

## 9. Safety, Privacy, And Medical Boundary

This feature touches medication, supplement, symptom, exercise, wearable, location, calendar, and potentially chronic disease context. It must follow these boundaries:

- SafetyGuardian filters red flags, medication/supplement conflicts, training risk, acute symptoms, and disease escalation before any action is displayed as executable.
- Medication cards can remind and explain an existing user-entered or clinician-provided regimen, but cannot change dose, prescribe, stop, or replace clinician review.
- NFC/location evidence can support adherence confidence but does not prove ingestion.
- Calendar/location usage must be consented, minimally retained, and auditable.
- Logs must not expose medication names, health details, exact location, tokens, or raw health text without masking.

## 10. AI Behavior

LLMs may:

- summarize why the next action matters;
- transform Chat context into candidate card descriptors;
- ask for missing low-risk context;
- explain evidence and uncertainty.

LLMs must not:

- generate arbitrary UI outside the card registry;
- bypass deterministic safety or notification budget;
- change medication dose or produce a diagnosis;
- claim causal effect without the evidence language gate;
- auto-write without WriteIntent/manual confirmation.

If LLM or card translation fails, the product degrades to deterministic Agenda next action and text explanation.

## 11. Acceptance Criteria

```gherkin
Given a user has valid agenda items, wearable freshness, and protocol actions
When Mobile Home loads
Then Home shows exactly one primary next action and not a full 7-day calendar.

Given a user asks "我今天很累,还要不要跑步"
When Chat receives the message
Then Reva returns text plus an allowlisted plan-adjust card that can downgrade, postpone, or explain the movement action.

Given a medication action is due
When the user approaches an NFC-tagged medication box
Then the event can be marked nearby_confirmed but still requires user_confirmed before being treated as taken.

Given a user skips an action with reason "太累"
When the runtime plan is rebuilt
Then the next 7-day projection reflects the skip reason instead of blindly repeating the same action.

Given a red-flag symptom or medication safety rule fails
When a candidate action is generated
Then the executable card is blocked or downgraded to clinician/escalation guidance.
```

## 12. Verification Plan

```bash
# Backend
cd backend && venv/bin/python -m pytest tests/test_agenda.py tests/test_today_timeline.py -q --no-cov

# Mobile
cd mobile && npm test -- --runInBand app/__tests__/home.test.tsx app/__tests__/system-map.test.tsx
cd mobile && npx tsc --noEmit --pretty false

# Repo hygiene
git diff --check
```

Manual checks:

- Simulator walkthrough: Home, Agenda drill-down, Chat card, Watch summary if available.
- Dynamic click audit after this spec is accepted: traverse every Mobile page, screenshot each state, compare against next-action-first IA.

## 13. Rollout And Rollback

First slice should be opt-in by `mode=runtime` or a mobile feature flag. Rollback returns Home to the existing Daily Artifact / Agenda behavior. Pages that duplicate function-directory access should be hidden only after dynamic click audit confirms safe replacement paths.

## 14. Open Questions

- Should the first runtime projection be purely virtual, or should we persist daily snapshots for audit and comparison?
- Which three card types ship first: next action, plan adjust, medication confirm, movement start, meal decision, hydration, or rest break?
- How much calendar/location detail can be used before the value no longer justifies privacy sensitivity?
- Should Home expose 2 or 4 secondary participation items beneath the primary next action?

## 15. Changelog

| Date | Change | Reason |
|---|---|---|
| 2026-06-27 | Initial draft | Make rolling 7-day health runtime orchestration a first-class Reva capability before UI redesign. |
| 2026-08-15 | Mark superseded | 2026-06-28 spec is the shipped runtime authority; Health Day v2 now has a separate convergence spec, avoiding two same-name active truths. |
