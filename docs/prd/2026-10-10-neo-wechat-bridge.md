# Independent owner WeChat bridge

User-authorized extension of R10 (controlled external Agent/MCP) and R15 (private
notifications) in `docs/prd/reva-personal-health-os-prd.md`. While the Mac is closed,
one Health-hosted collector accepts only the pinned owner's private text and wakes
the existing Neo via a constant Slack incoming-webhook signal. Neo reads, claims,
acknowledges and replies to that stored conversation via a separately consented MCP.

The owner explicitly approved 3650-day revocable grants, their own read-only health
records, isolated hosting, fresh QR (possibly disrupting prior binding), and personal
secret entry/scan/OAuth consent. No old Site secrets or bindings are transferred.

Acceptance: encrypted durable cursor/inbox/outbox, OS-exclusive single consumer,
fixed identity/destination, no retry after uncertain send, exact public-client PKCE,
600-second access with rotating refresh/replay revocation, revocation enforcement,
owner-only Health reads through independent upstream OAuth, generic Slack signal,
closed-Mac and restart receipt tests. G3/G4 and exact main CI precede production.

Non-goals: groups/media, third-party messages, arbitrary destinations, Health writes,
database/shared Health credentials, changes to the parent's Slack automation, or
changes to existing Site connections. User handoffs remain explicit acceptance gates.
