# Share location layout and truthful meal continuation

| 字段 | 值 |
| --- | --- |
| 状态 | building |
| 当前阶段 | G3 verification |
| Controller | health-harness-orchestrator |
| Overlay | safety-gate |

## G1 — Scope admission

裁决: PASS

User requests repair of the share-poster location UI and continued optimization
of previously discussed meal interactions. This is maintenance of existing
Mobile Capture/ExecutionEvent and authenticated meal-write contracts, not new
location collection or health autonomy. Backend remains write authority;
public location remains explicitly confirmed, session-only user input.

Bounded slice: compact poster location inside the content panel, truthful
missing-image continuation, and investigate meal correction gaps before changing
their authority. No GPS/AMap feature rollout, native permission changes,
automatic publication of location, new schema or raw health data in fixtures.
Existing uncommitted GPS/AMap code and unrelated work remain untouched.

Run: `docs/_generated/harness-runs/240cf9e854ed.jsonl`.
Router selected implementation + safety. Disabled superpowers capabilities are
not used; repository RED/GREEN and fresh verification rules apply.

## Acceptance

- Location is a compact part of the poster, not an absolute full-width overlay.
  Empty location has no space; long labels fit without hiding nutrition/footer.
  Text and image retain the same confirmed, normalized label.
- Missing required meal image cannot claim a saved record or complete task.
  Request the missing input with no speculative write or duplicate retry.
- Meal corrections use existing authenticated record identity/date and receipt
  checks; ambiguous targets must clarify, never guess or create a new meal.
- Tests precede implementation. Native visual verification uses iOS simulator;
  synthetic fixtures must be explicitly distinguished from live acceptance.
- Fixed-commit independent safety GO, clean exact-main CI and scoped release
  gates are required before backend deployment or Mobile OTA.

## Progress

- Confirmed poster location uses `position:absolute`, both left/right anchors
  and a fixed photo-relative bottom; screenshot matches the current layout.
- System Map does not index the exact component; fallback map check passed,
  source and adjacent tests inspected.
- G2 PASS: location is now a compact in-panel badge. Conditional intrinsic panel
  height accommodates wrapped content; the no-location layout is unchanged.
- The missing-photo sentence previously reached `complete` on ordinary and
  panel paths; a bare half-portion follow-up could compile a new meal containing
  only the portion word. Closed original-utterance frames now use the existing
  local clarification exit after durable recovery and before model/tool routing.
  No target lookup, guessed meal, media reuse or write authority is added.
- Public and persisted `turn_outcome` agree on `waiting_for_user`; legacy
  `completion_status=complete` retains its existing generation-finished meaning.

## G3 — Incremental evidence

- UI RED: 2 failed / 41 passed; focused GREEN: 45 passed. Expanded Mobile
  regression: 3 suites / 71 tests passed. TypeScript and scoped ESLint passed.
- Current component bundled into a separate iOS simulator visual harness with
  synthetic data: short, long and absent locations inspected; nutrition, note
  and brand footer remain visible. This is component-native layout evidence,
  not a fresh full-app native build, actual GPS test or store-review acceptance.
  Temporary harness entry removed; no synthetic fixture enters the release.
- Backend RED: 8 real-entrypoint failures plus 24 not-yet-implemented helper
  cases. GREEN: 39 new tests; combined CI-mode regression 439 passed / 1 existing
  PostgreSQL-only skipped. No dispatch/provider calls, original meal unchanged,
  same-client-turn replay still waits; explicit-target/media paths stay intact.
- System Map stale after adding the helper; regenerated, subsequent check PASS.
  Clean-candidate generated artifacts will exclude unrelated GPS work.
- Evidence: `/tmp/reva-location-layout-red.log`,
  `/tmp/reva-location-mobile-regression.log`, `/tmp/reva-meal-input-regression.log`,
  `/tmp/reva-location-native.Ye8bfD/location-{short,long,empty}.png`.

## Remaining gates

Clean-candidate integration, independent PostgreSQL verification, fixed-commit
safety GO, real-provider gate and exact-main CI precede publication. Backend
deployment and JS-only OTA must separately pass their release/verification gates.
