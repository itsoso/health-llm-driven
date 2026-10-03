# Audited frontend publication with an unchanged backend

| Field | Value |
| --- | --- |
| 状态 | implementation in progress; production unchanged |
| 当前阶段 | G1 admitted; G3/G4/G5/G6 pending |
| Controller | health-harness-orchestrator |
| Overlay | safety-gate |

## G1 scope and authorization

The user approved a reviewed frontend-only publication entry on 2026-10-03,
following PR review, exact CI and operator preflight. Preserve the deployed
backend revision, processes and configuration. No backend deployment, native
release, credential rotation, actual OAuth grant or data-permission expansion is
included. Existing same-tree rebuild requirements remain unchanged.

Base: `b6bfece100f6c7e7a94a1526331abdce217f2284`. Existing dirty checkouts are
preserved; implementation uses an isolated branch. Inspected production remains
`30ac1c67be7b2df79363ac7509f70f8a56ce4834`, with its original successful backend
receipt and precise historical CI. Public and internal `/connect/health` currently
return 404 while `/privacy` returns 200. Source includes the connection page;
availability is separate from successful OAuth authorization.

## G2 design

Add a separate canonical frontend operator for the existing hardened systemd
service. Bind current main publisher SHA, requested complete frontend tree,
original successful production SHA and unique operation ID. Build only verified
frontend blobs in the existing isolated build sandbox. Switch frontend artifacts
only, preserving old artifacts and durable audit. Unknown outcomes retain their
lease and block later releases; no retry or automatic rollback.

The prior production and current main frontend differ only in three dependency
mitigation files from `474c446c73eacb71d702af0a5f9de4296b3c06af`. The independent
final-candidate review must include that braces guard. Backend and Mobile changes
on main are neither copied to production nor activated by this operator.

## G3 / G4 verification

Pending behavioral regressions, release-invariants CI-mode suite, independent
fixed-commit safety review and exact final main CI. No passing gate is inferred
from earlier SHAs.

Initial independent review of `c8297e332c8fdd5a6a4d67f5c72a6b2d7dc6e46c`
returned NO-GO: old artifact metadata validation happened after frontend stop and
partial switch. The repaired operator validates both fixed live bundle trees
during inspect and immediately before stop. After confirmed stop, it binds frozen
old digests before any rename and compares the retained backups. Synthetic
invalid cache/link/hardlink/write-permission regressions prove zero service stops
and zero artifact switches. A new fixed-candidate independent rereview is pending.

Independent rereview of `8a2aa82c13e0b1ee81e592aae56b4af600c50a43` returned
G4 GO, including the effective braces mitigation. After Mac reconnection the
reviewer independently reran 56 targeted tests, all passing. Draft PR #275 is open.
The retained sandboxed full run ended with 882 passed and a privileged-mode test
failure: its synthetic setuid/setgid bits were stripped by the local sandbox.
An unrestricted synthetic probe preserves those bits; the full suite is rerunning
without changing the test or validator.

PR Linux CI exposed a synthetic ancestor mismatch in the new live-metadata test:
the test's temporary directory was world-writable `/tmp`, whereas the production
path requires protected `/opt` ancestors. The fixture now models those ancestors;
a malicious ancestor regression still exercises the unchanged real validator.
Live readback also showed a stable historical frontend restart count of 1518.
The operator now validates stable PID/start-time/counter across the fixed restart
window, retaining the actual counter instead of requiring zero or resetting it.
Updated fixed-candidate review and exact CI remain required.

## G5 / G6 release and acceptance

Pending reviewed canonical staging, matching read-only evidence digest,
publication receipt, unchanged backend proof, and internal/public connection-page
acceptance. Do not create an OAuth grant during availability verification.

## Work log

Local workflow ledger: `docs/_generated/harness-runs/6f1e9c5f9ee7.jsonl` (ignored,
not committed). Current GitHub Actions has no frontend target; publication uses
the existing administrative channel and canonical server staging, without new
credentials or RPC permissions.
