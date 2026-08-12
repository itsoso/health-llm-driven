# Release Feedback Loop Efficiency Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Reduce avoidable CI and release waiting while preserving every health-data safety, backup, rollback, and production verification gate.

**Architecture:** Add a conservative shared change classifier and locked API generator, then use them to select CI and local preflight work. Optimize slow shards and release scripts with content-addressed artifacts and fail-closed cache markers rather than weakening gates.

**Tech Stack:** Python 3.12, Bash 3 compatible release scripts, GitHub Actions YAML, pytest, Expo/EAS Update, Git.

---

### Task 1: Fast preflight classifier

**Files:**
- Create: `scripts/ci_change_scope.py`
- Create: `scripts/release-preflight.sh`
- Create: `scripts/test_ci_change_scope.py`
- Modify: `scripts/test_release_ci_contract.py`

**Steps:**
1. Add failing tests for docs-only, backend, Mobile, API-contract,
   release-tooling, unknown-path, empty-diff, and workflow-dispatch selection.
2. Run the focused tests and confirm the missing classifier fails.
3. Implement the minimal deterministic classifier with JSON, shell, and GitHub
   output formats; unknown input selects `full`.
4. Add failing dry-run tests for preflight command selection and baseline-CI
   reporting.
5. Implement the Bash entry point without swallowing command exit codes.
6. Run focused tests and `bash -n scripts/release-preflight.sh`.
7. Commit only Task 1 files.

### Task 2: Locked OpenAPI client generation

**Files:**
- Create: `scripts/generate-api-types.sh`
- Create: `scripts/test_generate_api_types.py`
- Modify: `mobile/package.json`
- Modify: `frontend/package.json`
- Modify: `.github/workflows/ci.yml`
- Modify: `scripts/release-preflight.sh`

**Steps:**
1. Add failing tests for the lock-digest cache path, Python 3.12 requirement,
   check-mode non-mutation, both client outputs, and CI installed-runtime mode.
2. Confirm the new tests fail because the generator is absent.
3. Implement cached locked-environment bootstrap and generate/check modes.
4. Route both package scripts and the CI type-drift job through the generator.
5. Run the generator in check mode and focused contract tests.
6. Commit only Task 2 files.

### Task 3: Change-aware CI

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `scripts/test_release_ci_contract.py`
- Modify: `scripts/test_ci_change_scope.py`

**Steps:**
1. Add failing workflow-contract tests for the classify job, lightweight docs
   gate, fail-closed full route, and stable backend aggregate behavior.
2. Confirm the workflow tests fail for the missing route.
3. Add the classifier job and condition existing runtime jobs conservatively.
4. Add the lightweight documentation gate and preserve secret/System Map/dossier
   checks.
5. Parse the workflow and run all release CI contract tests.
6. Commit only Task 3 files.

### Task 4: Balance slow pytest shards

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `scripts/test_release_ci_contract.py`

**Steps:**
1. Add a failing contract test proving the replacement partitions cover the
   previous q-r and agent-executor-a-h file sets exactly once.
2. Split q/r and agent-executor a-d/e-h entries.
3. Run collection-only checks for each replacement shard and the contract test.
4. Commit only Task 4 files.

### Task 5: Reusable OTA artifacts and timeout circuit breaker

**Files:**
- Modify: `scripts/mobile-ota.sh`
- Modify: `scripts/test_mobile_fast_feedback_scripts.py`
- Modify: `.gitignore`

**Steps:**
1. Add failing tests for one Hermes export across retry, direct no-bytecode
   fallback after asset-processing timeout, bounded attempt counts, and failure
   audit records.
2. Confirm failures against the current rebundling behavior.
3. Implement exported input-directory reuse, error classification, and bounded
   fallback.
4. Add privacy-safe JSONL audit events and ignore the local audit file.
5. Run OTA contract tests and Bash syntax checks.
6. Commit only Task 5 files.

### Task 6: Relevant-tree main compatibility

**Files:**
- Modify: `scripts/mobile-ota.sh`
- Modify: `scripts/test_mobile_fast_feedback_scripts.py`

**Steps:**
1. Add failing tests for docs-only main advancement, Mobile divergence, dirty
   relevant paths, and manifest source/main/tree fields.
2. Implement tracked-tree equality as the only exception to exact HEAD equality.
3. Verify mismatches still fail before export or upload.
4. Run OTA and release-lock contract tests.
5. Commit only Task 6 files.

### Task 7: Fail-closed deployment input digests

**Files:**
- Modify: `deploy.sh`
- Modify: `scripts/test_deploy_script.py`

**Steps:**
1. Add failing static and harness tests for requirements and System KB digest
   decisions, missing markers, malformed markers, and marker update ordering.
2. Implement requirements marker comparison with mandatory `pip check`.
3. Implement conservative System KB input digest comparison; only write the
   marker after successful activation and post-gates.
4. Keep backup, restore drill, migrations, revision, runtime contract, and
   health verification unconditional.
5. Run deployment, rollback, runtime-state, and release-lock tests plus Bash 3
   syntax verification.
6. Commit only Task 7 files.

### Task 8: Integration and documentation

**Files:**
- Modify: `docs/dossiers/2026-08-12-release-feedback-loop-efficiency.md`
- Modify generated System Map files only if the generator detects structural
  changes.

**Steps:**
1. Run focused script suites, release invariants, System Map check, dossier
   consistency, shell syntax, and `git diff --check`.
2. Run the local preflight against the complete change range.
3. Push main and require one full green main CI run.
4. Record measured job durations and Gate results in the dossier.
5. Deploy only if runtime code changed; otherwise record why deployment is not
   applicable. Do not publish a Mobile OTA for release-script-only changes.
6. Commit and push the release record through the lightweight documentation
   route, then verify that route's elapsed time.
