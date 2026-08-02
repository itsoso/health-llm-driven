# Garmin Native Auth Recovery

| Field | Value |
|---|---|
| date | 2026-08-02 |
| status | ready_to_deploy |
| current_stage | G3/G4 PASS; G5 deployment retry pending after unit-drift fix |
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
- In 0.3.6 MFA mode, the returned challenge state contains the native HTTP
  client and its cookies/CSRF response. It cannot safely cross a process
  boundary, so recovery must keep a short-lived user-bound server-side session
  and preserve worker affinity until a durable encrypted coordinator exists.
- Regression introduction: dependency upgrade in `0826b2246` without a matching
  adapter migration.

## Decision

Implement the user-approved native-auth recovery described in
`docs/specs/active/2026-08-02-garmin-native-auth-recovery.md` and
`docs/plans/2026-08-02-garmin-native-auth-recovery-design.md`:

- migrate backend authentication, refresh, MFA and workout sync to the native
  `garminconnect` 0.3.6 token store;
- store the native token store in a versioned encrypted envelope;
- keep the backend on one process for native MFA affinity while moving all
  blocking Garmin SDK work to a dedicated two-thread executor, with locked MFA
  session access, so slow Garmin I/O cannot stall the API event loop;
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
secret leakage, legacy-token confusion, duplicate authentication paths and
event-loop starvation. The implementation uses user-bound short-lived sessions,
fail-closed decoding, safe errors, one shared adapter, one Uvicorn worker for
challenge affinity, a bounded two-thread Garmin executor and an MFA session
lock. The single-worker constraint has an infrastructure regression test. G4
remains mandatory before deployment.

### G3 Tests: PASS

Focused Garmin and infrastructure verification is green: 133 backend tests,
including event-loop responsiveness, bounded executor capacity, whole-flow
scheduler isolation, serialized MFA verification, post-commit truth and
single-worker affinity. Blocking Ruff, compileall, doc drift and dossier checks
are green. The full Mobile suite is green at 289 suites / 2,274 tests, plus
TypeScript, lint and design-token checks. The secondary Web surface is green at
54 suites / 312 tests, TypeScript and lint (0 errors; pre-existing warnings
only). The complete backend suite is green across mutually exclusive shards:
9,537 passed and 12 skipped (9,549 collected). Twenty-four unrelated knowledge
release tests initially hit the filesystem sandbox's loopback-bind restriction;
both complete affected files then passed 66/66 outside that restriction.

### G4 Safety Review: PASS

Required because the change handles credentials, refresh tokens and private
health-data ingestion. Independent reviews returned NO-GO findings including
shared live-client caching, token/MFA log leakage, false-green daily/workout
sync, non-atomic reconnect truth, parser regression, side-effecting test flow,
cross-worker MFA loss, post-commit cleanup false failure and single-worker
event-loop starvation. Each finding now has a regression test and architectural
fix: Web/Mobile share the scheduler truth path, Celery fails loudly, test-purpose
MFA never writes connection state, commits remain authoritative, production MFA
has process affinity, and all API-side Garmin work runs in a bounded executor
with locked session access.

The third independent review returned **GO** after verifying the two-thread
executor, all connect/test/verify entry points, whole-scheduler isolation,
deadlock-free retry, single-worker affinity and locked session lifecycle. Its
independent focused suite passed 143 Garmin, Workout Twin and infrastructure
tests, with no new production blocker. Long-term follow-up: replace the
process-local challenge with an encrypted durable coordinator before restoring
multiple Uvicorn workers.

### G5 Deployment Health: PENDING

The first backend deployment reached commit `5ecaaa41a1c2`, completed database
backup and restore rehearsal, and passed the built-in 60/60 health gate. The
Garmin-specific post-deploy probe then correctly blocked G5: the repository
base unit specified one worker, but the older `/etc/systemd/system` unit still
ran two because the release transaction only installs the runtime-state
drop-in.

The deployment artifact now resets and replaces `ExecStart` in that
transactional drop-in, and `deploy.sh` rejects an effective production command
that does not contain `--workers 1`. The complete infrastructure, deploy and
runtime-state transaction regression suite passes 244 tests. A second backend
deployment and effective-unit probe remain required before G5 can pass; Mobile
OTA has not started.

### G6 Production Verification: PENDING

Production credential status, reconnect/MFA recovery and one manual sync remain
to be verified without exposing secrets.
