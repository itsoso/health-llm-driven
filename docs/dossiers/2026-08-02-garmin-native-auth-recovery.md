# Garmin Native Auth Recovery

| Field | Value |
|---|---|
| date | 2026-08-02 |
| status | planned |
| current_stage | implementation hardened; G3 integration and G4 re-review in progress |
| owner_surface | Backend / Mobile data connection |

## Problem

Production installs `garminconnect==0.3.6`, but the application adapter still
dereferences the removed `Garmin.garth` client. Every Garmin authentication or
session-resume attempt therefore fails before login, and Mobile exposes only a
generic manual-sync failure without a reconnect or MFA recovery path.

## Evidence

- Production dependency: `garminconnect==0.3.6`.
- Production no-network reproduction: constructing the current patched client
  raises `AttributeError: 'Garmin' object has no attribute 'garth'`.
- The installed client exposes native `client.dumps()`, `client.loads()`,
  `login(tokenstore)` and `resume_login(client_state, mfa_code)` APIs.
- In 0.3.6 MFA mode, login returns `("needs_mfa", None)` and retains challenge
  state in the native client, so recovery must keep a short-lived user-bound
  server-side session rather than expect a returned state dictionary.
- Regression introduction: dependency upgrade in `0826b2246` without a matching
  adapter migration.

## Decision

Implement the user-approved native-auth recovery described in
`docs/specs/active/2026-08-02-garmin-native-auth-recovery.md` and
`docs/plans/2026-08-02-garmin-native-auth-recovery-design.md`:

- migrate backend authentication, refresh, MFA and workout sync to the native
  `garminconnect` 0.3.6 token store;
- store the native token store in a versioned encrypted envelope;
- add a Mobile bind/reconnect/MFA/sync recovery surface with truthful errors;
- deploy backend first, then publish the Mobile JS/TS change by production OTA.

## Gates

### G1 Product Admission: PASS

This restores the existing wearable Data In -> Health Twin loop and the
Wearable Router's Garmin input. It introduces no diagnosis, treatment advice or
new wearable metric.

The user explicitly selected the complete backend plus Mobile recovery option
(`方案 1`) on 2026-08-02.

### G2 Feasibility And Risk: PASS

The production 0.3.6 authentication, serialization, refresh and MFA source
contracts were inspected directly. The implementation plan is recorded in
`docs/plans/2026-08-02-garmin-native-auth-recovery-implementation.md`.

The slice needs no schema migration: the legacy-named session column can hold a
strict versioned encrypted envelope. The highest risks are cross-user MFA state,
secret leakage, legacy-token confusion and duplicate authentication paths; the
plan addresses them with user-bound short-lived sessions, fail-closed decoding,
safe errors and one shared adapter. G4 remains mandatory before deployment.

### G3 Tests: PENDING

Focused Garmin verification is green: 119 backend tests, 20 Mobile Garmin /
Settings tests, TypeScript, blocking Ruff, compileall, Mobile lint and design
token checks. The full Mobile suite is green at 284 suites / 2,196 tests. Full
backend integration remains pending after reconciling the latest `origin/main`.

### G4 Safety Review: PENDING

Required because the change handles credentials, refresh tokens and private
health-data ingestion. The first independent review returned NO-GO on shared
live-client caching, token log leakage, false-green sync errors and non-atomic
reconnect. Those paths now have regression tests and architectural fixes; a
fresh independent re-review is running before any deployment.

### G5 Deployment Health: PENDING

Backend deployment and Mobile OTA have not started.

### G6 Production Verification: PENDING

Production credential status, reconnect/MFA recovery and one manual sync remain
to be verified without exposing secrets.
