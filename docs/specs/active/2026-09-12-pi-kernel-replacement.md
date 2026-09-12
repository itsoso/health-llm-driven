# Reva official Pi kernel replacement

> Status: implementation and live validation passed; authorized release in preparation
> Updated: 2026-09-12
> Owner: Reva engineering

## Decision and problem

Replace the hand-written model/tool loop with the official
`@earendil-works/pi-agent-core` runtime. The user explicitly requested replacement
after recurring failures in the existing design. Pi owns message state, structured
tool calling, and loop termination. Reva retains its domain tools and durable
execution and release boundaries.

## Requirement admission

- Classification: infrastructure; significant internal migration.
- Core loop: safe execution and verified outcome of health actions.
- Objects: SafetyGuardian, WriteIntent, ExecutionEvent.
- Surface/source of truth: backend; existing client SSE and persistence contracts.
- Safety: privacy-sensitive health read/write and medical output boundaries.
- Autonomy: existing authorization tiers; no elevation and no new medical claims.
- Evidence: current executor, gateway, runtime facade, receipt and evidence tests;
  official Pi package and actual local Pi subprocess integration.
- Added user burden: none.
- Success: the real Pi package executes a multi-turn tool loop through Reva's
  gateway; denied/uncertain writes cannot be reported complete or repeated;
  unverified model text cannot reach the client.

## Architecture and contracts

The existing durable `run_stream` wrapper and turn preparation remain. A local,
per-turn Node child runs Pi over bounded JSONL pipes. Pi's provider transport asks
Python for model responses, using the existing provider configuration and usage
tracking. Its tools ask Python to execute registered health tools. Credentials
are not passed to or inherited by the child. The child has no coding-agent shell
tools, autonomous file tools, session persistence, or external listener. It runs
as the backend OS account; this transport is not an OS security sandbox.

Before returning each model response, Python checkpoints all proposed writes in
that response. Every tool still crosses `_execute_tool` and `ToolGateway`, then
the existing durable operation ledger and verified receipt checks. Shared DB
sessions require sequential tool execution. Uncertain writes stop further tool
dispatch. Existing medical evidence and output gates run before final text is
emitted or persisted.

The former model retry/textual-tool-recovery loop is removed from the active
path; unavailable Pi fails explicitly. No hidden legacy fallback. Existing
deterministic pre-execution medical/confirmation terminals remain valid.

## Non-goals and rollout

No database schema or client API migration; no new health tools or permission
tiers. The user subsequently authorized production deployment, including necessary
verified source publication. Node and pinned Pi dependencies must be included in
backend packaging. Rollback uses a previously verified backend revision, not an
automatic per-request switch to the old loop.

## Acceptance and verification

- Scripted provider with real Pi: model -> tool -> model -> terminal answer.
- Invalid tool schema/arguments cannot reach dispatch.
- All planned writes checkpoint before first dispatch; repeated writes execute
  once; uncertainty, cancellation and worker loss cannot cause duplicate writes.
- Health evidence, medical boundaries, grounded cards and receipts are preserved.
- IPC malformed output, EOF, timeout and cancellation fail explicitly and reap
  the child; no health payload or secrets in diagnostic output.
- Run Node package tests/audit, focused Python gateway/completion/health-evidence
  regressions, LLM change gate and required live regression where executable.
- Independent safety review of the final diff, system-map regeneration/check,
  and `git diff --check` before completion claims.

## Changelog

- 2026-09-12: accepted direct replacement scope from user; implementation started.
- 2026-09-12: normal and multi-model loops replaced; pinned runtime packaging,
  provider/output boundaries and durable write reconciliation verified locally.
  Live validation requires a correctly configured PostgreSQL runtime role.
