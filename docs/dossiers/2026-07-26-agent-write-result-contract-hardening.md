# Dossier: Agent Write Result Contract Hardening

| 字段 | 值 |
|---|---|
| slug | `agent-write-result-contract-hardening` |
| 创建日期 | 2026-07-26 |
| 当前阶段 | G6 production verification |
| 状态 | complete |
| 负责 | Codex |
| 反馈环 | backend deploy |

## Problem

Several registered write adapters still report deterministic local validation
failures as natural-language `Error:` strings. Agent Runtime can only infer
their dispatch state through a legacy phrase list. A wording change can
therefore turn a harmless local rejection into `reconciliation_required`,
blocking later writes and showing users that health records are unavailable.

## Scope

- Backend Agent Runtime and registered write adapters only.
- No mobile binary or UI contract change.
- Preserve fail-closed handling for remote, database, cancellation, timeout,
  and otherwise ambiguous outcomes.

## S3 · Plan

- `docs/plans/2026-07-26-agent-write-result-contract-hardening.md`

## G1 · Admission

**裁决**: PASS

This restores existing reliable write behavior and Runtime safety invariants;
it adds no new health autonomy.

## G2 · Feasibility And Risk

**裁决**: PASS

A shared result builder can be introduced without schema or database migration.
The main risk is falsely labeling a post-dispatch failure as local; the
migration is therefore restricted to deterministic pre-dispatch exits.

## G3 · Test

**裁决**: PASS

- Full backend regression suite: 8,524 passed, 9 environment-dependent tests
  skipped, 0 failed.
- Focused write-outcome, ToolGateway, privacy logging, behavior battery,
  memory-attribute, starter-pregen, Watch voice and Kernel static suite:
  153 passed.
- Added commit-boundary regressions proving that intervention and medical-exam
  failures after a database commit remain uncertain and are not declared safe
  to retry.
- Added regressions proving that `rejected`/`failed` results are terminal only
  with an explicit `dispatch_started=false`; otherwise they remain uncertain.
- Added HTTP-timeout, pre-dispatch decision-observer and content-free logging
  regressions.
- Changed Python files compile successfully.
- Blocking Ruff checks, `git diff --check`, doc-drift, Dossier consistency and
  Operating Harness validation passed.

## G4 · Safety Review

**First review**: BLOCK / NO-GO

The independent reviewer found two adapters that could label a
post-commit `ValueError` as `dispatch_started=false`, plus raw exception text in
medical-import and generic dispatcher logs.

**Remediation**:

- Intervention-cycle status validation now runs before the service call; every
  exception after entering the commit-capable service remains uncertain.
- Medical text parsing and date validation now run before persistence;
  exceptions from `import_from_items()` remain uncertain.
- Runtime, ToolGateway, finalize and medical-import error logs retain only
  stable identifiers and exception types, never raw health content or upstream
  exception text.

**Second review**: BLOCK / NO-GO

The independent reviewer found that a `rejected` or `failed` payload could
still be treated as terminal after dispatch, that capability telemetry still
ran after the adapter dispatch, and that three Runtime-adjacent logging paths
could retain raw exception text.

**Second remediation**:

- `rejected` and `failed` are terminal only when
  `dispatch_started is False`; true or unknown dispatch state is uncertain.
- Capability-decision telemetry now runs before adapter dispatch. A telemetry
  failure returns a structured pre-dispatch rejection and proves the adapter
  was never called.
- Generic tool execution, Telegram write handling and directive parsing log
  only stable identifiers and exception classes; client responses do not echo
  upstream exception text.

**Final review**: PASS / GO

The independent reviewer found no P0, P1 or P2 issues. It confirmed that all
three prior blockers are closed, independently reran the focused 153-test
suite, verified the frozen commit diff, and found no cross-user write,
fabricated-receipt or automatic duplicate-dispatch path across medication,
genetics, laboratory and diet writes.

**裁决**: PASS / GO.

## G5 · Deployment Health

**裁决**: PASS

- `main` commit `cc072e1ebd29330698772c77993c0fb3d5b5baee` passed
  GitHub Actions run
  [30206252426](https://github.com/itsoso/health-llm-driven/actions/runs/30206252426).
  The one-time live-eval repository variable was deleted immediately after the
  rerun and its absence was verified.
- The production deploy gate completed a fresh PostgreSQL backup, restored and
  verified 234 tables in a temporary database, and verified the encrypted
  off-site archive hash and HMAC before changing code.
- `deploy.sh -b -y` deployed the exact reviewed commit. Managed migrations had
  no pending entry; backend and Celery services restarted successfully.
- Deployment health score was `60/60`, the first-party Skills manifest matched
  `22/22`, and the remote Git revision matched `cc072e1ebd29`.

## G6 · Production Verification

**裁决**: PASS

- Public `/api/v1/health` reported API, PostgreSQL, Redis and Celery healthy.
  The administrator-only Runtime rollout endpoint returned `401` without
  authentication.
- The production Runtime configuration is `enforce`; the circuit is `active`
  with no reason code. In the one-hour aggregate probe, all three terminal Runs
  succeeded, with zero failed, reconciliation-required or stale-active Runs.
- Runtime contract snapshots covered all five Runs in the observation window.
  There were no settled-message linkage gaps, missing attempts or active Runs
  beyond their deadline.
- A content-free smoke against the deployed code proved the write-result
  boundary: explicit `dispatch_started=false` rejection remains terminal,
  while missing or true dispatch state remains uncertain and requires
  reconciliation.
- The three observed `health_record/tool_rejected` operations occurred before
  deployment at 22:40–22:41 CST; no post-deploy tool failure was present in the
  verification window.
- One `agent_stream` Run from 2026-07-23 remains in `waiting_for_user` for more
  than 24 hours. It predates this release, has no active lease or write
  reconciliation, and is retained as a separate lifecycle-cleanup follow-up.
- This release changed backend Runtime behavior only. No Mobile OTA or
  TestFlight build was required.
