# Garmin Native Auth Recovery

| Field | Value |
|---|---|
| date | 2026-08-02 |
| status | blocked |
| current_stage | G5 PASS; G6 BLOCKED by EAS asset processing and authenticated-account smoke |
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

### G5 Deployment Health: PASS

The first backend deployment reached commit `5ecaaa41a1c2`, completed database
backup and restore rehearsal, and passed the built-in 60/60 health gate. The
Garmin-specific post-deploy probe then correctly blocked G5: the repository
base unit specified one worker, but the older `/etc/systemd/system` unit still
ran two because the release transaction only installs the runtime-state
drop-in.

The deployment artifact now resets and replaces `ExecStart` in that
transactional drop-in, and `deploy.sh` rejects an effective production command
that does not contain `--workers 1`. A second deployment then stopped in
read-only preflight, before changing the service or live environment, because
the transaction parser's exact candidate whitelist still described the old
drop-in. The parser now accepts only the new byte-exact single-worker artifact,
with a drift regression linking the checked-in file to the production parser.
A third deployment passed preflight but stopped in phase `PREPARED`: effective
systemd state correctly showed the new one-worker command, while candidate
validation still required the backend command to equal its old snapshot. All
services were inactive under the armed boot gate, so the staged controlled
rollback runner restored commit `5ecaaa41a1c2`, schema compatibility, auth
probe, runtime state and active service health before further work continued.

Candidate validation now requires the exact new Uvicorn path and argv for the
backend while retaining fail-closed rejection of additional or changed command
records. The complete infrastructure, deploy and runtime-state transaction
suite passes 245 tests. The final backend deployment of commit `64fbf0b016fc`
passed candidate preflight/install, three 60/60 health checks, exact revision,
guard/staged serving contracts, Skills 22/22 and transaction finalize. A
separate production probe confirmed all four units active and the effective
backend command contains `--workers 1` and no `--workers 2`.

### G6 Production Verification: BLOCKED

Production health and the Garmin credential, sync, connect, test and MFA routes
are live; unauthenticated probes returned 401 for all five, proving registration
and auth protection without sending real credentials. Production intentionally
disables OpenAPI/Docs, so route probes replace a public schema fetch.

The production Mobile OTA built successfully, but repeated Hermes uploads
failed before an update ID with EAS asset-processing timeout/connection-reset
errors. Expo CLI's supported `--no-bytecode` export and EAS Update's supported
`--input-dir --skip-bundler` path were added as a fail-closed fallback after the
two normal retries, plus an explicit direct retry for a previously submitted
asset hash; release-lock, ID, manifest and anchor behavior passes all 17 Mobile
release-script tests.

Both the fallback JS asset and its direct same-hash retry also timed out in EAS
processing. No update group was published: `.last-ota-commit` and the release
manifest remain on known-good commit `ffa790f67c62`. G6 is therefore blocked on
an external EAS per-asset processing failure and on the lack of a safe
authenticated Garmin account for one credential/reconnect/MFA/manual-sync
smoke. Do not mark the feature complete until both are cleared.
