# Feature Spec: Mobile Medical Exam Import Flow

> **Current release override (2026-08-12):** every server/OTA/native writer is frozen. Validate
> locally and keep manual release Gate BLOCKED; do not deploy, build/sign/install or call OTA.

> Status: approved
> Owner: Mobile / Medical Exams
> Updated: 2026-07-29
> Related PDD: `docs/plans/2026-07-29-mobile-medical-exam-import-design.md`
> Related code: `mobile/app/import.tsx`, `mobile/components/chat/ChatInputBar.tsx`, `backend/app/api/medical_exams.py`

## 1. Decision

Replace the nested, immediate-write medical report attachment flow with one
Mobile-first import flow: select a report, preview extraction, explicitly save,
and retry in place without losing the selected report.

## 2. Problem

The Chat composer currently opens an attachment sheet and then a second import
sheet. Selecting a PDF or image immediately invokes a write endpoint. On any
picker, parser, network or persistence failure, a blocking alert is shown and
the import sheet closes. The user loses context, cannot inspect extracted data
before it enters the health record, and cannot retry without starting over.

## 3. Requirement Admission

```yaml
RequirementAdmission:
  request: Redesign and repair medical report import on Mobile
  classification: existing core-loop repair
  first_user_fit: users importing labs, imaging and annual checkup reports
  core_loop_step: health data capture -> HealthTwin input -> review
  first_class_objects: [HealthTwin, WriteIntent, ExecutionEvent]
  target_surface: Mobile
  source_of_truth: backend medical_exams
  safety_level: health data, manual confirmation required
  prescription_or_causal_verdict: no
  autonomy_tier: manual_confirm
  evidence_provenance: user-selected report plus OCR/parser preview
  claim_hedging: extraction is unverified until user review
  verification_window: immediate after save and later in medical exam detail
  success_metric: preview-to-save completion without duplicate records
  added_user_burden: one explicit save action
  burden_justification: prevents incorrect OCR from silently becoming health truth
  non_goals: diagnosis, treatment advice, automatic report correction
  smallest_end_to_end_slice: one PDF or image -> preview -> idempotent save -> result card
  stale_surface_to_remove_or_archive: nested Chat import source sheet
  spec_required: yes
```

## 4. Non-Goals

- No diagnosis or treatment recommendation is generated during import.
- No new report storage provider is introduced.
- No Watch, Mac or Web redesign is included.
- The first slice does not merge multiple PDFs into one report.
- Structured item editing remains in the existing medical exam detail screen.

## 5. Product Object Mapping

| Object | Change |
|---|---|
| `HealthTwin` | Receives confirmed medical exam data only after persistence. |
| `WriteIntent` | The preview is proposed state; the save button is explicit confirmation. |
| `ExecutionEvent` | A successful idempotent save produces one durable report/result card. |

## 6. User Flow

```text
Chat attachment or Medical Exams import
  -> full-screen import flow
  -> choose PDF, camera or photo library
  -> parse without persistence
  -> review source/date/item and abnormal counts
  -> Save to health record
  -> idempotent backend create
  -> success result / Chat result card
```

Failures remain on the current step. The selected report and parsed preview are
retained, with explicit Retry and Change report actions.

## 7. Surface Contract

| Surface | Responsibility | Contract |
|---|---|---|
| Mobile | Source selection, progress, preview, confirmation, inline recovery | Never writes before explicit confirmation |
| Backend | Authenticated parse preview and owner-scoped idempotent persistence | Same idempotency key returns the same report |

## 8. Data Contract

```yaml
apis:
  - POST /medical-exams/parse-pdf-preview
  - POST /medical-exams/parse-image-preview
  - POST /medical-exams/ with Idempotency-Key
events:
  - existing chat_runtime_skill_completed after confirmed save
models:
  - existing MedicalExam and MedicalExamItem
fields:
  - source_fingerprint stores a namespaced one-way idempotency fingerprint
enums: none
backward_compatibility: existing import/pdf and import/image endpoints remain
migration: none
```

## 9. Safety, Privacy, And Medical Boundary

- Preview and persistence require the authenticated user.
- Persistence ignores any payload user ID and binds to the current user.
- Idempotent replay is scoped by current user and contains no report content.
- UI states that OCR/AI extraction must be reviewed.
- Logs must not include report text, findings or item values.

## 10. AI Behavior

The parser may extract report metadata and items. It must not diagnose or
recommend treatment. Empty or invalid extraction is a recoverable inline error.
Persistence occurs only after deterministic schema validation and user action.

## 11. Acceptance Criteria

```gherkin
Given a user opens medical report import from Chat
When the source action is tapped
Then one full-screen flow opens and no nested source sheet appears

Given a valid PDF or image
When parsing completes
Then a preview is shown and no MedicalExam has been written yet

Given a parsed preview
When the user confirms save twice with the same import identity
Then one owner-scoped MedicalExam exists and both responses identify it

Given parsing or saving fails
When the error is shown
Then the selected report and preview remain available for retry or replacement
```

## 12. Verification Plan

```bash
# Backend
pytest -q --no-cov backend/tests/test_medical_exams.py

# Mobile
cd mobile
npm test -- --runInBand components/medical/__tests__/MedicalExamImportFlow.test.tsx
npm test -- --runInBand components/chat/__tests__/ChatInputBar.test.tsx
npx tsc --noEmit

# Repo hygiene
git diff --check
```

## 13. Rollout And Rollback

Validate backward compatibility locally. Do not deploy backend or ship/rollback Mobile OTA; the
existing production state remains unchanged. No database migration is required.

## 14. Open Questions

- Multi-page camera capture can be promoted after one-report preview/save is
  stable; the UI should not imply support before it is verified.

## 15. Changelog

| Date | Change | Reason |
|---|---|---|
| 2026-07-29 | Initial approved spec | Repair failed immediate-write import UX |
