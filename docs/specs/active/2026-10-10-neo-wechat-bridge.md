# Feature Spec: independent owner WeChat bridge

> Status: implementation; production and owner handoffs pending
> Updated: 2026-10-10
> PRD: [owner bridge](../../prd/2026-10-10-neo-wechat-bridge.md)
> Delivery: [dossier](../../dossiers/2026-10-10-neo-wechat-bridge.md)

## Decision and problem

Run one isolated WeChat text consumer on Health so the owner's existing Neo can
read and reply while the Mac is closed. The existing Site has no reviewed service
credential handoff. Create a fresh owner-confirmed binding and independent OAuth
authority instead of exporting that connection.

## Requirement admission

```yaml
RequirementAdmission:
  request: owner WeChat access and owner-only read-only Health access, 3650-day revocable grants
  classification: controlled external Agent extension, R10 and private notifications R15
  first_user_fit: explicitly approved by the owner
  core_loop_step: observe and review owner observations through a controlled agent
  first_class_objects: [HealthTwin, ExecutionEvent]
  target_surface: WeChat, private Slack signal, remote MCP, owner consent web UI
  source_of_truth: encrypted bridge snapshot and separately authorized Health API
  safety_level: sensitive health and private messaging
  prescription_or_causal_verdict: none
  autonomy_tier: bounded owner-authorized read and fixed-conversation reply
  evidence_provenance: authenticated pinned peer and authenticated pinned Health user
  claim_hedging: preserve source records; no diagnosis or causal claims added by bridge
  verification_window: before production activation and after restart with Mac closed
  success_metric: actual owner receipt with private generic Slack wakeup
  added_user_burden: secure secret entry, fresh QR scan, two OAuth consents
  burden_justification: independent authority with no credential export or old-grant expansion
  non_goals: third-party messages, groups, media, arbitrary replies, Health writes
  smallest_end_to_end_slice: one owner text to Slack wakeup to authorized Neo read and reply
  stale_surface_to_remove_or_archive: none; preserve old Site data and grants
  spec_required: yes
```

## Objects, surfaces and flow

HealthTwin remains the source of read-only sleep, diet and exercise projections.
ExecutionEvent maps to encrypted receive/claim/reply/audit state; this bridge adds
no Health business writes or database schema.

```text
Owner-confirmed private WeChat text
 -> atomic cursor/inbox/generic-signal outbox
 -> channel-scoped Slack webhook
 -> parent's existing Neo automation
 -> separately authorized MCP claim/read/reply
 -> stored peer/context only, durable uncertain-send guard
 -> actual owner receipt and acceptance evidence
```

| Surface | Contract |
|---|---|
| Health host | Separate account, venv, encrypted state, credentials and Unix socket; no Health DB/shared credential access |
| Owner web UI | Basic owner authentication, same-origin one-use CSRF, explicit binding confirmation and revocation |
| Neo MCP | Independent issuer/resource, preregistered public client, exact HTTPS callback, S256 PKCE |
| Slack | Constant new-message text only; no message/health payload, IDs or counts |
| Health OAuth | New dedicated client with verified owner pin; health:read only; old grants unchanged |

## Data and authority contract

Bridge scopes are `wechat:inbox`, `wechat:reply`, `health:read`. A new grant may
last 3650 days, access tokens last 600 seconds and refresh tokens rotate with a
30-day maximum lifetime. Replay revokes the grant family. Revoked or expired
grants cannot consume future authorization capacity indefinitely. No bearer has
a ten-year lifetime. Refresh uncertainty requires a new connection.

The encrypted snapshot has an owner/schema-bound AES-GCM envelope. A lifetime OS
lock precedes reads. Cursor/message/outbox changes commit atomically with file
and directory fsync. Unknown persistence poisons the process. Capacity exhaustion
stops collection without evicting deduplication evidence. Reply destinations and
provider context come from accepted records, never tool arguments or message
instructions. Unknown external send outcomes are retained and never blindly retried.

Health queries permit only `get_sleep`, `get_diet`, `get_exercise`, bounded ISO
dates and timezone. The upstream authority checks the client owner pin on consent
and token use. No existing grant is extended. Generic encrypted audit events
record OAuth authority changes and requested/completed Health reads without
tokens, message text, health values or query arguments.

## Safety and AI behavior

Incoming text is untrusted task content and cannot grant rights, change owner,
destination, scope or identity. This transport grants no health mutations,
medication changes, diagnoses or arbitrary external action. Neo's existing policy
and confirmations still apply. Deterministic owner filtering, tool allowlists,
OAuth scopes and stored-destination checks enforce the transport boundary.
Errors are fixed and privacy-preserving; upstream bodies are not logged.

## Acceptance and verification

- Non-owner/group/media records never enter the inbox or wake Slack.
- Restart preserves cursor, deduplication, claims and uncertain sends; a second
  consumer cannot read or poll.
- Real browser consent follows only the exact registered OAuth callback.
- Wrong owner/resource/client/PKCE fails, refresh replay revokes, and local
  revocation takes effect before later network launches.
- Health owner isolation is verified against disposable PostgreSQL; no real
  medical records are used in tests.
- Slack actual webhook sender must pass a synthetic acceptance test before the
  parent changes its automation filter.
- Closed-Mac receipt, restart and stop/revoke are live G6 checks, not unit-test claims.

Verification commands and results are retained in the dossier and review record.
The service suite, affected backend suites in CI mode, PostgreSQL OAuth suite,
frontend consent tests/typecheck, deployment tests, dependency audit, JavaScript
syntax, System Map and documentation checks precede a fixed-commit independent
G4 review. High-risk cross-family capstone and exact current-main full CI also
remain required before deployment.

## Rollout, rollback and remaining gates

Only the reviewed canonical `deploy.sh --neo-wechat` path may install. The current
bounded installer ends at `INSTALLED_DORMANT`: no secret values, listeners, nginx
activation, binding, grants or live signals. Interrupted operations retain durable
evidence and block later publication; recovery requires an exact-operation review.
The [deployment runbook](../../ops/neo-wechat-deployment.md) specifies containment,
admission and outstanding activation/removal work.

The owner must personally use an approved secret-entry surface, scan the new QR,
connect the MCP plugin and consent. The secret-entry surface and reviewed activation
transaction are not yet supplied by this mode. This is an implementation candidate,
not a completed production delivery. Existing Site data and connections remain intact.
