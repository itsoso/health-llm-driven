# Agent Runtime Hardening Design

> Status: approved by priority selection
> Updated: 2026-07-23
> Reuses: `docs/specs/active/2026-07-19-agent-runtime-control-plane.md`

## 1. Decision

Keep the existing modular-monolith Runtime Coordinator and AgentExecutor. Add a
content-free execution contract snapshot, expose integrity observations, then
move remaining cloud entrypoints behind one Runtime facade. Do not change the
strict-local iPhone execution contract.

## 2. Runtime Contract Snapshot

Each newly managed Run records:

- `runtime_contract_version`: explicit bounded contract identifier;
- `tool_registry_digest`: deterministic SHA-256 of operational ToolSpec metadata;
- `capability_policy_digest`: deterministic SHA-256 of the deterministic policy
  contract.

These values describe code contracts, not user content. Old Runs may remain
`NULL`; new managed Runs must always receive all three values. A retry or replay
preserves the original snapshot.

## 3. Integrity Projection

The administrator monitoring surface adds a recent-window projection:

- contract snapshot coverage;
- counts grouped by contract version;
- succeeded/waiting Runs missing source or assistant message links;
- active and waiting age buckets;
- Runs whose current Attempt is missing.

The first release is observation-only. Contract mismatch during a rolling deploy
is not itself a circuit condition. Existing automatic pause rules remain
authoritative for failure rate, reconciliation and stale leases.

## 4. Cloud Runtime Facade

A new facade will own the common lifecycle for non-HTTP cloud producers:

```text
entrypoint identity
  -> Runtime admission
  -> Run/Attempt lease
  -> AgentExecutor.run_stream(canonical IDs)
  -> message binding
  -> terminal/waiting/reconciliation outcome
  -> durable replay
```

Each entrypoint must provide a stable `client_turn_id`. If its upstream protocol
does not expose one, it must derive a bounded opaque ID from the upstream message
identity, not from health text. The facade never accepts strict-local execution.

Migration order:

1. Siri, because it already has a dedicated conversation and first-party auth.
2. WeChat Bot, after adding a stable upstream message identity contract.
3. Telegram direct writes and voice shortcuts, only after their existing
   confirmation behavior is preserved by tests.
4. Starter pregen is explicitly excluded from managed Runtime. It has no user
   submission, performs no business write, uses a disposable scratch
   conversation and only warms a replaceable cache. Recording it as a durable
   user Run would add high-volume ledger noise without improving idempotency or
   recovery. If pregen later gains side effects or user-visible resume semantics,
   it must receive a separate read-only Runtime origin and budget.

All migrated external channels reuse one `AgentConversation` per user/channel.
This preserves context without mixing Siri, WeChat or Telegram history into the
primary mobile conversation. Query/chat traffic is not allowed to bypass the
Agent through a direct provider call.

The facade and HTTP API share one lease-heartbeat implementation. Long-running
external turns therefore renew ownership, honor cancellation/deadline signals
and stop before the lease expires if the control plane becomes unreachable.

## 5. Safety And Privacy

- No prompt, answer, media URL, health value, diagnosis, medication name or raw
  tool argument/result enters Runtime tables or monitoring payloads.
- Digest input is static operational metadata only.
- Monitoring remains administrator-only and aggregate.
- Entry migration cannot turn a confirmation-bound action into an automatic
  write.
- A Run cannot claim success while a write operation is unresolved.

## 6. Rollout

1. Deploy nullable schema and code that writes snapshots for new Runs.
2. Observe coverage and linkage for a production window.
3. Migrate entrypoints one at a time behind flags or explicit origins.
4. Keep `AGENT_RUNTIME_MODE=off` as the hard rollback and the existing circuit as
   the soft stop.

## 7. Deferred

- Parent/child Run budgets for multi-stage AIGC jobs.
- Persisted supersede/queue semantics for multiple distinct turns.
- Resuming a `waiting_for_user` Run in place across clients.
- Prompt-template hashes. The current prompt assembly is multi-source and must
  first gain explicit versioned bundles; hashing user-expanded prompts is
  prohibited.
