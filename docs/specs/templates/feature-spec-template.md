# Feature Spec: <name>

> Status: draft
> Owner:
> Updated:
> Related PRD/PDD:
> Related code:

Use this template when `docs/specs/reva-product-governance-spec.md` says a
feature spec is required.

## 1. Decision

One sentence: what are we deciding to build or change?

## 2. Problem

What user/system problem exists today?

Include:

- who it affects;
- where it appears;
- why existing flows are insufficient;
- what happens if we do nothing.

## 3. Requirement Admission

```yaml
RequirementAdmission:
  request:
  classification:
  first_user_fit:
  core_loop_step:
  first_class_objects:
  target_surface:
  source_of_truth:
  safety_level:
  prescription_or_causal_verdict:
  autonomy_tier:
  evidence_provenance:
  claim_hedging:
  verification_window:
  success_metric:
  added_user_burden:
  burden_justification:
  non_goals:
  smallest_end_to_end_slice:
  stale_surface_to_remove_or_archive:
  spec_required: yes
```

## 4. Non-Goals

Explicitly list what this feature will not do.

Good non-goals remove ambiguity:

- surfaces not touched;
- medical claims not made;
- data sources not supported;
- old flows not migrated yet;
- experiments not promoted to production.

## 5. Product Object Mapping

| Object | Change |
|---|---|
| `HealthProblem` | |
| `HealthProgram` | |
| `HealthProtocol` | |
| `HealthAgendaItem` | |
| `LeveragePoint` | |
| `LeverageAction` | |
| `SafetyGuardian` | |
| `InterventionCycle` | |
| `HealthTwin` | |
| `ExecutionEvent` | |
| `WriteIntent` | |

Remove rows that do not apply.

## 6. User Flow

Describe the smallest end-to-end path:

```text
trigger
  -> backend state / ranking / safety
  -> target surface
  -> user action
  -> execution event
  -> verification / review
```

## 7. Surface Contract

| Surface | Responsibility | Contract |
|---|---|---|
| Watch | | |
| Mobile | | |
| Mac | | |
| Web | | |
| Backend | | |
| External agents | | |

Remove rows that do not apply.

## 8. Data Contract

List API, schema, event, enum, database, or client contract changes.

```yaml
apis:
events:
models:
fields:
enums:
backward_compatibility:
migration:
```

## 9. Safety, Privacy, And Medical Boundary

State:

- whether this feature touches health data, medication, supplement, lab,
  symptom, genetic, CGM, or red-flag paths;
- which SafetyGuardian or deterministic rule applies;
- what the system must not claim;
- whether audit logging is required;
- how user ownership and data isolation are enforced.

## 10. AI Behavior

If an LLM or external agent is involved:

- what it may do;
- what it must not do;
- which deterministic checks run before/after it;
- what evidence or sources it must show;
- how failures degrade.

## 11. Acceptance Criteria

Use concrete checks.

```gherkin
Given ...
When ...
Then ...
```

Include at least:

- product behavior;
- safety behavior;
- data persistence or event logging;
- cross-surface behavior if relevant;
- backwards compatibility if relevant.

## 12. Verification Plan

List exact commands or manual checks required.

```bash
# Backend

# Mobile

# Watch

# Web

# Repo hygiene
git diff --check
```

If a command is intentionally not run, explain why.

## 13. Rollout And Rollback

State:

- feature flag or rollout path;
- migration path;
- rollback behavior;
- old surface deprecation or archive plan;
- user-visible communication if needed.

## 14. Open Questions

Track decisions that should not block the first slice separately from decisions
that must be resolved before implementation.

## 15. Changelog

| Date | Change | Reason |
|---|---|---|
| YYYY-MM-DD | Initial draft | |
