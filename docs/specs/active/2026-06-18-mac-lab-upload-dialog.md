# Mac Lab Upload In Dialog

> Status: accepted
> Date: 2026-06-18

## Decision

Add Mac app support for uploading lab reports from an explicit record entry and directly from the Agent dialog. The smallest slice reuses existing backend import endpoints and does not add a new database table or new medical judgment flow.

## Requirement Admission

- Classification: new_product_behavior
- Core loop step: Labs -> HealthTwin -> Safety/Ranking context
- Objects: HealthTwin, LeveragePoint, HealthProblem input data
- Target surface: Mac workbench and Agent dialog
- Source of truth: backend `medical_exams` and derived medical indicators
- Safety level: privacy_sensitive
- Autonomy tier: manual_confirm for file selection, no autonomous medical action
- Evidence boundary: OCR/import output is data capture, not diagnosis
- Verification: Mac Core tests for upload routing and Agent extra context

## Surface Contract

- Record surface shows a lab report upload entry for image/PDF files.
- Agent composer supports lab images/PDF through attach, drag-drop, and image paste.
- Sending a message with a lab attachment imports the report first, then includes `exam_id`, item counts, abnormal count, file name, and source hash in Agent context.
- The UI must remind the user that OCR/import results need review and correction before medical reliance.

## Non Goals

- No new backend endpoint.
- No automatic diagnosis or dose/medication decision.
- No full review-and-confirm OCR editor in this slice.

## Changelog

- 2026-06-18: Accepted minimal implementation slice.
