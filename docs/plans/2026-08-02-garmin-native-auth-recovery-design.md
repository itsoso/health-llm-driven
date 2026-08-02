# Garmin Native Auth Recovery Design

## Decision

Replace every application-owned `garth`/curl-cffi compatibility path with one
shared adapter over `garminconnect` 0.3.6 native DI OAuth. Keep backend state as
the source of truth and add a focused Mobile recovery screen.

The chosen design is the complete recovery option approved by the user:
backend auth/session/MFA/workout migration plus Mobile bind/reconnect/MFA and
honest sync errors.

## Alternatives Considered

1. **Downgrade to `garminconnect==0.2.38`.** Fastest temporary rollback, but it
   restores an obsolete private API and preserves duplicate garth/curl-cffi
   patches. Rejected because the next upgrade would repeat the outage.
2. **Backend-only native migration.** Restores some scheduled syncs but leaves
   Mobile users unable to recover revoked or MFA-challenged accounts. Rejected
   because Mobile is the primary daily surface.
3. **Native migration plus Mobile recovery.** Chosen because it removes the
   incompatible API and closes the smallest user-visible recovery loop.

## Backend Components

Introduce a focused native-auth adapter used by `GarminConnectService`,
`WorkoutSyncService` and the Garmin maintenance task. It owns:

- construction of the pinned `Garmin` client without `.garth` access;
- native token restore via `login(tokenstore)`;
- password login with `return_on_mfa=True`;
- MFA resume via `Garmin.resume_login(client_state, code)`;
- authenticated-client validation using native DI token state;
- token serialization via `client.dumps()` and encrypted persistence.

Daily collection and workout parsing remain in their existing services. They
receive an authenticated client from the adapter and do not implement separate
fallback authentication.

## Encrypted Token Envelope

Reuse `GarminCredential.garth_session` to avoid a schema migration, but treat
the column as a generic encrypted Garmin session field in code and comments.
The stored value is a JSON envelope:

```json
{
  "version": 2,
  "format": "garmin_di_oauth",
  "ciphertext": "<fernet ciphertext>"
}
```

`ciphertext` contains the native `client.dumps()` payload encrypted with the
existing Garmin encryption key. A dedicated codec performs strict version and
format validation. Malformed, undecryptable or legacy oauth1/oauth2 blobs are
never passed to the native client and are classified as requiring migration.

Updating the username/password invalidates the prior token envelope,
expiration marker and MFA flag. Deleting credentials removes both password and
token state through the existing owner-scoped service.

## Authentication State Machine

```text
no credentials
  -> save encrypted credentials
  -> native login
     -> success: persist encrypted token, clear MFA, connected
     -> MFA: retain short-lived in-memory client_state, mark requires_mfa
        -> valid code: resume, persist token, clear MFA, connected
        -> invalid/expired: actionable retry or reconnect

existing token envelope
  -> native login(tokenstore)
     -> success/refresh: persist rotated token, connected
     -> rejected/malformed: encrypted-password login
        -> success or MFA as above
```

The short-lived MFA session remains in process and contains only the minimal
native client state required by the library. It is never returned to Mobile;
Mobile receives an opaque application MFA session identifier.

## Sync And Renewal

Manual sync, scheduled daily sync, workout sync and maintenance all call the
same adapter. Native login handles refresh-token rotation. After any successful
restore or refresh the adapter writes the current encrypted token payload back
to the credential row.

The old fixed 23-hour session expiry no longer decides validity. An optional
timestamp remains operational metadata; authentication truth comes from the
native token restore. There is no garth refresh or curl-cffi fallback.

## API And Mobile

Preserve existing endpoint paths and response shapes where possible. Correct
state semantics so successful MFA clears `requires_mfa`, and return actionable
authenticated errors for `not_configured`, `reconnect_required`, `mfa_required`
and sync failures without including upstream response bodies or secret data.

Add a dedicated Mobile Garmin connection screen reached from Settings. It
loads credential status and supports:

- bind or replace username/password with secure password entry;
- test/connect;
- MFA code submission when challenged;
- manual sync for connected users;
- enable/pause scheduled sync and delete credentials;
- inline actionable error text and refresh after each successful transition.

The Settings row becomes navigation rather than an unconditional sync action.
After a successful sync, Mobile invalidates its health snapshot so new data is
visible without an app restart.

## Security And Failure Handling

- Every credential and sync endpoint remains authenticated and user-scoped.
- Logs contain user ID, operation category and counts only; never usernames,
  passwords, MFA codes, tokens, serialized clients or upstream bodies.
- Decryption and token parsing fail closed to reconnect.
- The service does not silently report success when authentication or data
  collection failed.
- Partial daily/workout collection retains existing transaction semantics; no
  new health interpretation is introduced.

## Test Strategy

Use 0.3.6-shaped fake clients and no live Garmin credentials in tests. Start
with failing tests for client creation, encrypted envelope round-trip, legacy
rejection, native restore/refresh, MFA resume, credential state reset, workout
client validation and maintenance-task reuse. Add API contract tests for error
categories and Mobile tests for unbound, reconnect, MFA, sync and honest errors.

Then run focused regression suites, type checking, compile checks, dossier and
system-map drift checks, and `git diff --check`.

## Rollout

Deploy and verify the backend before Mobile OTA. Production checks must not use
or print real credentials: verify package/API shape, service import, protected
route behavior and connector status; perform an actual user sync only through
the authenticated product flow. Then publish the Mobile JS/TS bundle and verify
status, reconnect/MFA and sync behavior on the production app.
