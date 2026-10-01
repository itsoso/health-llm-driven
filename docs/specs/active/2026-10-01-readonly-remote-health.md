# Read-only remote health connection

Status: local implementation, not enabled or deployed. Owner: Reva backend/web.

## Decision and admission

Provide an explicitly consented connection for a supported external assistant to query the account owner's sleep, diet and exercise records without exports or copied API keys.

```yaml
RequirementAdmission:
  classification: privacy-preserving infrastructure
  first_user_fit: existing health-data owner asking questions in an external assistant
  core_loop_step: observation and verification
  first_class_objects: [HealthTwin, ExecutionEvent]
  target_surface: web consent and remote MCP
  source_of_truth: existing owner-scoped health record tables
  safety_level: sensitive health data and authentication
  prescription_or_causal_verdict: none
  autonomy_tier: explicit user consent, read only
  evidence_provenance: stored source and calendar-date labels
  claim_hedging: missing data is unknown, overlapping sources are not additive
  verification_window: local synthetic tests before release approval
  success_metric: supported client retrieves only consenting user's requested bounded records
  added_user_burden: one website login and explicit permission approval per 30-day grant
  non_goals: health writes, family proxy, diagnoses, arbitrary URL access, production activation
  smallest_end_to_end_slice: OAuth consent then sleep/diet/exercise tool call and revocation
  spec_required: yes
```

## User and surface contract

The operator pre-registers an exact HTTPS callback and public client ID after approval. A compatible client discovers OAuth metadata, creates an S256 PKCE request, and opens `/connect/health`. Website owner authentication and an explicit allow/deny choice are mandatory. Approved grants last at most 30 days; access tokens last at most 10 minutes. `/connect/health` without a request lists active grants and revokes them.

Only the backend determines user identity. Family proxy, API Key, and first-party Bearer sessions cannot consent. The frontend binds the displayed account to approval and aborts stale account/request responses. Consent uses same-origin HttpOnly cookies and checks Origin on mutations. OAuth tokens are opaque and do not authenticate to the general REST API.

## Data and security contract

Three MCP tools: `get_sleep`, `get_diet`, `get_exercise`. Parameters are explicit ISO start/end dates and an IANA timezone. Maximum 31 inclusive days, 200 records and 100 KB serialized result. Stored daily labels cannot be reliably rebucketed to another timezone; timezone controls the current-day boundary, and responses disclose this limitation. No raw payloads, free-text notes, food descriptions, GPS, photos or device identifiers leave these projections.

Use official `mcp==1.30.0` (maintained stable v1 line). This requires `pydantic==2.12.5`; existing auth/date regressions are included in validation. The adapter enforces exact client/resource/redirect binding, mandatory S256 PKCE and state, single-use pending/code consumption, refresh rotation, grant revocation on a valid credential replay, owner revocation and disabled-account denial. Persist only credential hashes. Expired credentials and rate buckets are cleaned during ingress. Used refresh hashes remain until grant expiry to detect replay. Revoked/expired grant metadata remains as audit history.

New additive managed tables: `remote_health_grants`, `remote_health_credentials`, `remote_health_rate_buckets`. PostgreSQL is the production semantic authority; SQLite is a compatibility test target. OAuth changes never mutate health records. Rate limits are database-backed: 600 ingress requests/minute total, 120/minute per observed peer, 60 health queries/minute per user. Behind a reverse proxy the peer limit conservatively applies to that proxy; forwarded IP headers are not trusted.

SDK diagnostics can include raw inputs, so a request-context-scoped log factory replaces MCP/root SDK messages and exceptions with a constant event while preserving severity. Application audits contain only grant IDs, fixed tool names and outcome codes. Deployment must continue to disable raw URL access logging. The SDK's public-client revocation parsing defect is handled by a small RFC 7009 adapter; no client secret is required.

## Acceptance and release boundary

Required: real HTTP code/PKCE flow, invalid redirect/resource/scope rejection, no auto-consent, owner/account/CSRF checks, health write refusal, tenant separation, expiry/revoke/replay, malformed-input log privacy, bounds and missingness, PostgreSQL concurrent redemption and migration replay, existing auth/date regressions, frontend tests/typecheck and independent security review.

Default `REMOTE_HEALTH_ENABLED=false`. No client is registered by default and no credentials or grants are created at startup or by migration. Local synthetic tests do not prove actual ChatGPT or dot/mobile account integration. Deployment and real user authorization require separate approval. See [setup and limits](../../remote-health-connection.md).
