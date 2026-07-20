# Agent Runtime Tool Control P1 Design

> Status: approved continuation of P0
> Updated: 2026-07-19
> Parent: `docs/plans/2026-07-19-agent-runtime-control-plane-design.md`

## 1. Decision

Keep the existing health-tool implementations inside `AgentExecutor`, but move tool metadata, effect classification, policy enforcement and dispatch selection behind two stable contracts:

1. `ToolSpecRegistry` is the single source for every executable tool's schema identity, effect class, timeout, receipt requirement and Executor adapter.
2. `ToolGateway.execute()` is the only path from a validated tool request to an implementation adapter.

The P0 Runtime ledger records content-free operation state for write tools. Existing message checkpoints remain the recovery authority during P1 rollout; Runtime operation rows are an additional, stricter control-plane view until parity is proven.

## 2. Why This Shape

The Executor already contains tested argument recovery, health validation, write-before-dispatch checkpoints, receipt extraction and domain-specific adapters. Moving those implementations in one change would combine architecture migration with health behavior changes. P1 therefore separates control from implementation:

```text
validated request
      |
ToolSpecRegistry -- effect / timeout / receipt / adapter
      |
ToolGateway.execute -- policy / block / dispatch result
      |
AgentExecutor adapter map -- existing _exec_* methods unchanged
      |
existing receipt parser + message checkpoint
      |
Runtime AgentToolOperation mirror (enforce mode only)
```

## 3. ToolSpec Contract

Each registered tool has an immutable specification:

- `name`: exact schema and provider tool name;
- `effect`: `read`, `write` or `mixed`;
- `executor_method`: existing bound method name, or the specialist adapter sentinel;
- `timeout_seconds`: the current per-tool execution budget;
- `receipt_required`: whether a successful write must produce a verified resource identity;
- `read_actions` / `write_actions`: deterministic classification for mixed tools;
- `non_write_record_types`: action-like `health_record` variants such as `garmin_sync` that do not produce a resource receipt;
- `annotate_implausible`: preserve current read-result plausibility annotation.

Unknown tools and unclassified mixed actions fail closed. The provider schema remains in `tool_schema_registry.py`; Registry coverage tests require every exposed schema and every specialist tool to have exactly one ToolSpec.

## 4. Gateway Contract

`ToolGateway.execute(request, dispatch)` performs:

1. deterministic capability policy evaluation;
2. enforce-mode blocking before dispatch;
3. normalized request construction;
4. exactly one injected dispatch call;
5. a typed `ToolExecutionResult` containing the decision and content.

Shadow policy still records a blocking decision but executes, preserving current rollout behavior. Policy evaluation failure is surfaced to the Executor, which keeps the existing fail-closed user response and telemetry.

Argument parsing, symptom authorization and `validate_tool_call` remain before the Gateway. This preserves the current safety order: malformed or unauthorized health writes never reach capability dispatch.

## 5. Runtime Tool Operation Ledger

In `agent_runtime_mode=enforce`, write-effect requests create or claim an `AgentToolOperation` before the existing business adapter runs. The row stores only:

- opaque operation ID;
- Run and Attempt IDs;
- registered tool name and effect class;
- SHA-256 fingerprint of normalized arguments;
- operational status;
- verified resource type/ID or coarse error code.

It never stores arguments, result bodies, image URLs, diagnoses, drug names or health values.

State transitions:

```text
requested -> executing -> succeeded
                       -> failed
                       -> reconciliation_required
```

The unique `(run_id, operation_fingerprint)` constraint makes a repeated write in one logical Run observable and non-dispatchable after a verified success. A duplicate caller that finds a live `executing` operation receives a reconcile response without mutating the original owner's row. Explicit cancellation or timeout after claim moves the owned operation to `reconciliation_required`; detecting an operation orphaned by process death requires the deferred lease/recovery scanner. No uncertain operation is retried automatically.

## 6. Compatibility And Rollout

- `agent_runtime_mode=off`: no operation rows and no behavior change; Registry and Gateway still centralize in-process execution.
- `agent_runtime_mode=enforce`: operation rows mirror write checkpoints and reject duplicate verified dispatch in the same Run.
- Strict-local iPhone execution remains outside the cloud Runtime.
- Existing `_exec_*` signatures and synthesized user-visible responses remain unchanged. Write helpers may add an internal structured receipt envelope while retaining their human-readable message.
- Existing helper functions stay as compatibility wrappers until all callers and tests use Registry classifications.

Rollback is one configuration change for ledger behavior and one code rollback for Registry/Gateway routing. No destructive migration is required.

## 7. P1 Invariants

1. Every exposed tool has exactly one ToolSpec and executable adapter.
2. Unknown tools and unknown mixed actions cannot execute.
3. Every validated tool dispatch passes through `ToolGateway.execute()` exactly once.
4. Read-only pre-generation uses ToolSpec effect classification, not a second manual allowlist.
5. A write operation is persisted before business dispatch when Runtime is enforced.
6. A verified operation is never dispatched twice within one logical Run.
7. Uncertain writes are never retried automatically.
8. Runtime rows and events remain free of health content and raw arguments/results.

## 8. Deferred

- Downstream cross-Run idempotency enforcement by every business endpoint.
- Automated resource-specific reconcile queries.
- Process-death worker leases and recovery scanner.
- Durable streaming cursor, cancellation/supersede and parent/child Runs.
