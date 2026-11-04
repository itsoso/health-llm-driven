# Release orchestration optimization — 2026-11-04

| 字段 | 值 |
|---|---|
| 状态 | in_progress |
| 当前阶段 | S5 实现与增量验证 |
| Controller | health-harness-orchestrator |
| Overlay | safety-gate |
| Base revision | `50d3ae26813d608263f350c5a2b250fca59022b1` |
| Run ledger | `docs/_generated/harness-runs/b9336cc411b9.jsonl` (local, not committed) |

## G1 准入

裁决：PASS。用户明确要求按已确认的发布优化规划执行。本批次只收敛发布协调、
重复 dispatch、凭据寿命准入和操作文档，不改变健康数据、诊疗语义、产品权限、
数据库 schema 或客户端运行功能。生产写入仍由既有 trusted workflow、一次性 claim
和独立发布授权控制；合入本批代码本身不等于部署或 OTA。

## Objective

Reduce avoidable release latency and operator error without weakening exact-SHA CI,
one-shot claims, credential isolation, production health readback, or OTA manifest
verification. Replace the abandoned PR #252 path with a small, reviewable release
coordination layer built on the trusted workflows already proven in production.

## Scope

1. Make the Mobile OTA skill and repository entrypoint agree on the trusted GitHub
   workflow; local publication remains disabled.
2. Add a read-only release coordinator that discovers and reuses a unique applicable
   run for the exact SHA and target before dispatching anything.
3. Split backend-only credential admission from the 30-minute native horizon and
   move the applicable lifetime check ahead of expensive or claim-consuming work.
4. Record bounded end-to-end timing evidence and expose the actual slow phase.
5. Document deferred optimization work: immutable OTA artifact reuse, Pi/runtime
   cache, cross-runner tool images, and release latency SLOs.

## Non-goals

- No relaxation of CI, G4, production lock, receipt, or public manifest gates.
- No automatic retry after a claim, vendor write, or unknown result.
- No new credential scope, storage location, ambient token fallback, or secret output.
- No App Review submission, native build, backend deploy, or OTA publication merely
  because orchestration code is merged.
- No attempt to generalize historical fixed-SHA incident profiles in this change.
- No automatic credential mint or refresh. The repository has no general audited
  provider; incident-pinned refresh operators cannot be reused.

## Acceptance criteria

- Repeated coordination for the same SHA/target observes or waits for the existing
  run instead of creating a duplicate.
- Failed, cancelled, stale-SHA, ambiguous, or unknown runs are never represented as
  success and are not automatically retried.
- Credential insufficiency is detected before claims and vendor work; refresh, when
  needed, uses the existing repository-scoped audited operator.
- Timing output contains only allowlisted phases and numeric durations, never URLs,
  tokens, logs, or arbitrary exception text.
- Tests cover success, in-progress reuse, ambiguity, failure, cancellation, SHA
  drift, credential expiry, and secret-redaction boundaries.
- Repository release instructions have one canonical OTA path.

## Design verdicts

- Duplicate admission: GO only inside the trusted workflows. A client-side
  read-before-dispatch helper alone has a TOCTOU race and is not used as authority.
- Election: the shared non-cancelling production concurrency group serializes runs;
  the lowest exact `(workflow, target, SHA)` run ID may proceed. Every later exact
  dispatch is blocked regardless of the earlier terminal outcome.
- Credential boundary: GO for fixed `check-backend` / `run-backend` commands using
  full CI with a 300-second read-credential horizon. Combined release/native keeps
  1800 seconds and rechecks before execution.
- Automatic credential refresh: NO-GO in this batch. Missing/expired credentials
  fail closed and require the separately installed, reviewed external operator.
- Telemetry: reuse `release_performance_report.py`; do not create a parallel timing
  parser or treat timing as release authority.

## Evidence log

- Router: `implementation`, controller `health-harness-orchestrator`, overlay
  `safety-gate`.
- Latest remote base fetched before work; shared dirty `main` was not modified.
- System Map selectors for the trusted workflow and release gate are not indexed;
  source and neighboring tests are the evidence source. Full drift gate remains a
  verification requirement.
- RED: focused tests failed because duplicate admission and backend-specific fixed
  commands did not exist (`30 failed, 9 passed`).
- GREEN: trusted workflow/server/OTA/CI contract regression set passed `371 passed,
  1 skipped` before the final documentation-only edits; final verification remains
  pending.
