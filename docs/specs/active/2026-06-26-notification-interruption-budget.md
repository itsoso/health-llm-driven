# Feature Spec: Notification And Interruption Budget Contract

> Status: draft
> Owner: Reva / Personal Health OS
> Updated: 2026-06-26
> Related PRD/PDD: docs/prd/2026-06-15-global-product-requirements.md · docs/prd/2026-06-16-health-leverage-action-os-pdd.md · docs/plans/2026-06-26-reva-global-product-architecture-plan.md
> Related code: backend/app/services/proactive_coordinator.py · backend/app/services/interruption_budget.py · backend/app/services/notification/push_service.py · backend/app/agents/audit.py

## 1. Decision

Create a structured interruption-budget contract for proactive health nudges so every P0/P1/P2 decision can explain whether it is allowed, why it was blocked, whether quiet hours were respected, and which reason/action/fallback surface the user should see.

## 2. Problem

The app already has several notification paths: PushService quiet-hours handling, proactive watcher budgets, Watch summaries, event reminders, and safety alerts. The rules exist but are split across services, making it hard to answer:

- Is this a P0 urgent alert, P1 actionable nudge, or P2 log-only signal?
- Did we respect sleep/quiet hours?
- If not pushed, what should the user do and where should the next surface show it?
- Are proactive notifications missing reason/action/fallback metadata?

That fragmentation directly increases sleep disruption risk and makes Watch/Rokid/Mobile behavior hard to reason about.

## 3. Requirement Admission

```yaml
RequirementAdmission:
  request: Continue global architecture implementation with notification and interruption budget
  classification: product_change
  first_user_fit: yes - user has Apple Watch / mobile / Rokid proactive reminders and sleep-disruption complaints
  core_loop_step: Health Agenda / Safety Gate / ExecutionEvent
  first_class_objects:
    - HealthAgendaItem
    - NotificationDecision
    - SafetyGuardian
    - ExecutionEvent
  target_surface: Backend source of truth -> Watch/Mobile/Mac/Rokid can render decision later
  source_of_truth: backend interruption_budget + proactive_coordinator
  safety_level: medium
  prescription_or_causal_verdict: none
  autonomy_tier: none
  evidence_provenance: deterministic tier, quiet-hours, busy-window, and audit-log counts
  claim_hedging: n/a
  verification_window: focused backend tests
  success_metric: P1/P2 do not wake the user during quiet hours; P0 remains explicit and capped
  added_user_burden: none
  burden_justification: only changes backend decision metadata and existing gates
  non_goals:
    - no new notification channel
    - no new P0 condition
    - no autonomous medical action
    - no client UI change in this slice
    - no hard failure for legacy watchers missing metadata yet
  smallest_end_to_end_slice: pure decision contract -> proactive coordinator decision -> existing bool gate
  stale_surface_to_remove_or_archive: none
  spec_required: yes
```

## 4. Tier Contract

| Tier | Meaning | Quiet Hours | Budget | Delivery |
|---|---|---|---|---|
| `P0` | urgent safety or must-response health item | may bypass only when explicitly P0 | global + P0 cap | immediate |
| `P1` | actionable but not urgent nudge | must block/delay | global cap | delay or fallback surface |
| `P2` | informational/log-only signal | no push | no push | log only |

## 5. Required Proactive Message Fields

P0/P1 proactive decisions should carry:

- `reason`: why the system wants to interrupt now.
- `action`: what the user can do next.
- `fallback_surface`: where the item should appear if it is delayed or suppressed.

This slice reports missing fields through `contract_complete=false` and `missing_contract_fields`. It does not hard-block legacy callers yet, to avoid silently disabling existing watcher paths before those callers are migrated.

## 6. Surface Contract

| Surface | Responsibility |
|---|---|
| Watch | Show only current executable P0/P1 actions; never show P2 as an interrupt. |
| Mobile | Primary fallback for delayed/suppressed P1 nudges. |
| Mac | Review/workbench surface for suppressed or historical decisions. |
| Rokid | Execution-only voice/vision flows; no noisy proactive broadcast until command-ready. |

## 7. Data Contract

```yaml
decision.allowed: boolean
decision.tier: P0 | P1 | P2
decision.blocked_reason: null | log_only | global_budget | tier_budget | quiet_hours | busy_window
decision.delivery_policy: immediate | delay_or_fallback | suppress | log_only
decision.quiet_hours_respected: boolean
decision.contract_complete: boolean
decision.missing_contract_fields: [reason, action, fallback_surface]
decision.contract.reason: string | null
decision.contract.action: string | null
decision.contract.fallback_surface: string | null
decision.budget.sent_global: integer
decision.budget.global_budget: integer
decision.budget.sent_tier: integer
decision.budget.tier_budget: integer | null
```

## 8. Safety Boundary

P0 is not expanded in this slice. Existing SafetyGuardian and PushService severity policies remain responsible for deciding whether a health event is critical. This contract only makes the interruption decision explainable and testable.

## 9. Acceptance Criteria

```gherkin
Given a P2 proactive signal
When interruption budget is evaluated
Then it is log_only and cannot push

Given a P1 nudge during quiet hours
When interruption budget is evaluated
Then it is blocked with quiet_hours and delay_or_fallback

Given a P0 urgent alert during quiet hours
When budgets allow and the contract is complete
Then it can bypass quiet hours, while reporting quiet_hours_respected=false

Given a P0/P1 nudge without reason/action/fallback_surface
When interruption budget is evaluated
Then missing fields are reported instead of hidden
```

## 10. Verification Plan

```bash
cd backend
DATABASE_URL=sqlite:///:memory: venv/bin/python -m pytest \
  tests/test_interruption_budget.py \
  tests/test_proactive_coordinator.py \
  tests/test_timeline_driver_schedule.py \
  tests/test_push_service_quiet_dedup.py \
  tests/test_quiet_hours_policy.py \
  -q --no-cov

python3 -m compileall -q backend/app/services/interruption_budget.py backend/app/services/proactive_coordinator.py

git diff --check
```

## 11. Rollout And Rollback

Roll out as additive backend metadata with no new push channel. Rollback by reverting `proactive_coordinator` to the previous bool logic and leaving PushService quiet-hours behavior unchanged.

## 12. Changelog

| Date | Change | Reason |
|---|---|---|
| 2026-06-26 | Initial draft | Phase 0 product-spine stabilization. |
