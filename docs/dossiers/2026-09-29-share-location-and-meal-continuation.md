# Share location layout and truthful meal continuation

> 历史本地审计补录（2026-10-03）：以下状态、测试数、发布 SHA 与回执来自原工作树既有记录，未在本次整合中重新验证；不是当前生产状态或本轮发布 Gate 的新鲜证据。本轮整合与验证见 docs/dossiers/2026-10-03-local-change-integration.md。

| 字段 | 值 |
| --- | --- |
| 状态 | shipped |
| 当前阶段 | G6 verified |
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

## Candidate verification history

Candidate: `478fbae04e701db1854b96c614ba286d2d3bfb76` (implementation plus
clean-tree generated System Map; unrelated GPS artifacts remain uncommitted).

- Clean-source CI-mode: 2,642 passed / 3 existing PostgreSQL-only skipped,
  exit 0. Independent PostgreSQL 17.11: 89 passed / zero skipped, exit 0;
  new clarification cases, owner/date targeting, replay, existing record
  preservation and receipt persistence included. Temporary socket-only cluster
  stopped normally; frozen source hashes agree with the candidate.
- Clean-source Mobile: 170 diet tests and 28 turn-state tests passed. TypeScript,
  blocking Ruff, secret scan, dossier and System Map checks passed.
- Real-provider regression: PASS; invariants 12/12, health core 50/50,
  orchestrator 5/5 (average 0.96), trajectory contract 12/12 and goldens 9/9.
  Synthetic consent/in-memory test DB only. Existing missing usage-log-table
  warnings mean this does not claim budget/usage-persistence coverage.
- Production baseline d7c290ac4 verified, services active and lease absent.
  Prior production OTA c0eb135e / group 008cd999-2007-4c17-8398-4d5dfa91c287
  uses runtime 1.3.4; native configuration and dependencies unchanged.
- Evidence: `/tmp/reva-location-clean-ci.log`,
  `/tmp/reva-location-clean-mobile.log`, `/tmp/reva-location-live.log`,
  `/tmp/reva-pg-meal-clarification.rvYGzF/tests.log`.

Fixed-commit safety GO and exact-main CI still precede publication. Backend
deployment and JS-only OTA must separately pass release/verification gates.
This section is a local post-candidate audit supplement, not part of runtime code.

## G4 — First review

NO-GO on 478fbae04: `file_base64` carries non-image files but was included in
`has_attachment`, allowing a TXT/PDF attachment to bypass deterministic
missing-image/untargeted-correction clarification. No push or deployment occurred.
Return to RED/GREEN with actual image presence distinguished from generic files,
ordinary/panel entrypoint tests and existing-record preservation checks.

Remediation RED: 56 failed / 43 passed, exit 1. Tests validate real in-memory
PDF/TXT/MD/CSV uploads through the API validator before invoking both executor
modes. Minimal fix renames the predicate to `has_image` and uses only
`effective_images`, never `file_base64`. Focused GREEN: 99 passed, exit 0.
Evidence: `/tmp/reva-meal-nonimage-red.log`, `/tmp/reva-meal-nonimage-green.log`.
Fresh integration, PostgreSQL and fixed-commit re-review remain required.

## G3 / G4 — Remediation verified

- Final candidate: `8bd2655b6b7d94ec96219c8f3a0bd63a27463f2f`.
- Clean-source CI-mode: 2,702 passed / 3 PostgreSQL-only skipped, exit 0.
  Related meal suites separately: 499 passed / 1 PostgreSQL-only skipped.
- Independent PostgreSQL 17.11: 149 passed / zero skipped, exit 0; source hashes
  before/after match the fixed candidate. Shutdown checkpoint exceeded the first
  60-second wait, then completed normally; server, PID and socket absence were
  independently verified. No forced kill or production connection.
- Live-provider gate passed again: invariants 12/12, health core 50/50,
  orchestrator 5/5 (average 0.94), trajectory 12/12 and goldens 9/9.
  Existing usage-persistence warning limitation above remains unchanged.
- G4 GO: independent fixed-object re-review confirmed the non-image bypass is
  closed; no new safety finding. UI/native blobs unchanged from verified render.
- Final map, secret, dossier, blocking Ruff, scoped ESLint and design-token checks
  passed. Live evidence bound to the exact SHA before push; three owned commits
  pushed without force. Unrelated WIP preserved.
- Evidence: `/tmp/reva-location-final-ci.log`, `/tmp/reva-location-final-live.log`,
  `/tmp/reva-pg-meal-nonimage.wfCoLp/tests.log` and shutdown evidence in that folder.

## G5 — Publication

Exact candidate CI: https://github.com/itsoso/health-llm-driven/actions/runs/36511196706
completed successfully. Reused clean release checkout;
Mobile dependencies copied from identical lockfile, not symlinked into dirty WIP.

Backend `deploy.sh -b` exited 0. Production SHA exactly 8bd2655b6, clean source;
backend/worker/beat active with zero restart counters. Three health gates passed
60/60, staged KB contracts passed, runtime finalized and release lease absent.
Public API/database/Redis/Celery health passed. No new migration; database
backup/restore/offsite steps default-off per existing policy, not claimed as new
backup coverage. Candidate config preserves production values.

Fifteen synthetic deployed-helper checks passed with zero DB/provider calls.
These are read-only code checks, not live historical conversation replay; actual
stream/persistence evidence is the local/CI and PostgreSQL regression above.
Backend evidence: `/tmp/reva-location-deploy.log`.
Temporary sensitive candidate configuration deleted after successful backend
deployment. No unrelated dirty GPS/native/privacy files entered the candidate.

OTA script exited 0 on the first Hermes upload. Production iOS runtime 1.3.4:

- Group: `2cd9f0ea-e5ce-4a35-94c5-23e1dfc9ca53`.
- Update: `01a0eafb-4146-7b5b-bf91-332dba1ae631`.
- Source/main/commit SHA: 8bd2655b6, as verified by EAS readback.
- Prior known-good group retained in the release manifest:
  `008cd999-2007-4c17-8398-4d5dfa91c287`.

## G6 — Verified delivery and limits

Production backend revision, stable services, public health and read-only
deployed-code checks passed. Expo's actual production/iOS/1.3.4 manifest endpoint
returned HTTP 200 with the exact published update ID and a launch asset; MIME
manifest content and EAS metadata agree. The first JSON-only Accept probe was
rejected with 406; using protocol 1's multipart response passed, without changing
the published update or retrying publication. Local canonical OTA anchors synced
from the verified manifest. Evidence: `/tmp/reva-location-ota.log`,
`/tmp/reva-location-eas-after.json`, `/tmp/reva-location-served-headers.txt`,
`/tmp/reva-location-served-manifest.mime`.

This proves published/served OTA, not installation on the user's phone. Native
visual evidence is the labelled synthetic simulator component harness above;
no claim of full-app native rebuild, live GPS or store-review acceptance.
User must apply the update and regenerate an old share image to see the layout.
Broader compound-task handling, automatic historical target linking and summary
quality optimization are not claimed by this bounded release.
Post-release evidence is a local audit supplement to the deployed commit.
