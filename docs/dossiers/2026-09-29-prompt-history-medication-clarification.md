# Production prompt audit and medication-status clarification

Controller: health-harness-orchestrator. Overlay: safety-gate.
Status: G2 implementation; not released.
Trace: `docs/_generated/harness-runs/b2c92782fb79.jsonl`.
Spec: `docs/specs/active/2026-09-29-prompt-history-medication-clarification.md`.

## G1 scope — PASS

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
Pending: final-candidate verification/re-review, branch reconciliation and
exact-SHA CI, then clean backend release and validation.
