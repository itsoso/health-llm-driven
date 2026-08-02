# Clinician Provenance Guard Design

## Status

Approved by the user on 2026-08-01. This design supersedes the general
ActionEvidence authorization-parser design for clinician-bearing turns. The
previous experiments remain historical evidence in Git and the dossier, but
their parser must not ship or remain as unused security-critical code.

## Goal

Make XiaoBa understand a user-reported clinician diagnosis or assessment as
provenance-bearing context instead of an incomplete symptom record. Persist it
only after a narrow, explicit command to record or save clinician feedback.

The guard is intentionally not a general Chinese action parser. It proves one
product capability safely and delegates ordinary non-clinician turns to the
existing classifier.

## Why the architecture changed

Three increasingly structured general parsers were rejected by independent
review. They repeatedly failed on nested speakers, quotation ownership,
unknown negation or questions, embedded action nouns, target scope and
complexity accounting. More markers made the implementation larger without
changing the unsafe default: an unrecognized sentence shape could still become
an authorized operation.

The product requirement is narrower than that parser:

- understand clinician-attributed statements;
- do not auto-save them;
- save clinician feedback only when the user explicitly asks;
- preserve attribution in later reasoning.

Authorization should therefore be capability-specific rather than inferred by
a universal natural-language grammar.

## Approaches considered

### 1. Narrow provenance guard and explicit save envelope — selected

Detect clinician reports before symptom inference. Route bare statements and
questions to the reliable model without a write. Authorize only a narrow
`record/save + clinician feedback object` envelope. Fail closed on compound or
ambiguous clinician-bearing actions.

This is small, deterministic and aligned with the actual product contract.

### 2. Continue the general deterministic action parser — rejected

This could preserve more compound commands, but multiple independent reviews
found new fail-open shapes after every redesign. Its security surface is much
larger than the feature requires.

### 3. Let the LLM decide write authority — rejected

An LLM is appropriate for understanding and response generation, but not for
granting medical-data write authority. Authorization must remain deterministic
and independently testable.

## Architecture

### Clinician provenance guard

Add a small pure service that classifies only the clinician boundary:

```text
ClinicianTurnDecision
  kind:
    none
    clinician_context
    clinician_advice
    explicit_doctor_feedback_write
    ambiguous_clinician_action
  content_span
  provider_span
  command_span (only for an explicit write)
  reason_code
```

The guard runs on raw text before broad symptom inference and before fast
record. It detects clinician report forms such as a provider followed by a
report, diagnosis, assessment or advice predicate. A clinician record noun,
such as “医生诊断记录”, is not by itself a report.

The guard does not classify delete, update, sync, plan, reminder, media or
ordinary health actions. It has no fallback that can authorize those actions.

### Explicit save envelope

An explicit doctor-feedback write requires all of the following:

1. one supported root command: `记录/保存/录入/写入` with an optional strict
   polite prefix such as `请`;
2. one explicit clinician-feedback object: `医生诊断/医生意见/医生反馈/医生结论`
   or an equivalent provider-specific form;
3. non-empty feedback content in the same command segment;
4. no additional action family or ambiguous coordinated command in that
   segment.

Supported examples:

```text
请记录医生诊断：臀肌无力导致腰肌代偿
保存医生意见：建议减少负重训练
医生说是臀肌无力。请记录医生诊断：臀肌无力导致腰痛
```

The final example is supported only because the second hard-boundary segment
repeats both the explicit command and clinician-feedback object.

Non-authorizing examples:

```text
医生诊断是臀肌无力导致腰肌代偿
医生说是臀肌无力，帮我记录一下
医生建议休息然后请保存诊断记录
医生说需要复查并删除昨天的用药记录
```

These turns remain clinician context or ambiguous clinician actions. The Agent
responds normally and asks the user to send a separate explicit record command
when persistence is desired.

### Existing classifier boundary

- `kind=none`: call the existing classifier unchanged.
- `clinician_context`: return the existing public clinical-context chat frame
  and require the reliable model.
- `clinician_advice`: return the clinical-context advice frame and require the
  reliable model.
- `explicit_doctor_feedback_write`: return the clinical-context write frame;
  the later tool capability and receipt path still decides whether persistence
  succeeded.
- `ambiguous_clinician_action`: return a non-write clinical-context frame with
  a reason code that prompts the model to ask for a separate explicit command.

Clinician-bearing decisions never fall back to the raw whole-text write,
mutation, plan, reminder or media authorizers.

## Data flow

```text
Raw user turn
  -> ClinicianProvenanceGuard
     -> none --------------------------> existing classifier
     -> bare clinician statement ------> reliable response, no write
     -> clinician question/advice -----> reliable advice, no write
     -> explicit feedback save --------> clinical_context/write
                                           -> record_doctor_feedback tool
                                           -> capability policy
                                           -> verified receipt
     -> compound/ambiguous action ------> clarification, no tool
```

The reliable model may explain and reflect the clinician's causal chain, but it
must label it as user-reported clinician information rather than Reva's own
diagnosis.

## Persistence and context

The downstream plan remains unchanged:

- expose `record_doctor_feedback` as a receipted Agent tool;
- reuse `doctor_report_service.record_doctor_feedback` and
  `ClinicalJournalEntry(created_by="doctor")`;
- require owner-scoped identity and explicit-write capability;
- invalidate the full health-context cache after success;
- include a small recent set in full context under the label “用户转述的医生意见”;
- omit it from minimal knowledge-only context;
- never create or upgrade `HealthProblem` from free text.

## Error handling

- Bare clinician context is a successful chat turn, not a failed record.
- Ambiguous clinician actions produce no tool choice or write receipt and do
  not reach the generic “类型和值” fallback.
- The clarification names the supported separate command without claiming any
  persistence occurred.
- Missing feedback content, mixed action families or unclear object fail closed
  to `ambiguous_clinician_action`.
- The guard does not log raw medical text.
- Tool validation, rollback and honest receipt handling remain downstream
  responsibilities.

## Removal and migration

Remove the unshipped general ActionEvidence parser, its evidence-only lexicon
metadata, performance instrumentation and implementation-derived property
matrix. Retain or migrate only fixed externally meaningful regression cases
that exercise the new guard. Do not keep two competing clinician authorization
paths.

Legacy classifier constants and behavior must remain byte/behavior compatible
unless a specific guard integration test requires the new clinician decision
before the legacy path.

## Testing

TDD must cover:

1. the exact screenshot statement becomes clinician context, not symptom write;
2. bare reports with symptom terms never enter fast record;
3. clinician questions become reliable advice without a write;
4. every supported explicit save command becomes only the doctor-feedback
   write intent;
5. missing content, objectless save and all compound/mixed actions fail closed;
6. clinician record nouns without report semantics retain existing read/delete
   behavior;
7. clinician-basis mutations such as `根据/依据/按照医生意见 + 删除/调整/同步`
   fail closed and ask the user to restate the operation as a separate explicit
   command; standalone non-clinician mutations retain existing legacy behavior;
8. ordinary diet, symptom, medication, media, plan and reminder classifier
   behavior does not drift;
9. a structural canary proves clinician-bearing decisions never call legacy raw
   authorizers;
10. streaming regression proves the screenshot no longer receives the generic
    record-details fallback or retry outcome;
11. later tasks prove tool schema, capability, receipt, persistence, context
    recall and cache invalidation.

The fixed external safety corpus should be rewritten around these product
boundaries. It must not be generated from guard constants.

## Rollout

Backend only. No database migration and no Mobile change. Deploy after the
classification, tool, context and streaming gates pass. Production smoke tests
use the screenshot sentence and one explicit save command; final G6 requires
the user to confirm Mobile behavior.
