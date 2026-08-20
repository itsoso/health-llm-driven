# Diet Confirmation And Access Log Hardening Design

> Status: approved
> Date: 2026-08-19
> Scope: Mobile diet draft disclosure and Backend HTTP access logging

## Problem

The compact diet draft card reports the complete number of recognized food
items but renders only the first four. A user can therefore confirm a record
without seeing every recognized item. Separately, Uvicorn and Nginx default
access logs record the raw request target, including signed upload query
parameters. This puts short-lived capabilities and private filenames into
production logs.

## Decision

### Diet draft disclosure

Keep the compact card at four visible ingredients by default. When more items
exist, render an explicit `查看其余 N 项` button immediately below the visible
ingredients. Pressing it expands the same list to all recognized items and
changes the control to `收起`. The control is a real accessible button with a
descriptive label.

This preserves the scan-friendly card while removing silent truncation. It does
not change recognition, nutrition estimation, editing, confirmation, or stored
data.

### Sanitized access logging

Disable Uvicorn's raw access logger in both production systemd ExecStart
artifacts and disable raw access logging in both Nginx server blocks. Add one
application-owned ASGI middleware that logs only:

- HTTP method;
- resolved route template, such as `/api/v1/upload/files/{category}/{file_id}`;
- response status;
- bounded request duration.

The middleware never logs raw paths, query strings, headers, bodies, filenames,
client addresses, user identifiers, or exception text. Requests that do not
resolve to a route use the constant `<unmatched>` instead of the raw path.
Exceptions are re-raised after recording a status of 500 so existing error
handling remains authoritative.

Existing slow, timeout, and exception logs reuse the same safe route-template
resolver. Exception logs retain only the exception type, never the exception
message, because exception text can contain user input or private filenames.

## Alternatives Rejected

1. **Render every ingredient by default.** Truthful but makes ordinary chat
   cards unnecessarily tall and degrades conversation scanning.
2. **Keep the first four with no disclosure.** Preserves height but continues
   the current correctness bug.
3. **Regex-redact proxy or Uvicorn log lines.** Fragile because new query keys, encoded
   values, filenames, or future routes can bypass the filter. It also retains
   unnecessary user-specific paths.
4. **Remove access logging entirely.** Avoids exposure but loses basic route,
   status, latency, and incident evidence.

## Data And Safety Boundaries

- No API, database, write-intent, or health-record schema changes.
- Ingredient text remains device-visible health data and is not added to logs.
- Signed upload capabilities remain usable but are absent from new access logs.
- Existing slow, timeout, and exception logs use the same route-template-only
  boundary and exclude exception messages.
- The structured logger is operational telemetry only and must not become a
  user-level audit trail.

## Acceptance Criteria

1. Given eight recognized foods, the compact card initially renders the first
   four and an explicit `查看其余 4 项` control.
2. Activating that control makes all eight foods visible; activating `收起`
   returns to the compact state.
3. Four or fewer foods render no expansion control.
4. A request containing a private filename and signed query values produces an
   access record with the route template, method, status, and duration, but none
   of those private values.
5. An unmatched request logs `<unmatched>` and never the raw request target.
6. Both production Backend ExecStart artifacts contain `--no-access-log`, and
   both production Nginx server blocks contain `access_log off`.
7. Existing card confirmation, Backend routing, timeout, and deployment
   contracts continue to pass.

## Rollout And Rollback

The Backend middleware, systemd, and Nginx changes deploy together so sanitized
logging is active before raw proxy and Uvicorn logging is disabled. The Mobile
disclosure is a pure JavaScript/TypeScript change and can ship by the guarded
production OTA path after the Backend deployment is healthy. Rollback is the
previous source revision; no data migration or repair is required.
