# Isolated owner WeChat bridge

This source is a new service, not an export of the existing Site binding. Production
activation is gated; test evidence alone does not prove live WeChat, Slack, OAuth,
Health discovery or closed-Mac acceptance. See the delivery dossier and deployment
runbook for current status.

## Authority and storage

`store.py` holds an OS process lease before reading encrypted state. A single process
serves the Unix socket and polls WeChat. AES-GCM protects complete bounded snapshots,
with fixed owner/schema AAD, private metadata, atomic rename/file+directory fsync and
fail-stop uncertain persistence. No Health DB access or shared Health credential.
Store corruption is not reset automatically. A maximum 4000 messages/16MiB prevents
unbounded disk growth; reaching capacity stops collection and requires operator
review. No automatic eviction weakens deduplication. Preserve the encryption key
through the owner's secure backup process; loss makes prior encrypted data unreadable.

`binding.py` requests a fresh QR only after owner Basic authentication, same-origin
CSRF and explicit risk acceptance. Scan identity is shown to the owner for confirmation.
Unexpected IDC/redirect/verification states stop for review. Existing binding cannot
be silently replaced. No upstream unbind is called. The QR renderer is the existing
MIT-licensed Site vendor implementation; it runs locally with no third-party resources.

`core.py` filters pinned sender AND bot recipient, private completed text only. Cursor,
inbox and notification state commit together. Claims expire in60 seconds. Replies use
the stored recipient/context and are limited to one payload per message. Durable
uncertain state precedes external IO; timeout/crash never automatically retransmits.
Slack receives exactly the constant in `transport.py`, without IDs, counts, links,
message text, health information or per-message metadata. Uncertain wake-ups require
operator review; a lost notification can delay processing but does not lose the inbox.

`oauth.py` provides a new issuer/resource and pre-registered public client. S256, exact
callback and exact resource are mandatory. New grants expire after3650 days; access
tokens expire after600 seconds; refresh tokens rotate and expire within30 days.
Refresh replay revokes its family immediately. Scopes are wechat:inbox (read/claim/ack),
wechat:reply (fixed stored destination), health:read (separate upstream connection).
Owner admin credentials are not exposed as an MCP tool. Messages cannot grant rights.

`health.py` obtains a separate new owner-pinned Health OAuth grant through the owner
website consent screen. It relays only get_sleep/get_diet/get_exercise with bounded
dates and timezone. Tokens are independently encrypted, not forwarded from Neo.
Uncertain code/refresh exchanges require fresh owner linking. Existing Health grants
keep their stored expiry; other clients retain the30-day default.
Revocation stops local reads before its upstream request. A failed request retains
only the encrypted refresh token in `revocation_pending`; restart never retries it
automatically, and relinking is blocked until an explicit owner revoke succeeds.
An upstream HTTP acknowledgment is not independent proof that a grant disappeared:
verify the Health grant-management surface, especially after uncertain code exchange.

## Owner handoffs — not performed by tests or startup

1. Slack workspace finn (`T6TNPEFLY`): owner creates/installs a dedicated Slack app,
   enables Incoming Webhooks, and selects private channel `C0C89QBQLBB`. Required bot
   OAuth scope is **incoming-webhook** only. Do not grant history, search, admin or
   broad chat scopes. The installer must belong to that private channel. The webhook
   is bound to the selected channel; sender identity is the new Slack app, not owner.
   Official instructions: https://docs.slack.dev/messaging/sending-messages-using-incoming-webhooks/
2. Owner personally supplies the new webhook and independent storage/admin secrets
   through the reviewed secure provisioning UI/terminal. Never paste them into chat,
   commits, CLI arguments, logs or agent tool parameters. No existing Site credential
   is an acceptable substitute. Current source contains no automatic secret setup.
3. Operator pins the new Health client to the authenticated owner's verified Health
   ID, `grant_days:3650`, exact callback `<origin>/neo-wechat/admin/health/callback`.
   Discovery must actually pass before owner Health OAuth consent. No guessed owner ID.
4. Owner opens the bridge admin page, personally requests/scans a fresh QR and confirms
   the displayed identity. Unknown Tencent verification/redirect states require review.
5. Plugins > Add > Add custom MCP server: owner selects OAuth and User-Defined public
   client; auth method `none`, S256, exact displayed callback pre-registered by operator.
   Issuer `<origin>/neo-wechat`, resource/MCP `<origin>/neo-wechat/mcp`, scopes above.
   Owner completes the new bridge consent (and separate Health read consent).
6. Parent tests one generic webhook message, verifies actual sender/channel and changes
   its existing automation filter only after that evidence. No owner-synthetic filter
   is assumed to accept bot/webhook events. Agent does not change that automation here.

## Required live acceptance

Record separate evidence for HTTPS discovery/401, owner/replay/revoke negative tests,
new QR first owner text, generic Slack wake-up, Neo claim/read/reply and owner receipt,
service restart, closed-Mac operation and stop/revoke. Do not auto-send a diagnostic
reply until the owner has supplied/approved the test interaction. Production success
requires the actual message receipt, not merely provider HTTP200 or green unit tests.

Local tests: `.venv/bin/python -m pytest -q services/neo_wechat/tests`.
Install only via reviewed `deploy.sh` mode; no direct SSH install, copied Health venv,
shared .env, public TCP listener or old ten-year bearer.
