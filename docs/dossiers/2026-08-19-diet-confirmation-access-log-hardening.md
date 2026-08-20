# Diet Confirmation And Access Log Hardening

| Field | Value |
|---|---|
| date | 2026-08-19 |
| status | in_progress |
| current_stage | G4 PASS; G5 deployment pending |
| owner_surface | Mobile diet confirmation / Backend production telemetry |

## Problem

The compact Mobile diet draft reports all recognized food items but silently
renders only the first four. Production proxy and Uvicorn access logs also
record raw request targets, which can include private filenames and signed
upload query parameters.

## Decision

Implement the approved design in
`docs/plans/2026-08-19-diet-confirmation-access-log-hardening-design.md`:

- retain a four-item compact diet summary while making every remaining item
  explicitly expandable and collapsible; and
- disable proxy and Uvicorn raw access logging only after application-owned
  sanitized route-template logging is present.

No recognition, nutrition estimation, write-intent, API, database, ownership,
or medical behavior changes are in scope.

## Gates

### G1 Product Admission: PASS

This repairs truthfulness at the existing Mobile confirmation surface and
reduces production telemetry exposure. It maps to the existing diet
`WriteIntent` confirmation flow and to infrastructure maintenance; it creates no
new product object, autonomous action, or health claim.

### G2 Feasibility And Risk: PASS

Source inspection confirmed the fifth and later ingredient rows were discarded
by a fixed four-item slice. Production systemd and Nginx artifacts left raw
request-target logging enabled. The chosen solution is local-state disclosure
plus a pure-ASGI route-template logger. It requires no migration and preserves
existing history and confirmation behavior.

Primary risks are a tall card, accessibility regression, loss of operational
telemetry, or accidentally moving private data into a replacement log. A compact
default, explicit accessible control, fixed log field allowlist, `<unmatched>`
fallback, and systemd contract tests address those risks.

### G3 Tests: PASS

Failure-first evidence was observed before each implementation:

- Mobile: the new eight-item disclosure regression failed with 1 failed and 82
  passed because no `查看其余 4 项` control existed; after the fix the suite
  passed 83 tests.
- Backend: the new middleware suite first failed at import. After the initial
  implementation, a second test failed because `RequestContextMiddleware`
  still logged private exception content; after tightening, all 4 privacy tests
  passed.
- systemd: the new `--no-access-log` contract failed before both production
  artifacts and the transactional candidate builder were updated.
- Nginx: the new two-server `access_log off` contract failed before both server
  blocks were updated.

Fresh combined verification on the final local source snapshot:

- Mobile diet card suite: 83 passed.
- Mobile TypeScript: passed.
- Mobile scoped ESLint: 0 errors; 8 pre-existing test-file warnings.
- Backend privacy, infrastructure, and full runtime-state transaction suites:
  126 passed with 6 dependency/framework deprecation warnings.
- System Map, Mobile navigation graph, document drift, dossier consistency, and
  `git diff --check`: passed.

### G4 Privacy And Security Review: PASS

The replacement access logger has a fixed four-field allowlist: method, resolved
route template, status, and duration. Unmatched requests use `<unmatched>`; raw
paths are never a fallback. Slow, timeout, and exception logs use the same safe
template helper, and exception messages are excluded. Uvicorn raw access logging
is disabled in both production ExecStart artifacts, and Nginx raw access logging
is disabled in both production server blocks. The older detailed performance
middleware can log raw data but is not registered in the application; this
slice does not activate it.

### G5 Deployment Health: PENDING

Backend deployment and production health evidence are not yet available.

### G6 Production Verification: PENDING

Production log-sentinel verification and Mobile OTA applicability are not yet
available.

## Rollback

Rollback is the preceding source revision. There is no data migration and no
record repair step. A failed Backend or OTA gate stops the release and keeps the
dossier in a blocked state.
