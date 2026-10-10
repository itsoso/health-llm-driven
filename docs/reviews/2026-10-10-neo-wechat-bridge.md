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
audit absence of tokens, arguments and returned health content. Targeted browser
retest and a new independent fixed combined-diff review are pending.

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
  Final run after the new application regressions is pending.
- Complete hash-locked service dependency audit: 17 packages, no vulnerabilities.
  Local audit used `--disable-pip --no-deps` after the auditor's temporary ensurepip
  subprocess aborted; the full pinned lock was still audited. CI retains hash checks.
- JavaScript vendor syntax, System Map canonical graph/mobile-nav/doc-drift,
  dossier consistency and whitespace checks passed before final documentation edits.

## Cross-family capstone — not run

The repository product-pipeline G3 contract requires a cross-family high-risk
capstone. Automatic approval review rejected sending a private source packet to
the installed Claude CLI, because that external destination was not specifically
authorized. The command was not executed and neither source packet nor output was
created. Do not retry through a different route or record platform same-family
review as this capstone. Explicit destination authorization is a remaining gate.

## Production evidence and limits

Read-only strict-host SSH checks observed production
`346035f78b362804df06e1524099f87294286ef6` and the four main services active at
05:56–06:00 UTC. Release-lock absence was only a snapshot. No installation,
service restart, nginx change, secret creation, QR scan, OAuth grant or Slack
message was performed. No G5 or G6 pass is claimed.

The bounded installer is dormant-only. Approved secret-entry tooling, reviewed
activation/removal/recovery, Linux sandbox verification and live end-to-end
acceptance remain work; this record is not a completed production delivery.
