# GitHub Actions Node 24 Runtime Upgrade Design

**Date:** 2026-08-18

## Context

The exact-commit CI run for `bf7f27a32` completed successfully, but GitHub annotated jobs that still use `actions/checkout@v4`, `actions/setup-python@v5`, and `actions/setup-node@v4`. Those action releases bundle the deprecated Node 20 runtime, so GitHub-hosted runners are already forcing them onto Node 24 compatibility behavior.

The goal is to remove the warning before it becomes a hard failure without changing application runtimes, dependency versions, cache keys, checkout depth, or release behavior.

## Decision

Use the first stable Node 24 major for each affected first-party action:

- `actions/checkout@v5`
- `actions/setup-python@v6`
- `actions/setup-node@v5`

Do not move to later feature-bearing majors in this slice. Checkout v5 changes only the embedded runtime compared with the current workflow contract. Setup Python v6 likewise moves the action runtime to Node 24. Setup Node v5 enables package-manager cache detection by default, so jobs that do not currently request caching must set `package-manager-cache: false`; jobs that already declare an explicit npm cache retain that declaration.

## Scope and invariants

Only `.github/workflows/ci.yml` and CI contract tests change. The workflow must preserve:

- every existing runner image and language version;
- every `fetch-depth` setting;
- explicit frontend and Mobile npm caches and lockfile paths;
- no cache for the type-drift Node setup;
- existing job names, conditions, matrices, commands, permissions, and aggregation behavior.

A static contract test will fail if an affected Node 20 action major is reintroduced or if the type-drift setup silently enables automatic package-manager caching.

## Verification

Follow TDD: first add a contract that fails against the current v4/v5 action majors, then make the minimal workflow substitutions and verify the contract turns green. Run the complete CI contract and change-scope suites, YAML parsing, diff checks, and finally push the exact commit to `main`. Completion requires the new GitHub Actions run to finish successfully and no longer report the Node 20 deprecation annotation for the upgraded first-party actions.
