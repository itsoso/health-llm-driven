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
4. Reuse validation evidence across rebases only when source tree, commands, dependencies, and toolchain are identical.
5. Export an OTA artifact once per release transaction and reuse its exact bytes for transient upload retries.
6. Skip expensive server substeps only when a fail-closed proof establishes identical inputs and intact outputs.
7. Add deterministic simulator smoke coverage for GPS city refresh and Settings navigation.
8. Preserve all database, migration, schema, rollback, runtime-state, health, and revision gates.

## Non-goals

- No cross-release persistent OTA bundle cache. EAS environment values can change without a Git change.
- No automatic App Store/TestFlight submission for native changes.
- No simulator replacement for Garmin OAuth, HealthKit, APNs, camera, microphone, Keychain, background execution, or real permission prompts.
- No cache hit may turn a failed proof into success. Missing or malformed proof always falls back to the existing full step.

## Architecture

### 1. Unified release planner

`scripts/release.py` compares a trusted baseline with the target commit, classifies both sides of additions/deletions/renames, and produces a deterministic plan. `scripts/release.sh` is a small shell wrapper.

Release surfaces are classified conservatively:

- Mobile JS/TS and ordinary runtime assets: production OTA.
- Mobile native configuration, plugins, native modules, lock/package changes, iOS/Android and Watch code: native build required; OTA is suppressed.
- Backend: backend deployment.
- Frontend: full deployment with the current architecture, because a new frontend SHA cannot safely use `deploy.sh -f` until the remote checkout already matches.
- Mac: Mac build required.
- Documentation/tests/release tooling: validation only.
- Unknown paths: block and require an explicit classifier rule.

Mixed backend + OTA releases execute backend first and OTA second. Partial success is persisted per surface so a failed OTA retry does not repeat a successful server deployment.

### 2. Permanent release worktree and shared state

The planner maintains a detached worktree outside the repository at `<repo>.release`. It never deletes or resets a dirty worktree. A production run requires:

- clean tracked and untracked state;
- detached HEAD or branch `main` only;
- `HEAD == origin/main`;
- origin/main remote SHA equals local HEAD.

Release state, receipts, logs, and Mobile anchors live below the Git common directory in `reva-release-state/`, so all worktrees share one history without committing operational state. Directories use mode `0700`, files `0600`. The production `.env` remains in the owner workspace and is referenced through `DEPLOY_ENV_FILE`; it is never copied into Git.

### 3. Parallel validation and tree credentials

Independent checks launch concurrently into separate log files. The coordinator waits for each PID directly, records its true return code, and only reads log tails after completion for display. The default concurrency limit is four.

A successful run writes a credential whose identity includes:

- `HEAD^{tree}`;
- validation profile/version and exact command vectors;
- lockfile hashes;
- Node/npm/Python/Swift/OS fingerprints;
- result and log hashes;
- expiry time.

A rebase with the same tree can reuse the credential. Any command, dependency, toolchain, profile, log, or tree mismatch is a cache miss. GitHub CI remains commit-specific and cannot be inherited from an older commit.

### 4. OTA transaction-local artifact reuse

The first EAS attempt exports into a fresh `mktemp` directory and starts publishing. On a recognized transient upload failure, the script:

1. validates the generated iOS metadata, bundle and referenced assets;
2. rejects symlinks, path traversal, missing or empty files;
3. computes a stable artifact digest;
4. rechecks clean tree, commit, tree hash, runtime and digest;
5. retries upload from the same directory with `--skip-bundler`.

Authentication, runtime, syntax, Metro and configuration errors remain non-retryable. Ambiguous failures first query EAS with a unique transaction identifier to avoid duplicate groups. A successful publish is verified through structured EAS JSON and `update:view` before the manifest or anchor is updated.

### 5. Server step proofs

Server proof reuse supports `off`, `shadow`, and `on` modes. Shadow mode evaluates and reports potential hits but still performs the full step. On mode skips only the proven step.

- Python dependencies: lock blob, Python/pip/platform, installed distribution set, `pip check`, venv ownership, and receipt must match.
- Frontend dependencies: package/lock blobs, Node/npm/platform and installed dependency proof must match.
- Frontend build: frontend tree, dependency proof, build-environment digest, `.next` output digest, prior PM2/HTTP success must match.
- System KB: artifact/importer/model inputs and a canonical live database projection must match while holding the existing mutation lock. Otherwise import runs. Per-document content hashes avoid re-embedding unchanged documents even when import is required.

These optimizations never skip database backup/restore rehearsal for a backend deployment, migrations, schema probes, release leases, runtime state transitions, process stability, revision checks, health score, or rollback gates.

### 6. Simulator smoke

The existing XCTest harness gains Simulator-only location options. It grants location permission, injects coordinates, validates the expected detected city and ready state, then clears location in a trap. It also walks a maintained production Settings matrix:

- safe navigation entries open, assert a unique target, and return;
- modal-only actions open and cancel;
- logout/version/destructive actions are assertion-only;
- Garmin, HealthKit synchronization, account deletion confirmation, and update application are never automated.

A deterministic contract test keeps the XCTest matrix aligned with production-visible Settings entries.

## Error handling and observability

Every release creates a transaction ID and a stage-timing record. Failure output identifies the failed stage, elapsed time, log path, completed surfaces, pending surfaces, and safe retry command. Logs and manifests must not include secrets or health data.

Classifiers and caches are fail-closed. Unknown input, missing baseline, corrupt receipt, stale worktree, mismatched artifact, incomplete EAS metadata, or unverifiable production state stops publishing or performs the original full step.

## Rollout

1. Land planner, validation, OTA transaction cache, tests, and simulator harness.
2. Run server proof reuse in `shadow` mode for at least three production deployments.
3. Compare shadow decisions with the full steps and retain receipts.
4. Enable Python/frontend proof reuse individually after evidence matches.
5. Enable whole-KB skip last; keep per-document embedding deduplication active independently.

## Success criteria

- A Mobile-only source diff plans and performs OTA without invoking `deploy.sh`.
- A native Mobile diff blocks OTA and reports the native build route.
- Parallel validation fails if any blocking child fails and never pipes a running test into `tail`.
- Same-tree rebase evidence is reused; any relevant fingerprint change invalidates it.
- A transient OTA upload retries the same verified export rather than running Metro twice.
- Server proof misses preserve the current complete deployment behavior.
- Simulator smoke verifies GPS city refresh and representative Settings entries without executing destructive or third-party flows.
