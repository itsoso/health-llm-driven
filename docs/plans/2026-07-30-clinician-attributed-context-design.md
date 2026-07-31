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

### Architecture correction: clause-level provenance

Three TDD and review cycles showed that marker precedence alone cannot safely
separate a user's command from a command quoted from a clinician. The whole-text
classifier first collected read/write/mutation keywords and then tried to
repair actor attribution for individual actions. That design repeatedly:

- treated “医生告诉我是……” as a user read command;
- treated quoted clinician update/delete/sync language as user authorization;
- rejected a valid second-clause command such as
  “医生说是臀肌无力。请帮我记录一下”.

The approved correction is a deterministic clause-level provenance frame. It
replaces per-action position patches while preserving the existing public
`IntentFrame`.

The following alternatives were rejected:

1. An LLM semantic classifier would understand more language but is too
   non-deterministic, slow and expensive to carry medical write authority.
2. A capability-policy-only deny layer would reduce unsafe writes but would not
   fix incorrect read/advice routing or support a valid “state, then save”
   interaction.

### Clause frame

The classifier splits the raw text before normalization so punctuation and
newlines remain structural boundaries. It recognizes
`，,。；;：:！？!?\n` and builds a private frame for each non-empty clause:

```text
source: user | clinician_quote
action: read | save | update | delete | sync | none
actor: user | clinician | ambiguous
object: clinician_content | health_record | medication | unknown
```

This is an internal routing primitive, not a new persistence model or public
API. Existing keyword sets may supply evidence to a clause frame, but no
whole-text keyword can independently grant write authority.

### Clause reduction

Clause frames reduce to the existing `IntentFrame` under these rules:

- A clinician-quoted clause never authorizes a tool.
- A user action applies to an explicit object in the same clause.
- A user save command with an omitted object may refer to the immediately
  preceding clinician-content clause. This supports
  “医生说是臀肌无力。请帮我记录一下”.
- Delete, update and sync do not inherit an omitted object from clinician
  content; they require an explicit object in the user's command clause.
- Explicit user read/mutation commands keep their existing semantics.
- If clinician provenance is present but the actor is ambiguous, reduction is
  fail-closed to `chat / clinical_context / acknowledge` with
  `is_write=False`.
- Text without clinician provenance continues through the existing general
  classifier path.

The reliable model still owns the natural-language response. The deterministic
clause frame owns routing and authorization only.

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

- Clause parsing is deterministic and local; it does not call an LLM.
- Ambiguous actor or object attribution fails closed to a non-write
  `clinical_context` turn.
- Parsing does not emit user-visible exceptions or log the clinical text.
- Newline and punctuation boundaries are preserved before text normalization.
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

1. A clause matrix crosses source (user/clinician), action
   (none/read/save/update/delete/sync), structure (single/multiple/newline) and
   Chinese/ASCII punctuation boundaries.
2. The exact screenshot sentence classifies as `clinical_context` and is not
   fast-record eligible.
3. “医生告诉我是……” and quoted read/update/delete/sync language never become
   user actions.
4. “医生说是……。请记录” is a valid user save, while ambiguous language fails
   closed.
5. Explicit user read/delete/update and ordinary current symptoms retain their
   existing behavior.
6. Tool schema, registry and capability policy expose only the intended write.
7. Adapter validation and persistence produce an owner-scoped verified receipt.
8. Full context recalls saved feedback with provenance; minimal context omits it;
   cache invalidation makes the next turn fresh.
9. Focused Agent streaming regression proves the original sentence no longer
   reaches the record-details fallback.

## Rollout

Backend-only deployment. No schema migration and no Mobile release. Verify the
original sentence and an explicit-save sentence through the production Agent
path, then ask the user to confirm the Mobile behavior before closing G6.
