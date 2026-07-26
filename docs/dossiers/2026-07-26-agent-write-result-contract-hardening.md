# Dossier: Agent Write Result Contract Hardening

| 字段 | 值 |
|---|---|
| slug | `agent-write-result-contract-hardening` |
| 创建日期 | 2026-07-26 |
| 当前阶段 | G4 safety re-review |
| 状态 | building |
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

- Full targeted Runtime, Kernel, write, intervention, medication,
  symptom/rhinitis, AIGC, genetics, medical-exam and diet suite:
  1,111 passed, 9 environment-dependent tests skipped.
- Added commit-boundary regressions proving that intervention and medical-exam
  failures after a database commit remain uncertain and are not declared safe
  to retry.
- Added HTTP-timeout and content-free logging regressions.
- Changed Python files compile successfully.
- Blocking Ruff checks and `git diff --check` passed.

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

**Current verdict**: PENDING independent re-review.

## G5 · Deployment Health

PENDING.

## G6 · Production Verification

PENDING.
