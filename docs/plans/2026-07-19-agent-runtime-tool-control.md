# Agent Runtime Tool Control P1 Implementation Plan

> **Goal:** Make tool policy, metadata and dispatch one reliable Runtime path, then mirror write execution into the content-free operation ledger without changing health behavior.
>
> **Architecture:** `ToolSpecRegistry` owns static execution metadata; `ToolGateway.execute()` owns policy-to-dispatch control; `AgentExecutor` retains validated domain adapters; `AgentRuntimeCoordinator` owns operation state.

## Task 1: ToolSpec Registry

**Files:**
- Create: `backend/app/services/agent_kernel/tool_registry.py`
- Modify: `backend/app/services/agent_kernel/capability_policy.py`
- Modify: `backend/tests/test_agent_kernel_static_coverage.py`
- Create: `backend/tests/test_agent_kernel_tool_registry.py`

1. Add failing coverage and mixed-effect classification tests.
2. Implement immutable ToolSpec definitions for all core and specialist tools.
3. Derive legacy policy sets from Registry while preserving imports.
4. Verify unknown tools/actions fail closed and schema coverage is exact.

## Task 2: Unified Gateway Execution

**Files:**
- Modify: `backend/app/services/agent_kernel/tool_gateway.py`
- Modify: `backend/app/services/agent_executor.py`
- Modify: `backend/tests/test_agent_kernel_tool_gateway.py`
- Modify: `backend/tests/test_agent_kernel_static_coverage.py`

1. Add failing tests for allow, enforce block, shadow execution and single dispatch.
2. Implement `ToolGateway.execute()` with an injected async adapter.
3. Replace the Executor's tool-name branch with Registry adapter lookup.
4. Preserve validation order, specialist thread offload, deep-analysis marker and plausibility annotation.
5. Verify every executable path calls the Gateway and no direct surface write exists.

## Task 3: Runtime Tool Operations

**Files:**
- Modify: `backend/app/services/agent_runtime.py`
- Modify: `backend/app/services/agent_executor.py`
- Modify: `backend/tests/test_agent_runtime_service.py`
- Create: `backend/tests/test_agent_runtime_tool_operations.py`

1. Add failing state, ownership, retry and privacy tests.
2. Implement claim/start/succeed/fail/reconcile transitions with Run/Attempt fencing.
3. In enforce mode, claim write operations before dispatch and finalize from existing verified receipts.
4. Treat an already verified fingerprint as replay. A duplicate live claimant returns reconcile without mutating the owner; explicit cancellation/timeout marks the owned operation uncertain. Process-death orphan scanning remains deferred.
5. Keep message checkpoint recovery authoritative and verify both views agree.

## Task 4: Regression And Gates

1. Run focused Tool Registry/Gateway/Runtime tests under SQLite.
2. Run real PostgreSQL concurrency and migration suites.
3. Run Agent Executor, write receipt, health record/manage and photo-diet regressions.
4. Run Ruff, document drift, Dossier consistency and `git diff --check`.
5. Record exact evidence in the Dossier, commit only P1 files and push the feature branch.

## Explicit Non-goals

- No framework migration, service split or event sourcing.
- No automatic retry of uncertain writes.
- No change to strict-local iPhone execution.
- No deployment or Runtime enablement from this branch.
