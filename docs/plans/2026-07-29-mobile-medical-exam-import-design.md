# Mobile Medical Exam Import Design

## Decision

Use a single full-screen import flow shared by Chat and
`/import?focus=medical`. Do not stack another bottom sheet on the Chat
attachment sheet.

## Interaction

The screen has three visible phases:

1. **选择报告**: PDF file, camera, or photo library. The selected file remains
   visible until the user replaces or closes it.
2. **核对结果**: show report date/type/source, extracted item count, abnormal
   count and a compact sample. Nothing is written yet.
3. **已保存**: show one success state with actions to view the report or return
   to Chat.

The bottom primary action is stable and phase-specific: `开始解析`,
`保存到健康档案`, or `完成`. Parser and save errors render inline above the
action with `重试` and `更换报告`; no blocking system alert is used for
recoverable service failures.

## Visual Direction

- Use the existing warm app background, white unframed content and restrained
  green accent.
- Keep the progress indicator textual and compact; no oversized hero or nested
  cards.
- Source actions are three scan-friendly rows with icons and one-line helper
  copy.
- The review area is one bounded report preview, not a card inside a card.
- The sticky action respects safe-area and keyboard insets.

## Data Boundary

Parsing and persistence are separate network operations. PDF and image preview
endpoints return structured candidate data without writing. The confirmed
create call carries a random per-import idempotency key; the backend stores only
a namespaced one-way fingerprint and returns the existing report on replay.

## Failure Recovery

- Picker cancellation: remain on source selection.
- Permission denial: show a source-specific inline message and keep other
  source choices available.
- Parser failure: preserve the asset and allow retry.
- Save/network failure: preserve the parsed preview and idempotency key.
- Closing before save: discard the local draft and do not write.

## Compatibility

Legacy `/medical-exams/import/pdf` and `/medical-exams/import/image` remain for
other clients. Chat only emits `medical_exam_import_result` after confirmed
persistence.
