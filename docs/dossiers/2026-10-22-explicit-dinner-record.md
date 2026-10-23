# Explicit dinner recording through Pi

| 字段 | 值 |
|---|---|
| 状态 | building |
| 当前阶段 | S5 验证 |

## G1 准入
裁决: PASS。修复明确餐食新增请求没有产生工具调用时未保存的问题，不新增数据权限或绕过营养估算。

## Evidence and scope

- The screenshot caption compiles to a diet/create goal with all five foods/amounts preserved. The existing diet preplan helper was not connected to the ordinary Pi loop.
- RED: synthetic provider returns no tools, receipt remains empty. First two test invocations had an incorrect model import; corrected fixture then reproduced the behavioral failure.
- Connect the existing proposal helper only after a normal round-zero model stop without tool calls, for authorized current-turn diet/create, no crisis language, no attachments, no pending/unverified operations, no runtime block or read-only mode. Keep ordinary nutrition enrichment, Pi validation, gateway, persistence and receipt verification.
- Focused SQLite tests: 213 passed. Includes original request and owner-bound retry through real diet API, blocked/runtime/read-only/incomplete-nutrition boundaries. No real models or real health records used.
- System Map passed. PostgreSQL: 213 passed in 33.78s, isolated UTF-8 test database; /tmp/reva-dinner-pg.log.
- Safety review, full CI and production deployment pending. No mobile change.
- Existing local prompt-contract commits 51d7cf09b and 7b3c69f8c are included in this release batch. On 2026-10-22 the user explicitly replied “跳过 继续发布” to the question about skipping live model evaluation for this dinner and prompt-contract batch. Live evaluation status is waived, confirmed=false; bind HARNESS_LIVE_LLM_EVAL_WAIVED_SHA to the final exact release commit. Offline validation, independent safety review, full exact-SHA CI and production gates remain required.
- Screenshot alone does not prove the retry was stuck for its entire timestamp interval. The test verifies original-message recovery and finalization; device UI timing remains unverified.

- Duplicate retry replay tests: 5 passed on SQLite and 5 passed on isolated PostgreSQL; no duplicate meal was created. Independent safety review GO for implementation 92e14d4ff; final candidate incremental review remains required. Clean CI-mode on 92e14d4ff: 4588 tests, zero failures/errors, 49 skipped; final candidate verification and production readback pending.

- Full remote CI 39788650370 rejected candidate 1ec8534b3 before production changes. Failures revealed a stale prompt projection assertion, crisis-turn enrichment, and automatic proposals preempting structured model results. Move proposal generation after a normal no-tool model stop, preserve structured nutrition and model-call accounting, exclude crisis turns, and strengthen crisis no-enrichment assertions. Existing receipt/gateway guards remain unchanged. Repaired candidate requires fresh exact-SHA CI and independent review.

## Release handoff 2026-10-22

- Final candidate `ae49cf1fc53c567b305c2a9f6cfff5c3257e7309`: independent safety GO; SQLite 747 passed; PostgreSQL 747 passed; independent reviewer 322 passed.
- Exact clean CI-mode: 4588 tests, zero errors/failures, 49 skipped. Full GitHub CI `39791359741` succeeded. Live evaluation remains explicitly waived, confirmed=false, repository waiver variable bound to this SHA.
- Trusted validate `39794147425` queued without a runner; GitHub official Actions component reports degraded performance. No deployment or OTA performed.
- Initial read-only operational inspection stopped before inspect because old backend-only release had no optional build.lock. No mint/refresh/stage/rotation occurred. Preserve `/tmp/reva-dinner-ae49-delivery-inspect-refresh-*.json`; never replay that driver.
- Corrected optional-build-lock script and new local prefix independently reviewed GO: `/tmp/reva-dinner-ae49-backend-release-remote.py` and `/tmp/reva-dinner-ae49-backend-release-driver.py`. Hold launcher and existing build lock; when absent require it stays absent; do not create a lock. Precise hashes, evidence and current state are in `docs/reviews/2026-10-22-explicit-dinner-record-receipt.json`.
- Resume only after validate success and fresh canonical baseline checks. Production last proven `f42bb4c6d1c962453a6eadd1318ca6b663174b80`, healthy and COMMITTED. Execute reviewed phases once; failures preserve evidence and require new review. Then trusted backend workflow and independent `/tmp/reva-dinner-ae49-readback.py`, public health check, and clear only this owned waiver after release. No mobile changes; OTA not required.

## External release block after validate

- Validate `39794147425` eventually succeeded. Corrected operational inspect/refresh/stage/inspect-rotate/rotate all completed for ae49; preserve their original `/tmp/reva-dinner-ae49-backend-delivery-*-result.json` receipts. Never replay those phases.
- Backend workflow `39798692177`, job `119893400834`, failed in “Independently materialize and recheck before accessing production credentials”: `release gate: Incomplete or malformed CI history`. The production capability step was skipped.
- Fresh workflow-name and numeric-workflow-ID API queries both returned total_count=0 / workflow_runs=[] for ae49 despite individual CI 39791359741 having completed successfully. No gate bypass or new workflow was attempted.
- Independent production readback `/tmp/reva-dinner-failed-deploy-readback.jsonl` confirms f42 remains SUCCEEDED/COMMITTED and healthy; candidate workspace/started/completed all absent. Installed authorization is now ae49, as intended by completed rotation. Candidate has not been deployed. Short-lived repository credential expires at UTC epoch 1792682928.
- Resume requires recovered complete GitHub CI history, fresh installed/canonical state, and independent review of the failed-before-production-credentials continuation. Do not replay refresh/stage/revoke/key/rotate. If repository credential expires, prepare a newly reviewed refresh for current installed state; the old pre-rotation refresh is invalid. Retain the exact-SHA waiver pending release; no actual model evaluation, health-record inspection, backup, OTA or TestFlight occurred.


### 2026-10-23 deployment incident

- GitHub CI history recovered; reviewed refresh-only operation completed and the original failed-before-credentials backend job resumed once. Original stage/rotation was not replayed.
- Run `39798692177`, attempt 2, job `120186164694` consumed the server capability and failed with `NEEDS_OPERATOR`. Production HEAD remains `f42bb4c6d1c962453a6eadd1318ca6b663174b80`; services are stopped, so deployment is not complete.
- Worker stop proof rejected `ActiveState=failed`. An ungrouped generated multiline dependency snippet escaped the shell AND chain, invoking Pi installation despite the failed prerequisite and from the wrong directory. No checkout/prepare/install checkpoint occurred. Independent read-only evidence: `/tmp/reva-dinner-incident-readonly-proof.json` and `/tmp/reva-dinner-incident-readonly-extra.json`.
- Added reproducing guard regression (failed before fix), then grouped the generated snippet. Focused deploy regressions: 216 passed in 99.26s; bash syntax passed. Fix remains local pending independent review and publication gates.
- Preserve original receipts and lease. No re-run, backup, real model invocation, or personal health record access. User explicitly confirmed dedicated old-service recovery on 2026-10-23. Recovery remains limited to unchanged previous services, preserving original receipts/lease, without replay or backup. A reviewed no-backup proof is required; existing legacy recovery cannot be reused as-is.
