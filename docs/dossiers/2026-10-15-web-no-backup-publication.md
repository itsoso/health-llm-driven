# Web publication without backups

| Field | Value |
| --- | --- |
| status | shipping |
| current_stage | S5 implementation and G4 review |
| Controller | health-harness-orchestrator |
| Overlay | safety-gate |

## G1 Scope admission

裁决: PASS. Deliver the existing Web layouts under the user's continuing
no-backup policy. No new product behavior, personal data access or health writes.
The release infrastructure change remains subject to independent G4 review.

## Implementation and evidence

Baseline: c662a18800a1157a50414522cc0084942e862a9b.
Trace: docs/_generated/harness-runs/1500831b458b.jsonl.

The user requested continuing the remaining Web delivery after backend and iOS
OTA succeeded. The current Web bundle is older than the compact LifeNav code.
Legacy frontend publishers are frozen because they create old-artifact copies.

Implement a separate explicit no-backup publication entry. Consume an already
verified artifact, hold the existing launcher/build/business locks, verify the
installed history consumer, stop Web, replace only fixed compiled artifact
directories, and verify live digest and pages before releasing the lease.
Never create old-artifact copies or automatically roll back. Any uncertain
failure retains evidence and blocks further release. Keep legacy publishers
and historical recovery entrypoints frozen. Version the new receipt and update
the shared history consumer while preserving all legacy history checks.

The earlier unmerged assistant branding patch is included: brand aligned to the
history rail, accessible history toggle, and no duplicate desktop new-chat button.
The compact LifeNav layout is already in the baseline and awaits Web publication.

G3: initial no-backup tests failed before the new entry existed. Focused helper
and history regressions passed after implementation; broader release integration
is running. Frontend regression passed 97 files / 549 tests, with one existing skip.
System Map check and production build passed.

G4 rejected candidate 03be013b346b0c5dbea4eb018676732250cc4f93: same-device
Linux bind mounts can evade device/is_mount checks during recursive deletion.
The correction reads the kernel mount inventory, fails closed on unavailable or
malformed data, and rejects mounts at or below each artifact root, including a
fresh check at the deletion boundary. Seven new regressions failed before the
fix; focused publisher/history/artifact/CI-contract tests then passed. CI also
runs an actual same-device bind mount in a disposable private Linux namespace;
that native result remains pending. The corrected candidate requires G4 review.

Exact-SHA CI remains pending. GitHub CLI returned HTTP 401 at startup;
the user was asked to restore authentication while local implementation proceeds.
No production mutation has been performed in this continuation.
