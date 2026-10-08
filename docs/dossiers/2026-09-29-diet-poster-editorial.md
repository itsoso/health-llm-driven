# Diet poster editorial simplification

> 历史本地审计补录（2026-10-03）：以下状态、测试数、发布 SHA 与回执来自原工作树既有记录，未在本次整合中重新验证；不是当前生产状态或本轮发布 Gate 的新鲜证据。本轮整合与验证见 docs/dossiers/2026-10-03-local-change-integration.md。

| 字段 | 值 |
| --- | --- |
| 状态 | closed |
| 当前阶段 | G6 production readback PASS |
| Controller | health-harness-orchestrator |

## G1 — Scope

裁决: PASS

User explicitly requests a more Xiaohongshu-like share card and removal of
low-value repeated labels such as meal-record and image-estimate chips. This is
presentation-only maintenance, not a new health behavior or estimation contract.
The poster uses actual food/portion text as its headline, one meal badge/date,
the existing nutrition grid, explicit location and unchanged safety footer.
Remove generic headline, decorative rules and duplicate chips; allow the copy
panel to size to content with a smaller minimum, leaving more room for the photo.
Use neutral card colors instead of warning-style fills for ordinary nutrition.

No changes to presentation/estimate logic, caption hashtags, private-data
projection, low-confidence suppression, numbers/units, write paths, photo
permissions or native dependencies. Existing unrelated GPS/native/privacy WIP
and previous release audit supplements stay untouched. No System Map activation
needed: known local component/test paths, no structural architecture change.
External workflow capabilities are unavailable/disabled; repository RED/GREEN
and fresh validation rules apply without invoking superpowers.

## Acceptance

- Meal appears once; no meal-record/image-estimate/confirmed chips or generic
  poster title. Actual food/portion is the primary text with a three-line budget.
- All approximate-number qualifiers and original public notes remain; uncertain
  nutrition still says pending verification and hides exact values.
- Photo-led 3:4 canvas; shorter intrinsic content panel, long food/location and
  absent location checked in the iOS simulator with labelled synthetic inputs.
- Existing caption/share/privacy tests remain green. Clean candidate CI-mode
  Mobile suite, tsc/lint/design-token checks and exact-main CI precede OTA.
- Only Mobile OTA needed. No backend redeploy, GPS/native or TestFlight rollout.

## Evidence

Tests updated before production code. Corrected RED: 10 failed / 38 passed,
`/tmp/reva-editorial-red-corrected.log`; GREEN: 11 suites / 186 passed,
`/tmp/reva-editorial-green.log`. The root suite includes unrelated GPS WIP tests;
clean-candidate integration is required separately before publication.

TypeScript, scoped ESLint and design-token ratchet passed. iPhone 17 Pro simulator
rendered the current component with labelled synthetic data in five states:
short location, long food/location, no location, low confidence and confirmed.
All preserve the footer without overlap; low confidence hides numeric estimates.
Screenshots: `/tmp/reva-editorial-{short,long,no-location,pending,confirmed}.png`.
This is component-layout evidence, not real-data/full-app/hardware acceptance.
The temporary fixture entry was removed after export and is not part of release.

## G3–G5 — Clean candidate validation

Candidate: `fda864c2b7f491be79db7b4523896a499581730d`.
Clean checkout: `/private/tmp/reva-half-meal-release.Yd82Ox/source`.
Matching package lock and copied dependencies reused; no unrelated root WIP.

- CI-mode Mobile main: 310 suites, 2,886 passed, one existing skipped.
- Isolated chat input / chat screen / auth / GPS prompt: 75 / 64 / 33 / 7 passed.
- Total: 314 suites, 3,065 passed, one skipped; shell chain exited 0.
- TypeScript, scoped ESLint, design token ratchet: PASS.
- Image parser security test and seven OSV gate tests: PASS; production audit
  found no high, critical or unknown-severity advisories.
- Secret scan, dossier consistency, skill governance and System Map: PASS.
- No health behavior, identity isolation, write path or API contract change;
  safety overlay, PostgreSQL and live LLM regressions are not applicable.
- Five-state simulator component evidence above: PASS, synthetic-only limits apply.

Logs: `/tmp/reva-editorial-ci-{main,input,chat,auth,gps}.log`.
Exact-main CI `36513830065`: success for the candidate SHA; fresh readback verified
before release. Remote main advanced from the green `8bd2655b6` without divergence.
Release terminal: `mobile-ota`; standard script exited 0 from the clean candidate,
runtime 1.3.4, with no bypasses. One Hermes export and one upload attempt.

## G6 — Production readback

裁决: PASS

- Production iOS group: `fc8792f0-627c-4937-928c-c2a640a784f8`.
- Update: `01a0eb0e-ec64-7a0b-bc3e-ff3bdc3deb02`.
- EAS readback matches exact candidate SHA, iOS and runtime 1.3.4.
- Actual production Expo protocol 1 multipart response: HTTP 200; header and
  parsed manifest both match this update, runtime and a present launch asset.
- Rollback group: `2cd9f0ea-e5ce-4a35-94c5-23e1dfc9ca53`.
- Root manifest/anchor synced only after checking the expected previous group.
- Evidence: `/tmp/reva-editorial-ota.log`, `/tmp/reva-editorial-eas-after.json`,
  `/tmp/reva-editorial-served-{headers.txt,manifest.mime}`; release checkout retains
  its append-only `.mobile-ota-audit.jsonl`.

Production is serving the new bundle; no claim is made that a user's phone has
already installed it. User confirms the app update and regenerates the share
image. Backend remains unchanged at `8bd2655b6`; no TestFlight/native rollout.
This post-release evidence is a local audit supplement after the published SHA;
all unrelated GPS/native/privacy WIP and prior dossiers remain preserved.
