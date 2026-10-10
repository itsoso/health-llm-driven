# Dossier: independently hosted owner WeChat bridge

| Field | Value |
|---|---|
| slug | neo-wechat-bridge |
| Created | 2026-10-10 |
| 当前阶段 | S5 implementation |
| 状态 | building |
| Branch | codex/neo-wechat-health-bridge |

## User request

> 1、授予读取健康数据的权限 2、期限3650天  其他没问题 开干

Delegated outcome: independent Health-hosted single consumer, private generic Slack
wakeup, separate OAuth MCP, pinned owner private-text replies and owner health reads.
User explicitly authorizes code/tests/review/protected PR/CI/deployment; personally
owned secret entry, QR scan and OAuth consent are handoffs, not implicit agent actions.

## Discovery

Clean origin/main base `fa4703060594472933bca35553c9de05c5016cd6`; dirty original
checkout preserved. Existing Site transports inspected without secrets. Existing
`backend/app/api/remote_health.py` exposes only sleep/diet/exercise read projections.
`remote_health_oauth.py` has 600-second access, 30-day grants and owner website consent.
Health consent needs a dedicated client owner pin and NEW grant duration configuration.
No bridge imports business models, sessions or environment files.

Strict SSH at 05:56–06:00 UTC: production `346035f78b362804df06e1524099f87294286ef6`;
health-backend, celery-worker, celery-beat and backend socket active; business lease
absent; canonical launcher.lock root 0600 with no observed holder. This is a snapshot,
not a reservation. Relay enabled and canonical ls-remote succeeded. Main CI pending.

## G1: PASS

裁决：PASS。

Controlled external R10 surface; HealthTwin observations and ExecutionEvent feedback;
sensitive private data, scoped autonomous replies authorized only to pinned owner.
Spec required. No stale surface removed. User approval above covers this bounded scope.

## G2: PASS (architecture; implementation/production remain gated)

裁决：PASS。

Independent read-only reviewer `boundary_review` confirms split-authority plan fits
approval. Health must enforce pinned Health user at consent and token use. No old grant
expansion, arbitrary RPC relay or identity inferred from incoming WeChat content.

## Artifacts and tasks

- PRD: `docs/prd/2026-10-10-neo-wechat-bridge.md`
- Plan: `docs/plans/2026-10-10-neo-wechat-bridge.md`
- Feature spec: `docs/specs/active/2026-10-10-neo-wechat-bridge.md`
- Review/evidence: `docs/reviews/2026-10-10-neo-wechat-bridge.md`
- T1 encrypted bounded storage and inbox/outbox.
- T2 independent OAuth and MCP/owner UI.
- T3 separately consented owner-only Health adapter.
- T4 reviewed bounded deploy entry and service containment.
- T5 tests, independent safety review, protected PR/CI and acceptance.

## G3 / G4 / G5 / G6

G3: local service, PostgreSQL isolation, frontend, deployment, System Map and
dependency checks passed (details in review record). Final combined verification:
151 passed, 1 skipped. Exact `3b834ea74` CI passed at run `38031204452`; draft
PR280 was created and remains unmerged. New continuation changes need their own
fixed review and CI. Cross-family capstone was blocked by automatic
approval review because its external private-code destination was not authorized.
The owner subsequently cancelled Claude before the authorized retry was initiated;
no retry/source transmission occurred. Same-family independent review cannot be
recorded as the mandatory cross-family capstone. No applicable exception procedure
was found; G3 retains this unresolved governance decision.

G4: first fixed application review of `4892c41b1e8cd19ec5262ff5dc91b518316fa6b0`
was NO-GO: browser CSP callback, revoked-grant capacity and missing authorization/
Health audit evidence. Corrections and regressions are implemented and the targeted
real-browser, revoke/reconsent and audit retest passed. Fresh independent combined
review of `f7785ec68d604188afe2a1f7a9d1a68f85d480ea`: **GO for a draft PR of the
dormant candidate only**, no new P1/P2 findings, 375 independent tests passed.
This explicitly does not admit deployment or activation.

G5/G6: pending. No deployment, secret creation, QR request, grant or live signal
has occurred. Installer currently ends at dormant placement; approved secret-entry
surface, reviewed activation/removal/recovery and Linux sandbox validation remain
work. Final completion requires real closed-Mac/restart receipt and user-owned handoffs.

## S5 continuation and bounded G2 decision

Parent authorized continued independent local lifecycle preparation while external
review permission is pending. The specific secret-entry surface is an unresolved
G2 branch: reviewed owner-operated SSH hidden-input UI versus an existing browser
secret manager. A choice has been requested; actual provisioning/activation writers
remain stopped until resolved. No re-request or retry of Claude export occurred.

Independent work: offline provisioning validation/hashing with synthetic inputs;
ephemeral Linux systemd containment probe and portable contracts; pure lifecycle
inventory/reconciliation planning. These helpers do not supply a working lifecycle
entry or change production. Health revocation uncertainty was found and corrected:
local reads stop first, the encrypted refresh token survives in revocation_pending
for explicit owner retry, relinking is blocked, and HTTP acknowledgment is not
misreported as proof of grant removal.

PR252 is open and is not a code prerequisite; it freezes legacy writers but does
not ship the external launcher. The actual dependency is independently established
canonical staging provenance plus the installed executor's new history enforcement.
Absent that proof, release-trust repair requires a separate bounded feature. The
concurrent `637520e25` release run `38031474956` failed at 06:42:57 with retained evidence
and retry forbidden. It must be reconciled by the original release owner, never
bypassed. Fresh draft-only G4 for `6fd5e5d44` passed 214 independent tests. A dedicated
Ubuntu 22.04 job now requires actual systemd 249 evidence before release-invariants.

Native run `38033498010` failed an actual IP-listening check under systemd 249;
the old SocketBindDeny-only boundary is rejected. The corrective candidate now
uses paired static service/socket units, strict inherited listener validation before
secrets, and seccomp denial of bind/listen plus io_uring entry syscalls. Installer
readback rejects drop-ins and leaves both units inactive; production activation
and recovery remain unimplemented. CI-mode backend/bridge rerun passed 171 tests
with one environment-specific skip. A new fixed review and actual Linux CI must
cover these corrected bytes before any further gate claim.
