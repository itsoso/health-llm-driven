# Advice and action explanation scope incident

| Field | Value |
| --- | --- |
| 状态 | building |
| 当前阶段 | G4 passed; awaiting coordinated release |
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
- Final focused: 150 passed / two PostgreSQL-only skips, exit 0.
- Broad capability/gateway/recovery/required-history regression: 6,007 passed,
  14 conditional skips, exit 0 (`/tmp/reva-conversation-advice-broad.log`).
- CI-mode user-workflow/coherence/tool-recovery integration plus new ordinary
  and panel tests: 53 passed, exit 0 (`/tmp/reva-conversation-ci-integration.log`).
- Live LLM gate: 5/5 orchestrator cases passed (average 0.9), plus invariants
  12/12, health-agent core 50/50, trajectories 12/12 and goldens 9/9. Evidence
  `/tmp/reva-conversation-live-gate2.log`. Initial attempt failed because the
  assumed backend `.env` was absent; retry used only existing TokenPlan settings
  from the workspace online env. Test database/consent remained synthetic and
  isolated; no production data or configuration was changed.
- Combined Mobile candidate: 320 suites / 3,128 passed / one existing skip;
  typecheck exit 0. Dossier, skill governance, secret and diff checks passed.
- Upstream advanced by three release-only commits to `b10c5a154`; exact CI
  36594594034 succeeded. Merged without conflict in local `9397629dd`; backend,
  Mobile and Mac production blobs unchanged from reviewed candidate. The only
  added test verifies the panel path. Original workspace remains untouched.
- System Map check passed before changes; no architecture nodes added.

## G4 / G5 / G6

Independent review: `94c979c33` NO-GO (invented private evidence could complete);
`a58b990b` NO-GO (claim denylist bypassed by semantic paraphrases). Tests on that
rejected candidate passed 6,064 cases and the live gate, but are not G4 proof.

Correction: new bedtime/general-sleep and exact Agenda-wrapper goals now use
canonical server-owned guidance before provider/panel calls, after durable
write recovery. Existing symptom-recovery stays unchanged. Lower model routes
fail closed on any noncanonical answer for these goals. Provenance is public
guidance plus current input, not personal records or a verified appointment.
Editorial sources: NHS sleep hygiene and appointment-question checklist, linked
inline in the canonical answers. No user health content is interpolated.

New entrypoint RED: 7 failures / 8 passes in `/tmp/reva-local-advice-red.log`,
demonstrating unwanted provider/panel dispatch and missing ACK recovery path.
The first GREEN attempt exposed a test-only event-shape assumption (progress
frames do not have `event`); corrected to use the existing `.get` convention.
Fresh final-code verification:

- Focused transport/scope/recovery: 206 passed, two PostgreSQL-only skips,
  exit 0 (`/tmp/reva-local-advice-focused2.log`).
- CI-mode integration plus canonical-route/claim tests: 88 passed, exit 0
  (`/tmp/reva-local-advice-ci.log`).
- Expanded capability/gateway/longitudinal/context/recovery: 6,480 passed,
  14 conditional skips, exit 0 (`/tmp/reva-local-advice-broad.log`).
- Live gate: invariants 12/12, core 50/50, orchestrator 5/5 average 0.98,
  trajectory 12/12, goldens 9/9, exit 0 (`/tmp/reva-local-advice-live.log`).
  Isolated in-memory test DB lacks usage-log tables, so quota/usage audit is
  explicitly unverified by this run; production was not queried. New canonical
  routes prove zero provider calls independently, not through that live eval.
- System Map wrapper, dossier consistency, skill governance, secret scan and
  diff checks passed. No new schema/endpoint/architecture node.
- G4 GO: independent reviewer on fixed `50b42db154610d3b6a76374a3b5c2b2266b393be`,
  independently 125 focused passes. Prior NO-GO examples cannot be promoted:
  canonical output selection replaces semantic keyword validation.
- Remote advanced to release-only `1ee419a27f15bda407dc124104cb44ab4cf6fd4b`,
  exact CI run 36597403523 success; merged locally at `f58b8e65d`. Backend,
  Mobile and Mac blobs remain identical to reviewed `50b42db15`.

- Independent PostgreSQL 17.11 verification: 17 passed, zero skipped, exit 0
  using the CI shard runner at fixed `f58b8e65d`; executor/test hashes unchanged
  before/after. Proves owner isolation, canonical persistence/replay, failure
  propagation and zero-model routing with real PostgreSQL. Evidence:
  `/tmp/reva-pg-local-advice.8lGFL3/tests.log` and sibling hash/shutdown files.
  Isolated server stopped cleanly; no production data accessed.

No backend, OTA or desktop publication claimed. Existing HTML G4 does not
substitute for review of backend behavior. Exact main CI and post-release
verification are required. Another MacBook's frontend finalization receipt for
operation `72988375dd2a4785ddbd351523197536` was absent on last read-only check;
do not take over its finalization or change current main underneath it.
