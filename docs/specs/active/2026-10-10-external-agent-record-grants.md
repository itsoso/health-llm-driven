# External Agent Record Grants

Status: draft — awaiting human G1/G2 decision; no permission or credential has been issued.
Updated: 2026-10-10
Owner: Reva backend

## Decision and scope

Allow an explicitly authorized external Agent to add and correct the owner's ordinary health records through a server-enforced grant. Installing a Skill is discovery, not authorization. Use one Agent identity, explicit data domains/operations, purpose, expiry and revocation per grant. Do not broaden legacy `read,write` API keys implicitly.

The first complete slice is dated water reading, new intake, correction and historical daily-total backfill. Follow-on ordinary domains are diet, weight and workout records through the same policy. Clinical medication/prescription changes, account administration, family access, device synchronization and paid AI endpoints are excluded from this grant family.

## Admission

- Classification: security / new external Agent capability.
- Objects: WriteIntent, ExecutionEvent, HealthTwin, SafetyGuardian.
- Core loop: authorized capture/correction → owned records → updated Twin with attributable execution evidence.
- Surface/source of truth: backend; owner management in Web, external Agent consumes documented Skill/API. Mobile retains the same underlying records.
- Safety: privacy_sensitive; no medical advice or clearance. New writes default to manual_confirm.
- Verification: end-to-end synthetic PostgreSQL execution before release; consented owned record after deployment.
- Success: authorized correction succeeds once with receipt; wrong owner, scope, expired/revoked grant and unconfirmed proposal cannot mutate data.
- Added burden: owner approves the Agent's scope and confirms a concrete write proposal; no credential in chat.

## Current evidence

- `backend/app/api/deps.py`: shared API-key auth, read/write enforcement and tenant binding; method classification does not make arbitrary GET side-effect free.
- `backend/app/models/user_api_key.py` and `backend/app/api/user_api_key.py`: hashed keys and owner management; no granular data-domain scope or expiry/revocation metadata.
- `backend/app/models/data_connection.py`: ConsentGrant already describes grantee, purpose, scopes, expiry and revocation, but is not bound to API-key auth.
- `backend/app/services/water_backfill.py`: existing baseline/delta/TTL/receipt safeguards; its trusted chat-message presentation cannot be forged by an external caller.
- `backend/app/api/water.py`: create takes authenticated owner and accepts date; quick intake uses current date. Creation adds intake and is not a daily-total setter.
- `backend/app/api/deps.py::require_self_or_admin`: administrator-owned API keys need explicit owner-only enforcement for ordinary health records.
- `backend/app/models/agent_audit_log.py`: existing best-effort specialist audit does not guarantee mutation/audit atomicity.

## Proposed contract

1. Owner JWT/cookie management creates, lists and revokes grants. An external credential cannot create or enlarge its own grant. Owner UI displays Agent, domains, operations, purpose, expiry and last activity; secret is shown once and stored only as a digest.
2. Link a grant and credential explicitly, preferably reusing ConsentGrant after checking connection lifecycle semantics. Require expiry; reject absent, unknown, expired, revoked or disabled-account authorization on every call. Choose schema/migration only after G2 acceptance; no unreviewed metadata hidden in free-text fields.
3. Enforce a positive operation/route allowlist. First slice: `water:read`, `water:create`, `water:update`, `water:backfill_total`. No blanket GET authority, no generic API relay and no admin role inheritance.
4. External Agent proposes an exact dated change; the owner confirms through a trusted Reva session; execute only the owner-confirmed unchanged proposal. Agent-supplied text saying 'confirmed' is not proof. Grant policy cannot lift clinical autonomy caps.
5. Take owner exclusively from authentication. Data access, confirmation, execution, receipts and audit use the same owner and grant. Reject another owner's record IDs regardless of the owner's admin role.
6. Mutation and success receipt/audit commit in the same transaction. Audit records actor/grant, operation, target identifier, request identifier, time and outcome, with no secret, request body or full health payload. Audit persistence failure rolls back the mutation. Rejected attempts produce sanitized durable evidence.
7. Require idempotency per owner/grant/operation. Same key and same proposal returns the same receipt; different proposal returns conflict. Lock/recheck grant, proposal and target baseline during execution to address concurrent revocation, correction and retry.
8. Daily-total backfill computes the difference from a locked current total; it is not a blind addition. No-op if equal; require owner decision if current total exceeds the requested total; reject changed baseline. Do not invent an intake time for a daily aggregate.
9. Return stable status, changed record/date, receipt and audit references. Replace legacy runtime Skill instructions with documented new grant operations only when implementation is actually available; do not claim local code is deployed.

## Acceptance and validation

Synthetic tests must cover owner management and forbidden Agent self-escalation; header/Bearer equivalence; missing/unknown scopes; expiry/revocation/disabled accounts; admin-key cross-owner denial; side-effect GET exclusion; confirmation forgery; same/different idempotency payloads; PostgreSQL concurrent retries/revocation/baseline conflicts; successful data+audit transaction and audit-failure rollback; daily-total semantics; secret/body-free logs; existing API-key compatibility; migration up/down; generated client types and owner-management UI.

Release requires safety-gate GO on a fixed commit, PostgreSQL and CI-mode integration checks, target-revision green CI, explicit release authorization and a consented user-path check. Rollback disables/revokes new Agent grants first; retain receipts/audit, do not reverse unrelated health corrections or restore blanket write authority. No production grant, new credential, account permission, helper allowlist or deployment is changed by this draft.

## Changelog

- 2026-10-10: concrete proposal prepared from user-selected server-side scope and read-only source review.
