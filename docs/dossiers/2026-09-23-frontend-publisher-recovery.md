# Frontend publisher pre-install failure recovery

- Date: 2026-09-23
- Owner/controller: Health Harness, incident mode; safety-gate overlay.
- Run: `docs/_generated/harness-runs/8391e1daf4f9.jsonl`.
- Scope: separately authorized recovery of failed frontend rebuild
  `ada1af2bf76245ecae376eadad3f6c63`, npm startup correction, then gated backend
  deployment and compatible Mobile OTA. Does not reset the exhausted earlier
  monthly-journey/read-intent runs. Links: [journey](2026-09-22-monthly-journey.md),
  [app fixes](2026-09-23-read-intent-false-blocks.md).
- User explicitly answered “允许” to controlled failure retirement/recovery and
  subsequent deployment/OTA. No manual lock deletion, unknown-write retirement,
  account reset, new native signing or App Store submission is authorized.

## Evidence and gates

- Production still `a1e39bbfab675ac7f52227b33d4673f7bc3ccf87`;
  original audit has only before/build.log/failed/intent, no install-started.
  Exact transient build unit failed, exit 1, MainPID 0, empty ControlGroup;
  backend/worker/beat active with original PIDs and restart count 0.
- Publisher `7e6313f85c06028d64f626a3c3e9e10286d47b89` CI
  `35839735072` is green. Current local app fixes are four unpushed commits.
- Root cause: npm userconfig/globalconfig both point to `/dev/null`; npm rejects
  duplicate config source before installing dependencies. Prior sandbox test
  covered isolation but not real npm configuration startup.
- Plan: RED real npm config-startup test; distinct empty isolated configs; bounded
  pre-install-only closure preserving original failure, artifacts and lease in
  private durable audit; independent fixed-commit G4; full exact remote CI; only
  then controlled recovery and release. Any unknown phase or evidence drift blocks.
- External debugging/TDD/verification skill files unavailable; follow repository
  evidence-driven RED/GREEN rules. Disabled superpowers is not loaded.
- G3/G4/G5/G6: pending. No new production mutation or release claimed.

## Implementation / local evidence

- Real npm 10 startup regression first reproduced the exact double-loading error;
  GREEN after keeping user config `/dev/null` and selecting a distinct absent
  config inside fresh private HOME. Native Linux sandbox test now executes npm
  config startup with the actual production environment and deny list.
- Pre-install closure and protected-stdin acknowledgment implemented. Complete
  old code digest and exact error classify the failure; private lease copied
  durably then moved without overwrite on its original filesystem. No original
  audit/artifact deletion, service restart or credential rotation in closure.
- Independent design review identified tmpfs-vs-disk rename, stale frontend PID
  claims and fsync-uncertain receipt hazards; all addressed in the implementation.
- Focused release/recovery suite: 326 passed, 1 Linux-only skip. Added frontend
  descendant process probes also pass (9 cases). Full release CI-mode integration
  is running; exact remote Linux/CI and fixed-commit G4 remain pending.
- System Map selector does not index this script. Per policy, checked direct
  source/tests and ran full System Map/doc-drift verification: PASS.
- PR #252 remains separate/unmerged. Server recovery uses canonical root staging;
  its safety verdict does not authorize a developer-workspace OTA publisher.
  OTA trusted environment and runtime compatibility must be separately proven.
