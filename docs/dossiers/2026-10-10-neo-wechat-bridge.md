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
secret manager. A choice has been requested; selecting and connecting an owner-input
adapter remains stopped until resolved. The earlier decision to defer all lifecycle
implementation was our sequencing choice, not a governance prohibition. Local
transport-independent transactions, injected-host activation/stop logic and
synthetic interruption tests may proceed under the existing scope. Production
dispatch still needs reviewed provenance, history/lease gates and fixed-code G4.
No re-request or retry of Claude export occurred.

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

Continuation at `eeaa3a8bc`: native systemd 249.11 job `114163305601` passed in
CI `38034927895`, with protected and positive-control runs. Full CI nevertheless
failed in Ubuntu 24.04 job `114163336534` at the credential private-mode assertion;
later release checks did not run. A mode-bit-only test cannot distinguish a POSIX
ACL mask from actual owning-group access. The correction must verify the exact
credential file/directory ACL or private-owner form and read-only access, never
merely allow broader mode bits. This is a probe correction, not a sandbox policy
change. Production identity, proxy/egress and live acceptance remain unverified.

Independent review of `120e0f472` found the application's credential reader also
used the mode-only assumption. The continuation extracts a strict stdlib reader
shared by the application and the synthetic native worker; native evidence must
bind its exact module digest. No broader credential access is permitted.

The local provisioning transaction now accepts only an already-validated memory
bundle and trusted directory descriptors. It creates four fixed files and a
separate one-shot metadata namespace, preserves uncertain writes and rejects
retries. It has no input adapter, CLI, production caller or activation authority.
Canonical provenance, lock/path guard implementation, lifecycle history admission
and activation/recovery remain integration work. A visible completion record alone
cannot authorize activation after an uncertain fsync or final-guard failure.

## Preserved green candidate and local lifecycle continuation

Exact commit `9f10f37cb800cc0c202a09d18220c98fe62ae73f` passed full CI
[`38036868221`](https://github.com/itsoso/health-llm-driven/actions/runs/38036868221).
Native jobs observed systemd 249.11 and 255.4, including the shared production
credential reader digest `e3ba7520c8b0854ba83a6d16dcca65647fff48ce568b9b5b84cb5b108ace3cdf`.
Both private-owner and exact named-service-UID ACL credential forms passed with
read-only mount evidence. This proves synthetic runner containment, not production
identity, routing or egress. Local deployment regressions passed 550 tests;
CI-mode backend/bridge passed 220 with 2 skips. The saved 9f10 evidence remains
immutable historical evidence; subsequent lifecycle changes need their own tests.

Read-only task history identifies the original failed release owner as
`优化 README`, thread `01a120c7-1ba0-75c3-9487-447bd5bfa28f`. Its turn
`01a1246a-93ae-74b1-b0fd-2a4674286ab6` records deployment of `637520e25`,
dispatch and observation of run `38031474956`, and failure handling. That thread
reports rollback to `346035f78` and later blocked reconciliation of an unresolved
write and the failed batch. These are attributed task reports, not fresh production
proof. This continuation makes no production calls, sends no message to the owner,
and clears no locks or retained receipts.

The agent-neutral product contract requires a cross-family capstone (line 54)
and explains it as different model families (line 48). It does not require Claude.
The historical Claude × GPT example establishes that pair, but there is no found
taxonomy mapping GPT versions or sol/astra/luna to different families. Available
GPT options therefore cannot yet be claimed to satisfy this gate. An authorized,
connected non-Claude different-family reviewer could satisfy the original rule;
a governance interpretation of a specific available model pair is another route.
Only accepting same-family review as a substitute would require an explicit
exception. No alternate provider is invoked or private code transmitted here.

The frozen local lifecycle increment adds injected-host start/stop sequencing,
strict runtime/provision metadata histories and read-only conservative recovery.
Related deployment regressions passed 704 tests. No production adapter, installed
history admission or boot enablement is supplied. The owner-input adapter remains
pending independently. Fixed-commit review and candidate-specific CI are required
before advancing this increment beyond draft status.
