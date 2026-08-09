# Authenticated Conversation No-Store Design

**Date:** 2026-08-09  
**Release:** iOS 1.3.3 / TestFlight Build 253  
**Status:** Approved

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
4. Deploy the backend through the guarded project deployment flow.
5. Verify production returns `Cache-Control: no-store` without exposing review
   credentials or health content.
6. Reinstall TestFlight Build 253 once to remove the response cached before the
   fix, then require the safe physical-device suite to pass all six tests.

## Rollback

Revert the backend commit and redeploy the previous revision. No schema,
fixture, native binary, or stored health data migration is involved.
