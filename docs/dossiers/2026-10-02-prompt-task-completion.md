# Production prompt task completion

| Field | Value |
| --- | --- |
| 状态 | local verified; production delivery blocked by GitHub authentication |
| 当前阶段 | G3 verified, G4 GO, G5 blocked |
| Controller | health-harness-orchestrator |
| Overlay | safety-gate |

## Scope and admission

The user authorized the improvement plan derived from their production prompt
history. Deliver the three P0 paths first: owned reads, meal portion corrections,
and multi-day water backfill. This batch also repairs bounded P1 continuity and
historical-context provenance. Preserve owner isolation, explicit
write authorization, cancellation, verified receipts and idempotency.

Base: `d4628eecd341afcf1e533c5114907a5ba2c84de0` from freshly fetched origin/main.
The shared primary checkout is dirty and is not modified. No raw production
prompts, personal health values or credentials are committed; tests use synthetic
data and deidentified utterances.

## G3 acceptance

- Owned read requests resolve identity from the authenticated principal, preserve
  bounded dimensions and dates, and do not reject valid self queries as foreign.
- Meal corrections retain one verified meal target and absolute portion semantics;
  ambiguity produces a usable selection, not an arbitrary update or duplicate.
- Multi-day water requests preserve date and exact-versus-lower-bound semantics;
  missing facts receive targeted clarification, verified writes are not replayed.
- Add failing behavior regressions before implementation, then run adjacent
  authorization, cancellation, tenant isolation and user-flow tests.

## G4 safety

Independent review initially rejected `ecc1d7540071f2c9f639760656d797678868545b`:
the water path bypassed the Agent Runtime write circuit and the meal authorization
fingerprint omitted transitive executor dependencies. Both were reproduced with
failing tests and corrected in `f683d6f2ebfd7a54455674b441dd3baa14689a21`.

Independent fixed-commit rereview: **GO** for `f683d6f2e`, 52 passed and 3
PostgreSQL-only skips. Paused/unavailable water confirmation produces no health
writes or receipts, preserves the pending plan, and can resume after recovery.
The existing explicit manual WriteIntent API retains its own admission boundary.
Meal dependency changes and water grammar/expiry/execution changes now alter
the runtime authorization contract. No safety gate was waived.

## Implemented acceptance surface

- Self-read grammar now handles multi-domain insight and report-based exercise
  planning; unsupported restrictions and foreign owners remain blocked.
- Saved-meal corrections bind a single current owned row and original baseline.
  An immediate short follow-up can bind a verified receipt within 24 hours.
  Ambiguity shows up to five copyable explicit commands, not a new selection UI.
  Pending meal drafts never inherit permission to change a persisted record.
- Water totals use a source-bound manual WriteIntent and dated preview, expire
  after 30 minutes, and atomically add only missing amounts. PostgreSQL confirmation
  holds a short table lock to serialize against legacy writers; lock timeout is
  three seconds, no network/model work runs while holding it. A changed baseline
  requires a new preview. Replay describes historical targets, not current totals;
  no-op dates are revalidated and never receive invented write receipts.
- Sync plus an explicit bounded analysis gets one missing read through the normal
  Pi/gateway. Existing data and sync-job success remain separate evidence. No
  background polling or completion-triggered wakeup was added.
- Short acknowledgments and HTML-format requests retain an existing owned read
  scope. The early short-input gate now checks that scope before clarification.
- Expired conversation memories are excluded from context/openers. Medical
  conversation memories retain report time and self-report/clinical uncertainty.
  This does not implement a new persistent clinical-recovery state machine.
- New synthetic regressions verify dispatch, real adapter results, persisted
  outcomes, write receipts and negative authorization cases rather than model stop.

## Verification evidence

Producer tests before integration: owned-read reproduction 7 failures, sync/device
reproduction 5 failures, memory provenance/expiry 2 failures, short-ack full flow
1 failure, and new receipt grammar fingerprint 1 failure. Each was made green.

Fresh targeted evidence: read suites 378 passed; capability-policy suite 2189
passed; meal suite 231 passed with 2 PostgreSQL skips, separately PostgreSQL 11
passed; signed-portion/CAS PostgreSQL 13 passed including concurrent one-winner
updates; water PostgreSQL final 33 passed, adjacent suite 256 passed with 3 PostgreSQL
skips; memory/context PostgreSQL 23 passed. These overlapping counts are not a
combined test total.

First broad CI-mode integration: 5008 passed, 5 PostgreSQL skips, one obsolete
assertion failed because a valid meal correction now performs an owned, date/meal
bounded lookup before presenting ambiguous candidates. Updated that test to
verify the exact lookup, candidates, zero writes, no receipt and failure state.

Final CI-mode integration on `f683d6f2e`: **3907 passed, 5 skipped**, 208.47 seconds,
33 files, `DATABASE_URL=sqlite:///:memory:`, `TZ=Asia/Shanghai`. The long synthesis
projection matrix passed in the earlier broad run and was not repeated for the
narrow circuit/fingerprint/test-assertion corrections. PostgreSQL-only tests are
verified separately; a SQLite skip is never counted as a production DB pass.

Live synthetic LLM gate passed: invariants 12/12, health_agent_core 50/50,
orchestrator 5/5 (final fixed-code run average rubric score 0.94), trajectory contract 12/12 and
trajectory goldens 9/9. Run used a consented synthetic subject in in-memory
SQLite and configured provider credentials. Optional usage-log/budget tables
were absent in that harness database; warnings are retained in the local log,
so this is not production cost-accounting validation.

System Map regenerated from code and its drift gate passed. Full user-interface,
production write, native device and long-running background acceptance were not
performed. Existing production health records were not changed for testing.

## G5 release and G6 production validation

Pending. Local tests and source changes are not deployment or acceptance evidence.
Local `gh auth status` reports its configured GitHub token invalid, and the
repository Actions variables API returns HTTP 401. Existing SSH authentication
can read the target main ref, but it cannot publish the required API-side live-eval
confirmation. The in-app GitHub browser is signed out. Exact-commit
live-eval CI variable publication and authenticated workflow dispatch must succeed
before delivery; no guard is bypassed. Native-only release inventory is separately
governed and must pass current readiness before a backend deployment.

## Work log

- Workflow ledger: `docs/_generated/harness-runs/2b523da0635a.jsonl` (local ignored evidence).
- 2026-10-02: began reproducing the production prompt failure paths.
