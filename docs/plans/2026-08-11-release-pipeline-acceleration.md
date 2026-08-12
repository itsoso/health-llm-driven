# Release Pipeline Acceleration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a conservative source-aware release pipeline that removes unnecessary work while retaining every production safety gate.

**Architecture:** A Python release planner owns change classification, shared state, validation profiles, credentials, and orchestration. Existing deploy/OTA scripts remain the mutation authorities and gain narrow proof/cache hooks. All caches fail closed and server proof reuse rolls out through off/shadow/on modes.

**Tech Stack:** Python 3, Bash 3-compatible shell, Git worktrees, Expo/EAS Update, pytest, Jest/TypeScript, Xcode XCTest, PostgreSQL/System KB import tooling.

---

### Task 1: Change classifier and release plan

**Files:**
- Create: `scripts/release.py`
- Create: `scripts/release.sh`
- Create: `scripts/test_release_pipeline.py`

1. Write failing tests for Mobile OTA, native, backend+OTA ordering, frontend full deploy, docs-only, unknown paths, rename/delete and partial surface state.
2. Run `python3 -m pytest scripts/test_release_pipeline.py -q` and verify RED.
3. Implement deterministic Git name-status parsing and fail-closed surface planning.
4. Implement `plan`, `validate`, and `publish` commands; only `publish` may invoke mutation scripts.
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

### Task 3: Parallel validation and reusable credential

**Files:**
- Rewrite: `scripts/run-all-tests.sh`
- Modify: `scripts/validate.py`
- Modify: `scripts/release.py`
- Modify: `scripts/test_release_pipeline.py`
- Create: `scripts/test_run_all_tests.py`

1. Write failing tests proving parallel checks retain true child exit codes, lint failures block, interrupts reap children, and credential fingerprints invalidate on every relevant input change.
2. Verify RED.
3. Run each check to a separate private log, wait by PID, and print output only after completion.
4. Add missing Mobile lint, Settings routes, design check and `git diff --check`; remove all running-test `| tail` use.
5. Implement tree/profile/toolchain/lock/command/log-bound credentials with expiry and atomic writes.
6. Verify focused tests GREEN.

### Task 4: OTA artifact reuse and structured verification

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
3. Pin EAS CLI and export once into a transaction-private directory.
4. Validate/digest the artifact and retry transient uploads with the same input directory and `--skip-bundler`.
5. Verify published update/group/channel metadata before atomically writing manifest schema v2 and anchor.
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
2. Document the planner, shared state, cache modes, timing records, fallback rules and rollback path.
3. Run focused suites, `python scripts/validate.py --full`, shell syntax checks, diff checks, and an independent code review.
4. Rebase onto current `origin/main`; if the tree changes, rerun affected credentials and tests.
5. Commit only this worktree's files, push to `main`, run planner dry-run, and leave server reuse in shadow mode until production evidence is collected.
