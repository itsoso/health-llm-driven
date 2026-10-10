# Delivery plan: independent WeChat bridge

1. Implement bounded encrypted filesystem snapshots with atomic rename/fsync,
   lifetime flock, strict private metadata and per-operation locking. No business DB
   or SQLite production persistence; corruption/unknown disk outcome stops service.
2. Implement identity-pinned QR validation, single collector, atomic batch/cursor,
   message claims, reply deduplication and durable uncertain state before network IO.
3. Implement independent OAuth issuer/resource, fixed public client and exact callback,
   owner admin consent, 3650-day grant, 600-second access, rotating refresh with replay
   family revocation. Admin setup/revoke is separate from remote MCP authority.
4. Keep Health authority separate: new dedicated Health registered client with a
   pinned Health owner and explicit new 3650-day consent; old clients default 30 days.
   Relay only three existing projected read tools, exact resource, no token forwarding.
5. Harden a dedicated Unix-socket systemd service and exact HTTPS proxy paths. Only a
   reviewed bounded `deploy.sh` mode may install it, under existing release ownership,
   exact main/full CI/G4 and immutable receipt semantics. Stop if gates unavailable.
6. Run adversarial/local and integration tests, independent review, protected PR/CI.
   Owner personally enters secrets, scans QR and consents. Parent owns Slack webhook
   sender filter acceptance. No live message/health payload goes to Slack or logs.

Data flow: WeChat -> isolated collector -> encrypted inbox -> constant Slack signal
-> existing Neo -> independent MCP -> pinned stored WeChat reply. Health read MCP uses
a separately consented upstream grant, never the bridge's bearer or Health DB secrets.

Rollback: stop only new service; revoke new grants/webhook; remove exact new proxy
routes through reviewed deploy entry. Preserve old Site and encrypted audit state.
