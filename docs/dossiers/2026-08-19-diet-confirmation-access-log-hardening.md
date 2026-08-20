# Diet Confirmation And Access Log Hardening

| Field | Value |
|---|---|
| date | 2026-08-19 |
| status | in_progress |
| current_stage | G2 PASS; G3 implementation pending |
| owner_surface | Mobile diet confirmation / Backend production telemetry |

## Problem

The compact Mobile diet draft reports all recognized food items but silently
renders only the first four. Production Uvicorn access logs also record raw
request targets, which can include private filenames and signed upload query
parameters.

## Decision

Implement the approved design in
`docs/plans/2026-08-19-diet-confirmation-access-log-hardening-design.md`:

- retain a four-item compact diet summary while making every remaining item
  explicitly expandable and collapsible; and
- disable Uvicorn raw access logging only after application-owned sanitized
  route-template logging is present.

No recognition, nutrition estimation, write-intent, API, database, ownership,
or medical behavior changes are in scope.

## Gates

### G1 Product Admission: PASS

This repairs truthfulness at the existing Mobile confirmation surface and
reduces production telemetry exposure. It maps to the existing diet
`WriteIntent` confirmation flow and to infrastructure maintenance; it creates no
new product object, autonomous action, or health claim.

### G2 Feasibility And Risk: PASS

Source inspection confirms the fifth and later ingredient rows are discarded by
a fixed four-item slice. Production systemd artifacts currently leave Uvicorn's
raw access logger enabled. The chosen solution is local-state disclosure plus a
pure-ASGI route-template logger. It requires no migration and preserves existing
history and confirmation behavior.

Primary risks are a tall card, accessibility regression, loss of operational
telemetry, or accidentally moving private data into a replacement log. A compact
default, explicit accessible control, fixed log field allowlist, `<unmatched>`
fallback, and systemd contract tests address those risks.

### G3 Tests: PENDING

Failure-first and regression evidence will be recorded after implementation.

### G4 Privacy And Security Review: PENDING

The review must confirm that the replacement log contains only method, route
template, status, and duration, and that production Uvicorn raw access logging
is disabled in both deployable artifacts.

### G5 Deployment Health: PENDING

Backend deployment and production health evidence are not yet available.

### G6 Production Verification: PENDING

Production log-sentinel verification and Mobile OTA applicability are not yet
available.

## Rollback

Rollback is the preceding source revision. There is no data migration and no
record repair step. A failed Backend or OTA gate stops the release and keeps the
dossier in a blocked state.
