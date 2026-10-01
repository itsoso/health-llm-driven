# Release documentation drift repair

| Field | Value |
| --- | --- |
| 状态 | implementation; release not yet completed |
| 当前阶段 | G3 regression and G4 independent review |
| Controller | health-harness-orchestrator |
| Overlay | safety-gate |

## Scope and authorization

The user confirmed concurrent main commits are documentation and explicitly asked
to publish after the proposed bounded release-check repair. This infrastructure
repair is linked to `2026-09-30-realtime-voice-conversation.md`; it does not reopen
voice implementation or claim its pending UI acceptance is complete.

The previous voice implementation ledger has no allocation remaining. This newly
authorized repair uses a separate bounded implementation run, not a safety overlay
run or a continuation of S5: `docs/_generated/harness-runs/b7ed7b93c56e.jsonl`.

## Boundaries

- Dispatch still requires candidate SHA = workflow SHA = main at dispatch.
- Later main movement is accepted only along at most eight linear commits, each
  changing only explicitly classified non-runtime documents. Each comparison must
  be complete and below the GitHub file-list bound. Merge, divergence, unknown
  paths, code edits followed by reverts, and uncertain metadata fail closed.
- Both candidate and observed main require fresh exact-SHA green CI; ref and CI
  attempts are rechecked. Package source never switches to the moving main.
- Server Git main observation is bound to the same canonical API attestation;
  canonical helper bytes are checked before isolated execution.
- Native-only continuation still compares complete production/candidate Git
  inventories, requires real production SUCCEEDED/health, and retains one-shot
  claims, business lease and immutable old receipts.
- No SSH credential change, native version bump or backend redeployment is needed
  for this source repair. Bootstrap authorization migration remains required.

## Evidence

- RED: gate suite 5 failed / 61 passed before implementation; four accepted-doc
  cases rejected by old strict-main gate and observed-main binding absent.
- Initial gate GREEN: 66 passed. Server and native-continuation regressions added
  before their corresponding implementation.
- Server/native RED: 4 failed / 126 passed before implementation. Combined initial
  regression: 213 passed; expanded gate/server/workflow/bootstrap/EAS/continuation
  regression including intermediate-code-revert cases: 432 passed, exit 0.
- G4 and actual TestFlight build/upload remain pending; this is not a release receipt.
