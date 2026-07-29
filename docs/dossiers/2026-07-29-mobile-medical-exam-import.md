# Mobile Medical Exam Import

| Field | Value |
|---|---|
| date | 2026-07-29 |
| status | ready_for_deploy |
| current_stage | G4 passed; G5 awaiting explicit production-backup authorization |
| owner_surface | Mobile / Medical Exams |

## Problem

The Chat attachment menu uses a nested import sheet and immediately persists a
selected report. Recoverable failures close the sheet and discard user context.

## Decision

Implement the approved preview-first, manual-confirm and idempotent flow defined
in `docs/specs/active/2026-07-29-mobile-medical-exam-import-flow.md`.

## Gates

### G1 Product Admission: PASS

This repairs the HealthTwin capture loop and reduces the risk of unreviewed OCR
becoming health truth.

### G2 Feasibility And Risk: PASS

Existing PDF preview, medical exam create and source fingerprint primitives can
be extended without a migration or new service.

### G3 Tests: PASS

- Backend medical exam API regression: 20 passed.
- Mobile import service, flow, Chat and focused-route regression: 99 passed.
- TypeScript `--noEmit`: passed.
- Mobile design token ratchet: passed with no new drift.
- System-map documentation drift check: passed.

### G4 Safety Review: PASS

Preview endpoints require authentication and perform no persistence. Confirmed
saves bind to the authenticated owner, ignore client-supplied ownership and use
an owner-scoped, content-free idempotency fingerprint. Parse and save failures
retain the selected report or parsed preview for retry. Logs contain no report
text or extracted values.

### G5 Deployment Health: BLOCKED

The standard deploy workflow creates a fresh production health-data backup and
encrypted offsite export. Deployment is intentionally blocked until the user
explicitly authorizes that sensitive backup operation for this release.

### G6 Production Verification: BLOCKED

Pending backend deployment, Mobile OTA and production/simulator verification.
