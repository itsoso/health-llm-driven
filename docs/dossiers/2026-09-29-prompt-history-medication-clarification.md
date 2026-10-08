# Production prompt audit and medication-status clarification

> Historical local evidence imported 2026-10-03. All earlier test counts, SHA and
> release claims below are historical, not fresh release evidence. Current
> reconciliation is tracked in docs/dossiers/2026-10-03-local-change-integration.md.

| Field | Value |
|---|---|
| status | building |
| current_stage | S5 · revalidation on current main |

Controller: health-harness-orchestrator. Overlay: safety-gate.
Status: final candidate locally verified, G4 GO; release paused for reconciliation.
Trace: `docs/_generated/harness-runs/b2c92782fb79.jsonl`.
Spec: `docs/specs/active/2026-09-29-prompt-history-medication-clarification.md`.

## G1 scope — PASS

裁决：PASS（original scope; retained for reconciliation）。

Owner-scoped production audit used a read-only transaction; only aggregate and
structural evidence exported. Mixed-release historical results are not current
failure rates. No production health writes. Existing unrelated dirty files are
excluded. Source/tests show the current medication statement reaches the model
with ambiguous intent; generic hold removes unsupported advice. Preserve that
guard and improve intent instructions instead of adding a lexical shortcut.
OpenAI prompt guidance informs explicit intent examples and regression coverage;
model/provider unchanged. System-map fallback check passed.

## G2 / G3 progress

Prompt propagation RED: 5 failures / 1 pass; panel synthesis RED: 1 failure /
6 passes. Initial focused prompt/safety suites: 133 passed. Real provider using
the configured disclosed TokenPlan recipient reproduced an additional false
positive for a question explicitly deferred to a clinician. Narrow existing
assessment grammar extension RED: 4 failures / 18 passes; medical boundary and
appended-action regression: 2,984 passed. No general question-mark exemption.
Model prompt requires only acknowledgement + clarification for ambiguous status.

Live synthesis gate: invariants 12/12, health-agent core 50/50, orchestrator 5/5
(mean 0.96), trajectory contract 12/12, goldens 9/9. Initial unconfigured local
attempt was blocked by recipient disclosure and was not counted as a pass.
Real AgentExecutor synthetic status turn now completes with no tools, no medical
flags, no write receipts, and an intent question (9.72s in one run, not a latency
benchmark). Final frozen-revision reruns remain required.

## G4–G6

Initial candidate `54b034a764b9df98bb51d84097021e12feb58f8c`: **NO-GO**.
Reviewer reproduced newly allowed referral sentences with appended “断药” or
“停一晚” actions. Withdraw the entire validator exception; preserve the original
guard bytes and add both counterexamples. This is a prompt-only final scope.
Three final synthetic status turns already passed without relying on the new
exception (5.01–10.94s, illustrative samples not a benchmark); urgent-symptom
control still advised medical care. A separate synthetic explicit advice query
failed after attempting a read and is not counted as verified.

Release baseline changed during work: remote main and production are now
`26917b8458ca5639b8b99b11755dd56714d1cd04`, a sibling of the first local candidate,
with common base `210ce15fd72b0a48bdd54500919eb35813f97c3f`. External writes paused;
no push, CI attestation variable update, deployment or production data writes.
Pending: user direction on branch reconciliation and new exact-SHA CI, then
clean backend release and production validation.

## Final candidate evidence (local audit, not deployment)

Candidate `492a727cd01e34603feb646a89655dff61f686cc`. Independent G4 **GO** for
the full delta from `210ce15`; reviewer independently ran 25 tests. Validator
blob equals baseline `22aba90fae934e5ba61b1405f8a9446bcfd7d425`. Compact prompt
insertion preserves exactly the previous remaining context budget.

- Final focused safety regression: 2,987 passed, exit 0.
- Clean fixed-SHA CI-mode integration: 4,274 passed, exit 0, 15 suites through
  the project's bounded shard runner; `/tmp/reva-med-status-safe-final-ci.log`.
  No schema or persistence semantics changed; SQLite does not assert new
  PostgreSQL behavior. No PostgreSQL behavior change is claimed by this slice.
- Clean candidate real-provider AgentExecutor: three status turns (one after
  prior advice context) completed with an intent question, no tools, no medical
  flags and no write receipts. Urgent-symptom control gave immediate referral.
  Four cases completed, exit 0; no production records or copied health history.
- Clean map/drift, secret scan, skill governance, blocking Ruff and diff checks
  passed. Final live synthesis gate passed: invariants 12/12, core 50/50,
  orchestrator 5/5 (mean 0.96), trajectories 12/12 and goldens 9/9. Local
  exact-SHA live-change gate passed; no remote attestation variable updated.
- Earlier clean integration was deliberately stopped after the G4 rejection;
  it is superseded, not counted as a pass.
- No push, remote CI attestation, deployment, OTA or TestFlight performed.

## Remaining audit priorities

Historical permission failures need current-version replay before another
authorization change: the batch includes older exercise-plan, summary and meal
correction behavior already addressed by separate releases. Do not broaden
personal-data access based on aggregate counts. Generic medical holds still need
semantic precision work with adversarial evaluation; the rejected grammar
exception demonstrates why. Long-tail latency needs a matched current-version
batch with tool/model timing before claiming speed improvement. Finally,
status-only follow-ups such as generic “更新近况” still require source-bound
intent resolution; this slice does not reclassify arbitrary update commands.
