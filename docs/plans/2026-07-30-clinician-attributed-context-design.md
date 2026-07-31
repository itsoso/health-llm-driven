# Clinician-Attributed Context Design

## Goal

Make XiaoBa understand clinician diagnoses and assessments as provenance-bearing
health context instead of misclassifying them as incomplete symptom records.
Persist such context only when the user explicitly asks to record or save it.

## Root Cause

The failure is a contract mismatch across layers:

1. The intent classifier uses broad symptom words such as “痛” to infer both the
   domain and an implicit write.
2. The symptom extractor is intentionally narrower and rejects doctor/report
   language because it is not a current self-observation.
3. The fast-record path sees zero write receipts and replaces the model response
   with a generic request for record type and value.
4. The turn outcome becomes retryable, so Mobile displays “上一轮未完成”.

Each component behaves according to its local contract, but the system lacks a
semantic frame and tool for clinician-attributed facts.

## Approaches Considered

### 1. Change only the fallback copy

This would hide the most visible nonsense but keep the false symptom write,
failed turn, and missing clinician provenance. It is rejected as a symptom fix.

### 2. Reuse Clinical Journal and add a typed Agent capability

Add a `clinical_context` intent domain, route bare statements to the reliable
model, and expose the existing doctor-feedback service as a receipted Agent
tool for explicit saves. Add the latest saved clinician feedback to full health
context with a provenance label. This is the selected approach because it
connects existing architecture without a migration.

### 3. Create a new clinical-assessment model

A dedicated model could encode provider, encounter and confidence in more
detail, but it would duplicate `ClinicalJournalEntry` before the current
primitive is connected. It is deferred until a future structured encounter
feature needs fields the journal cannot represent.

## Architecture

### Intent boundary

Clinician-attribution markers such as “医生诊断”, “医生说”, “医生认为”,
“医生评估”, “康复师认为” and “检查提示” are evaluated before symptom domain
inference.

- Bare statement: `chat / clinical_context / acknowledge`
- Question or advice request: `advice / clinical_context / analyze`
- Explicit record/save command: `write / clinical_context / create`, with a
  reliable tool-capable model required

The same sentence may still contain symptom terms, but provenance wins over the
keyword because it changes both persistence semantics and medical authority.

### Tool boundary

Add model-visible `record_doctor_feedback`:

- inputs: `summary`, `assessment`, `plan`, `visit_date`;
- at least one text field is required;
- capability policy allows it only for an explicit write intent;
- adapter delegates to `record_doctor_feedback`;
- success returns a positive resource ID and
  `resource_type=clinical_journal_entry`;
- the normal Agent runtime operation and receipt machinery owns dispatch,
  identity verification and honest completion.

The tool does not create a `HealthProblem`, prescribe treatment, or infer risk.

### Context boundary

Full personalized health context includes a small, recent set of
`created_by="doctor"` entries. Each line is prefixed as user-reported clinician
feedback and length-bounded. Pure knowledge questions using the minimal context
budget do not receive these entries.

After a successful tool write, the per-user health-context cache is invalidated
so the next turn can see the new entry.

### Prompt behavior

The Agent prompt explicitly requires:

- preserve clinician attribution;
- reflect the stated causal chain without endorsing it as Reva's diagnosis;
- do not auto-save bare statements;
- use `record_doctor_feedback` only after explicit save language;
- do not redirect structured medical facts to `remember`.

## Data Flow

```text
User sentence
  -> clinician attribution frame
  -> bare statement -------------------------> reliable response, no write
  -> explicit "记录/保存"
       -> record_doctor_feedback tool
       -> ToolGateway explicit-write check
       -> doctor_report_service
       -> ClinicalJournalEntry(created_by=doctor)
       -> verified receipt
       -> invalidate full health context cache
       -> provenance-bearing recall on later turns
```

## Error Handling

- Missing all text fields: structured local rejection; no dispatch.
- Missing user identity: structured local rejection; no dispatch.
- Invalid visit date: structured local rejection with correction guidance.
- Persistence error: rollback, log only exception type/no clinical text, and
  return an observable failure; never claim success.
- No tool call on a bare statement: normal chat completion, not a failed action.
- No receipt after an attempted explicit write: existing honesty gate reports
  that the write was not verified.

## Testing

TDD covers each boundary independently:

1. Exact screenshot sentence classifies as `clinical_context` and is not
   fast-record eligible.
2. Explicit save and clinician question produce distinct write/advice frames.
3. Ordinary current symptoms retain existing classification and deterministic
   symptom recovery.
4. Tool schema, registry and capability policy expose only the intended write.
5. Adapter validation and persistence produce an owner-scoped verified receipt.
6. Full context recalls saved feedback with provenance; minimal context omits it;
   cache invalidation makes the next turn fresh.
7. Focused Agent streaming regression proves the original sentence no longer
   reaches the record-details fallback.

## Rollout

Backend-only deployment. No schema migration and no Mobile release. Verify the
original sentence and an explicit-save sentence through the production Agent
path, then ask the user to confirm the Mobile behavior before closing G6.

