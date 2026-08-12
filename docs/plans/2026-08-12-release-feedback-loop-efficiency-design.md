# Release Feedback Loop Efficiency Design

## Context

The supplement batch repair took more than three hours from design to the final
release record. The dominant delays were repeated full CI runs, a locally stale
OpenAPI generation environment, late failures in oversized pytest shards,
repeated Mobile OTA bundling during EAS timeouts, and unconditional production
dependency and System KB work.

The objective is to remove avoidable waiting without weakening the existing
health-data safety, backup, rollback, runtime compatibility, or production
verification gates.

## Options considered

### 1. Keep the current pipeline and document faster manual commands

This has the smallest code change, but it keeps correctness dependent on the
operator choosing the right environment and remembering which jobs matter. It
does not prevent another stale type-generation environment or another full CI
run for a documentation-only release record.

### 2. Add a change classifier and incremental gates inside the current workflow

This keeps the current workflow, stable gate names, release locks, and rollback
mechanisms. A deterministic classifier selects the smallest safe gate set;
unknown or high-risk paths fail closed to the full suite. Local preflight uses
the same classifier and a locked type generator. This is the recommended
approach because it removes repeated work while preserving current contracts.

### 3. Replace CI and release scripts with a new orchestrator

A new orchestration service could optimize globally, but it would create a new
stateful control plane and a large migration surface. The current bottlenecks do
not justify that complexity.

## Design

### Change classification and fast preflight

A repository-owned classifier maps a Git diff into conservative scopes:
documentation, backend, frontend, Mobile, Mac, API contract, release tooling,
and full. Unknown paths, workflow changes, dependency locks, and classifier
changes select `full`.

The local preflight entry point reads the same classification and runs cheap
fail-fast checks before expensive suites. It supports a dry-run mode so its
selection contract is testable. It reports the baseline main CI state when the
GitHub CLI is available, but a missing CLI or network is reported rather than
silently treated as green.

### Locked OpenAPI generation

One script generates both Mobile and frontend API clients. Locally it uses a
Python 3.12 virtual environment cached by the SHA-256 digest of
`backend/requirements.lock`; CI may reuse its already installed locked Python
environment. Both package scripts call this single entry point. Check mode
generates into a temporary directory and compares without mutating tracked
files.

### Change-aware CI

A lightweight classify job exposes scope outputs. Documentation-only pushes run
secret scanning, System Map drift, and dossier consistency, while runtime jobs
are skipped. Code and unknown changes keep the full current safety matrix. API
contract changes additionally run locked client generation. The stable backend
aggregate remains present and treats a deliberately skipped matrix as success
only when the classifier explicitly selected the lightweight route.

### Test shard balancing

The historically longest name-based shards are divided without changing test
selection semantics. A contract test enumerates collected files and proves that
the new partitions neither omit nor overlap their predecessor scope. The target
is to reduce the longest ordinary shard while keeping failure retry and timeout
behavior unchanged.

### OTA artifact reuse and bounded fallback

Expo export happens once per artifact variant. EAS upload retries reuse the same
`--input-dir --skip-bundler` output. A server-side asset-processing timeout skips
an identical Hermes retry and moves directly to one no-bytecode fallback;
ordinary transient network failures may retry the same artifact once.

Each attempt appends a privacy-safe local audit event containing only platform,
channel, runtime, source commit, relevant tree digest, result, and duration.
No health content, credentials, or command environment is recorded.

### Concurrent-main compatibility

Production OTA still rejects dirty Mobile/shared paths. If local HEAD differs
from `origin/main`, publication is allowed only when the tracked `mobile/` and
`packages/shared/` trees are byte-identical. The manifest records both source
and main commits plus the relevant tree digest. Any runtime-affecting difference
continues to fail closed.

### Deployment input digests

Database backup, restore drill, offsite archive, migrations, service health,
revision proof, and runtime-only KB serving contracts remain mandatory.

Production dependency installation may be skipped only when the locked
requirements digest matches a root-owned successful-install marker; `pip check`
still runs. System KB mutation may be skipped only when a conservative digest of
all seed/import inputs matches the last successfully activated digest. Read-only
serving-contract and health verification still run. Missing, malformed, or
inconsistent markers force the full existing path.

## Error handling and safety properties

- Unknown change classification selects the full suite.
- A failed or unavailable type environment is an explicit preflight failure.
- CI path selection never skips health-write safety tests for backend code.
- OTA identifiers remain mandatory before manifest or anchor mutation.
- Failed OTA attempts do not modify the active production manifest.
- Deployment cache-marker uncertainty forces install/import rather than skip.
- Database protection and production health gates are never cached or skipped.

## Verification

- Unit tests cover classifier paths, dry-run command selection, locked generator
  environment selection, CI skip contracts, shard coverage, OTA retry/export
  counts, concurrent-main decisions, and deployment marker fail-closed behavior.
- Shell syntax checks cover every changed shell entry point.
- Existing release invariant suites run after each batch.
- The final code commit must receive a full main CI run before deployment.

