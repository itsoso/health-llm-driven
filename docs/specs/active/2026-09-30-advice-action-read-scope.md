# Feature Spec: Current-input advice and action explanation

> Status: implementing
> Owner: Health Harness
> Updated: 2026-09-30
> Related PRD: `docs/prd/reva-personal-health-os-prd.md`

## Decision / problem

Treat complete everyday bedtime-advice questions and the Agenda clinical
follow-up explanation starter as current-input answer goals, not implicit
personal-history queries. The previous flow lets optional model reads turn
these questions into terminal permission/date errors.

## Requirement Admission

```yaml
RequirementAdmission:
  classification: bugfix
  first_user_fit: daily recovery and follow-up action comprehension
  core_loop_step: safe action explanation
  first_class_objects: [HealthAgendaItem, SafetyGuardian]
  target_surface: backend contract shared by Mobile and Mac chat
  source_of_truth: current original user input and deterministic capability policy
  safety_level: medical_boundary
  prescription_or_causal_verdict: none
  autonomy_tier: none
  evidence_provenance: current user statement and optional public knowledge
  claim_hedging: absolute_disallowed
  verification_window: same turn
  success_metric: useful complete answer without personal reads or writes
  added_user_burden: none
  non_goals: new read authority, individualized clearance, schedule mutations
  smallest_end_to_end_slice: whole-input proof -> tool scope -> gateway -> safe reply
  stale_surface_to_remove_or_archive: none
  spec_required: yes
```

## Scope and contract

- Preserve the existing symptom-recovery proof and its instructions.
- Extend the same restrictive path with bounded bedtime/general-advice grammar
  and the exact Agenda explanation wrapper around a supported follow-up title.
- Match the complete original request. Quotes, negation, added read/write
  clauses, unknown annotations, other subjects, and acute symptom clauses do
  not gain this proof. Existing authorization remains authoritative for them.
- New bounded bedtime/general-sleep and Agenda-wrapper goals receive reviewed,
  server-owned canonical guidance before provider/panel dispatch. No model or
  tool call is needed. Recovery of an ACKed request binds the original text and
  rejects attachment/replacement-caption shortcuts; uncertain-write recovery
  takes precedence. Existing symptom-recovery remains on its existing path.
- Defense in depth: only public knowledge search may be exposed if a lower
  model entrypoint is used directly. Private reads fail before dispatch in
  enforce and shadow modes. For the new goals, only exact goal-bound canonical
  output may complete; disclaimers/keyword denylists do not prove grounding.
- Do not preload Twin, past action cards, opener side effects or opaque entry
  context. An action title is supplied material, not verified scheduling evidence.
- Explain general purpose/preparation/limitations, explicitly stating why its
  exact due date or individual suitability cannot be confirmed from the title.
- No prescribing, diagnosis, dose/timing/course changes, or safety clearance.
  Keep existing medical output validation on model paths; an unsafe rewrite
  cannot complete. Canonical prose is not interpolated from titles or context.
- No API/schema/database changes. Conversation outcome and persisted content
  must agree with the streamed answer. Truncation remains failure.

## Verification and rollout

RED/GREEN synthetic grammar, tool filter, gateway and real Pi transport tests;
existing recovery, required-history and scope-denial regressions; independent
fixed-commit G4; live LLM gate; exact main CI; trusted backend release then
trusted OTA for the separate HTML slice. No health data from screenshots is
stored in fixtures. Production health and actual user-path verification remain
separate gates. Roll back through governed release receipts only.

## Changelog

| Date | Change | Reason |
| --- | --- | --- |
| 2026-09-30 | Initial bounded bugfix contract | Optional private reads should not replace ordinary advice with query errors |
| 2026-09-30 | Canonical pre-model guidance for new goals | Two G4 rounds rejected free prose promoted through a claim denylist |
