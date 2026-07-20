# Agent Runtime Resilience P2 Design

> Status: approved by continuation of the Agent Runtime objective
> Updated: 2026-07-19
> Parent spec: `docs/specs/active/2026-07-19-agent-runtime-control-plane.md`

## 1. Decision

Extend the existing modular-monolith Runtime Coordinator with durable worker
leases, cancellation/deadline control, stale-run settlement and a content-free
event cursor. Keep `AgentExecutor` as the execution engine and keep Runtime
disabled by default.

P2 does not persist token deltas or health text in Runtime tables. Conversation
messages remain the only durable content source. A reconnecting client can read
Runtime milestones and replay the final message after completion, but cannot
retrieve partial health text from the Runtime Ledger.

## 2. Run Control

When an Attempt starts, Runtime records an opaque worker identifier and a bounded
lease. The worker periodically renews the lease on a fixed interval. The API
runs that heartbeat in a separate coroutine and database
session, so a long model/tool call with no tokens cannot accidentally lose its
lease. Renewal also evaluates durable control signals:

- a requested cancellation stops execution;
- an expired Run deadline stops execution;
- a stale Attempt cannot renew or finalize a newer Attempt.

The local fail-stop deadline is captured from a monotonic clock before the
database `mark_running` or `renew_lease` call. Only a committed `continue`
renewal advances it. A delayed heartbeat start, slow database call, cancellation
signal or failed control settlement therefore cannot make the worker outlive
the lease recorded in PostgreSQL. Transient heartbeat failures retry only inside
that remaining window; session cleanup failure cancels the owner task
immediately.

Cancellation is two phase. The API records `cancel_requested_at` and a coarse
reason without immediately pretending the worker has stopped. The worker owns
the final transition after it unwinds. If a write operation is still executing
or already uncertain, cancellation settles the Run as
`reconciliation_required`; otherwise it settles as `cancelled`. A verified
write receipt is preserved when task interruption arrives after the business
write, while cancel/deadline still wins over non-success Executor completion.

## 3. Recovery

A recovery scan claims expired running Attempts using the same database locking
rules as normal lifecycle changes. It never resumes model generation in P2.

- no unresolved write operation: mark the Attempt failed and the Run failed,
  retryable with `worker_lease_expired`;
- unresolved write operation: mark the operation and Run
  `reconciliation_required` with `worker_lease_expired_write`;
- cancelled or deadline-expired Run: settle through the same safe cancellation
  rule;
- a legacy P1 running Attempt with no lease: allow one bounded adoption window,
  at least the normal Run deadline plus a deployment drain window (420 seconds
  by default), then settle it through the same read/write-safe recovery rules;
- current, terminal or waiting Runs: leave unchanged.

This closes active-run admission after process death without risking duplicate
health writes. Automatic Executor restart remains deferred until durable input
replay and downstream business idempotency are complete.

Verified tool receipts remain content-free: each write-capable `ToolSpec`
registers allowed resource types and an exact resource-ID pattern. Formal health
writes use positive integer IDs; AIGC draft confirmations use the existing
`aigc_confirm_<32 hex>` identity. Arbitrary diagnosis text, English health labels
or tool result prose cannot enter the Runtime Ledger through receipt fields.

## 4. Event Cursor And Streaming Backpressure

`AgentRunEvent.sequence_no` is the durable cursor. An owner-scoped query returns
only allowlisted milestone events after a supplied sequence and a bounded limit.
It does not return message content, prompt text, tool arguments or tool results.

The live SSE bridge uses a bounded queue. When a client disconnects, the
background Agent continues to completion but stops enqueueing live chunks once
the bounded buffer is full and no consumer remains. Final content is still
written to the normal message store and can be replayed on reopen. This bounds
memory without allowing transport pressure to cancel the health operation.

## 5. Compatibility And Rollout

- Existing `/agent/stream` and `/agent/send` contracts remain valid.
- New Run-control endpoints and response fields are additive.
- `agent_runtime_mode=off` remains the default and bypasses all new persistence.
- Strict-local iPhone execution does not call these endpoints.
- No deployment, OTA or TestFlight release is part of P2 implementation.

## 6. Deferred Work

- automatic model/tool execution restart after process death;
- downstream resource-level idempotency for every business write endpoint;
- parent/child Runs and inherited budgets;
- durable token streams containing health text;
- multi-service Runtime extraction or external workflow frameworks.
