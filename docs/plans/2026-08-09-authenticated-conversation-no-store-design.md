# Authenticated Conversation No-Store Design

**Date:** 2026-08-09  
**Release:** iOS 1.3.3 / TestFlight Build 253  
**Status:** Implemented historically; current release verification BLOCKED

> **Current safety override (2026-08-12):** the historical production deploy, reinstall and
> physical-device steps below are not executable. All repo-contained automatic remote/vendor
> release entrypoints, local signing/install/automatic-provisioning entrypoints and OTA/rollback
> channels are frozen. The repository XCUITest harness is Simulator-only. Physical acceptance may
> resume only as separately authorized external manual evidence after the freeze is lifted.

## Problem

The final physical-device acceptance run loaded an older authenticated health
conversation after the App Store review fixture had been reset. The production
API returned the correct latest fixture, but the iPhone made no conversation
list or detail requests during repeated cold launches. Both authenticated GET
endpoints omitted cache-control headers, so the client could reuse an older
response from its URL cache.

This is a release blocker because stale authenticated health conversation data
can mislead the user and can make deterministic App Review preparation depend
on deleting and reinstalling the app.

## Decision

Set `Cache-Control: no-store` on both authenticated conversation read paths:

- `GET /api/v1/agent/conversations`
- `GET /api/v1/agent/conversations/{conversation_id}`

The server response is the enforcement point. This fixes the already-uploaded
Build 253 without a new native binary and protects every current client.

## Alternatives Considered

1. Add `cache: 'no-store'` only to the mobile requests. This is useful defense
   in depth but would require a new App Store build, so it is not the release
   fix.
2. Add a cache-busting query parameter. This is brittle, creates unbounded cache
   keys, and does not express the privacy contract.
3. Require users or reviewers to reinstall after fixture changes. This is not
   an acceptable product behavior or release procedure.

## Implementation

Accept FastAPI's `Response` in the two route handlers and set the same
`Cache-Control: no-store` header already used by the authenticated turn-status
endpoint. Do not change response bodies, sorting, persistence, authentication,
or mobile UI behavior.

## Verification

1. Add request-level tests that fail against the current handlers because the
   header is missing on both list and detail responses.
2. Implement the response header and make both tests pass.
3. Run the relevant Agent conversation API suite and release-pack checks.
4. Run local tests and read-only release validation; the automatic backend release entrypoint is
   frozen and this plan cannot authorize deployment.
5. Observe production read-only only; do not interpret the current header as proof that this change
   was deployed by the present transaction.
6. Run the repository acceptance harness against iOS Simulator only. Do not reinstall or connect a
   physical iPhone. Same-build physical acceptance remains BLOCKED until a future, separately
   authorized external manual evidence process runs after the global freeze is lifted.

## Rollback

The historical rollback would revert the backend commit and redeploy the previous revision. During
the freeze, no repository deploy/rollback command is authorized; record BLOCK and route any future
recovery through the newly approved external trust root. No schema, fixture, native binary, or
stored health data migration is involved.
