# Garmin Native Auth Recovery

| Field | Value |
|---|---|
| date | 2026-08-02 |
| status | definition |
| current_stage | G1 passed; design approved; G2 pending implementation plan |
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

### G2 Feasibility And Risk: PENDING

Pending the task-level implementation plan, contract consistency check and
security pre-review.

### G3 Tests: PENDING

Test-first implementation has not started.

### G4 Safety Review: PENDING

Required because the change handles credentials, refresh tokens and private
health-data ingestion.

### G5 Deployment Health: PENDING

Backend deployment and Mobile OTA have not started.

### G6 Production Verification: PENDING

Production credential status, reconnect/MFA recovery and one manual sync remain
to be verified without exposing secrets.
