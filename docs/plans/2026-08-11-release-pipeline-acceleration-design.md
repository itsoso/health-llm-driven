# Release Pipeline Acceleration Design

## Context

The settings-location release changed only Mobile JavaScript and documentation, yet the release path also ran the complete backend and frontend deployment transaction. That transaction correctly performed database backup and restore rehearsal, schema and runtime-state proofs, System KB activation checks, frontend dependency installation and build, and repeated health verification. Those gates are necessary when their inputs change, but invoking them for an OTA-only change added time without adding evidence.

The same release exposed four more sources of avoidable latency:

- validation suites were serial and some shell pipelines hid or weakened real exit codes;
- rebases invalidated commit-based evidence even when the Git source tree stayed identical;
- an EAS upload timeout reran the Mobile export instead of reusing the exact artifact from the same release transaction;
- simulator acceptance did not cover GPS city refresh or the production-visible Settings navigation matrix.

## Goals

1. Route each source change to the smallest safe release mechanism.
2. Make a clean, detached `origin/main` release worktree the normal production source.
3. Run independent validation checks concurrently while preserving every real exit code.
4. Do not let same-UID local validation records authorize a skip; retain full blocking validation until trusted, commit-bound CI evidence exists.
5. Export an OTA artifact once per release transaction and reuse its exact bytes for transient upload retries.
6. Skip expensive server substeps only when a fail-closed proof establishes identical inputs and intact outputs.
7. Add deterministic simulator smoke coverage for GPS city refresh and Settings navigation.
8. Preserve all database, migration, schema, rollback, runtime-state, health, and revision gates.
9. Give the SwiftPM Mac client a reproducible Developer ID release path with notarization,
   immutable artifacts, crash recovery, rollback, and public-route verification.

## Non-goals

- No cross-release persistent OTA bundle cache. EAS environment values can change without a Git change.
- No automatic App Store/TestFlight submission for native changes.
- No Mac App Store/TestFlight packaging in this slice. Formal Mac distribution uses a notarized
  Developer ID DMG outside the store; during the freeze only Mac compile/test is allowed, not
  signing/notarization packaging.
- No simulator replacement for Garmin OAuth, HealthKit, APNs, camera, microphone, Keychain, background execution, or real permission prompts.
- No cache hit may turn a failed proof into success. Missing or malformed proof always falls back to the existing full step.

## Frozen-release safety correction

Implementation and independent review showed a deeper bootstrap-trust failure than the original
surface-specific correction. A same-UID actor can keep the checkout apparently clean/canonical while
changing executed bytes through Git replacement refs, shared `.git/info/attributes` plus local
clean/smudge filters, or an untracked import shadow hidden by `.git/info/exclude`. `BASH_ENV` and
`PYTHONPATH`/`sitecustomize` can also execute before repository-contained shell/Python guards. Thus
the writable repository cannot verify the program doing the verification.

A final hostile-Bash review adds one more constraint: callers can use `BASH_ENV` and functions named
`exit`/`builtin`, so a top-of-file rc78 guard is only an ordinary-invocation tombstone. Any retained
legacy in `deploy.sh` or `_run-mobile-tf.sh` must be inside a literal-false, syntactically unreachable
block and may never be sourced/extracted/eval'd by runtime/operator paths. Isolated tests may extract
marker fixtures only for protocol regression; they may not call writers/network and are not release
proof. `release-dmg.sh` is frozen in its
entirety; a read-only Mac checker must be a separate reviewed file with no writer code. These
tombstones still do not replace the external trust root.

Therefore this release freezes every repo-contained automatic remote/vendor release entrypoint and
every local signing/install/automatic-provisioning entrypoint before mutation:

- server backend/frontend/env/restart/push/health-evidence/App Review reset/coordinator;
- every Mobile OTA/rollback channel, plus production native/EAS/ASC build/upload/selection/submission;
- Mac build/publish/recover/rollback and nginx route mutation;
- legacy raw SSH/direct upload/server-build release helpers and local QR public upload.

Release plan/validate/publish, production-state network modes, and deploy status/logs/inspect are
also frozen because they cross root SSH, token-bearing vendor observation, or untrusted repo
bootstrap. App Store `--final-submit` is frozen because it logs in as the production reviewer and
obtains a writable bearer token. Only non-final-submit static pack/config checks, offline evidence
parsing, public unauthenticated HTTPS, local Metro/iOS Simulator/tests, and offline inspection
metadata/report generation from an existing IPA via
`--no-upload --ipa <EXISTING_IPA>` remain available. This creates no install manifest, install QR,
or installability claim. Bare `--no-upload`, automated
archive/export/signing/provisioning (especially `-allowProvisioningUpdates`) are frozen. EAS channel→branch mapping can drift or
be shared, so preview/development cannot prove isolation from production and all OTA/rollback network
writers are frozen. `npm run ios` uses the Simulator wrapper; callers must not append npm/Expo
`--device`. The wrapper resolves an available Simulator name/UDID to an exact Simulator UDID before
Xcode; physical iOS repo CLI, connection/install and acceptance are frozen. The repository XCUITest
harness also requires an exact available Simulator UDID; future physical
acceptance must be external manual evidence after reauthorization. A manual Gate means STOP/BLOCK, never a direct
CLI/SSH workaround. G5, G6 and App Store submission remain BLOCKED.
Android is not a shipped/audited Mobile surface. `npm run android`/`expo run:android` enters native
generation, debug signing and ADB installation without the exact-iOS-Simulator destination guard,
so the repository entrypoint exits 78; there is no Android native CLI exception.

The protocol code and negative tests remain useful hardening work, but their presence is not release
authority. Re-enabling any frozen writer requires a new dossier and a repo-external, root-owned
launcher using fixed interpreters, an `env -i` allowlist and repo-external materialization of a
canonical Git archive/tree. Source/artifact/cohort authority and recovery must then pass a new,
independent G4 and explicit rollout decision.

Server-local DB migration/setup/admin utilities are not automatic release entrypoints. They belong
to a separate manual-admin Gate and may run only on the production host in an explicitly authorized,
audited change/incident. No automatic release entrypoint may invoke them, and a blocked manual
release Gate cannot be relabeled as an admin event.

## Architecture

### 1. Unified release planner

The historical design had `scripts/release.py` independently probe the live server and EAS
production channel, compare production surfaces with the target commit, and produce a deterministic
plan. Final review revoked that route: `plan`/`validate`/`publish` and production-state network modes
now exit 78 before network/credential access. Only a pure offline evidence parser may consume
caller-supplied local materials; the baseline is never evidence that anything was deployed.
`scripts/release.sh` remains a frozen shell wrapper.

Release surfaces are classified conservatively for this frozen release:

- Mobile JS/TS and ordinary runtime assets: every OTA/rollback channel is blocked and routed to the
  manual Gate; use only local Metro/iOS Simulator/test feedback.
- Mobile native configuration, plugins, native modules, lock/package changes, iOS/Android and Watch
  code: manual native Gate required; OTA and automated native build creation are suppressed.
- Backend: report the frozen server Gate; no production deployment action.
- Frontend: report the frozen server Gate; no production deployment action.
- Mac: manual formal-release Gate required. The planner reports the route but the automated publish,
  recovery, rollback and route entrypoints fail closed with exit 78.
- Documentation/tests/release tooling: validation only.
- Unknown paths: block and require an explicit classifier rule.

Every production plan remains non-publishable. Fresh server/Mobile/Mac network probes are frozen,
not read-only exceptions. Planning/reconciliation may consume only caller-supplied offline evidence
or public unauthenticated HTTPS; neither authorizes a mutation or a completion claim.
Local transaction history never authorizes an omission or completion claim.

The production server probe exposes backend and frontend as independent runtime identities. Backend
identity is tied to the finalized deployment marker plus the live systemd process identities;
frontend identity is tied to a root-owned receipt containing the PM2 pid/uptime and Next BUILD_ID.
A missing historical frontend receipt is represented as unknown and causes the next server release
to use a full deploy that bootstraps the receipt. It is never inferred from the checkout revision.

### 2. Diagnostic release worktree and shared state

The planner maintains a detached worktree outside the repository at `<repo>.release` for validation
diagnostics. It never deletes or resets a dirty worktree. A validation run requires:

- clean tracked and untracked state;
- detached HEAD or branch `main` only;
- `HEAD == origin/main`;
- origin/main remote SHA equals local HEAD.

Release state, receipts, logs, and Mobile anchors live below the Git common directory in
`reva-release-state/`, so all worktrees share one history without committing operational state.
The local state is an audit journal only. Its `completed_actions` cannot prove a live surface, skip a
mutation or resume an automatic production release entrypoint. Production `.env` is not read or
synchronized while frozen.

The state directory is owner-owned mode `0700`. State, log and lock entries are owner-owned,
single-link, non-symlink regular files mode `0600`; reads are byte-bounded and validate type,
owner, mode, link count, inode stability, schema and field types. Snapshot writes use a new
same-directory `O_EXCL` file, complete write and `fsync`, atomic replace, then parent-directory
`fsync`. Any malformed, oversized or unsafe local state fails closed, but even a valid state remains
non-authoritative for production completion.

`plan` and `validate` remain diagnostic. The Git-common-dir locking protocol and production reprobes
are retained for tests/future design, but cannot establish bootstrap trust or authorize a writer.

### 3. Parallel validation and validation authority

Independent checks launch concurrently into separate log files. The coordinator waits for each PID directly, records its true return code, and only reads log tails after completion for display. The default concurrency limit is four.

A diagnostic credential format can bind:

- `HEAD^{tree}`;
- validation profile/version and exact command vectors;
- lockfile hashes;
- Node/npm/Python/Swift/OS fingerprints;
- result and log hashes;
- expiry time.

However, an unsigned local credential and its log are both mutable by another same-UID process.
They therefore cannot authorize the release planner to skip the blocking suite, even when every
fingerprint matches. The current release path runs full validation and issues no local skip. A future
optimization would require independently verifiable, trusted CI evidence bound to the exact commit;
until then GitHub CI remains commit-specific and every publish validates again.

### 4. OTA transaction-local artifact reuse (historical protocol only; all channels frozen)

The first EAS attempt exports into a fresh `mktemp` directory and starts publishing. On a recognized transient upload failure, the script:

1. validates the generated iOS metadata, bundle and referenced assets;
2. rejects symlinks, path traversal, missing or empty files;
3. computes a stable artifact digest;
4. rechecks clean tree, commit, tree hash, runtime and digest;
5. retries upload from the same directory with `--skip-bundler`.

Authentication, runtime, syntax, Metro and configuration errors remain non-retryable. The historical
design queried EAS with a unique transaction identifier to avoid duplicate groups and verified a
non-production publish through structured JSON before updating local state. It is now test-only:
every channel returns exit 78 before network access because channel→branch isolation is not trusted.

### 5. Server step proofs (protocol only; server writer frozen)

Server proof reuse supports `off`, `shadow`, and `on` modes. Shadow mode evaluates and reports potential hits but still performs the full step. On mode skips only the proven step.

- Python dependencies: lock blob, Python/pip/platform, installed distribution set, `pip check`, venv ownership, and receipt must match.
- Frontend dependencies: package/lock blobs, Node/npm/platform and installed dependency proof must match.
- Frontend build: frontend tree, dependency proof, build-environment digest, `.next` output digest, prior PM2/HTTP success must match.
- System KB: artifact/importer/model inputs and a canonical live database projection must match while holding the existing mutation lock. Otherwise import runs. Per-document content hashes avoid re-embedding unchanged documents even when import is required.

These optimizations are not active in production while the server writer is frozen. Any future
re-enable must still never skip database backup/restore rehearsal, migrations, schema probes, release
leases, runtime state transitions, process stability, revision checks, health score or rollback gates.

### 6. Simulator smoke

The existing XCTest harness gains Simulator-only location options. It grants location permission, injects coordinates, validates the expected detected city and ready state, then clears location in a trap. It also walks a maintained production Settings matrix:

- safe navigation entries open, assert a unique target, and return;
- modal-only actions open and cancel;
- logout/version/destructive actions are assertion-only;
- Garmin, HealthKit synchronization, account deletion confirmation, and update application are never automated.

A deterministic contract test keeps the XCTest matrix aligned with production-visible Settings entries.

### 7. Formal Mac publication protocol (production frozen)

The Mac client remains SwiftPM-owned. `apps/mac/scripts/package-app.sh` is a historical source-bound
`.app` packaging protocol, but any signing/package/install invocation is frozen;
`apps/mac/scripts/release-dmg.sh` is the historical Developer ID protocol authority but its entire
entrypoint is frozen, including former preflight/proof modes. Formal writer behavior is retained only
as inert design/test material, and `deploy.sh` rejects Mac mutation. The direct Mac/nginx Python
production CLI is frozen as well. Independent test-only protocol fixtures are the only internal
mutation-shaped exception and require strict non-root execution, explicit test mode and paths wholly
under fixed non-production roots (macOS `/private/tmp` or `/private/var/folders`; `/tmp` elsewhere,
ignoring caller `TMPDIR`); they must not invoke/source/extract/eval `release-dmg.sh`. Local
`create-candidate` requires the same isolation and may emit
candidate metadata, but does not sign, package, upload or publish. The
future protocol requires a clean checkout exactly at
fresh `origin/main`, an explicit monotonically non-regressing version/build, the configured Developer
ID identity and protected App Store Connect API notarization credentials. It signs the app and DMG with hardened runtime and
timestamping, submits and verifies notarization, staples the result, mounts the DMG, and validates the
installed bundle identity, source manifest, architecture and minimum OS before any upload.

The remote publisher installs content-addressed immutable bytes under a source-SHA/artifact-digest
key. Only after the immutable object and a sealed candidate receipt agree does it enter a journaled
crash-recoverable sequence that replaces `/mac/current.json` and the stable identity individually.
Terminal proof requires both to agree; `/xiaoba-mac.dmg` resolves to those same bytes.
Root-owned current/previous receipts, a transaction journal, and a version/build high-water mark make
publish, recovery and rollback fail closed. Recovery is bound to the exact staged publisher, source,
candidate and artifact rather than whatever happens to be on a later `main`.

The Git-common-dir local lock and the single remote release lease cover backend/frontend, Mac route
bootstrap, Mac publish, recovery and rollback. Remote ownership metadata is root-owned, exact-schema,
single-link state; cleanup renames the lease to a private tombstone before removing it, so partial or
unexpected state cannot become an apparently free lock. Ambiguous SSH, signal or terminal-proof
outcomes retain the exact recovery bundle and lease for reconciliation instead of guessing success.

The designed Mac routes would be bootstrapped once through a reversible nginx transaction. The
current shell wrapper is unconditionally frozen before path, lock or SSH access. Route-bootstrap rollback is
allowed only before any formal Mac receipt, journal or current manifest exists; after formal release
state exists, route removal is rejected. Routine server deploys do not rewrite this route. Production
proof checks the private receipt/disk identity and independently downloads the public current manifest,
immutable URL and stable URL over fixed HTTPS, validating route markers, size and digest.

## Error handling and observability

Every release creates a transaction ID and a stage-timing record. A retry of the same release range
may reuse that ID for audit and bounded OTA reconciliation, but must derive execution/skip decisions
again from live production. Failure output identifies the failed stage, elapsed time, log path,
locally observed completed/pending surfaces, and safe retry command. Logs and manifests must not
include secrets or health data.

Classifiers and caches are fail-closed. Unknown input, baseline/live-state disagreement, corrupt local
state or receipt, stale worktree, mismatched artifact, incomplete EAS metadata, or unverifiable or
drifting production state stops publishing; only an optional server step-proof miss may safely fall
back to the original full step.

An interrupted remote mutation is not converted into a normal failure by cleanup. The process exits
with the dedicated reconciliation status, preserves the exact transaction inputs, and blocks all later
supported/controlled release operations until recovery proves a terminal state and releases the lease.

## Rollout

1. Land planner/validation/test/simulator improvements; keep all OTA network paths disabled.
2. Keep every automatic remote/vendor release and local signing/install/provisioning entrypoint at
   exit 78; record G5/G6/Store submission as BLOCKED.
3. Open a new dossier for the repo-external root-owned launcher and canonical materialization design.
4. Run a new G3 and independent G4 before any surface-specific rollout or shadow production proof.

## Success criteria

- A Mobile-only source diff performs no production mutation and reports the manual native Gate.
- A native Mobile diff blocks both OTA and automated native build creation and reports the same Gate.
- Parallel validation fails if any blocking child fails and never pipes a running test into `tail`.
- Same-UID local validation evidence never skips the blocking suite; any future skip authority must be trusted CI evidence bound to the exact commit.
- A forged/stale local state or bootstrap environment cannot reach any production mutation.
- Every repo automatic server/Mobile/Mac/ASC release entrypoint and release bypass returns 78 before mutation.
- Every OTA/rollback channel returns 78 before EAS/network access; transaction reuse remains mock-only protocol coverage.
- Server proof code remains protocol-only and cannot be used to claim deployment.
- Simulator smoke verifies GPS city refresh and representative Settings entries without executing destructive or third-party flows.
- Every Mac production command, direct Python CLI and nginx wrapper fails before production
  path/lock/network mutation; only strict non-root test-mode protocol tests and local
  candidate-metadata creation under the fixed non-production roots remain, and neither claims that
  a formal Mac release exists.
- Repo-contained lock inspection also exits 78 before reading lock/environment state. Output
  redaction cannot prevent `SHELLOPTS=xtrace`/`BASH_ENV` from capturing variables before the repo
  guard; a future repo-external root-owned inspector is required.
- A future launcher is explicitly repo-external/root-owned, uses fixed interpreters + `env -i`, and
  materializes a canonical archive/tree outside the writable repository before execution.
