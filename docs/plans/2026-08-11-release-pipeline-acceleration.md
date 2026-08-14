# Release Pipeline Acceleration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a conservative source-aware release pipeline that removes unnecessary work while retaining every production safety gate.

**Architecture:** Historically, a Python release planner owned change classification and live-production
reconciliation, local audit state and validation profiles. Existing mutation protocols remain test
fixtures/future design inputs, not current authorities. Same-UID repo bootstrap trust is unclosed, so
all repo-contained automatic remote/vendor release and local signing/install/provisioning entrypoints
fail before mutation.

**Tech Stack:** Python 3, Bash 3-compatible shell, Git worktrees, Expo/EAS Update, pytest,
Jest/TypeScript, Xcode XCTest, SwiftPM, Developer ID/notarytool, nginx, PostgreSQL/System KB import tooling.

**Final safety boundary (2026-08-12):** Git replace, shared info attributes+filter, hidden untracked
import shadow, `BASH_ENV` and `PYTHONPATH`/`sitecustomize` prove a writable repo cannot bootstrap a
trusted production executor. Server backend/frontend/env/restart/push/evidence/reset/coordinator,
Mobile OTA/rollback on **every channel**, production native/EAS/ASC, Mac routes/publish/recovery and
all legacy release bypasses are frozen at exit 78. Server-local DB migration/setup/admin utilities
remain a separate explicit manual-admin Gate and may never be invoked by an automatic release
entrypoint. EAS channel→branch mapping may drift or be shared, so
preview/development is not a trusted non-production boundary. Only offline evidence parsing,
public unauthenticated HTTPS, local Metro/iOS Simulator/test and existing-IPA offline inspection
metadata/report via `mobile-local-qr.sh --no-upload --ipa <EXISTING_IPA>` remain. It creates no
install manifest, install QR, or installability claim. Bare `--no-upload` and automated
archive/export/signing/provisioning (especially `-allowProvisioningUpdates`) are frozen. G5/G6/App
Store submission are BLOCKED. `npm run ios` uses the Simulator wrapper; callers may not append
npm/Expo `--device`. It resolves the available Simulator destination to an exact UDID before Xcode.
Physical iOS repo CLI, connection/install and acceptance are frozen. The repository XCUITest harness
accepts only an exact available Simulator UDID; physical acceptance is future external manual evidence.
Mac/nginx direct Python production CLI is also frozen. Protocol tests and local
`create-candidate` require non-root execution, explicit test mode and fixed non-production roots
(macOS `/private/tmp` or `/private/var/folders`; `/tmp` elsewhere, ignoring caller `TMPDIR`).
`deploy.sh --inspect-release-lock` exits 78 before reading lock/environment state; lock inspection
waits for a repo-external root-owned inspector.
Android is not a shipped/audited Mobile surface; `npm run android`/`expo run:android` performs
native generation, debug signing and ADB installation, so its repo entrypoint exits 78 with no
native CLI exception.
`release.py`/`release.sh` plan/validate/publish, production-state network modes, deploy
status/logs/inspect and App Store `--final-submit` are therefore frozen too. All task commands below
that name a frozen entrypoint are historical implementation/negative-test records and **must not be
executed as release operations**.
For Bash entrypoints, rc78 is only an ordinary-invocation marker because `BASH_ENV` and
caller-defined `exit`/`builtin` functions run outside the repo guard. Retained legacy in `deploy.sh`
and `_run-mobile-tf.sh` must be literal-false/syntactically unreachable; runtime/operator paths may
never source/extract/eval that material. Isolated tests may extract marker fixtures only for protocol
regression, without calling writers/network and without producing release proof. `release-dmg.sh` is
wholly frozen; any read-only Mac checker must be a separate no-writer file.

---

### Task 1: Change classifier and release plan

**Files:**
- Create: `scripts/release.py`
- Create: `scripts/release.sh`
- Create: `scripts/test_release_pipeline.py`

1. Write failing tests for Mobile OTA, native, backend+OTA ordering, frontend full deploy, docs-only,
   unknown paths, rename/delete, independent live surface baselines, forged local completion state,
   and production drift after planning/during validation/between surfaces.
2. Run `python3 -m pytest scripts/test_release_pipeline.py -q` and verify RED.
3. Implement deterministic Git name-status parsing and fail-closed surface planning.
4. Historical design intended read-only `plan`/`validate`; final bootstrap review requires
   `plan`/`validate`/`publish` all to exit 78 before network/credential access. Preserve only a pure
   offline evidence parser outside those network modes.
5. Run the focused tests and verify GREEN.

### Task 2: Permanent clean release worktree

**Files:**
- Modify: `scripts/release.py`
- Modify: `deploy.sh`
- Modify: `scripts/test_release_pipeline.py`
- Modify: `scripts/test_deploy_script.py`

1. Write failing tests for dirty-worktree refusal, detached exact-main acceptance, named feature-branch refusal, and shared common-dir state permissions.
2. Verify RED.
3. Implement safe creation/update of `<repo>.release`, with no automatic destructive cleanup.
4. Let `deploy.sh` accept detached HEAD only when it exactly equals verified `origin/main`; retain all clean/SHA checks.
5. Verify focused tests GREEN.

### Task 3: Parallel validation and explicit validation authority

**Files:**
- Rewrite: `scripts/run-all-tests.sh`
- Modify: `scripts/validate.py`
- Modify: `scripts/release.py`
- Modify: `scripts/test_release_pipeline.py`
- Create: `scripts/test_run_all_tests.py`

1. Write failing tests proving parallel checks retain true child exit codes, lint failures block,
   interrupts reap children, and a forged same-UID local credential cannot skip validation.
2. Verify RED.
3. Run each check to a separate private log, wait by PID, and print output only after completion.
4. Add missing Mobile lint, Settings routes, design check and `git diff --check`; remove all running-test `| tail` use.
5. Keep tree/profile/toolchain/lock/command/log-bound credentials as diagnostic/test artifacts only;
   production validation runs the full suite and issues no local skip. Defer any skip to a separately
   reviewed, independently verifiable CI authority bound to the exact commit.
6. Verify focused tests GREEN.

### Task 4: OTA artifact protocol and structured verification (historical/test-only)

**Files:**
- Create: `scripts/verify_mobile_ota_artifact.py`
- Create: `scripts/test_mobile_ota.py`
- Modify: `scripts/mobile-ota.sh`
- Modify: `scripts/mobile-ota-rollback.sh`
- Modify: `mobile/package.json`
- Modify: `mobile/package-lock.json`
- Modify: `mobile/eas.json`
- Modify: `docs/release/mobile-update-manifest.md`

1. Write failing tests for valid/invalid export metadata, path traversal, symlinks, stable digest, same-directory retry, mutation refusal, structured EAS verification and rollback active/source IDs.
2. Verify RED.
3. Preserve the pinned-CLI and transaction-private export design in protocol tests only.
4. Validate/digest mock artifacts and test same-input retry semantics without EAS/network access;
   every real channel writer must exit 78 first.
5. Verify published update/group/channel metadata before individually atomically replacing manifest
   schema v2 and anchor; recovery must reconcile the two-file terminal state.
6. Correct rollback republish handling to store new active IDs and separate rollback source IDs.
7. Verify focused tests GREEN.

### Task 5: Server dependency and frontend proof reuse

**Files:**
- Create: `scripts/release_step_proof.py`
- Create: `scripts/test_release_step_proof.py`
- Modify: `deploy.sh`
- Modify: `scripts/test_deploy_script.py`

1. Write failing tests for missing/corrupt/weak/symlink receipts, input/toolchain/output drift, shadow mode, successful on-mode reuse and failed-step no-receipt behavior.
2. Verify RED.
3. Implement root-owned atomic receipts under `/var/cache/health-app/release-proofs`.
4. Add Python dependency and frontend dependency/build proofs. A miss runs the existing step and records only after its postcondition succeeds.
5. Keep backup, migration, schema, lease, service, revision, health and rollback gates unconditional.
6. Verify focused tests GREEN.

### Task 6: System KB incremental work and proof

**Files:**
- Modify: `backend/app/services/system_knowledge_importer.py`
- Modify: `backend/app/services/system_knowledge_service.py`
- Modify: `backend/scripts/import_system_kb_v2_artifacts.py`
- Modify: `deploy.sh`
- Add/modify focused tests under `backend/tests/`
- Modify: `scripts/test_release_step_proof.py`

1. Write failing tests for unchanged documents, one changed document, missing/stale vector, model/dimension changes, deletion cleanup and DB/artifact drift.
2. Verify RED.
3. Return changed document IDs/content hashes from import and embed only missing/stale rows.
4. Add whole-import proof evaluation under the existing KB mutation lock, defaulting to shadow mode.
5. Preserve guard/staged KB contract and health checks on every path.
6. Verify focused tests GREEN.

### Task 7: Simulator GPS and Settings smoke

**Files:**
- Modify: `scripts/run_ios_real_device_acceptance.sh`
- Modify: `scripts/ios-real-device-acceptance/generate_project.rb`
- Modify: `scripts/ios-real-device-acceptance/XiaobaAcceptanceUITests.swift`
- Modify: `scripts/ios-real-device-acceptance/README.md`
- Modify: `scripts/test_ios_acceptance_harness.py`

1. Write failing contract tests for Simulator-only location flags, cleanup trap, expected-city launch arguments and Settings action safety classes.
2. Verify RED.
3. Add `--location` and `--expected-city`, simctl grant/set/clear, and test launch arguments.
4. Add GPS ready/city assertion and safe Settings entry traversal.
5. Verify harness tests and generated Xcode project GREEN; run simulator smoke when an unlocked simulator is available.

### Task 8: CI, documentation, rollout and verification

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `scripts/test_release_ci_contract.py`
- Modify: `docs/governance/deploy.md`
- Modify: `.claude/skills/backend-deploy/SKILL.md`
- Modify: `.claude/skills/mobile-ota/SKILL.md`
- Modify: `docs/dossiers/2026-08-11-release-pipeline-acceleration.md`

1. Wire all release invariant tests into blocking CI and test the CI contract.
2. Document live per-surface reconciliation, the unified publish lock, audit-only local state,
   safe bounded/atomic state I/O, cache modes, timing records, fallback rules and rollback path.
3. Run focused suites, `python scripts/validate.py --full`, shell syntax checks, diff checks, and an independent code review.
4. Rebase onto current `origin/main`; if the tree changes, rerun affected credentials and tests.
5. Run planner/validation dry-runs and record the production freeze; do not push, deploy or collect
   production shadow mutation evidence as part of this task.

### Task 9: Formal Mac release and one-time public routes

**Files:**
- Modify: `apps/mac/scripts/package-app.sh`
- Modify: `apps/mac/scripts/release-dmg.sh`
- Create: `apps/mac/scripts/mac_release_publish.py`
- Create: `scripts/test_mac_release_receipt.py`
- Create: `infra/nginx/mac-release-routes.conf`
- Modify: `infra/nginx/health.executor.life.conf`
- Create: `scripts/mac-release-nginx-bootstrap.sh`
- Create: `scripts/mac_release_nginx_bootstrap.py`
- Create: `scripts/test_mac_release_nginx.py`
- Modify: `deploy.sh`

1. Write failing tests for source/version/build binding, signing/notarization receipts, immutable
   install, current/stable switch, high-water monotonicity, rollback and every crash boundary.
2. Verify RED.
3. Implement and mock-test the future clean-source/sign/notarize/mount/receipt protocol, but do not
   invoke signing, notarization, package/install or credentials during the current freeze.
4. Implement and mock-test immutable-first plus journaled current/stable semantics without publishing
   bytes or mutating routes. The future protocol must persist root-owned
   current/previous receipts, transaction journal and version/build high-water state outside Git.
5. Add exact-transaction recovery and rollback. Ambiguous mutation outcomes retain the lease and
   exact helper/candidate/artifact bundle; a later `main` must not change recovery semantics.
6. Add protocol code/tests for a future one-time nginx bootstrap transaction for
   `/mac/current.json`, immutable DMGs and `/xiaoba-mac.dmg`; never execute the route writer now.
7. Verify receipt, nginx and shell-contract suites GREEN.

### Task 10: Unified remote lease, public proof and final release Gates

**Files:**
- Modify: `deploy.sh`
- Modify: `scripts/release.py`
- Modify: `scripts/release_production_state.py`
- Modify: `scripts/mobile-ota.sh`
- Modify: `scripts/mobile-ota-rollback.sh`
- Modify: `scripts/_run-mobile-tf.sh`
- Modify: `scripts/mobile-local-archive.sh`
- Modify: `.github/workflows/ci.yml`
- Modify: `scripts/test_deploy_script.py`
- Modify: `scripts/test_release_pipeline.py`
- Modify: `scripts/test_release_production_state.py`
- Modify: `scripts/test_mobile_ota.py`
- Modify: `scripts/test_release_lock.py`
- Modify: `docs/governance/deploy.md`
- Modify: `apps/mac/README.md`
- Modify: `.claude/skills/mac-build-deploy/SKILL.md`
- Modify: `.claude/skills/backend-deploy/SKILL.md`
- Modify: `.claude/skills/mobile-ota/SKILL.md`
- Modify: `.claude/skills/mobile-testflight-release/SKILL.md`
- Modify: `docs/release/mobile-update-manifest.md`
- Modify: `infra/README.md`
- Modify: `docs/dossiers/2026-08-11-release-pipeline-acceleration.md`

1. Write failing tests for one remote lease shared by server/Mac/route mutations, exact ownership
   metadata, partial acquisition, tombstone cleanup, non-stealable recovery and cleanup failure.
2. Verify RED, then implement strict root-owned metadata and delegated mutation calls. Cleanup errors
   must remain visible and ambiguous outcomes must retain recoverable state.
3. Extend production probing to validate the private Mac receipt/disk identity and independently
   hash the public current, immutable and stable HTTPS routes with bounded reads.
4. Freeze the implementation snapshot and run complete release invariants, full validation, Swift
   build/tests, shell/Python/Ruby syntax, diff checks and Simulator acceptance; do not connect or
   install a physical iOS device and do not archive/export/sign/provision.
5. Obtain an independent frozen-snapshot G4 review. Any blocker returns to implementation and causes
   affected tests plus G4 to rerun.
6. Reconcile with fresh `origin/main` and rerun invalidated checks; source integration is separate
   from production release and does not authorize mutation.
7. Prove every automatic remote/vendor release entrypoint and legacy release bypass exits 78; record server, Mobile, Mac, G5/G6 and App
   Store submission as BLOCKED. Open a new dossier for a repo-external root-owned launcher using
   fixed interpreters, `env -i` and canonical archive/tree materialization before any future rollout.
