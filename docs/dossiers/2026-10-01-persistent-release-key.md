# Persistent release key — implementation dossier

| 字段 | 值 |
| --- | --- |
| 状态 | blocked |
| 当前阶段 | release recovery; G5 blocked pending credential repair |

## G1 — maintenance admission

裁决: PASS

The user explicitly requested removal of mandatory eight-hour key renewal,
approved implementation and subsequently requested deployment. This is bounded
release-infrastructure maintenance with no Health OS object or medical behavior change.

## Scope

- Request: remove mandatory eight-hour renewal and allow reuse of the dedicated
  release key. Preserve version, CI, command, audit and failure boundaries.
- Baseline: `644b6a2ded140d8eff45d6a4e063b9575103768c` (fetched origin/main).
- Initial scope was source-only. The user subsequently requested deployment on
  2026-10-01, authorizing delivery of this change and migration of the release
  authorization. No unrelated application or mobile release is included.
- Controller: `health-harness-orchestrator`; overlay: `safety-gate`.
- Trace: local ignored `docs/_generated/harness-runs/8b23150f7c2a.jsonl`.
- Spec: [Persistent release identity](../specs/active/2026-10-01-persistent-release-key.md).

## Evidence

- RED: new lifetime tests failed on the original behavior (5 failures, 4 passes).
- Initial GREEN: bootstrap and server suites passed, 233 tests, before additional
  CLI and persistent-loopback cases were added.
- System Map check passed; these scripts are not indexed by the path selector,
  so conclusions are based on direct source and adjacent tests.
- Expanded regression: **815 passed, 9 skipped, 84 subtests passed**, exit 0,
  361.45 seconds. The skipped cases require isolated Linux SSH/systemd or a
  dedicated PostgreSQL integration URL; these are not claimed as locally passed.
- Interpreter: `/Users/liqiuhua/work/personal/health-llm-driven/.venv/bin/python`;
  invocation: `-m pytest --noconftest --no-cov -q --tb=short` over the bootstrap,
  trusted release server/gate/workflow/receipt, trusted OTA server/OTA, TestFlight,
  contained/review-maintenance/partial-Laya/native retirement, lost-closure
  acknowledgment, admin-key pause, frontend rebuild and review-reset test modules.
- Final `./scripts/system-map-check.sh` and `git diff --check`: passed.
- Reviewed tracked diff SHA256:
  `aeadba4997adf460bbc2578989b8c5e9531a9b9f8c4f2667d4efb2410ad6a070`.
- Independent `release_key_safety` reviewer: **G4 GO for source changes** on the
  above fixed diff. No blocking finding. Reviewer independently inspected source,
  tests and documentation; the expanded test receipt is producer evidence, not
  a second test execution. This is not a production migration or release GO.
- Source implementation complete; release preparation now in progress in the isolated worktree.

## Release boundary

Source completion does not recover the expired production authorization. After a
separately authorized reviewed release, the operator must migrate through canonical
bootstrap rotation; unchanged cloud key means no GitHub Secret replacement needed.
Local macOS verification does not substitute for Linux native gates or exact-SHA CI.

## G5 — production migration attempt

裁决: BLOCK

- Committed and pushed `cec484a25044fca46203894ed15c2792c42f366e` to GitHub main.
- Exact CI passed: https://github.com/itsoso/health-llm-driven/actions/runs/36847512724.
- Local release preflight passed, including secret scan, System Map, dossier,
  generated API types and 29 release contract/scope/lock tests.
- Independent reviewer reaffirmed code GO on the fixed commit and conditional GO
  for canonical bootstrap migration with the existing cloud key.
- Server canonical Git fetch timed out after 120 seconds before obtaining source.
  The server pinned github.com to 20.205.243.166. A DNS-returned alternate passed
  certificate-verified HTTP probes, but isolated Git requests still timed out,
  including after explicit nscd cache invalidation. No TLS/CI/source guard relaxed.
- Original `/etc/hosts` was restored byte-for-byte and host cache invalidated.
  A verified root-only compressed backup remains in the candidate staging parent.
- No revoke/rotate/deployment dispatch occurred. Policy remains bound to
  `051ee281f8247d162bcdef7b3f93fdf51930c94c` with its original expired deadline.
- Final readback: production `644b6a2ded140d8eff45d6a4e063b9575103768c`, backend
  active, original PID unchanged, NRestarts=0, local health HTTP 200, no business lease.
- Resume after canonical Git connectivity is restored; inspect the retained
  incomplete candidate staging directory before retrying. Reverify current main,
  exact CI and live operation state before any credential mutation.

This final operational receipt is local and uncommitted; it does not change the
CI-bound release revision or claim production migration success.

## Subsequent live verification — 2026-10-01

- Refreshed origin/main is `b9972b1602d1f6620119486cf74792e8aab842c7`; its only
  change after cec484a is an unrelated biomarker dossier. Exact CI 36854655980 passed.
- Another operation has completed retirement of 051ee281 and installed b9972b160
  with `expires_at: 0`, preserving the cloud public-key fingerprint and recording
  `cloud_key_reused: true`. This continuation observed that migration; it did not
  execute it.
- Installed executor digest matches policy and the clean canonical b9972b160
  source. Cloud authorization is unique, forced-command/restrict, without expiry.
  The installed executor's local-only loopback validation passed.
- GitHub run 36855172706 failed before dispatch: SSH private key could not be
  parsed (`error in libcrypto`). Backend and TestFlight jobs were skipped.
- Fresh installed-executor readiness probe also failed its strict GitHub
  `ls-remote` (exit 128). Network readiness remains unverified.
- Business lease absent, backend active, health HTTP 200, application source still
  644b6a2de. Permanent authorization is installed; end-to-end release is BLOCKED.
- Browser opened the exact REVA_RELEASE_SSH_KEY update form for user handoff;
  no secret value was read, entered or submitted by this continuation.

## Dedicated cloud key replacement candidate

- User generated a replacement Ed25519 key and supplied its public fingerprint:
  `SHA256:UQqFsX/wkqqDMNhFUVFTYUrIo25BVi7MgmF1C3ecFGw`.
- Local read-only verification confirmed that the private key derives the supplied
  public key and has mode 0600; no private material was printed or committed.
- This documentation revision provides a fresh candidate for canonical rotation
  away from b9972b160. No runtime code changes are included.
- Before mutation: exact candidate CI, independent review, canonical server source,
  no active operation/lease, and retained retirement history must pass. Then revoke
  the current authorization, remove only its loopback private key, and invoke the
  canonical rotate entry with the replacement public key and expires_at=0.
- GitHub secret entry remains a user handoff. Full recovery requires a successful
  check through the dedicated key and the GitHub workflow; generation alone is
  not evidence of server authorization or deployment.
