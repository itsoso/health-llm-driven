# Semantic Illness Query

| Field | Value |
|---|---|
| date | 2026-08-08 |
| status | in_progress |
| current_stage | G2 PASS; design approved; implementation plan pending |
| owner_surface | Backend Agent / Mobile, Mac and Web chat |

## Problem

The production query `我上一次口腔溃疡是什么时候 最近半年分别有哪些记录`
was treated as an incomplete record-creation command. A follow-up query then
attempted an unsupported symptom query and surfaced unrelated wearable/sleep
data.

## Evidence

- The user supplied screenshots of both failures and approved the hybrid
  semantic-query architecture on 2026-08-08.
- Local reproduction on `origin/main` classifies the full query as
  `primary=write, domain=unknown, operation=create`.
- The follow-up query is `read` but remains `domain=unknown`.
- `health_query` does not register illness or symptom dimensions.
- `tool_validator._validate_query` silently coerces an invalid dimension to
  `comprehensive`, which reads wearable data and explains the unrelated sleep
  result.
- The clean-worktree baseline passed 601 existing classifier and illness-manage
  tests before implementation.

No production health record was read or copied during diagnosis. The only
health phrase retained is the user-provided reproduction required for tests.

## Decision

Implement the approved design in
`docs/plans/2026-08-08-semantic-illness-query-design.md` and product contract in
`docs/specs/active/2026-08-08-semantic-illness-query.md`:

- determine read/write authorization from the speech act, not the token
  `记录` alone;
- let the LLM express illness entity and time semantics through a registered,
  typed query plan;
- compile illness queries to a deterministic owner-scoped canonical reader;
- fail loudly on unknown semantic dimensions; and
- preserve all explicit health-record write contracts.

## Gates

### G1 Product Admission: PASS

This repairs the existing review/converse loop and maps persisted illness
episodes to read-only `ExecutionEvent` evidence. It creates no new medical
claim, autonomous action or user burden. Existing illness writes remain behind
their current confirmation boundary.

### G2 Feasibility And Risk: PASS

The classifier, schema, validator, executor and illness API/model paths were
inspected. The change needs no database or client migration. Main risks are
false suppression of legitimate writes, cross-user illness disclosure,
semantic fallback into the wrong data family, and a model omitting the illness
name. Failure-first contrast tests, explicit owner filters, fail-loud dimension
validation and no-match honesty address those risks.

### G3 Tests: PENDING

TDD red/green evidence, focused regression, static checks and qwen-max-3.7
behavior evaluation are required.

### G4 Safety Review: PENDING

Required because this crosses the L3 health read and write-authorization
boundary. Review must verify owner isolation, zero-write behavior for queries
and preservation of true write commands.

### G5 Deployment Health: PENDING

Backend deploy and health checks have not started.

### G6 Production Verification: PENDING

Requires a read-only production query showing an illness tool call and no
write attempt. No health record may be created for the drill.

## Rollback

Rollback is the prior Backend release. There is no schema migration or data
backfill, so rollback requires no data repair.
