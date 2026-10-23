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

- Dedicated recovery candidate `c93f0ec5ba220ffbfa02234a0ff1527c250027d2` passed independent safety review and 52 recovery tests. Full CI `39887385644` found existing frontend Next 16.3.8 vulnerable to GHSA-2464-fhr4-w9xw, GHSA-673q-mjm6-r5xr and GHSA-p3m5-59mp-jv5r. Upgrade only Next/eslint-config-next and lockfile to 16.4.1. Original OSV audit passes, frontend production build passes, Vitest 565 passed/1 skipped, lint 0 errors. New exact-SHA full CI remains required. Recovery and deployment remain unexecuted.


### 2026-10-23 恢复后验失败：保留原 intent

恢复候选 `6492f31789edf257ace6710cdfdff7b6c6c3b8b6` 的完整 CI
`39888949129` 已成功；本地精确 CI-mode 4617 项，49 skipped，0 failures/errors。
独立审查 GO 后 canonical stage、只读 inspect 成功，证据摘要
`3d9c4ba906fae58c67c25d18bbc0ea2a18be37176a6745347a74387f3f2446a2`。

已授权的一次恢复在写入原 audit intent 后启动三个服务，随后后验拒绝，
保护逻辑停止全部服务。当前 audit 仅 intent.json，无 completed.json；
原失败回执、lease 和生产 f42 代码保留，晚餐修复没有部署。
只读诊断定位到 dinner_guard_recovery.unit_configuration 的 raw show hash；
ExecStart 输出含启动时变化的 pid/start_time/stop_time/code/status，
不可作为静态配置不变证明。原 FILE_PINS 在该诊断中通过。
不得重放已消费恢复、改写 intent 或换操作 ID。须先完成静态配置修复与独立
审查；任何第二次启动尝试需明确说明现有不重跑规则例外并取得具体授权。
证据见本任务 receipt 及 /tmp/reva-dinner-recovery-readonly-diagnostic.json。


### 2026-10-23 再次授权原服务恢复

用户获知上述失败及再次恢复的规则例外后回复「授权恢复原版本服务」。
继续限定原 f42 服务恢复，保留 ae49 失败回执、lease 与 6492 原恢复 intent。
静态配置规范化修复已独立 GO，65 项测试通过；原依赖与全部配置文件 pins
只读验证未变。当前正在准备固定原 audit/continuation-20261023-static-unit-proof 的单次继续入口；
尚未再次启动，完整新 revision CI、独立审查与两阶段检查仍为必需条件。
后续退休消费者也需认识该子目录终态，不能将其伪装为首次恢复成功。


### 2026-10-23 原服务恢复完成（不等于晚餐修复发布）

候选 `2c2679bf137aadc926c35d2197d740b3cefd5552` 经独立 G4 GO，
完整 CI `39896637763` success；本地 exact CI-mode 4650 项，49 skipped，
零失败/错误。canonical stage 与 inspect 成功，按固定摘要
`b79b4a14f724648f264db72193db08424a0fdc5dffd30abb5a97b217e68ccf9f`
执行已授权的单次 continuation，返回 RESTORED_PREVIOUS_SERVICES。

独立回读确认生产仍为 f42、原 runtime COMMITTED；三个服务 active/running、
NRestarts=0，原 ae49 NEEDS_OPERATOR、发布 lease、6492 原 intent 原字节均保留。
continuation terminal 只在固定子目录内，未冒充首次恢复成功。公开 HTTPS
health healthy，API/database/Redis/Celery 正常；匿名 auth/me=401。
只读回读对 systemd socket 不提供 MainPID/NRestarts 的序列化差异做严格兼容，
8 项正反测试和独立 GO 后复验成功；未重放生产恢复。

证据位于本任务 receipt 与 /tmp/reva-dinner-continuation-readback-2.json、
/tmp/reva-dinner-continuation-public-health-2.json。未备份、未读真实健康记录、
未调用真实模型。晚餐修复仍未部署；后续 lifecycle 收尾须消费真实 continuation
证据再走独立 gate，不能重跑原已失败部署或提前清除 lease。


### 2026-10-23 新候选发布准备

用户要求「想办法上线」。新鲜只读回读确认旧 f42 服务保持稳定、NRestarts=0，
没有其他活动 trusted-release；GitHub relay enabled/active 且隔离 canonical
ls-remote 返回当前 main。原 ae49 发布及两次恢复均禁止重放。

为新候选补专用 no-copy retirement：严格消费原 intent 与实际成功 continuation，
保留失败回执，撤销旧精确双身份，原 inode 归档租约后通过受保护回执轮换。
同时修正下一次 guard 对 worker sticky timeout 的处理：仅在无 PID、ControlPID、
cgroup、systemd 作业且租约仍有效时归一化 failed/timeout；其他失败仍阻断。
新候选尚未发布，独立审查、完整精确 CI、CI-mode 及 canonical 收尾/轮换仍需实证。


## 2026-10-23 第二次部署的停服检查事故

候选 `fdd5659502888d44bf91c9b35a7368366932098f` 的完整 CI `39904217306` 成功，本地 CI-mode 4711 项（零失败、49 skipped）。原 ae49 事故收尾、凭据刷新及 fdd 授权安装均有成功回执。

正式后端工作流 `39912810389` 在停止 writer 的 guard 阶段失败，终态 `NEEDS_OPERATOR`；生产代码仍为 f42，未 checkout、未启动 runtime prepare/install/commit/restore。后端及 worker 已正常停止，beat 保持原进程。失败日志没有精确检查项，不能从事后状态断言具体原因。

依据用户既有原版本恢复授权，固定 fdd/f42 专用恢复入口验证源码、配置、依赖、schema、原 lease/stage/runtime 及混合服务状态。只读预检摘要为 `de48cf7ce6985439c571692b9e7341ba356d01cde96c7bbbb5d4f6d874a714be`，受审 apply 正在执行；未把原失败发布改为成功，不重放部署，不创建备份。

新 guard 对状态/PID/cgroup/jobs 的异步收敛做固定有界等待，每轮复核 lease，查询错误与非 timeout 失败立即拒绝，最终两轮复证全部 writer 静止；新增静态 unit/phase/check/attempt 诊断。四种合理瞬态先红后绿，完整部署脚本测试 202 passed。此为收敛处理及诊断增强，不构成对本次现场具体失败项的确认。

恢复 apply 已在 `verify_snapshot` 阶段失败，原 core 完成失败停服。只读复核四服务均 inactive/dead、无 systemd jobs，原 `intent.json` 与 `restore/intent.json` 保留，未生成 completed。原 restore snapshot 的 incident、config、installed 三部分与停服后观测均无变化；三个服务启动时间戳已推进，具体运行态触发条件尚未确定，不将其宣称为恢复或部署成功。原回执摘要：quiesce `6cb754d7a286ad1495d1975781808324cd765210bb2d2b115b3efa117a583217`，restore intent `e6ade82f0baf2822f7e712246d2cd9d0d2d57225823caeb778568f56fe016f03`。后续限定入口必须保留两份原始证据、原校验与失败隔离，并记录首个脱敏异常或差异字段，不能重放原 apply。

限定续行实际完成 `RESTORED_PREVIOUS_SERVICES`；独立完整 collector 与公网 TLS 健康检查通过，数据库/Redis/Celery 均 connected，匿名 auth/me 仍 401。线上仍为 f42 旧版本，原 fdd NEEDS_OPERATOR 与 lease 保留。固定子目录 intent 原字节摘要 `0d60a90cc24c0735c8fef19ba98e5ba567437a5e81ecb80bf67ced18d04b2772`，completed `c464e556abce7814187745609758006fa3f77fe28c85831a6b395e01f087cc70`；实际取证摘要 `377c71560a95554f130b3f692336992ee0e5bcf97aaa7ab6c0a58e3e1e223531`。同一原校验在续行与独立运行态复核中通过，前次瞬态失败的具体原因仍未确定，不据此宣称其根因已修复。下一步仅为新候选发布，不重放 fdd 失败部署。
