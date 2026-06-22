# Feature Spec: Mac Calendar Sync

> Status: draft
> Owner: Reva
> Updated: 2026-06-22
> Related PRD/PDD: docs/prd/reva-personal-health-os-prd.md, docs/specs/archive/2026-06-18-calendar-v2.md
> Related code: apps/mac/Sources/HealthAgentMac/Features/Calendar/CalendarView.swift, apps/mac/Sources/HealthAgentMacCore/CalendarClient.swift, backend/app/api/calendar.py

## 1. Decision

Add a Mac calendar surface for read-only external calendar source management, manual sync, and upcoming-event inspection.

## 2. Problem

Calendar v2 already supports CalDAV/ICS sources, encrypted event sync, and mobile source management. Mac users still cannot connect, pause, delete, or manually sync calendar sources from the desktop app, even though Mac is where planning and review often happen. Without this surface, schedule-aware health planning remains split between mobile and backend behavior.

## 3. Requirement Admission

```yaml
RequirementAdmission:
  request: mac calendar feature including calendar sync
  classification: planning_context_integration
  first_user_fit: middle-aged health improvement with schedule-aware execution
  core_loop_step: collect_context
  first_class_objects: [ExecutionEvent, HealthAgendaItem]
  target_surface: Mac
  source_of_truth: backend CalendarSource and CalendarEvent tables through /calendar APIs
  safety_level: personal_schedule_pii
  prescription_or_causal_verdict: no
  autonomy_tier: user_confirmed_sync
  evidence_provenance: external calendar source id and backend sync result
  claim_hedging: schedule context only, not medical advice
  verification_window: immediate API response plus next-seven-day event view
  success_metric: Mac can list/add/pause/delete sources, run sync, and show upcoming events
  added_user_burden: low
  burden_justification: one desktop control surface replaces hidden API/mobile-only management
  non_goals: no write-back, no event creation, no LLM access to raw event details
  smallest_end_to_end_slice: Mac Calendar page using existing backend APIs
  stale_surface_to_remove_or_archive: none
  spec_required: yes
```

## 4. Non-Goals

- Do not write to external calendars.
- Do not create or edit system-native Reva calendar events.
- Do not expose event title/location/description to Agent or LLM flows.
- Do not add local EventKit sync in this slice.

## 5. Product Object Mapping

| Object | Change |
|---|---|
| `ExecutionEvent` | Calendar events become schedule context for future health execution timing. |
| `HealthAgendaItem` | Existing agenda/timeline surfaces can use synced calendar context to avoid collisions. |
| `SafetyGuardian` | Privacy boundary remains: LLM paths use the calendar privacy seam, not raw event details. |

## 6. User Flow

```text
open Mac Calendar
  -> list safe CalendarSource metadata
  -> add or pause a read-only CalDAV/ICS source
  -> manually sync through backend
  -> view upcoming event details on the user's own client
  -> Today Timeline and agenda planning can account for schedule context
```

## 7. Surface Contract

| Surface | Responsibility | Contract |
|---|---|---|
| Mac | Manage calendar sources and run manual sync. | Calls `/calendar/sources`, `/calendar/sync`, and `/calendar/events`; never writes events. |
| Mobile | Existing source management and timeline consumer. | Remains compatible with the same backend contracts. |
| Backend | Owns encrypted credentials, event sync, user isolation, and privacy seam. | Returns safe source metadata; detailed events only to authenticated owner clients. |
| External agents | Must not read raw event details. | Use `calendar_event_for_llm` busy-window output only. |

## 8. Data Contract

```yaml
apis:
  - GET /calendar/sources
  - POST /calendar/sources
  - PUT /calendar/sources/{source_id}
  - DELETE /calendar/sources/{source_id}
  - POST /calendar/sync
  - GET /calendar/events?from=YYYY-MM-DD&to=YYYY-MM-DD
events: []
models:
  - CalendarSource
  - CalendarEvent
fields:
  CalendarSource.sync_enabled: pause/resume import
  CalendarSource.last_sync_at: display freshness
  CalendarSource.last_error: display per-source sync failures
backward_compatibility: existing mobile and backend contracts unchanged
migration: none
```

## 9. Safety, Privacy, And Medical Boundary

Calendar data is personal schedule PII. The Mac app may show raw event details only to the logged-in owner through authenticated client APIs. It must not route raw title, location, description, attendee, or uid fields into Agent prompts. Health recommendations must treat calendar events as scheduling constraints, not medical evidence.

## 10. AI Behavior

No LLM is involved in this slice. Future agent features must use the existing calendar privacy seam and should only receive busy windows and source labels.

## 11. Acceptance Criteria

```gherkin
Given a logged-in Mac user has calendar sources
When they open Calendar
Then sources, sync status, and upcoming events are visible.

Given the user adds an ICS source
When the form is submitted with an https URL
Then Mac posts to /calendar/sources and refreshes the list.

Given the user clicks Sync Now
When /calendar/sync succeeds
Then the page refreshes sources and next-seven-day events.
```

## 12. Verification Plan

```bash
cd apps/mac && swift test --filter 'HealthAgentMacCoreTests.APIClientTests/testAPIClientPutEncodesJSONBody|HealthAgentMacCoreTests.CalendarClientTests|HealthAgentMacCoreTests.HealthAgentMacCoreTests/testSidebarDestinationsCoverMobileParityAndDesktopWorkflows'
cd apps/mac && swift test
git diff --check
```

## 13. Rollout And Rollback

The feature is a Mac-only surface over existing backend APIs. Rollback can hide the `calendar` sidebar destination while leaving backend and mobile behavior unchanged.

## 14. Open Questions

- Should Mac later support local Apple Calendar/EventKit import, or should all external calendars continue through backend sources only?
- Should sync failures create agenda items when a calendar source remains stale?

## 15. Changelog

| Date | Change | Reason |
|---|---|---|
| 2026-06-22 | Initial draft | Define the Mac source-management and sync slice. |
