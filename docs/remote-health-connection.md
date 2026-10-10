# Remote health connection: operator and user setup

This implementation is disabled by default. The URLs below describe the implementation; they are not a claim that these endpoints are live in production.

## Compatibility checked on 2026-10-01

OpenAI's [custom MCP/developer-mode documentation](https://help.openai.com/en/articles/12584461-developer-mode-and-mcp-apps-in-chatgpt) answers mobile availability with **“No - web only.”** This statement applies to that documented ChatGPT workflow. It does not establish support or lack of support in the separate dot runtime. Neither this account's client setup nor dot-mobile reuse has been verified.

The [official OpenAI authentication guide](https://developers.openai.com/plugins/build/auth) documents OAuth authorization code with S256 PKCE, resource metadata, exact redirect registration and issuer identification. The [MCP authorization specification](https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization) allows pre-registered clients. This implementation deliberately uses pre-registration; it does not advertise dynamic registration or fetch arbitrary client metadata URLs.

Before deployment, confirm the target client's UI supports a pre-registered public OAuth client (`token_endpoint_auth_method=none`) and provides the exact redirect URI. Do not assume a connector exists because Markdown Skills are installed. If the selected client only supports DCR/CIMD or a confidential client, this version is not yet compatible; do not enter a dummy secret or weaken validation.

## Operator steps after separate approval

1. Release through the repository's normal CI, security and database gates. Apply the additive managed migration pair using the existing runner. Back up and verify PostgreSQL according to existing deployment governance.
2. Configure `REMOTE_HEALTH_PUBLIC_ORIGIN` to the exact HTTPS website origin without trailing slash. Register the client using `REMOTE_HEALTH_CLIENTS_JSON`, a JSON array containing `client_id`, a trusted display `client_name`, and `redirect_uris`. Optional `grant_days` defaults to 30 and is bounded to 1–3650; values above 30 require an explicit positive `allowed_user_id` verified from the authenticated owner. Use a new dedicated client for the independent WeChat bridge. The pin applies at consent and every token validation. New consent previews display the configured duration; changing that policy invalidates pending requests, never extends existing grants. Access lasts at most 600 seconds and each newly issued rotating refresh at most 30 days. These are public metadata, not secrets. Copy the exact callback from the target client; never allow wildcards, fragments or arbitrary callback origins. No production values were set by this task.
3. Route these two exact discovery paths to the backend, in addition to the existing `/api/` proxy. Existing nginx routes them to the frontend and must be changed only during an approved deployment:
   - `/.well-known/oauth-authorization-server/api/v1/remote-health`
   - `/.well-known/oauth-protected-resource/api/v1/remote-health/mcp`
4. Retain HTTPS, host validation, request limits, and disabled raw URL access logging. OAuth codes, pending handles, state and tokens must not enter proxy/APM logs. `/connect/health` sets no-referrer/noindex/no-store. Do not expose the legacy port-8808 fixed-token MCP server.
5. Set `REMOTE_HEALTH_ENABLED=true` only after configuration validation and approval. Configure the target client's MCP URL as `https://<origin>/api/v1/remote-health/mcp`, OAuth and the pre-registered public client ID. No shared Health API Key or JWT is needed.
6. Run a synthetic-client discovery/initialize/tools-list test, then request separate approval before an actual user grant and health-data query. Verify disconnect invalidates access and refresh, and confirm tenant isolation in the deployed environment.

## User steps when the client is supported

Add the connection in the client, open the Health login page, review the named application and the current account, then choose **允许只读访问**. Ask about a date range and timezone. No credential paste or file export is required. Revoke access at `/connect/health`; granting again after expiry or revocation requires another explicit consent.

Only sleep, diet and exercise structured observations are exposed. Health suggestions, medication, records changes, family-member data and arbitrary REST access are outside this connection. Missing records do not mean zero activity or intake. Date-only source records retain their stored labels; requesting another timezone does not shift them.

## Rollback and limits

Disable `REMOTE_HEALTH_ENABLED` to remove the entire endpoint surface. Keep the additive tables so revocation history survives a rollback. Do not drop tables while any version may read them. Removing a client from configuration invalidates its grants at the next request. Access already returned to a client cannot be recalled; revocation prevents subsequent reads.

No public cloud callback, real-account OAuth grant, production deployment, ChatGPT connection, or dot-mobile end-to-end validation was performed. Local tests use only synthetic accounts and tokens. Independent review and fresh test evidence are recorded in the [dossier](dossiers/2026-10-01-readonly-remote-health.md).
