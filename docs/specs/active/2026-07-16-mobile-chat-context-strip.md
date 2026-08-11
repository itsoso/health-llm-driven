# Feature Spec: Mobile Agent Context Strip

> Status: approved
> Owner: Codex
> Updated: 2026-07-16
> Related PRD/PDD: `docs/specs/reva-product-governance-spec.md`
> Related code: `mobile/app/(tabs)/chat.tsx`, `mobile/components/chat/ChatTodayFocusCard.tsx`

## 1. Decision

Replace the permanent Mobile Agent Today Focus card with a conditional,
single-row context strip and keep the full plan behind the header menu.

## 2. Problem

The current card repeats the same title, action, and aggregate counters above
every conversation. It consumes first-screen space and creates visual fatigue;
its hidden launcher preserves the clutter after dismissal.

## 3. Requirement Admission

```yaml
RequirementAdmission:
  request: reduce repeated Today Focus UI on Mobile Agent chat
  classification: mobile product behavior and information hierarchy
  first_user_fit: high-frequency Mobile Agent users
  core_loop_step: agenda awareness -> conversation or Today execution
  first_class_objects: [HealthAgendaItem, LeverageAction]
  target_surface: Mobile Agent chat
  source_of_truth: existing Today timeline and active Agent turn state
  safety_level: low
  prescription_or_causal_verdict: none
  autonomy_tier: none
  evidence_provenance: existing timeline status, severity, scheduled timestamp
  claim_hedging: preserve backend-authored copy; do not invent health claims
  verification_window: immediate UI state
  success_metric: no permanent header card; qualified states remain visible
  added_user_burden: one menu tap when opening the full Today plan
  burden_justification: removes repeated first-screen clutter
  non_goals: [backend ranking, health writes, voice input, Today page redesign]
  smallest_end_to_end_slice: visibility policy + conditional strip + menu entry
  stale_surface_to_remove_or_archive: [full chat focus card, hidden launcher, focus loading shell]
  spec_required: yes
```

## 4. Product Object Mapping

| Object | Change |
|---|---|
| `HealthAgendaItem` | Show only when due, overdue, safety-relevant, or precisely near-term and executable. |
| `LeverageAction` | Full action remains available on the Today surface. |

## 5. User Flow

```text
timeline or Agent turn state
  -> deterministic client visibility policy
  -> optional single-row context strip
  -> open Today, retry, or dismiss
  -> existing Today execution and verification flow
```

## 6. Surface And Data Contract

| Surface | Responsibility | Contract |
|---|---|---|
| Mobile | Conditional strip and stable menu entry | No reserved space when hidden. |
| Backend | Existing state only | No API, schema, event, or migration change. |

## 7. Safety And AI Boundary

The client does not generate medical claims or change health data. Safety/high
severity outranks Agent and schedule states. Missing or ambiguous timestamps do
not qualify as near-term actions. Failures remain visible and retryable.

## 8. Acceptance Criteria

```gherkin
Given a normal conversation without a qualified timeline state
When the Agent page renders
Then no Today Focus card, launcher, skeleton, or reserved space is visible

Given an active or recoverable failed Agent turn
When the state changes
Then one compact status strip appears and later disappears with the state

Given a due, overdue, high-severity, or precisely scheduled near-term item
When the timeline loads
Then one direct context strip appears using deterministic priority

Given a time-window-only advisory or non-executable rhythm item
When it is within the near-term horizon
Then it does not occupy the Mobile Agent header

Given the user dismisses an action strip
When the strip closes
Then no hidden placeholder replaces it and the full plan remains available at 更多操作 > 今日计划
```

## 9. Verification And Rollout

Run focused Jest tests, TypeScript, targeted ESLint, `git diff --check`, and
iPhone simulator screenshots. This is a JS/TS/UI-only change and may roll out
through the production Mobile OTA channel. Rollback restores the previous
bundle; no data migration is required.

## 10. Changelog

| Date | Change | Reason |
|---|---|---|
| 2026-07-16 | Approved conditional context strip | Remove repeated first-screen UI while preserving timely state. |
| 2026-07-17 | Restricted near-term strip to executable precise schedules | Keep time-window rhythm guidance from becoming a repetitive chat notification. |
| 2026-08-11 | Approved visual refinement of the existing strip | Remove redundant normal-state iconography, support two-line task titles, and announce transient Agent status without changing visibility priority or source data. |
