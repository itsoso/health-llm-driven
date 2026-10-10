# Independent bridge review and verification evidence

## First fixed application review — NO-GO

Reviewer: independent platform agent `app_security_review`, read-only.
Reviewed commit: `4892c41b1e8cd19ec5262ff5dc91b518316fa6b0`.

1. P1: `form-action 'self'` prevented actual Chromium from following the consent
   POST's OAuth redirect to the registered external callback. A synthetic exact
   callback-origin positive control succeeded. Unit response assertions did not
   detect this browser behavior.
2. P2: revoked long-lived grants remained in the 20-grant capacity pool until
   expiry, preventing future consent after repeated normal revocation.
3. P2: OAuth authority changes and Health reads lacked private audit evidence.

The reviewer independently ran the 73-test application suite and a real MCP SDK
stateless tools/call probe. Those passed but did not override the findings.
No production traffic, secrets or real medical data were used.

Corrections: permit the registered callback origin in CSP with constrained host
syntax; prune revoked/expired grants while denying their tokens; add bounded,
encrypted generic audit events for consent/token/replay/revoke and Health reads.
New regression tests cover callback policy, repeated revoke/reconsent capacity and
audit absence of tokens, arguments and returned health content. The prior reviewer
retested actual Service.app headers in Chromium: the registered callback was
reached and the unregistered callback remained blocked. All 25 revoked access and
refresh tokens failed without harming the new grant; revoke-all/reconsent also
worked. Targeted OAuth/Health/server verification: 36 passed.

## Combined fixed review — GO for draft PR only

New independent read-only reviewer `combined_security_review` reviewed the entire
`fa4703060594472933bca35553c9de05c5016cd6..f7785ec68d604188afe2a1f7a9d1a68f85d480ea`
diff. No new P1/P2 issue was identified for publishing the explicitly dormant
candidate as a draft PR. This is not deployment or activation approval.

The reviewer independently ran service, installer, bootstrap and release-server
suites: 375 passed. Owner/destination pinning, encrypted atomic state, process
lease, rotation/replay/revoke, generic Slack signal, uncertain sends and durable
release-history gates were examined. The sole formatting observation (extra blank
EOF in installer tests) was removed without changing behavior.

Deployment blockers: exact current-main/full CI and release ownership; verified
external canonical bootstrap and installed executor with PR252 trust concerns
resolved; cross-family capstone; actual Linux/systemd containment; reviewed
secret-entry, activation, removal and interrupted-install recovery; personal owner
handoffs and real closed-Mac/restart/revoke acceptance.

## Verification before combined review

- Application: 76 passed, `.venv/bin/python -m pytest -q services/neo_wechat/tests`.
- PostgreSQL 17 disposable UTF-8 cluster, private temporary Unix socket, no TCP:
  76 affected backend tests passed; OAuth provider coverage 92%. No real records.
- Frontend consent: 20 tests passed and `npx tsc --noEmit` passed.
- Deployment author: 339 affected tests passed, including 38 bridge installer
  tests. Extended deployment suite earlier: 357 passed. Mac tests do not establish
  Linux systemd sandbox behavior.
- Initial CI-mode combined run from repository root failed one existing migration
  relative-path test; rerun from required backend cwd: 148 passed, 1 skipped.
  Final run after the new application regressions: 151 passed, 1 skipped.
- Complete hash-locked service dependency audit: 17 packages, no vulnerabilities.
  Local audit used `--disable-pip --no-deps` after the auditor's temporary ensurepip
  subprocess aborted; the full pinned lock was still audited. CI retains hash checks.
- JavaScript vendor syntax, System Map canonical graph/mobile-nav/doc-drift,
  dossier consistency and whitespace checks passed before final documentation edits.
- Fresh tracked-file high-confidence secret scan passed. LLM change classifier
  passed with no live LLM evaluation required; it does not replace the cross-family
  review requirement.

## Cross-family capstone — not run

The repository product-pipeline G3 contract requires a cross-family high-risk
capstone. Automatic approval review rejected sending a private source packet to
the installed Claude CLI, because that external destination was not specifically
authorized. The command was not executed and neither source packet nor output was
created. Do not retry through a different route or record platform same-family
review as this capstone. The owner briefly approved that exact destination at
07:04 UTC, then explicitly cancelled Claude at 07:04:48 before any retry was
initiated. No Claude process or source transmission was initiated by this task
during that interval. Do not use Claude or another external provider as a workaround.

`docs/specs/product-pipeline-contract.md` G3 still requires a cross-family capstone
for this high-risk change. The available independent platform reviewers are in
the same model family. The inspected contract and product-pipeline/safety/deploy
governance document no applicable waiver or alternate-family provider procedure.
Therefore current independent reviews and synthetic tests remain useful evidence
but do not satisfy that requirement. Any candidate-specific exception requires
an explicit governance-owner decision, recording the unmet requirement and residual
risk; no policy was modified and no exception is claimed here.

## Production evidence and limits

Read-only strict-host SSH checks observed production
`346035f78b362804df06e1524099f87294286ef6` and the four main services active at
05:56–06:00 UTC. Release-lock absence was only a snapshot. No installation,
service restart, nginx change, secret creation, QR scan, OAuth grant or Slack
message was performed. No G5 or G6 pass is claimed.

The bounded installer is dormant-only. Approved secret-entry tooling, reviewed
activation/removal/recovery, Linux sandbox verification and live end-to-end
acceptance remain work; this record is not a completed production delivery.

## Local continuation after draft PR280

PR280 at `3b834ea74f4f3c47c9af9bc0687dd654bd91ab74` passed full CI run
`38031204452`. Current main was rechecked as `637520e25` before the continuation.
The following additions require a fresh fixed-commit review and their own CI:

- Health revocation now persists `revocation_pending` before remote I/O, drops
  local access immediately, blocks relinking, and retains only the encrypted
  refresh token needed for explicit owner retry after an uncertain response.
- Offline provisioning validation and password hashing accept synthetic inputs
  only in tests. There is no secret-entry CLI, environment reader or writer.
- Pure lifecycle evidence validators fail closed on missing provenance, changed
  leases and ambiguous finalization. They provide no execution authority; the
  current installer does not yet emit their step records.
- The native systemd probe runs solely on an explicitly disposable Linux runner,
  remapping sensitive paths to public synthetic fixtures. It requires actual
  positive and negative controls plus cleanup before PASS. Mac reports
  UNSUPPORTED; actual systemd 249, production identities and egress remain unproven.

Local service, provisioning, lifecycle, portable Linux contracts and installer
tests: **214 passed**. Secret scan and dossier consistency passed. No production
action or private secret was used. The owner-operated SSH hidden-input UI choice
is a pending G2 decision; provisioning/activation writers remain stopped.

Fresh independent reviewer `continuation_security_review` reviewed fixed commit
`6fd5e5d44e142d127a1a216e927869b8758acd2c`, independently passed the 214 tests,
and found no P1/P2 issue: GO for updating the draft and ephemeral CI only. The
recommended dedicated Ubuntu 22.04 job now requires both PASS and an observed
systemd 249; release-invariants depends on that job. Newer systemd evidence alone
does not satisfy this check.

Concurrent release run `38031474956` for `637520e25` ended in failure at
06:42:57 UTC. Its server launcher reported “evidence retained, retry forbidden”
and receipt validation failed. This is not a successful production receipt;
the operation and lease must be reconciled through the original release owner.

## Native systemd 249 defect and corrective boundary

Runs `38032903850` and `38033130316` failed static probe validation. The probe's
ineffective oneshot `RuntimeMaxSec` was removed, retaining actual start/stop
timeouts. Static validation now uses exact candidate bytes and synthetic dependency
stubs in an isolated unit load path, rejecting all diagnostics; actual host startup
is independently exercised. Superseded runs were cancelled after failure evidence
was retained, never marked successful.

Run `38033498010`, fixed `ee076911e`, passed static validation then demonstrated an
actual protected worker could open an IP listener under `SocketBindDeny=any` on
systemd 249. This is a security finding, not a test waiver. Upstream issue #30556
and fix 736b774 describe the empty allow-map failure; BPF-install failure is another
fail-open path. The log alone does not distinguish those causes. A revised boundary
uses systemd socket activation plus seccomp denial of both bind and listen, with
the inherited AF_UNIX listener validated before private inputs. New fixed review
and actual native tests are required; no previous draft GO covers the new bytes.

The revised seccomp deny set also contains io_uring_setup, io_uring_enter and
io_uring_register. This closes the asynchronous equivalents documented by
[liburing bind](https://man7.org/linux/man-pages/man3/io_uring_prep_bind.3.html)
and [liburing listen](https://man7.org/linux/man-pages/man3/io_uring_prep_listen.3.html).
Protected native calls must fail with permission errors. If an unprotected control
is also denied by the host, that particular io_uring observation is explicitly
not attributed to the service filter. Existing direct bind/listen positive controls
remain mandatory.

Updated local CI-mode backend and bridge integration: 171 passed, 1 skipped.
The first sandboxed Mac attempt could not create fixture sockets and omitted the
repository PYTHONPATH for subprocess tests; the canonical-environment rerun with
synthetic-only socket permission passed. Deployment/installer/provisioning/lifecycle
regressions before the io_uring addition: 443 passed. Linux evidence remains separate.
