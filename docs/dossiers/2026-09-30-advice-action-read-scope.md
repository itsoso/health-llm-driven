# Advice and action explanation scope incident

| Field | Value |
| --- | --- |
| 状态 | building |
| 当前阶段 | G3 verification |
| Controller | health-harness-orchestrator |
| Overlay | safety-gate |

## G1 / G2

裁决: PASS

- Run `735704383ed9`, local trace `docs/_generated/harness-runs/735704383ed9.jsonl`.
- Spec: `docs/specs/active/2026-09-30-advice-action-read-scope.md`.
- This is a bounded bugfix to existing advice/Agenda explanation, not permission
  to read health records or alter a treatment/schedule.
- Clean candidate based on remote `d55e189cdf74e5cb61a645e761ab6d4018efd077`;
  four HTML-only commits ported, excluding unrelated local prompt/GPS/privacy
  changes. Original checkout untouched. Another MacBook is active; recheck
  remote SHA and release state before any external write; never force push.

## Diagnosis

Independent read-only investigation confirmed the bedtime input has no read
act, but longitudinal parsing treats sleep plus advice as unresolved read
residue. A speculative read therefore produces a terminal date error. The
Agenda explanation wrapper likewise lacks an answer-only proof and its optional
illness read produces a terminal authorization error. Merely bypassing the date
guard is unsafe: a bare bedtime question can reach a generic list-read fallback.

## G3 evidence

- Synthetic RED: nine filter/gateway assertions failed; real Pi transport after
  matching-lock dependency reuse reproduced blocked outcomes. Evidence:
  `/tmp/reva-conversation-advice-red2.log`.
- Initial focused GREEN: 136 passed / two PostgreSQL-only skips; two new tests
  required adjustment to preserve the existing medical source-prefix behavior
  while asserting streamed/persisted equality (not a runtime fix).
- Final focused, broad, live model and integration evidence pending.
- System Map check passed before changes; no architecture nodes added.

## G4 / G5 / G6

Pending. No backend, OTA or desktop publication claimed. Existing HTML G4 does
not substitute for review of this new backend behavior. Exact target CI and
post-release verification are required before completion.
