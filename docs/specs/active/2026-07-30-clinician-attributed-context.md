# Feature Spec: Clinician-Attributed Context in XiaoBa

> Status: accepted
> Owner: Backend / Agent Kernel
> Updated: 2026-07-30
> Related PRD/PDD: `docs/prd/reva-personal-health-os-prd.md` R10, R13
> Related code: `backend/app/services/utterance_intent_classifier.py`, `backend/app/services/agent_executor.py`, `backend/app/services/doctor_report_service.py`

## 1. Decision

Teach XiaoBa to distinguish clinician-attributed health facts from the user's
current symptoms, reuse the existing Clinical Journal for explicit saves, and
preserve clinician provenance in future Agent context.

## 2. Problem

A user can say:

> 医生诊断是大腿和臀部肌肉无力导致腰肌代偿进而导致腰肌痛

The current classifier sees the broad symptom token “痛”, labels the turn as a
fast symptom write, and later fails to extract a current self-observation. The
zero-receipt honesty fallback then asks for a record type and numeric value.
Mobile correctly renders the failed turn as unfinished, but the user experiences
the entire chain as an unintelligent Agent.

The repository already has the correct persistence primitive:
`ClinicalJournalEntry(created_by="doctor")`, exposed by the Doctor Loop API and
Mobile screen. It is not exposed to the Agent tool registry, and the intent
classifier has no clinician-attribution frame.

## 3. Requirement Admission

```yaml
RequirementAdmission:
  request: Correctly understand clinician diagnoses/assessments and save them only when explicitly requested.
  classification: bugfix + product_change
  first_user_fit: yes; clinician feedback is high-value context for ongoing health management.
  core_loop_step: clinician evidence -> health context -> safety-gated action reasoning
  first_class_objects: [HealthProblem, WriteIntent]
  target_surface: Backend Agent Kernel consumed by Mobile chat
  source_of_truth: ClinicalJournalEntry(created_by="doctor")
  safety_level: medical_boundary
  prescription_or_causal_verdict: clinician_review_downgraded
  autonomy_tier: manual_confirm
  evidence_provenance: user-attributed clinician statement
  claim_hedging: hedged
  verification_window: immediate turn plus next full-context turn
  success_metric: no false symptom write; explicit save has verified receipt; saved provenance is recalled
  added_user_burden: none for chat; explicit save wording is required for persistence
  burden_justification: prevents silent persistence of sensitive clinical facts
  non_goals: diagnosis generation, automatic HealthProblem mutation, treatment prescription
  smallest_end_to_end_slice: classify, respond, explicitly persist, recall
  stale_surface_to_remove_or_archive: none
  spec_required: yes
```

## 4. Non-Goals

- Do not create a new clinical-assessment database table.
- Do not automatically create, merge, or reprioritize a `HealthProblem`.
- Do not infer a diagnosis, risk tier, ICD code, treatment, or exercise
  prescription from clinician-attributed free text.
- Do not auto-save a bare clinician statement.
- Do not replace the Doctor Loop screen for structured editing.
- Do not change Mobile failure-banner behavior; removing the false failed turn
  fixes the observed banner at its source.

## 5. Product Object Mapping

| Object | Change |
|---|---|
| `HealthProblem` | Clinician feedback may inform later reasoning, but this slice never mutates the problem automatically. |
| `WriteIntent` | A clinician-feedback write is authorized only by explicit save/record language and remains manual-confirm forever. |
| `HealthTwin` | No schema or value mutation; clinician feedback is provenance-bearing context, not a measured Twin fact. |

## 6. User Flow

### Bare clinician statement

```text
clinician-attributed statement
  -> classifier selects clinical_context before symptom keywords
  -> reliable full-context model acknowledges the clinician's causal chain
  -> no write tool is authorized or executed
  -> turn completes normally
```

### Explicit save

```text
"请记录医生诊断：..."
  -> classifier emits write / clinical_context / create
  -> model calls record_doctor_feedback
  -> deterministic ToolGateway checks explicit write intent
  -> existing doctor_report_service persists ClinicalJournalEntry(created_by="doctor")
  -> verified clinical_journal_entry receipt
  -> later full Agent context includes the latest clinician feedback with provenance label
```

## 7. Surface Contract

| Surface | Responsibility | Contract |
|---|---|---|
| Mobile | Send the user text and render normal Agent completion/receipt cards. | No API or UI change. |
| Backend | Classify provenance, authorize explicit writes, persist a verified receipt, and compile future context. | Source of truth and safety boundary. |
| Mac / Web / external agents | Consume the same `/agent` behavior if they use the shared Agent Kernel. | No separate implementation. |

## 8. Data Contract

```yaml
apis:
  existing: POST /api/v1/doctor-report/feedback
agent_tools:
  record_doctor_feedback:
    inputs: [summary, assessment, plan, visit_date]
    required_semantics: at least one text field; explicit user write intent
    receipt_resource_type: clinical_journal_entry
models:
  reused: ClinicalJournalEntry
fields:
  created_by: doctor
  assessment: clinician statement
  objective: optional visit date provenance
enums:
  intent_domain: clinical_context
backward_compatibility: existing symptom, medical-exam, and Doctor Loop flows remain unchanged
migration: none
```

## 9. Safety, Privacy, And Medical Boundary

- The text is L3 health data and remains owner-scoped through the authenticated
  Agent session and existing `user_id` service boundary.
- The Agent must attribute the content to the clinician as reported by the user.
- Reva must not endorse the diagnosis, invent missing examination evidence, or
  turn the statement into a prescription or causal verdict of its own.
- A bare statement never writes. Explicit “记录/保存” language is the manual
  confirmation for the direct write.
- Every successful write must produce a verified resource identity; rejection
  or adapter failure must remain visible and must not claim success.
- Independent safety review is required before deployment.

## 10. AI Behavior

The model may:

- acknowledge the clinician-attributed explanation;
- reflect the stated causal chain without strengthening it;
- ask a useful follow-up or offer to save it;
- use explicitly saved feedback as provenance-bearing context later.

The model must not:

- treat “医生诊断” as a current symptom observation;
- auto-save a bare statement;
- say Reva made or confirmed the diagnosis;
- add unsupported risk levels, treatments, or exercises;
- use `remember` for structured medical facts.

Deterministic controls:

- clinician-attribution detection runs before broad symptom-domain inference;
- ToolGateway authorizes the write tool only for explicit write intent;
- the adapter validates identity, non-empty content, date, persistence and receipt;
- the post-tool receipt gate prevents unverified success claims.

## 11. Acceptance Criteria

```gherkin
Given the screenshot sentence about a doctor's muscle-compensation diagnosis
When the intent is classified
Then it is clinical_context, not a symptom write
And the fast-record fallback is not eligible

Given a bare clinician-attributed statement
When the Agent responds
Then no health write tool is executed
And the turn is completed rather than action_not_executed

Given "请记录医生诊断：大腿和臀部肌肉无力导致腰肌代偿..."
When the Agent tool executes
Then one owner-scoped ClinicalJournalEntry is persisted with created_by=doctor
And a verified clinical_journal_entry receipt is returned

Given a saved clinician feedback entry
When a later full health context is compiled
Then it contains a provenance label indicating user-reported clinician feedback
And the content is length-bounded

Given symptom statements such as "我今天腰痛"
When the intent is classified
Then existing symptom write behavior remains unchanged
```

## 12. Verification Plan

```bash
cd backend
DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai \
  python -m pytest -q --no-cov \
  tests/test_utterance_intent_classifier.py \
  tests/test_agent_executor_status_events.py \
  tests/test_agent_kernel_capability_policy.py \
  tests/test_agent_runtime_tool_operations.py \
  tests/test_doctor_report.py \
  tests/test_health_context_lite_service.py

python ../scripts/dump_system_map.py
python ../scripts/check_doc_drift.py
git diff --check
```

Run the repository's integration gate before deployment. Do not use `| tail`.

## 13. Rollout And Rollback

- Backend-only rollout through the normal deployment script.
- No database migration or client release is required.
- Rollback is the deployment's previous backend SHA.
- Existing Doctor Loop and symptom recording remain compatible.

## 14. Open Questions

None for the first slice. Structured promotion from clinician feedback into a
`HealthProblem` requires a separate feature spec and confirmation workflow.

## 15. Changelog

| Date | Change | Reason |
|---|---|---|
| 2026-07-30 | Initial accepted spec | User approved understand-only by default and explicit-save persistence. |
