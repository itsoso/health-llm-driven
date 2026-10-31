# Single supplement intake: preserve one parsed fact through persistence

| 字段 | 值 |
| --- | --- |
| 状态 | building |
| 当前阶段 | G3 locally verified; independent review and release pending |
| Controller | health-harness-orchestrator (incident), safety-gate overlay |
| Run | `docs/_generated/harness-runs/09731e372ccf.jsonl` (local) |

## G1 admission

PASS: existing record-and-verify loop reliability. A current-user explicit
supplement intake must preserve its name, quantity and unit through authorization,
tool planning, authenticated persistence and verified receipt. This is a bounded
bugfix, not dosage advice or regimen modification. No schema, public API, client
type or mobile change. Existing `docs/specs/recording-reliability.md` provides the
shared-plan contract; this follow-up includes single-item planning and actual
quantity persistence, and adds creatine to the bounded intake grammar.

## Reproduced causes

Synthetic local probes reproduce the reported sentence shapes. No production
health records, logs or model providers were accessed, so these findings are not
a claim about the exact production request trace.

- The classifier recognizes supplement/create, but the typed intake vocabulary
  omits the target. The legacy parser retains the completed-ingestion verb in
  the name. With a comma, the record label and intake are split into separate
  authorization clauses.
- Even supported typed names are re-parsed by deterministic tool repair and
  corrupted. This can replace a correct model-proposed payload with a bad one.
- Pi's no-tool repair handles complete batches but omits a complete single item.
- The legacy single-item adapter uses NFC tap, which does not store actual
  dosage. It rejects an explicit amount different from the usual regimen.
- Unresolved target authorization falls through to a misleading create/update
  clarification even when create intent is clear.

The relevant parser and single-item repair branches are also unchanged in the
inspected `origin/main` relative to the starting local revision. Remote changes
elsewhere are not integrated or verified by this task.

## Implementation

- Authorization and deterministic repair consume the same complete typed intake.
  The bounded grammar still rejects residual text, uncertain counts, other
  people, future/planned/negated/quoted requests and quantity/type changes.
- A complete single supplement intake can supply an omitted model tool call;
  attachment and existing-receipt guards remain in force, and the normal Pi
  capability/gateway/durable-operation path still executes it.
- That exact single-item path uses the existing authenticated `/supplements/records`
  endpoint to store `actual_dosage` and server-bound current date/time. Existing
  definitions keep their usual dosage. Name-only and other legacy grammars retain
  their existing adapter semantics; broader grammar consolidation is not claimed.
- Success requires a returned record ID, matching owner, definition, date,
  `taken=true` and actual quantity. Missing/conflicting responses are unverified;
  transport uncertainty does not prove no write. Definite auth denial remains
  a no-write error. Unresolved-target copy no longer invents operation ambiguity.

## G3 evidence

- Initial new regression: 17 failed / 16 passed, including exact identity,
  misleading copy and real gateway/API execution. After parser/repair correction,
  4 runtime failures exposed the independent actual-dosage persistence defect.
- Final focused tests: 49 passed (`/tmp/reva-single-intake-final.log`), plus 4
  auth/transport negative tests (`/tmp/reva-single-intake-errors.log`).
- Dedicated temporary PostgreSQL 17 UTF8 cluster: 49 passed
  (`/tmp/reva-single-intake-postgres.log`); server stopped afterward. Includes
  existing/new definitions, model call/omission, persisted actual quantity,
  unchanged regimen, verified outcomes and client-turn replay.
- Adjacent scope, mixed intake, autocreate, fast routing and real API streams:
  797 passed / 6 existing inapplicable parameter combinations skipped
  (`/tmp/reva-single-intake-regression.log`). Synthetic provider only.
- System Map check and `git diff --check` pass; no generated structure drift.

## Release boundary

Startup branch: local `main` ahead 2 / behind 102 relative to `origin/main`, with
unrelated user/agent modifications. Those changes are preserved. AGENTS §7
blocks external writes while this divergence and candidate provenance remain
unresolved. No push, deployment, OTA or production record mutation performed.

The path-sensitive LLM gate correctly reports live evaluation required and
unconfirmed. Exact integrated main CI, project CI-mode, live synthetic evaluation,
final G4 and production receipt/user-path verification are not satisfied by local
tests. This task must not be represented as released or as eliminating every
unsupported natural-language record failure.
