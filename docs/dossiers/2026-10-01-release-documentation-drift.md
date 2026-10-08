# Release documentation drift repair

| Field | Value |
| --- | --- |
| 状态 | repair delivered; TestFlight upload and Apple processing complete |
| 当前阶段 | release evidence archived; voice UI acceptance remains separate |
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

## Fixed source review and CI follow-up

- Infrastructure commit `37df1f1f5b8d87a5b9cc5dde99139bdaee907001` received
  independent G4 source GO; reviewer independently reran 201 tests, all passed.
- Fresh CI-mode integration: 67 passed, 44.14 seconds (SQLite contract scope,
  not PostgreSQL semantic evidence). Secret scan, System Map and dossier checks passed.
- Supplemental local broad release suite: 1,829 passed, 9 environment skips,
  84 subtests passed, 2 failures caused by missing Python 3.12 on PATH. Corrected
  environment reran the complete affected scope module: 11 passed.
- GitHub CI `36867737931` passed release-invariants but backend balanced-16
  exposed the existing `AGENTS.md` byte budget violation introduced by relay
  documentation: 10,358 bytes exceeds 10,240. Local targeted test reproduced RED.
- The follow-up only condenses the relay sentence; all operational details remain
  in `docs/ops/github-relay.md`, and canonical URL/TLS/isolation rules remain intact.
- Targeted GREEN: byte-budget test passed after reduction to 10,229 bytes;
  `git diff --check` and 167-dossier consistency also passed.
- No new release authorization, build claim or vendor write has occurred. Server
  canonical source is staged; 31 historical retirements and old NEVER_STARTED
  evidence were verified. Current policy remains a811; production remains 30ac.
- Main is non-green: external writes are paused pending explicit user permission
  for this narrow repair, followed by fresh exact-revision CI and release gates.

## Completed TestFlight release — 2026-10-01

The entries above describe historical checkpoints; the user subsequently authorized
the narrow repair push and continued publication. No main freeze was required.

- Final candidate `e19043ecb269e20f3bc0a546165e43d467f1fc8c` received independent
  G4 GO. Exact CI `36872307842` and trusted validate `36872453915` succeeded;
  fresh CI-mode integration passed 67 tests in 43.91 seconds.
- Canonical bootstrap retired the never-started a811 authorization and installed
  e190, retaining the existing dedicated cloud key, original lock inode and
  historical receipts. Only the exact old loopback private key was destroyed.
- Trusted TestFlight-only workflow `36877321184` completed successfully. Backend
  was intentionally skipped: production remains the healthy, receipt-backed
  `30ac1c67be7b2df79363ac7509f70f8a56ce4834`, with compatibility attested.
- EAS STORE/IOS/production build `20d5e73a-a6b9-4c70-ad69-e63d31e058f2` binds
  exact e190 and version `1.3.4 (273)`. Build ran from 14:37:58 to 14:44:47 UTC
  (approximately 6 minutes 49 seconds), without duplicate builds.
- Submission `fcfbb57d-4804-4a36-9c57-eab062bf321e` was scheduled at 14:47:02 UTC
  and reported successful App Store Connect upload at 14:50:03 UTC.
- App Store Connect subsequently showed build 273 as `Ready to Submit`, with
  both existing internal groups `内部测试` and `Team (Expo)`, and 4 invites.
  Apple processing is complete; no external beta or App Review was submitted.
- Exact IPA SHA-256:
  `01096258d356b66b55c3aaf4a590068fb8767cc06b90442f71e8272b1e06dcf1`.
  Strict/deep codesign, bundle/version, production channel/runtime and production
  push/application-identifier entitlements passed read-only validation.
- Permanent dedicated authorization and immutable native claims remain intact;
  this native-only workspace is not relabeled as backend SUCCEEDED or reset.
- This completes the requested TestFlight delivery, not authenticated voice UI
  acceptance, feature G5/G6, App Review approval or public App Store release.
