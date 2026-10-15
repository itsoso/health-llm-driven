# Web publication without backups

| Field | Value |
| --- | --- |
| status | shipped |
| current_stage | S7 publication verified; authenticated UI acceptance unverified |
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

## G3 verification

Initial no-backup tests failed before the entry existed. Frontend regression
passed 97 files / 549 tests, with one existing skip. System Map check and
production build passed. Focused release regressions passed 145 tests, with two
native checks deferred to Linux CI. The final frozen cb3ef7b8e local CI-mode
release-invariants run passed 3808 tests, 23 skipped, and 84 subtests (exit 0).
An earlier concurrent-edit run failed and is retained; it is not counted as a pass.

Exact cb3ef7b8e CI [38677863367](https://github.com/itsoso/health-llm-driven/actions/runs/38677863367)
passed, including the real Linux same-device bind mount and artifact build.
While publication was pending, another session advanced main to
`2fbc264e781a62f4b30895bb268cf31db30ffc53`. Its frontend, scripts, workflow trees
and deploy.sh are identical to cb3ef7b8e; the backend changes are outside this
Web-only deployment. Exact final CI
[38679141422](https://github.com/itsoso/health-llm-driven/actions/runs/38679141422)
passed. A new artifact was built and verified for that exact publisher SHA;
the old cb3ef7b8e artifact was left unconsumed.

## G4 review

Independent review rejected candidate 03be013b346b0c5dbea4eb018676732250cc4f93:
same-device Linux bind mounts can evade device/is_mount checks during recursive
deletion. The correction reads the kernel mount inventory, fails closed on
unavailable or malformed data, and rejects mounts at or below each artifact
root, including a fresh check at the deletion boundary. Seven new regressions
failed before the fix. Independent review gave GO to cb3ef7b8e and then to the
fixed 2fbc264e Web-only publication scope. This is not approval of the unrelated
backend increment.

## G5 deployment and G6 live evidence

Publication completed at 2026-10-15 12:32 Asia/Taipei readback:

- Publisher: `2fbc264e781a62f4b30895bb268cf31db30ffc53`.
- Frontend tree: `ba1a2c2aadef1789268d37b0e9603d2068ebfeaf`.
- Operation: `b42b10d8c222447ce79f16c0b64a1b04`.
- Terminal server receipt: `FRONTEND_SUCCEEDED`, policy `no-backup-v1`,
  `backups_digest={}`. The original receipt and all proof hashes are retained.
- Artifact digest: `d2097cc96e7cc96b3f22027f1d93368241512217d3e05261de6771b7faa1c52e`.
- Running BUILD_ID changed from `1v1RWWy0CW1TPrfU4o2YT` to
  `Nd_XFu1dD9V2J6vXEZCLm`; no stale-layout overwrite was found in source.
- Durable completed.json was read back independently after execution. Frontend
  and backend are active/running, NRestarts=0, and the business lease is absent.
- Public `/agenda?navigation=week`, `/ai-assistant`, and `/api/v1/health`
  returned HTTP 200. All 21 referenced JS/CSS assets match live artifact hashes.
  Public assets contain the 218px LifeNav sidebar, tightened margins, and the
  left-aligned assistant brand/history layout.
- Browser verification reaches login without an authenticated session. The
  authenticated production visual/user-flow check remains unverified; HTTP and
  asset checks do not substitute for it.
- Backend remains `c662a18800a1157a50414522cc0084942e862a9b`, with its prior
  SUCCEEDED receipt. This operation did not deploy the newer backend increment.
- Prior production iOS OTA at c662 remains SUCCEEDED: runtime 1.3.5, update
  `01a13d3f-4008-7d7b-ba0b-a4538831ad7c`, group
  `c4684fa6-51fd-4770-a00f-0389729bc49e`. Agent home and conversation menu include
  the LifeNav entry. No redundant OTA was issued for this Web-only change;
  individual-device loading and simulator UI acceptance remain unverified.

G5: PASS. G6: live publication and assets verified; authenticated UI acceptance
remains explicitly unverified. No product data, raw health payloads, or secrets
were used as acceptance fixtures.
