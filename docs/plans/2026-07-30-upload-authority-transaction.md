# Upload Authority Transaction Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make upload release migration preserve live files and deletions while leaving only the active release's upload tree after each terminal transition.

**Architecture:** Treat the checkout upload tree and the external upload tree as machine-detected authorities. The first migration alternates from checkout to external and a rollback to a legacy old release alternates back; later old releases already using external keep that authority. A legacy-old preflight accepts only an absent or empty external tree. Transaction copy re-entry accepts only destination content proven as a path/kind/hash subset of the sealed source, while retirement re-entry accepts only a deletion-only source subset with unchanged ownership, mode, kind, and file hash. Copy and hash-verify the complete destination before retiring the source, preserve any divergent tree and fail closed, and keep only the root-owned transaction snapshot while a release is in flight so an interrupted copy or retirement can be resumed without losing bytes.

**Tech Stack:** Python 3.12, pathlib/os filesystem primitives, pytest, the existing `ReleaseTransaction` journal and fault hook.

---

### Task 1: Specify single-authority behavior

**Files:**
- Modify: `scripts/test_runtime_state_release_transaction.py`

1. Add a failing test proving legacy-old preflight rejects a non-empty external tree with no authoritative provenance, while an absent or empty external root is accepted.
2. Run the focused test and confirm it fails because the legacy tree still exists.
3. Add failing tests proving rollback preserves candidate-window additions, does not recreate candidate-window deletions, and leaves no external authority when the old release is legacy-backed.
4. Add a failing consecutive-release test proving rollback to an old release whose effective writers already use external keeps external authoritative.
5. Run the focused tests and confirm deletion/source-retirement assertions fail for the current additive merge.

### Task 2: Specify crash recovery

**Files:**
- Modify: `scripts/test_runtime_state_release_transaction.py`

1. Add an install retirement fault test: fail after the destination is verified but during legacy retirement, then re-enter `install`.
2. Add a rollback retirement fault test: fail after legacy is verified but during external retirement, then re-enter `restore`.
3. Add bidirectional failing tests that mutate the surviving retirement source between attempts with a new file, changed bytes, a file/directory type change, and a safe permission change.
4. Assert clean re-entry preserves all authoritative files, propagates deletions, leaves a single authority, and leaves no upload staging hard links; assert divergent re-entry blocks without deleting the divergent source.
5. Run the tests and confirm the current implementation fails at the injected retirement and divergence boundaries.

### Task 3: Implement verified authority switching

**Files:**
- Modify: `backend/scripts/runtime_state_release_transaction.py`

1. Add a small upload-tree equality verifier based on the existing stable manifest.
2. Change `_install_uploads` to reject unproven external content, accept only a prepared legacy path/kind/hash subset after prepare, merge the prepared legacy snapshot into external, verify the resulting external tree, then retire the live legacy tree.
3. Derive `old_upload_authority` from both old effective writer units. Change `_restore_uploads` to copy the complete live external tree into an absent/transaction-created legacy tree, verify exact manifest equality, then retire external only for a legacy old release; keep external for an external old release.
4. Add narrowly scoped fault points around each source retirement so tests exercise resumability.
5. On re-entry, accept only transaction-produced partial states that can be proven from the sealed manifest. Before each retirement, require every remaining source entry to retain its sealed path, kind, uid, gid, mode, and file hash; preserve and fail closed on divergent content.

### Task 4: Verify release contracts

**Files:**
- Test: `scripts/test_runtime_state_release_transaction.py`
- Test: `scripts/test_release_rollback.py`
- Test: `scripts/test_deploy_script.py`
- Test: `scripts/test_infrastructure_security.py`

1. Run all focused upload transaction tests and require a clean pass.
2. Run the complete runtime transaction suite.
3. Run rollback, deploy-script, activation-runner, and infrastructure security contract suites without piping through `tail`.
4. Run `git diff --check` and Python/shell syntax checks.
5. Review the final diff for unrelated changes and hand the exact files and evidence to the parent task for integration.
