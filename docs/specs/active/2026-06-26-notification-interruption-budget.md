# Feature Spec: Notification And Interruption Budget Contract

> Status: active · code-aligned baseline
> Owner: Reva / Personal Health OS
> Updated: 2026-08-15
> Related PRD/PDD: docs/prd/2026-06-15-global-product-requirements.md · docs/prd/2026-06-16-health-leverage-action-os-pdd.md · docs/plans/2026-06-26-reva-global-product-architecture-plan.md · docs/specs/active/2026-08-15-quiet-proactive-health-day.md
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
| `P0` | urgent safety or must-response health item | may bypass ordinary quiet hours only when explicitly P0; never bypasses the morning sleep floor | global + P0 cap | immediate when allowed |
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
decision.blocked_reason: null | log_only | morning_sleep_floor | global_budget | tier_budget | quiet_hours | busy_window
decision.delivery_policy: immediate | delay_or_fallback | suppress | log_only
decision.quiet_hours_respected: boolean
decision.evaluation_status: ok | degraded  # planned additive field for new callers
decision.failed_checks: []                 # quiet_hours / morning_sleep_floor / budget / busy_window
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

### 8.1 Failure seam for new proactive callers

Legacy `can_notify_proactively` currently fails open for P0/P1 when budget/policy evaluation throws, and individual quiet-hours/busy checks can degrade to “not quiet/not busy”. That behavior remains documented historical compatibility, not the contract for new quiet-proactive Health Day P1 paths.

Before Health Day proactive rollout, the structured decision must expose `evaluation_status` and `failed_checks`. New P1/morning-plan callers fail to `delay_or_fallback` when any quiet-hours, morning-floor or budget check is degraded; they keep the item in XiaoBa/Today and do not push. This additive tightening does not redefine existing P0 safety behavior or silently suppress prescribed reminders; that seam requires its own G2 decision.

### 8.2 Health Day G2 blockers(not current code claims)

The current P0 bucket mixes true emergency safety with scheduled-required medication/recheck reminders. Before Health Day Phase 4, the contract must add an orthogonal delivery class:

- `emergency_safety`:dedicated, separately reviewed escalation/flood-control policy; not silently delayed by an ordinary wellness weekly budget or sleep-floor rule;
- `scheduled_required`:occurrence stays visible with due/unreceived/overdue/recovery state; delivery follows explicit clinical/user timing policy and is not promoted to emergency by `fixed` alone;
- `actionable` and `informational`:map to ordinary P1 and P2 behavior.

New producers also require an owner-scoped atomic reservation/outbox and typed state/receipt model. Budget is reserved atomically with a stable episode/occurrence key; concurrent workers cannot both pass count-then-send; delayed flush conditionally claims work; retryable failure reuses the same key; provider acceptance, device delivery/visibility and user action remain separate receipts. Missing required contract fields fail new non-emergency callers to fallback; emergency copy uses a deterministic privacy-safe template plus stable `rule_id/occurrence_id`.

### 8.3 Planned canonical notification lifecycle(G2 exit contract)

The outbox owns delivery execution state; receipts are monotonic evidence attached to the same operation and must not be collapsed into a single `sent/delivered` claim:

```yaml
notification_operation:
  operation_id: opaque server id
  user_id: authenticated owner
  channel: push | watch | other_reviewed_channel
  candidate_key: stable occurrence_id + rule + scheduled delivery slot + notification_semantic_revision; excludes snapshot generation and non-material source metadata revision
  delivery_class: emergency_safety | scheduled_required | actionable | informational
  policy_generation: interruption contract version
  contract_reason_code: controlled enum
  fallback_surface: controlled enum
  authorized_snapshot_generation: most recently revalidated authorizing generation
  source_revision: canonical source revision
  notification_semantic_revision: changes only when material delivery content/timing/class changes
  occurrence_id: owner-scoped occurrence
  actionable_at_reservation: boolean
  safety_classification_rule_id: allowlisted deterministic rule id
  safety_rule_version: version
  safety_episode_id: stable episode id
  valid_until: delivery deadline
  state: reserved | sending | provider_accepted | verifying_unknown | failed_retryable | failed_terminal | expired | suppressed | superseded | cancelled
  attempt_count: integer
  next_attempt_at: nullable timestamp
  expires_at: timestamp
  provider_operation_id: nullable opaque id
unique_constraint: [user_id, channel, candidate_key]
```

Reservation is one PostgreSQL transaction:insert the unique operation and atomically reserve the applicable global/tier counter under row lock or an equivalent conditional update. A uniqueness conflict returns the existing owner-scoped operation;it never consumes budget twice. `failed_retryable` and `verifying_unknown` retain the reservation. A terminal pre-acceptance failure releases it exactly once in the same state transition;`provider_accepted` consumes it. The exact counter period/timezone is part of `policy_generation`.

Immediately before every provider egress(including delayed flush and retry),the worker reloads the current owner-scoped snapshot/source and reruns the deterministic safety/classification gate. Stable occurrence identity,notification semantic revision,scheduled delivery slot,actionability,delivery class and `valid_until` must still match. A generation or generic source-revision change with identical notification semantics conditionally updates the stored authorization after full revalidation and continues under the same candidate key. Stop/retime/delete,source tombstone,material semantic/class/safety change or deadline expiry transitions the old row to `superseded | cancelled | expired`,releases any unconsumed reservation exactly once and performs zero provider send;the materially changed candidate has a new semantic revision/key.

`emergency_safety` can be minted only by an allowlisted deterministic SafetyGuardian rule/severity. The operation persists rule id/version,episode id and bounded evidence refs;producer/LLM/client input and `fixed` classification cannot self-upgrade it.

| Execution state | Retry/terminal | Allowed claim |
|---|---|---|
| `reserved` | non-terminal;budget/dedupe slot atomically owned | 已进入发送队列。 |
| `sending` | non-terminal;one conditional worker claim | 正在尝试发送。 |
| `provider_accepted` | terminal for provider-send;independent downstream receipts may follow | 推送服务已接收;不能说设备已送达/可见。 |
| `verifying_unknown` | non-terminal;query/retry same operation + dedupe key | 状态核对中;禁止换 key 盲发。 |
| `failed_retryable` | non-terminal;same-key retry policy | 本次发送未确认,可按策略重试。 |
| `failed_terminal` / `expired` / `suppressed` / `superseded` / `cancelled` | terminal | 未发送/不再发送;需要时保留 in-app recovery。 |

Independent monotonic receipt markers are `provider_accepted_at`, `device_delivered_at`, `surface_visible_at`, `notification_interacted_at` and `health_action_committed_at`. Provider acceptance,device delivery,surface visibility,notification interaction and durable health-task completion cannot be inferred from one another. Delayed flush must CAS `reserved -> sending`; failures never become successful dedupe evidence merely because a log row exists.

Allowed execution transitions are:

```text
reserved -> sending | suppressed | expired | superseded | cancelled
sending -> provider_accepted | verifying_unknown | failed_retryable | failed_terminal | expired | superseded | cancelled
verifying_unknown -> provider_accepted | failed_retryable | failed_terminal | expired | superseded | cancelled
failed_retryable -> sending | failed_terminal | expired | superseded | cancelled
```

All transitions are conditional owner-scoped updates. `provider_accepted`, `failed_terminal`, `expired`, `suppressed`, `superseded` and `cancelled` are terminal for provider-send execution;later receipt markers only add evidence and never reopen delivery.

## 9. Acceptance Criteria

```gherkin
Given a P2 proactive signal
When interruption budget is evaluated
Then it is log_only and cannot push

Given a P1 nudge during quiet hours
When interruption budget is evaluated
Then it is blocked with quiet_hours and delay_or_fallback

Given a P0 urgent alert during quiet hours
When it is outside the morning sleep floor, budgets allow and the contract is complete
Then it can bypass ordinary quiet hours, while reporting quiet_hours_respected=false

Given any P0/P1 proactive item is evaluated during the configured morning sleep floor
When interruption budget is evaluated
Then it is blocked with morning_sleep_floor; P0 classification alone cannot bypass that floor

Given a P0/P1 nudge without reason/action/fallback_surface
When interruption budget is evaluated
Then missing fields are reported instead of hidden

Given a new Health Day P1 caller cannot evaluate quiet-hours or budget state
When the structured interruption decision is built
Then it reports degraded/failed_checks and falls back in-app without sending push

Given two workers evaluate the same owner and occurrence concurrently
When notification admission runs
Then one atomic reservation consumes budget and the other observes the existing operation

Given a provider times out after submission
When no provider or device receipt is available
Then the operation becomes verifying_unknown and any retry verifies or reuses the same dedupe key

Given a new non-emergency producer omits reason, action or fallback
When contract completeness is checked
Then it falls back in-app without sending; a true emergency instead uses the deterministic privacy-safe template and stable occurrence key

Given a reserved occurrence is stopped,retimed,cancelled or newly blocked by SafetyGuardian
When delayed flush or retry performs pre-send revalidation
Then it transitions to superseded/cancelled/expired,releases unconsumed budget once and performs zero provider send

Given a producer or LLM self-labels a candidate emergency_safety
When deterministic classification provenance is checked
Then it cannot enter the emergency policy without an allowlisted SafetyGuardian rule id/version and episode id

Given an unrelated source increments the Health Day snapshot generation or non-material metadata revision
When the reserved occurrence,notification semantics,delivery slot,class,deadline and safety decision remain identical
Then pre-send revalidation rebinds the existing operation to the new generation without a duplicate reservation
```

## 10. Verification Plan

```bash
DATABASE_URL="$TEST_DATABASE_URL" TZ=Asia/Shanghai backend/venv/bin/python -m pytest \
  backend/tests/test_interruption_budget.py \
  backend/tests/test_proactive_coordinator.py \
  backend/tests/test_timeline_driver_schedule.py \
  backend/tests/test_push_service_quiet_dedup.py \
  backend/tests/test_quiet_hours_policy.py \
  -q --no-cov

backend/venv/bin/python -m compileall -q backend/app/services/interruption_budget.py backend/app/services/proactive_coordinator.py

git diff --check
```

## 11. Rollout And Rollback

The shipped baseline rolls out as additive backend metadata with no new push channel. Its current implementation can be rolled back to the previous bool logic only for legacy callers. Before any Health Day producer is enabled, the delivery-class, completeness, owner reservation/outbox and receipt gates become non-optional safety invariants:rollback disables the new producer/UI, not those gates, and may not return Health Day traffic to count-then-send or fail-open delivery.

## 12. Changelog

| Date | Change | Reason |
|---|---|---|
| 2026-06-26 | Initial draft | Phase 0 product-spine stabilization. |
| 2026-08-15 | Reconcile with active code and Health Day | Document the P0 morning sleep floor, PostgreSQL verification and legacy fail-open seam; define the blocked emergency/scheduled-required split, atomic outbox lifecycle and receipt semantics required before quiet-proactive rollout. |
