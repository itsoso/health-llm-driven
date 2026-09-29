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

Pending: RED/GREEN, synthetic live checks, integrated verification, fixed-revision
independent safety review, exact-SHA CI, clean backend release and validation.
