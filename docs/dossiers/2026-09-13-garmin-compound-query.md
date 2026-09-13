# Garmin compound query and attachment release

| 字段 | 值 |
|---|---|
| 状态 | building |
| 当前阶段 | S5 verification |
| slug | garmin-compound-query |

## G1 需求准入

裁决：PASS。用户授权修复既有本人睡眠查询、佳明同步口语识别及附件入口交互，并在验证后部署后端和发布 OTA。沿用已有认证、数据隔离、同步回执和健康安全边界，不新增后台同步权限或医疗结论。

## Engineering delivery

- Status: implementing; controller: health-harness-orchestrator; overlay: safety-gate.
- Trace: `docs/_generated/harness-runs/9a1dc5f7c4a7.jsonl`.
- User authorized fixes, backend deployment and production OTA. Baseline main `2f6cf0192` has green CI `34709530529`.
- Work takes place in the pre-existing clean main clone, preserving unrelated dirty root changes. Only the prior ChatInputBar attachment redesign is imported from root.

## Scope and acceptance

Restore existing owned reads and sync actions, without expanding to other people, historical sync windows, cancellation, quoted instructions or implicit synchronization. Accept the reported sleep + sync-status question and explicit imperative paraphrase. Last-night sleep uses wake-day attribution in the authenticated user's timezone.

The credential status endpoint can report binding, invalid credentials/MFA, enabled state, errors and last successful sync time. It cannot attest completion of a particular queued job. Preserve that uncertainty; neither data coverage nor an older success timestamp proves that the just-requested task finished. Read status without submitting another job or disclosing credentials.

Mobile: release the previously implemented inline attachment tray, with no title row or modal scrim, retaining all four existing actions and dismiss controls. Simulator is the default verification surface; no phone dependency.

## Gates

## Fresh implementation evidence

- Compound read first-red: 4 failed / 5 passed; explicit sync phrase first-red: 4 failed / 22 passed. Fixed regressions: 51 passed on isolated UTF-8 PostgreSQL, including public Pi transport/history, authenticated credential reads, owner isolation and malformed/secret-bearing status projection.
- Wider policy regression: 2206 passed; calendar/read-plan set: 95 passed / 6 PostgreSQL-only skipped (owner test separately passed on PostgreSQL). System Map regenerated and check passed; no schema or public API type changes.
- Mobile final wider regression: 165 passed and TypeScript passed. Actual simulator Release candidate verified compact four-action tray, no title/scrim, close and keyboard dismissal. CUA drag also failed a chat-scroll control; native XCUITest then passed the four accessible actions, import/cancel, X close and 140pt downward dismissal on the fixed candidate. Evidence: `/tmp/reva-attachment-native.KEXiaq/attachment.xcresult`; installed/built JS SHA256 `abcd1e92491da2ed4bdeb585f6dddfa005021b8b620fc22b88f5ec83007699b1`.
- Production preflight: exact runtime `deab5edcd6f6853c34cd6bbb2f6d94043001b159`; backend, celery-worker and celery-beat active; no release lock. No production mutation yet.
- CI-mode deployment/rollback invariants: 1184 passed, 7 skipped, 84 subtests; exit 0. Standard source-bound live model gate on clean `846873df4`: invariants 12/12, core 50/50, orchestrator 5/5; 10 successful TokenPlan calls, synthetic consent/budget only. Report SHA256 `290af8914598bbead12dc14f8cdddcf5f09cdcf9ec644ac552d51ab2f4ac15fb`.
- Extra screenshot-query trajectory on the same candidate: real Pi + TokenPlan + local authenticated ASGI credential endpoint passed. One health query and one status read returned 450 minutes/82 points, both read goals verified, current task completion unknown; no sync or health/credential writes. Final 2 provider calls succeeded. Earlier local harness encoding, encryption-key and URL failures are retained as invalid-environment attempts, not successful product evidence. Report: `/tmp/reva-garmin-live.y2yV7e/compound-final-summary.json`.
- Independent fixed-commit review: backend `3b19c58c9` GO (47 fresh tests and map check); subsequent mobile-only `846873df4` scoped GO (79 fresh tests). Runtime and UI source remain unchanged by this documentation correction.

- G3 local verification complete: first-red, policy/execution/PostgreSQL, mobile unit/typecheck/native simulator, standard live model and actual compound Pi trajectory, CI-mode integration all passed.
- G4 complete for runtime/UI: independent fixed-commit GO; documentation-only correction does not alter reviewed source.
- G5 pending: candidate `846873df4` pushed; CI `34731009440` failed dossier consistency because this new record lacked table front-matter/G1. That omission is corrected locally without weakening the checker. External deployment and OTA remain paused; no release is claimed.
- G6 pending: production runtime/health verification and OTA manifest serving. Do not claim device activation without evidence.
