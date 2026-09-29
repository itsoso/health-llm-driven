# Diet poster editorial simplification

| 字段 | 值 |
| --- | --- |
| 状态 | building |
| 当前阶段 | G3 verification |
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

Publication is pending clean-candidate CI-mode validation and exact-main CI.
