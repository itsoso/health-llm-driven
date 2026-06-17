# Reva Product Governance Spec

> Status: v1 baseline
> Updated: 2026-06-17
> Audience: humans and AI agents, including Claude, Codex, Qwen, GLM, Kimi,
> Gemini, Grok, OpenClaw, and future coding or planning agents.
> Role: product-scope constitution and requirement admission gate.

This document is intentionally model-agnostic. It does not describe how to use
one specific coding agent. It defines what Reva is, what new requirements must
prove before they enter the codebase, and how agents should keep product
evolution aligned with the Personal Health OS thesis.

## 0. Authority And Scope

### 0.1 Authority Order

When instructions conflict, use this order:

1. Current user instruction, unless it asks for unsafe behavior or hidden policy
   violations.
2. `AGENTS.md` and `docs/governance/*` for engineering safety, testing,
   deployment, privacy, database, logging, and commit rules.
3. This document for product scope, requirement admission, surface ownership,
   and product evolution.
4. `docs/prd/reva-personal-health-os-prd.md` for the global product blueprint.
5. Focused PDDs or feature specs for local product decisions.
6. Current implementation, tests, and live behavior.
7. Archived docs only as historical evidence. Archived root docs are not current
   authority.

This document must not be used to weaken `AGENTS.md`, security rules, privacy
rules, medical safety boundaries, or explicit user constraints.

### 0.2 What This Spec Is Not

This spec is not:

- a replacement for `AGENTS.md`;
- a clinical guideline;
- a deployment manual;
- a test plan for every subsystem;
- a generic prompt for one model vendor;
- permission to add process for trivial bug fixes.

It is a gate for product direction and requirement evolution.

## 1. Mission

Reva is a Personal Health OS.

It is not a health chatbot, wearable dashboard, habit tracker, social product,
generic AI assistant, anti-aging content feed, or one-off report generator.

Reva turns fragmented personal health data into a small number of safe,
high-leverage actions, helps the user execute them on the right surface, and
verifies whether those actions actually improved this user's trajectory.

The durable asset is the per-user causal ledger:

```text
what was observed
  -> what was recommended
  -> what was safety-gated
  -> what was executed
  -> what changed
  -> what should be tried next
```

## 2. First User And Wedge

The first product wedge is:

- 35-55 year-old high-intensity workers;
- early metabolic, recovery, sleep, medication, supplement, or chronic-risk
  pressure;
- meaningful data sources such as wearables, labs, HealthKit, Garmin, Withings,
  CGM, symptoms, medication, supplement, or manual records;
- enough motivation to act, but not enough time or execution bandwidth.

Requirements that primarily optimize for casual wellness browsing, generic
content consumption, vanity streaks, social competition, or broad consumer
virality are outside the first wedge unless they directly improve the Health OS
core loop.

## 3. North Star

Primary product metric:

> Weekly completed high-leverage health actions that passed safety gating and
> have an attached verification plan.

Supporting metrics:

- top action completion rate;
- Watch action confirm / later / skip rate;
- verification plan attached rate;
- retest or recheck completion rate;
- N-of-1 review generated rate;
- safety escalation correctness;
- notification disable rate;
- user-perceived execution burden.

Do not optimize engagement time as the primary product goal. A good Health OS
often succeeds by reducing attention and making the right behavior happen with
less effort.

## 4. Core Loop

All product behavior should strengthen this loop:

```text
Labs / wearables / symptoms / meds / supplements / behavior
  -> Digital Health Twin
  -> Safety Gate
  -> Leverage Action Ranker
  -> Agenda top action
  -> Watch / Mobile / Mac / Web execution
  -> Execution event
  -> Retest / outcome review
  -> next action, with more personal evidence
```

If a requirement does not improve at least one part of this loop, it must be
rejected, reframed, or explicitly marked as infrastructure / maintenance.

## 5. First-Class Product Objects

Every new product requirement must map to at least one first-class object.

| Object | Responsibility | Typical implementation anchors |
|---|---|---|
| `HealthProblem` | Medical problem, risk level, red lines, follow-up, escalation | chronic condition, checkup, safety, specialist models |
| `HealthProgram` | 8-12 week goal container | metabolic, recovery, sleep, medication, supplement, checkup programs |
| `HealthProtocol` | Default behavior protocol, cadence, passive/physical execution path | protocol templates, agenda projection, completion rules |
| `HealthAgendaItem` | Today/week/month/quarter executable action | `agenda_service`, mobile agenda, watch summary |
| `LeveragePoint` | Candidate upstream variable worth acting on | labs, twin, symptoms, protocols, safety triggers |
| `LeverageAction` | Concrete action the user can do now | `ActionRanker`, agenda top action, Watch/Mobile cards |
| `SafetyGuardian` | Deterministic safety gate and escalation rules | vitals, labs, DDI, DSI, PGx, CGM, training load, symptoms |
| `InterventionCycle` | Baseline, target, action, verification window, outcome review | 8-12 week cycles, outcome metrics, retest |
| `HealthTwin` | Current semantic state and uncertainty | twin schema, builder, snapshots |
| `ExecutionEvent` | Completed, skipped, delayed, adjusted, auto-observed, confirmed | client events, audit, adherence logs |

If a requirement cannot be mapped to these objects, the agent must do one of:

- reject it as out of scope;
- reframe it into one of these objects;
- classify it as pure engineering maintenance with no product semantic change.

## 6. Product Invariants

These are hard product rules.

1. Safety beats ranking.
   Critical red flags, medical escalation, and contraindications are not normal
   ranking weights. They gate or override the action list.

2. Executable actions beat insights.
   Dashboards, explanations, and reports are secondary unless they cause safer
   or better execution.

3. Writable variables beat outcome metrics.
   Reva should schedule actions such as post-meal walking, medication adherence,
   caffeine cutoff, sleep wind-down, training downshift, or recheck booking. It
   should not pretend the user can directly "improve HRV" or "lower HbA1c"
   without an executable variable.

4. No data without decision value.
   A new input, check-in, or metric is allowed only if it can verify a key
   behavior, explain failure, trigger safety escalation, or change the next plan.

5. Every important intervention needs a verification window.
   High-leverage actions should define whether validation happens in 1 day,
   1 week, 4 weeks, 8 weeks, 12 weeks, or at a future retest.

6. LLMs synthesize; deterministic systems gate.
   LLMs may explain, summarize, draft, route, and ask for missing context. They
   must not be the sole source of safety gating, medication dose changes,
   diagnosis, or red-flag clearance.

7. Medical boundaries are explicit.
   Reva does not prescribe, diagnose, replace emergency triage, autonomously
   change medication dose, or tell users they are fine when red flags exist.

8. Failure is a system signal.
   Missed actions should capture reasons such as too tired, forgot, not enough
   time, item unavailable, wrong location, plan too hard, social interruption,
   or physical discomfort. The system should adjust protocols, not shame users.

9. Passive and physical execution are preferred.
   Prefer device sync, physical containers, default environments, calendar
   commitments, and one-tap confirmation over manual logging.

10. Delete or archive stale product surface.
    If a new feature supersedes an old page, report, mode, or workflow, the
    spec must say whether the old one is kept, deprecated, hidden, merged, or
    deleted.

## 7. Surface Ownership

Do not duplicate the same workflow across surfaces without a reason.

| Surface | Role | Should do | Should not do |
|---|---|---|---|
| Watch | Low-friction execution | top action, confirm/later/skip, due item, freshness, tiny safety nudge | long reports, complex editing, deep explanation |
| Mobile | Primary daily product | Today, Agenda, Capture, Programs, Review, medication/supplement check-in, active cycle | become an admin console |
| Mac | Workbench | import, review, trace, long agent workflows, file/lab handling, debugging | replace daily mobile execution |
| Web | Admin/history/secondary | historical views, backend management, reports, compatibility surfaces | lead the consumer daily loop |
| Backend | Source of truth | safety, ranking, agenda, intervention cycles, audit, data ownership | push unsafe decisions to clients |
| External agents | Controlled extension | invoke documented skills/APIs with auth and audit | bypass safety, ownership, or data minimization |

If a requirement touches multiple surfaces, the feature spec must name the
source of truth and define the cross-surface contract.

## 8. Requirement Admission Gate

Before implementing a non-trivial product requirement, the agent must be able to
fill this card. The final answer does not always need to print the whole card,
but the reasoning must exist. If any required field fails, do not implement
until the requirement is reframed or the user explicitly accepts the trade-off.

```yaml
RequirementAdmission:
  request:
  classification: new_product_behavior | product_change | bugfix |
    infrastructure | security | docs | experiment | cleanup
  first_user_fit:
  core_loop_step:
  first_class_objects:
  target_surface:
  source_of_truth:
  safety_level: none | low | medical_boundary | red_flag | privacy_sensitive
  verification_window:
  success_metric:
  added_user_burden:
  burden_justification:
  non_goals:
  smallest_end_to_end_slice:
  stale_surface_to_remove_or_archive:
  spec_required: yes | no
```

### 8.1 When A Feature Spec Is Required

A feature spec is required when any of these are true:

- new user-visible product behavior;
- new or changed medical/safety behavior;
- new cross-surface contract;
- new Health OS object, state machine, protocol, ranker, or verification loop;
- new write path for health data;
- new external agent capability;
- new notification or behavior-change loop;
- significant deprecation or migration.

A feature spec is usually not required for:

- typo fixes;
- small copy changes that do not change claims;
- test-only changes;
- internal refactors with no behavior change;
- security hotfixes that must ship immediately.

For urgent security or medical-safety fixes, patch first under `AGENTS.md`, then
backfill the spec if the behavior changed.

## 9. Agent Compliance Protocol

Any AI agent working in this repository must follow this protocol when the task
touches product behavior or requirement evolution.

### 9.1 Minimal Read Set

Read these before product work:

1. this document;
2. `README.md`;
3. `docs/prd/reva-personal-health-os-prd.md` for product blueprint;
4. the focused PDD or feature spec if one exists;
5. relevant code and tests.

Read `AGENTS.md` for engineering rules. Do not duplicate those rules here.

### 9.2 Required Decision Steps

1. Classify the task.
2. If product semantics change, apply the Requirement Admission Gate.
3. If the gate fails, say why and propose a smaller or better-framed version.
4. If a spec is required and missing, create or update one before broad
   implementation.
5. Implement the smallest end-to-end slice that proves the product object,
   surface, safety boundary, and verification path.
6. Run focused verification.
7. Report what changed, what was verified, and what remains intentionally out of
   scope.

### 9.3 Required Agent Output When Blocking A Requirement

Use this short format:

```text
Gate result: blocked
Reason: <which invariant or admission field failed>
Better framing: <how to map it to a first-class object or smaller slice>
Next viable action: <spec / code / research / delete / defer>
```

### 9.4 Required Agent Output When Accepting A Requirement

Use this short format when helpful:

```text
Gate result: accepted
Object mapping: <objects>
Surface: <surface>
Safety boundary: <none/low/medical/red-flag/privacy>
Verification: <commands or product metric>
```

Agents should keep this concise. Do not turn every small fix into a ceremony.

## 10. Model-Agnostic Prompt Block

When handing this repo to any capable model, include or point to this block:

```text
You are working in the Reva Personal Health OS repo.
Before changing product behavior, read docs/specs/reva-product-governance-spec.md.
AGENTS.md controls engineering safety, tests, privacy, deployment, DB, and commit
rules. The governance spec controls product scope and requirement admission.
For new product behavior, map the request to a first-class Health OS object,
identify the target surface, name the safety boundary, define the verification
window, and implement only the smallest end-to-end slice. If the request cannot
strengthen the Health OS core loop, reject, reframe, or mark it as maintenance.
```

This prompt is intentionally not vendor-specific. Claude, Codex, Qwen, GLM,
Kimi, Gemini, Grok, and future agents should follow the same gate.

## 11. Common Admission Examples

### 11.1 Accepted

- "Show today's top action on Watch with confirm/later/skip."
  - Object: `LeverageAction`, `HealthAgendaItem`, `ExecutionEvent`.
  - Surface: Watch.
  - Why: improves low-friction execution.

- "Attach verification windows to supplement experiments."
  - Object: `HealthProtocol`, `InterventionCycle`, `OutcomeMetric`.
  - Why: prevents advice pile-up without N-of-1 evidence.

- "Create a follow-up flow for abnormal HbA1c."
  - Object: `HealthProblem`, `SafetyGuardian`, `HealthAgendaItem`.
  - Why: medical risk and retest loop.

### 11.2 Reframe Before Building

- "Add more charts."
  - Reframe: Which decision changes? Which action or review does the chart
    support?

- "Add social challenges."
  - Reframe: Does it increase safe high-leverage action completion for the first
    wedge, or is it a generic engagement mechanic?

- "Add an anti-aging score."
  - Reframe: Which biomarkers, claim boundaries, and verification windows make
    it medically honest?

### 11.3 Reject Or Archive

- Generic wellness content feeds.
- Vanity streaks that do not change action selection.
- LLM-only medical clearance.
- New manual check-ins with no decision impact.
- Duplicated Web/Mobile/Watch flows without a source-of-truth reason.

## 12. Spec Lifecycle

Feature specs live under `docs/specs/`.

Recommended layout:

```text
docs/specs/
  reva-product-governance-spec.md
  templates/
    feature-spec-template.md
  active/
    YYYY-MM-DD-feature-name.md
  completed/
    YYYY-MM-DD-feature-name.md
  deprecated/
    YYYY-MM-DD-feature-name.md
```

Status values:

- `draft`: idea is not accepted yet;
- `accepted`: gate passed, implementation can start;
- `implementing`: code is in progress;
- `shipped`: merged and verified;
- `deprecated`: superseded or intentionally retired.

Every feature spec must include a changelog. If product scope changes during
implementation, update the spec in the same PR or commit.

## 13. Change Control For This Governance Spec

Changing this document requires:

1. a concrete reason;
2. a note about which agents or workflows are affected;
3. updated links in `README.md`, `AGENTS.md`, or `CLAUDE.md` if discovery
   changes;
4. `git diff --check`;
5. a short final summary of the changed rule.

Do not make this document long enough that agents stop reading it. If a rule
becomes detailed implementation guidance, move it to a focused feature spec,
PDD, or governance file and link it here.
