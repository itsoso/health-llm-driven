# Meal item correction delivery

| 字段 | 值 |
| --- | --- |
| 状态 | building |
| 当前阶段 | G2 implementation |
| Controller | health-harness-orchestrator |
| Overlay | safety-gate |

## G1 — Scope

裁决: PASS

See `docs/specs/active/2026-09-29-meal-item-removal.md`. Fix the reported
component-removal request without widening generic reads, deleting meals or
automatically rewriting production health data. Existing confirmed revision-
checked editor remains the write boundary. Unrelated worktree changes preserved.
Router uses registry overlay key `safety` to activate `safety-gate`.
System Map exact service selector unindexed; fallback map check passed, source,
models and nearby tests inspected. External superpowers capabilities disabled;
repository test-first/fresh verification discipline used instead.

## G2 / G3

Implementation reuses the existing early photo-correction proposal handler and
Mobile revision-aware editor; no generic classifier/read-policy relaxation.
Closed item frames bypass model delete/list routing on the ordinary chat path.
Only the most recent immediate photo meal, or a retry after a failed matching
item-removal turn, may resolve via the owner's consumed photo draft. Confirmed
save continues through the existing recalculation API; no automatic data patch.

- RED: 21 failed / 7 passed (`/tmp/reva-item-removal-red.log`).
- Focused GREEN: 47 passed; expanded helper/stream/diet/save regression 241 passed
  / one existing PostgreSQL-only skipped (`/tmp/reva-item-removal-regression.log`).
- Mobile existing editor/action contract: 124 passed, two suites.
- Exact current request, auth owner, source conversation, finalized predecessor,
  pending/consumed state, freshness, ambiguous names and unchanged originals tested.
- Confirmed-save test proves same record, re-estimation, idempotent replay and
  rejection of stale revision. Synthetic estimates are not nutritional accuracy evidence.
- LLM change-path gate: PASS, no live-provider gate required by selected paths;
  this deterministic helper adds no prompt/provider/schema or model-ID authority.
- Blocking Ruff and diff whitespace checks: PASS. No dependencies/schema changed.

Run trace: `docs/_generated/harness-runs/e9fb0553133c.jsonl`.
Clean integration, PostgreSQL, G4 independent review, CI and release still pending.
