# Agent Golden Trace Gate

The offline Agent regression gate has two separate layers:

1. `health_agent_core` inventories representative prompts and required routing
   behavior. It is a rubric-shape check and does not execute write side effects.
2. `agent_trajectory_goldens.yaml` replays deterministic execution traces through
   `agent_trajectory_scorer.py`. This is the blocking contract for write
   correctness, verified receipts, readback, honest completion, and replay
   idempotency.

## Turning an incident into a golden trace

Add one fixture row to
`backend/eval/fixtures/agent_trajectory_goldens.yaml` with:

- a unique `scenario`;
- a non-sensitive `history_ref` describing the failure class, not user data;
- a `case_id` from `backend/eval/datasets/agent_trajectories.yaml`;
- an optional `expected_contract` that tightens execution postconditions for
  this historical trace without changing the shared intent-classification
  contract;
- a deterministic, de-identified tool trace;
- the expected pass/fail result and the required hard-failure codes.

Good traces must remain accepted. Historical bad traces must remain rejected for
the expected reason. The six P0 scenarios declared by the gate are mandatory;
deleting or renaming one also fails the gate. The gate fails if either direction
changes.

Use `expected_contract` for receipt, record type, target value, or readback
requirements that are only meaningful after tool execution. Keep the base
dataset focused on what the intent compiler itself can determine. A write may
omit a separate readback when its contract permits that optimization, but it
must still carry an identity-bearing verified receipt before the trace can
claim completion.

Do not store message bodies, image URLs, user IDs, tokens, model responses, or
production record IDs in fixtures. Use synthetic dates and IDs.

## Blocking command

```bash
DATABASE_URL=sqlite:///:memory: PYTHONPATH=backend \
  backend/venv/bin/python scripts/harness_llm_regression_gate.py
```

The default command is deterministic, reads no production health data, and does
not call a paid model. Live model evaluation remains opt-in through
`--include-live-llm`.

## Current boundary

Golden traces validate the compiler and deterministic postconditions, not model
quality under live sampling. New model or prompt changes still require the
explicit live LLM gate defined by the project harness.
