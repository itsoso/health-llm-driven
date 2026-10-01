# Persistent release key — implementation dossier

| 字段 | 值 |
| --- | --- |
| 状态 | shipped |
| 当前阶段 | S7; release credential and GitHub transport verified |

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

## Historical production migration attempt

当时结果: BLOCK. Resolved by the subsequent credential and transport recovery below.

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

At the time of that attempt, this operational receipt was local and uncommitted;
it did not change the CI-bound release revision or claim migration success.

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

## Replacement installation evidence

- Candidate `30ac1c67be7b2df79363ac7509f70f8a56ce4834` is on main; exact CI
  36857310949 passed, as did local release preflight. Independent reviewer approved
  the source-identical candidate and conditional canonical rotation.
- Server fetched the canonical GitHub repository at that SHA. Full retirement
  history, clean source, fresh candidate, known activity and idle checks passed;
  b997 workspace was NEVER_STARTED.
- The first rotate attempt stopped before intent creation because a previous
  read-only executor import by this agent had produced a Python cache. Old cloud
  and loopback authorizations were already revoked and loopback private key removed.
- Read-only diagnosis isolated the failure to the exact library inventory. The
  sole root-owned, regular, single-link Python 3.10 cache matched current canonical
  source by header and compiled code. Its SHA256 was
  `55f379728c25f3b272542a6c1c6400d9a27a57f46012980622e8f8af66f8acaa`.
- Independent reviewer approved preserving the attributable cache outside the
  installation. It was moved to the candidate bootstrap `readonly-inspection-cache`
  directory with parent fsync. No retirement intent or archive existed; all
  pre-intent checks passed again. Subsequent Python inspections use `-I -B`.
- Canonical rotate returned INSTALLED for 30ac1c67b, retiring b997. Readback shows
  expires_at=0 and the replacement fingerprint. Strict dedicated-key SSH returned
  `CHECKED` for this exact SHA, including GitHub and loopback readiness.
- GitHub reports the user updated REVA_RELEASE_SSH_KEY at 2026-10-01T11:41:38Z.
  Actual environment-secret verification in Trusted release 36857918284 failed
  with `error in libcrypto` before server authentication. Backend was skipped;
  no deployment claim was consumed. The same local replacement private key passed
  strict SSH CHECKED, isolating this blocker to the GitHub secret's stored format.
  Runtime trees are unchanged from production 644b6a2de.
- Reopened the exact GitHub Secret edit form for user entry of the full private
  file. No private bytes were read into conversation or entered by this agent.
- This evidence was retained locally during credential handoff to avoid moving
  main underneath the bound candidate. It is now included in the documentation closure.

## GitHub credential confirmed; network remains blocked

- User confirmed replacement Secret submission; GitHub metadata updated at
  2026-10-01T11:56:05Z. Main and exact CI remain bound to 30ac1c67b.
- Trusted release 36858579773 successfully authenticated to the forced-command
  server with the Environment Secret. The previous libcrypto/publickey errors
  are gone. Server readiness then failed before deployment; backend was skipped.
- Read-only installed-executor checks (`-I -B`) passed frontend/OTA history,
  deployment window, local-only loopback configuration and Python metadata.
  The exact GitHub ls-remote failed with exit 128: transfer remained below
  1024 bytes/sec for 30 seconds.
- Certificate-verifying HTTP/1.1 probes to both DNS-returned GitHub addresses
  also timed out. No DNS, TLS, source, timeout or authorization guard was changed.
- Credential recovery and permanent authorization are verified. Backend delivery
  remains blocked by server-to-GitHub networking; no release workspace or business
  lease was present before this unconsumed readiness attempt.

## GitHub transport recovery via base — 2026-10-01

- User explicitly authorized repairing the GitHub timeout and using
  base.executor.life as a proxy. Production TCP and TLS handshakes succeeded but
  HTTP stalled; API/raw GitHub hosts worked. The identical Git info/refs request
  completed with HTTP 200 in 0.29 s from base. This locates the failure in the
  production-to-GitHub HTTP path; it does not prove which network device caused it.
- Base resolves to 47.237.191.17. SSH port 22222 was verified using its existing
  exact IP:port known-host entry. The old hostname-only entry differs and was not
  replaced or used to disable validation.
- Health now runs `reva-github-relay.service` as a dedicated unprivileged user,
  forwarding only `[::1]:443` to base's `github.com:443`. Systemd grants only
  CAP_NET_BIND_SERVICE, enforces read-only system/home protection and network
  address allowlists, and supervises reconnect/startup. A dedicated identity stays
  on health; no admin or release private key is copied to base.
- Base's fixed root-owned `/etc/ssh/reva-github-relay/authorized_keys` contains
  only the new key, restricted to source 39.98.206.178 and target github.com:443.
  `/etc/ssh/sshd_config.d/90-reva-github-relay.conf` requires publickey auth,
  allows only local TCP forwarding, disables remote/streamlocal/agent/X11/tunnel
  forwarding, and sets MaxSessions=0 and ForceCommand=false. Both syntax and
  effective `sshd -T -C` settings were verified before reload.
- The previously retired same-name base account had expiry 1970-01-02. Its aging
  state was preserved in root-only `account-aging.before.txt` alongside the new
  relay configuration, then expiry removed. Historical retired key/config remain
  inactive and untouched; password authentication and shell sessions stay denied.
- HTTPS through the relay passed three times in 0.64–0.74 s with GitHub certificate
  verification. Shell, remote forwarding, other host and other port actual probes
  all failed as intended. No public proxy listener was added.
- `/etc/hosts` changed only `github.com` from 20.205.243.166 to ::1. Exact original
  bytes are backed up at `/var/backups/reva-github-relay-20261001/hosts.before`.
  nscd was invalidated; AI_ADDRCONFIG resolves GitHub solely to ::1. Exact isolated
  gate Git arguments passed three times in 1.05, 2.00 and 1.53 s. Stopping the
  relay made Git fail closed; restarting it restored Git. Service enabled at boot.
- Strict dedicated release-key `check 30ac1c67b...` returned CHECKED. Backend and
  nginx PIDs remained unchanged, health HTTP 200, no business lease/workspace.
- Independent reviewer: operational GO based on these producer receipts (no
  independent remote rerun). Resuming the already authorized backend workflow.

### Transport rollback

Restore the exact hosts backup only after confirming the current hosts differs
solely by the intended GitHub line; preserve any concurrent edits. Invalidate nscd,
then stop/disable `reva-github-relay.service`. On base remove only the newly added
authorization/config after checking their bytes, run sshd -t and reload ssh, and
restore account expiry with `chage -E 1970-01-02 reva-github-relay`. Preserve the
historical retired files and rollback evidence. This restores the prior direct
network path, including its known timeout; it is not a repair of that upstream path.

## G5/G6 — final production verification

裁决: PASS

- Trusted release 36861632116 completed SUCCESS: exact source/CI preflight,
  actual GitHub Environment Secret readiness and backend deployment all passed.
  iOS/TestFlight were intentionally not targeted.
- Server receipt is SUCCEEDED for `30ac1c67be7b2df79363ac7509f70f8a56ce4834`;
  production Git HEAD matches. Runtime transaction committed, health score 60/60
  passed, and the business lease was removed.
- Backend, Celery worker/beat and GitHub relay are active with NRestarts=0 after
  deployment. Backend local /health returns HTTP 200; public HTTPS
  health.executor.life/api/v1/auth/me returns expected unauthenticated HTTP 401
  with certificate validation. A stale health-api.executor.life hostname from
  skill guidance did not resolve and was not used as production proof.
- DB backup/restore/offsite work was skipped by the repository's explicit user
  preference (docs/governance/deploy.md, DEPLOY_DATABASE_BACKUP defaults to 0).
  No new DB backup is claimed. Env backup, rollback schema compatibility, managed
  migration checks, runtime transaction and health gates ran through deploy.sh.
- This later documentation closure records the verified 30ac1c67b deployment;
  it does not rebind its authorization or claim that the documentation commit was
  deployed. Permanent key and proxy are installed; the underlying direct GitHub
  network path remains unreliable and GitHub access depends on the relay.
