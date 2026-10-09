# Feature Spec: Owned health record repair

> Status: implementing
> Updated: 2026-10-09
> Parent dossier: docs/dossiers/2026-10-09-targeted-release-pipeline.md

## Decision and admission

Repair the existing observation and review loop: preserve explicit symptom-status observations, expose complete owned medical reports, and separate Garmin synchronization from activity evidence.

```yaml
RequirementAdmission:
  request: Repair failed symptom recording, report access and compound Garmin review.
  classification: engineering-maintenance
  first_user_fit: Existing users maintaining and reviewing their own health records.
  core_loop_step: Record observation, retrieve evidence, review limitations.
  first_class_objects: SymptomEntry, MedicalExam, WorkoutRecord, existing sync execution.
  target_surface: Mobile conversation and report screens, authenticated API, Health MCP.
  source_of_truth: Authenticated owner rows and current server-correlated sync receipts.
  safety_level: Sensitive reads, health writes and conditional health explanation.
  prescription_or_causal_verdict: No new diagnosis, prescription or causal verdict.
  autonomy_tier: Explicit current-user command within closed scopes.
  evidence_provenance: Stored report text, actual activity time, current task receipt, verbatim self observation.
  claim_hedging: OCR is not original-image verification; historical records are not current diagnosis.
  verification_window: Fresh unit, PostgreSQL, live-model, independent safety and exact revision release gates.
  success_metric: Authorized requests execute; errors, incomplete evidence and ambiguous records stay explicit.
  added_user_burden: Report selection only when complete evidence exceeds a bounded response.
  burden_justification: Avoid silently truncating material clinical evidence.
  non_goals: Automatic illness resolution, inferred severity, new schema, relaxed owner isolation.
  smallest_end_to_end_slice: Original utterance through capability gateway and owned DB to truthful persisted reply.
  stale_surface_to_remove_or_archive: Failure-as-empty-list and sync-success-on-all-activity-errors behavior.
  spec_required: yes
```

## Data and surface contract

- A closed explicit self status-record command creates one existing `SymptomEntry` with full original description and general body location. Recovery and residual symptoms remain together. It does not set severity, invent a date or update an illness to resolved. Quoted, third-person, cancelled and extra-action text stays outside this proof.
- Medical list failures throw and render a retry state. `GET /medical-exams/me/{exam_id}` filters the authenticated owner and uses the existing response schema. A selected report remains selected even when older than the list window. Legacy `exam-explain/{id}` and canonical `medical-exam/{id}` select the same owner-checked record; client summaries never authorize or supply medical evidence.
- A closed anatomy/MRI question reads owned, nonfuture matching reports without an arbitrary recent-year default. Assessment and conclusions are complete; oversized or ambiguous sets require selection. Stored text may originate from OCR or manual entry and is not a new interpretation of original imaging.
- Health MCP exposes bounded report listing and a full owned detail tool. List abbreviation is explicit and supplies the detail ID. Errors are not represented as absent history. Deploying this repository does not independently update third-party connector allowlists.
- A closed Garmin compound request admits sync plus today's latest actual Garmin running record only. Activity time is distinct from upload/update time. Unknown or tied timestamps, absent records and mismatching distance cannot verify the just-completed run. No background distance statement creates a workout.
- Sync submission, job completion and activity availability remain separate. Per-activity failures propagate through API, Celery and scheduler; committed counts reflect actual successful persistence. Existing settings timestamps alone do not certify the requested activity.
- Focused report turns exclude unrelated history, Twin and client health context; public knowledge remains separate from personal evidence. Existing medical safety and consent gates remain active.

## Verification and release

Use synthetic fixtures, including foreign-owner rows, old selected reports, long assessments, cancellation and model-added fields. Exercise real API and PostgreSQL persistence, current gateway, stream and stored terminal state. Test live model behavior separately from deterministic mocks. No private health snapshots enter repository evidence.

Rollback is code reversal through the normal release gate; no schema or historical record rewrite occurs. Backend deployment and OTA each require exact main CI and durable receipts. Native runtime incompatibility remains a separate mobile release gate and cannot be bypassed by changing a fingerprint pin.
