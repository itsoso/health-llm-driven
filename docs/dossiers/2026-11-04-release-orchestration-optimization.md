# Release orchestration optimization — 2026-11-04

| 字段 | 值 |
|---|---|
| 状态 | in_progress |
| 当前阶段 | S6 PR 与精确 revision CI |
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
2. Add a fail-closed workflow-side election that admits only the lowest exact
   `(workflow, target, SHA)` dispatch before any production credential or write.
3. Split backend-only credential admission from the 30-minute native horizon and
   move the applicable lifetime check ahead of expensive or claim-consuming work.
4. Preserve and document the existing bounded `release_performance_report.py`
   observer; collecting a new production timing sample is deferred until a real
   post-merge release is authorized.
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

- Concurrent dispatches for the same workflow/SHA/target are serialized; only the
  lowest exact run proceeds beyond credential-free preflight, while every later
  duplicate is blocked before production credentials or writes.
- Failed, cancelled, stale-SHA, ambiguous, or unknown runs are never represented as
  success and are not automatically retried.
- Backend-only credential insufficiency is detected before claims and vendor work.
  Missing or insufficient credentials fail closed; this batch does not mint or
  refresh credentials.
- Timing output contains only allowlisted phases and numeric durations, never URLs,
  tokens, logs, or arbitrary exception text.
- Tests cover success, in-progress blocking, ambiguity, failure, cancellation, SHA
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
- Deferred: a local read-only pre-dispatch observer, immutable OTA artifact reuse,
  Pi/runtime caching, cross-runner tool images, and latency SLO enforcement are not
  implemented by this batch and require separate design and verification.

## Evidence log

- Router: `implementation`, controller `health-harness-orchestrator`, overlay
  `safety-gate`.
- Latest remote base fetched before work; shared dirty `main` was not modified.
- System Map selectors for the trusted workflow and release gate are not indexed;
  source and neighboring tests are the evidence source. Full drift gate remains a
  verification requirement.
- RED: focused tests failed because duplicate admission and backend-specific fixed
  commands did not exist (`30 failed, 9 passed`).
- Independent safety review of `f99f93e87` returned NO-GO because the new GitHub
  reader did not yet inherit the canonical no-proxy, system-CA-only, no-redirect,
  exact-final-URL boundary, and because this Dossier overclaimed a pre-dispatch
  coordinator. Both findings were remediated with negative transport tests and
  corrected scope; independent re-review of the remediation remains required.
- GREEN after remediation: the related release regression set passed `414 passed,
  1 skipped`; `release-preflight.sh` passed after the code remediation. The only
  subsequent change corrected this Dossier's wording, and its consistency gate
  passed. Exact-revision remote CI remains required before merge.
- Independent safety review returned GO after the transport hardening and final
  Dossier truth corrections; no production release is authorized by that verdict.
- The registry-selected `verification-before-completion` capability is not installed
  in this environment. Repository release tests, preflight, CI, exact-SHA status,
  independent safety review, and post-merge readback remain the verification path.
