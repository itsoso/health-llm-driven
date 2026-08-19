# GitHub Actions Node 24 Runtime Upgrade Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove GitHub Actions Node 20 deprecation annotations without changing application runtimes or CI job behavior.

**Architecture:** Upgrade only the affected first-party action majors in the canonical CI workflow. Preserve checkout depth and explicit caches, disable Setup Node v5 automatic caching in the one job that previously had no cache, and enforce the runtime majors with parsed-YAML contract tests.

**Tech Stack:** GitHub Actions YAML, Python 3.12, pytest, PyYAML.

---

### Task 1: Add the Node 24 action contract

**Files:**
- Modify: `scripts/test_release_ci_contract.py`

**Step 1: Write the failing test**

Add a test that parses `.github/workflows/ci.yml`, collects every first-party `uses` entry, and requires:

```python
expected = {
    "actions/checkout": "v5",
    "actions/setup-python": "v6",
    "actions/setup-node": "v5",
    "actions/upload-artifact": "v6",
}
```

The same test must locate the `type-drift` Setup Node step and assert `package-manager-cache: false` so the v5 default cannot silently change that job.

**Step 2: Run the test to verify RED**

Run:

```bash
backend/venv/bin/python -m pytest -q --no-cov --tb=short scripts/test_release_ci_contract.py::test_ci_first_party_javascript_actions_use_node24_runtimes
```

Expected: FAIL because the workflow still uses checkout v4, setup-python v5, setup-node v4, and upload-artifact v4.

### Task 2: Apply the minimal workflow migration

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `backend/tests/test_llm_live_change_gate.py`

**Step 1: Update action majors**

Replace all affected action references with the approved majors. Retain all existing `with` values. Add `package-manager-cache: false` only to the `type-drift` Setup Node step because it previously requested no cache.

**Step 2: Remove the old version-coupled regex**

Change `test_ci_hard_wires_llm_change_gate` to parse the workflow YAML and inspect the `backend-quality` checkout step directly. Keep the existing `fetch-depth: 0` assertion; do not weaken the change-detection contract.

**Step 3: Run focused GREEN verification**

Run:

```bash
backend/venv/bin/python -m pytest -q --no-cov --tb=short \
  scripts/test_release_ci_contract.py \
  backend/tests/test_llm_live_change_gate.py
```

Expected: all tests pass.

### Task 3: Verify workflow integrity

**Files:**
- Verify: `.github/workflows/ci.yml`
- Verify: `scripts/test_ci_change_scope.py`
- Verify: `backend/tests/test_ci_pytest_shard_runner.py`

**Step 1: Run connected CI-contract suites**

Run:

```bash
backend/venv/bin/python -m pytest -q --no-cov --tb=short \
  scripts/test_release_ci_contract.py \
  scripts/test_ci_change_scope.py \
  backend/tests/test_llm_live_change_gate.py \
  backend/tests/test_ci_pytest_shard_runner.py
```

Expected: all tests pass.

**Step 2: Validate the final diff**

Run `git diff --check`, parse the workflow with `yaml.safe_load`, and confirm no affected Node 20 major remains.

### Task 4: Commit, push, and verify the exact CI run

**Files:**
- Commit only the two plan documents, `.github/workflows/ci.yml`, and the two contract-test files.

**Step 1: Commit**

Create a focused commit named `chore(ci): move first-party actions to Node 24`.

**Step 2: Push**

Fetch `origin/main`, require a fast-forward, and push the exact commit to `main` without force.

**Step 3: Verify production CI evidence**

Monitor the exact commit's GitHub Actions run to completion. Require every selected job to succeed and query check-run annotations to prove no Node 20 deprecation message remains. Do not deploy application services or publish OTA because this slice changes only CI infrastructure and tests.
