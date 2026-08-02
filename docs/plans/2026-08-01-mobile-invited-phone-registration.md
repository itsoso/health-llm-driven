# Mobile Invited Phone Registration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Require a single-use, admin-issued invitation bound to the target phone before an unknown phone can create a Reva account, while preserving invitation-free OTP login for existing users.

**Architecture:** Backend remains the only registration authority. A new PostgreSQL `RegistrationInvitation` plus one-time `PhoneRegistrationGrant` provide encrypted phone delivery data, HMAC equality matching, transactional invite consumption, and replay resistance; Mobile and Web only render backend outcomes. Rollout is additive-first and server-enforced only after the supporting Mobile OTA is active.

**Tech Stack:** FastAPI, SQLAlchemy, PostgreSQL managed migrations, Pydantic/OpenAPI, Aliyun SMS adapter, Expo Router, React Native, SecureStore, Next.js, React, TypeScript, pytest, Jest, Vitest.

---

## Preconditions And Guardrails

- Work from a clean, current `main`; preserve the user's dirty root worktree.
- Read `docs/plans/2026-08-01-mobile-invited-phone-registration-design.md`, the Feature Spec, and the Dossier first.
- Authentication changes require `.claude/skills/safety-gate/SKILL.md` producer-reviewer `GO` before deployment.
- Do not log full phone numbers, OTPs, invitation codes, deep-link tokens, or verification grants.
- Do not use the legacy default invite code or `auth_phone_registration_auto_approve` as a fallback.
- Do not reopen arbitrary phone auto-registration as rollback behavior.

### Task 1: Add PostgreSQL Invitation And Verification-Grant Schema

**Files:**
- Create: `backend/app/models/registration_invitation.py`
- Create: `backend/migrations/managed/20260801_230000_registration_invitations.postgresql.sql`
- Modify: `backend/app/models/__init__.py`
- Test: `backend/tests/test_registration_invitation_migration_postgres.py`

**Step 1: Write the failing PostgreSQL migration test**

Assert the migration creates `registration_invitations` and `phone_registration_grants`, including:

```python
assert columns("registration_invitations") >= {
    "id", "code_digest", "link_token_digest", "phone_ciphertext",
    "phone_hmac", "phone_masked", "status", "expires_at",
    "consumed_by", "consumed_at", "created_by",
}
assert unique_index_exists("registration_invitations", "code_digest")
assert partial_unique_index_exists(
    "registration_invitations", "phone_hmac", predicate="status IN ('created','sent','send_failed')"
)
assert columns("phone_registration_grants") >= {
    "id", "token_digest", "phone_hmac", "phone_ciphertext",
    "expires_at", "consumed_at", "created_at",
}
```

**Step 2: Run the RED test**

Run:

```bash
cd backend
DATABASE_URL="$TEST_POSTGRES_URL" venv/bin/pytest tests/test_registration_invitation_migration_postgres.py -q
```

Expected: FAIL because the managed migration does not exist.

**Step 3: Add the migration and ORM models**

- Use PostgreSQL check constraints for invitation status.
- Use `EncryptedString` for phone ciphertext, indexed HMAC columns for equality, and no plaintext credential column.
- Add foreign keys to `users.id` with safe delete behavior.
- Model `is_usable(now)` as deterministic state/expiry logic; do not mutate status from a property.

**Step 4: Re-run the test**

Expected: PASS on real PostgreSQL, including second-run migration idempotency.

**Step 5: Commit**

```bash
git add backend/app/models/registration_invitation.py backend/app/models/__init__.py backend/migrations/managed/20260801_230000_registration_invitations.postgresql.sql backend/tests/test_registration_invitation_migration_postgres.py
git commit -m "feat(auth): add registration invitation schema"
```

### Task 2: Build Credential, Phone-Matching, And Grant Primitives

**Files:**
- Create: `backend/app/services/registration_invitation.py`
- Modify: `backend/app/config.py`
- Test: `backend/tests/test_registration_invitation_service.py`
- Test: `backend/tests/test_registration_invitation_privacy.py`

**Step 1: Write failing unit tests**

Cover:

```python
def test_generated_manual_code_excludes_ambiguous_characters(): ...
def test_code_and_link_are_stored_as_digest_only(): ...
def test_phone_hmac_matches_normalized_equivalent_numbers(): ...
def test_phone_ciphertext_round_trips_but_repr_and_logs_are_masked(): ...
def test_grant_is_short_lived_single_use_and_bound_to_phone(): ...
def test_invalid_digest_comparison_is_constant_time(): ...
```

**Step 2: Run RED**

```bash
cd backend
venv/bin/pytest tests/test_registration_invitation_service.py tests/test_registration_invitation_privacy.py -q
```

Expected: FAIL because the service does not exist.

**Step 3: Implement minimal primitives**

- Generate an 8-character manual code from the approved non-ambiguous alphabet.
- Generate a separate random deep-link token with at least 128 bits of entropy.
- Derive lookup digests with keyed HMAC-SHA256 and `hmac.compare_digest`.
- Reuse canonical phone normalization from `app.services.phone_auth`.
- Encrypt delivery phone with the repository encryption primitive; never use reversible data for lookups.
- Create and consume `PhoneRegistrationGrant` rows with short expiry and row locks.
- Add dedicated secrets/config fields and fail startup in production when enforcement is enabled but keys are missing.

**Step 4: Run GREEN**

Expected: all service and privacy tests PASS.

**Step 5: Commit**

```bash
git add backend/app/services/registration_invitation.py backend/app/config.py backend/tests/test_registration_invitation_service.py backend/tests/test_registration_invitation_privacy.py
git commit -m "security(auth): protect registration invitation credentials"
```

### Task 3: Add Admin Create, List, Resend, And Revoke APIs

**Files:**
- Create: `backend/app/api/admin_registration_invitations.py`
- Create: `backend/app/schemas/registration_invitation.py`
- Modify: `backend/app/api/main.py`
- Test: `backend/tests/test_admin_registration_invitations.py`

**Step 1: Write failing API tests**

Test admin and non-admin callers for:

- create with normalized phone, optional note, default seven-day expiry;
- one active invite per phone;
- list returns only masked phone and never returns digests/ciphertext;
- resend reuses the same invite;
- revoke is allowed only before consumption;
- every mutation writes a bounded audit record.

**Step 2: Run RED**

```bash
cd backend
venv/bin/pytest tests/test_admin_registration_invitations.py -q
```

Expected: 404 for the new endpoints.

**Step 3: Implement the router and schemas**

Use exact endpoints from the approved design. Response types must not contain `code_digest`, `link_token_digest`, `phone_ciphertext`, full phone, OTP, or grant values. The create response may return the manual code and link exactly once for admin copying.

**Step 4: Run GREEN**

Expected: all authorization, masking, state, and audit tests PASS.

**Step 5: Commit**

```bash
git add backend/app/api/admin_registration_invitations.py backend/app/schemas/registration_invitation.py backend/app/api/main.py backend/tests/test_admin_registration_invitations.py
git commit -m "feat(admin): manage phone-bound registration invites"
```

### Task 4: Add Invitation SMS Delivery With Fail-Loud Semantics

**Files:**
- Create: `backend/app/services/registration_invitation_sms.py`
- Modify: `backend/app/config.py`
- Modify: `backend/app/services/registration_invitation.py`
- Test: `backend/tests/test_registration_invitation_sms.py`

**Step 1: Write failing delivery tests**

Cover enterprise Aliyun SMS success, configured provider rejection, missing config, timeout, resend reuse, and log redaction. Assert provider payload contains only template variables explicitly approved for the registration invite.

**Step 2: Run RED**

```bash
cd backend
venv/bin/pytest tests/test_registration_invitation_sms.py -q
```

**Step 3: Implement a dedicated template adapter**

- Reuse signing/transport helpers without overloading the OTP template.
- Add separate registration-invite template configuration.
- Persist `sent` only after provider acknowledgement; otherwise persist `send_failed` and bounded `last_send_error_code`.
- Never include admin note or health data in SMS.

**Step 4: Run GREEN and the existing OTP provider regression**

```bash
cd backend
venv/bin/pytest tests/test_registration_invitation_sms.py tests/test_phone_auth.py -q
```

Expected: PASS; existing OTP routing remains unchanged.

**Step 5: Commit**

```bash
git add backend/app/services/registration_invitation_sms.py backend/app/services/registration_invitation.py backend/app/config.py backend/tests/test_registration_invitation_sms.py backend/tests/test_phone_auth.py
git commit -m "feat(auth): deliver registration invitations by SMS"
```

### Task 5: Split Phone Verification From Invited Registration

**Files:**
- Modify: `backend/app/schemas/auth.py`
- Modify: `backend/app/api/auth.py`
- Modify: `backend/app/services/registration_invitation.py`
- Test: `backend/tests/test_invited_phone_registration.py`
- Test: `backend/tests/test_invited_phone_registration_postgres.py`
- Modify: `backend/tests/test_phone_auth.py`

**Step 1: Replace the old auto-registration expectation with RED contract tests**

Required cases:

```python
def test_existing_phone_verification_returns_authenticated_without_invite(): ...
def test_unknown_phone_verification_returns_one_time_grant_not_user(): ...
def test_unknown_phone_legacy_login_never_auto_creates_when_enforced(): ...
def test_registration_requires_matching_active_invite(): ...
def test_registration_consumes_grant_and_invite_exactly_once(): ...
def test_existing_user_from_invite_link_does_not_consume_invite(): ...
```

PostgreSQL concurrency tests must prove two concurrent consumes create at most one user and consume at most one invite.

**Step 2: Run RED**

```bash
cd backend
venv/bin/pytest tests/test_invited_phone_registration.py tests/test_phone_auth.py -q
DATABASE_URL="$TEST_POSTGRES_URL" venv/bin/pytest tests/test_invited_phone_registration_postgres.py -q
```

Expected: current `/phone/login` auto-creates the unknown phone, so the new contract fails.

**Step 3: Implement the endpoint state machine**

- `POST /auth/phone/verify` consumes OTP. Existing user returns the normal token response; unknown phone creates a `PhoneRegistrationGrant` and returns `invitation_required`.
- `POST /auth/invitations/inspect` returns only validity, phone mask, and expiry.
- `POST /auth/invited-registration` locks grant and invitation, verifies phone HMAC and idempotency key, creates approved active user, consumes both rows, and issues the token in one transaction.
- Keep `/auth/phone/login` for old clients. Under the rollout flag it can preserve legacy behavior; under enforcement it must return `REGISTRATION_INVITATION_REQUIRED` for unknown phones without creating rows.
- Stable error codes must be machine-readable and messages user-safe.

**Step 4: Run GREEN**

Expected: focused unit and real PostgreSQL concurrency suites PASS.

**Step 5: Commit**

```bash
git add backend/app/schemas/auth.py backend/app/api/auth.py backend/app/services/registration_invitation.py backend/tests/test_invited_phone_registration.py backend/tests/test_invited_phone_registration_postgres.py backend/tests/test_phone_auth.py
git commit -m "feat(auth): require invitations for new phone accounts"
```

### Task 6: Regenerate OpenAPI And Mobile Types

**Files:**
- Modify: `frontend/src/types/api.generated.ts`
- Modify: generated Mobile API types at the repository's existing generator output
- Test: CI type-drift gate

**Step 1: Run the generator before updating outputs**

Run the repository OpenAPI/type generation commands referenced by `.github/workflows/ci.yml`.

Expected: generated diff contains the new discriminated phone verification response, invitation schemas, and admin endpoints.

**Step 2: Inspect privacy boundaries**

Assert no generated public response exposes credential digests, ciphertext, full target phone, OTP, or grant database IDs.

**Step 3: Run type-drift checks**

Expected: no uncommitted regeneration drift.

**Step 4: Commit**

```bash
git add frontend/src/types/api.generated.ts <mobile-generated-type-path>
git commit -m "chore(api): sync invited registration contracts"
```

### Task 7: Add Mobile Auth Service And Secure Grant Storage

**Files:**
- Modify: `mobile/services/auth.ts`
- Create: `mobile/services/registrationInviteStorage.ts`
- Modify: `mobile/hooks/useAuth.tsx`
- Test: `mobile/services/__tests__/auth.test.ts`
- Create: `mobile/services/__tests__/registrationInviteStorage.test.ts`
- Modify: `mobile/hooks/__tests__/useAuth.test.tsx`

**Step 1: Write RED service tests**

Test the discriminated `authenticated | invitation_required` response, token persistence only for authenticated results, SecureStore-only grant persistence, expiry cleanup, logout cleanup, and absence from AsyncStorage.

**Step 2: Run RED**

```bash
cd mobile
npx jest services/__tests__/auth.test.ts services/__tests__/registrationInviteStorage.test.ts hooks/__tests__/useAuth.test.tsx --runInBand
```

**Step 3: Implement the minimal auth state contract**

Expose `verifyPhoneCode`, `completeInvitedRegistration`, and an explicit pending-registration state. Do not set the global authenticated session until a real access token is durably persisted.

**Step 4: Run GREEN and TypeScript**

```bash
cd mobile
npx jest services/__tests__/auth.test.ts services/__tests__/registrationInviteStorage.test.ts hooks/__tests__/useAuth.test.tsx --runInBand
npx tsc --noEmit
```

**Step 5: Commit**

```bash
git add mobile/services/auth.ts mobile/services/registrationInviteStorage.ts mobile/services/__tests__/auth.test.ts mobile/services/__tests__/registrationInviteStorage.test.ts mobile/hooks/useAuth.tsx mobile/hooks/__tests__/useAuth.test.tsx
git commit -m "feat(mobile): add invited registration auth state"
```

### Task 8: Build The Mobile Phone, OTP, And Invite UI State Machine

**Files:**
- Modify: `mobile/app/login.tsx`
- Modify: `mobile/app/_layout.tsx`
- Create: `mobile/services/registrationInviteDeepLink.ts`
- Modify: `mobile/app/__tests__/login.test.tsx`
- Modify: `mobile/__tests__/login.test.tsx`
- Create: `mobile/services/__tests__/registrationInviteDeepLink.test.ts`

**Step 1: Write RED UI and deep-link tests**

Cover:

- existing phone: phone → OTP → authenticated;
- unknown phone: phone → OTP → invite page without a second OTP;
- `health://invite?token=...` preloads invite state but not full phone;
- manual “我有邀请码” path;
- phone mismatch, expired, revoked, used, and ticket expired messages;
- app restart restores an unexpired SecureStore grant;
- success routes into existing Reva onboarding;
- primary copy says “登录小巴” and “首次使用需获得管理员邀请”, not “登录 / 注册”.

**Step 2: Run RED**

```bash
cd mobile
npx jest app/__tests__/login.test.tsx __tests__/login.test.tsx services/__tests__/registrationInviteDeepLink.test.ts --runInBand
```

**Step 3: Implement the approved screens**

Keep the login flow inside the unauthenticated root surface; do not create a second auth provider. Use the theme tokens, accessibility labels, OTP autofill attributes, masked phone copy, countdown, resend, change-phone, and actionable error mapping from the design.

**Step 4: Run GREEN, TypeScript, and lint**

```bash
cd mobile
npx jest app/__tests__/login.test.tsx __tests__/login.test.tsx services/__tests__/registrationInviteDeepLink.test.ts --runInBand
npx tsc --noEmit
npx expo lint
```

**Step 5: Commit**

```bash
git add mobile/app/login.tsx mobile/app/_layout.tsx mobile/services/registrationInviteDeepLink.ts mobile/app/__tests__/login.test.tsx mobile/__tests__/login.test.tsx mobile/services/__tests__/registrationInviteDeepLink.test.ts
git commit -m "feat(mobile): add invitation-gated phone onboarding"
```

### Task 9: Add The Admin Registration-Invite Panel

**Files:**
- Modify: `frontend/src/app/admin/components/InvitationTab.tsx`
- Modify: `frontend/src/app/admin/components/AdminModals.tsx`
- Modify: `frontend/src/app/admin/page.tsx`
- Create: `frontend/src/app/admin/components/RegistrationInvitationPanel.test.tsx`

**Step 1: Write RED component tests**

Test create/send confirmation with masked phone, status rendering, resend, copy link/code, revoke, send failure, no full-phone rendering, and non-admin unreachable behavior.

**Step 2: Run RED**

```bash
cd frontend
npx vitest run src/app/admin/components/RegistrationInvitationPanel.test.tsx
```

**Step 3: Implement the panel**

Add a registration-invite section ahead of legacy generic codes. Keep the legacy section clearly labeled and do not let it authorize Mobile phone registration. Never persist the one-time manual code in page state after the create modal closes.

**Step 4: Run GREEN and frontend checks**

```bash
cd frontend
npx vitest run src/app/admin/components/RegistrationInvitationPanel.test.tsx
npm run build
npm run lint
```

**Step 5: Commit**

```bash
git add frontend/src/app/admin/components/InvitationTab.tsx frontend/src/app/admin/components/AdminModals.tsx frontend/src/app/admin/page.tsx frontend/src/app/admin/components/RegistrationInvitationPanel.test.tsx
git commit -m "feat(admin): send phone-bound registration invites"
```

### Task 10: Add Rollout Flags, Legacy-Path Removal Tests, And Observability

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/app/api/auth.py`
- Modify: `backend/app/api/invitation.py`
- Modify: `backend/app/services/observability_service.py`
- Modify: `backend/.env.example`
- Test: `backend/tests/test_registration_invitation_rollout.py`
- Test: `backend/tests/test_registration_invitation_observability.py`

**Step 1: Write RED rollout tests**

Prove:

- enforcement OFF supports the pre-OTA compatibility window;
- enforcement ON makes every unknown-phone legacy path fail closed;
- existing phones work in both states;
- default invite code cannot authorize the new phone path;
- rollback mode is “new registrations closed, old users login”, not unrestricted registration;
- metrics contain counts/status/error enums only, never phone/code/ticket/user health data.

**Step 2: Run RED, implement, and run GREEN**

```bash
cd backend
venv/bin/pytest tests/test_registration_invitation_rollout.py tests/test_registration_invitation_observability.py tests/test_auth_secrets.py tests/test_auth_login_policy.py -q
```

Expected: PASS after adding flags, guards, bounded events, and environment documentation.

**Step 3: Commit**

```bash
git add backend/app/config.py backend/app/api/auth.py backend/app/api/invitation.py backend/app/services/observability_service.py backend/.env.example backend/tests/test_registration_invitation_rollout.py backend/tests/test_registration_invitation_observability.py
git commit -m "security(auth): enforce controlled phone registration"
```

### Task 11: Run Integrated Gates And Independent Safety Review

**Files:**
- Modify: `docs/dossiers/2026-08-01-mobile-invited-phone-registration.md`
- Modify if architecture changes: generated system-map outputs only through repository generators

**Step 1: Run focused and full relevant verification**

Run complete Backend auth/invitation suites including real PostgreSQL concurrency, Mobile full Jest + TypeScript + Expo lint, Frontend tests/build/lint, OpenAPI drift, doc drift, dossier consistency, and `git diff --check`. Do not pipe tests to `tail`.

**Step 2: Inspect the full diff for privacy leaks**

Search tracked diff and test snapshots for full phone samples, invite tokens, OTPs, ciphertext, secrets, free-form provider errors, and accidental response fields.

**Step 3: Invoke project safety-gate review**

Give the independent reviewer the commit range and explicitly ask it to attack:

- unknown-phone bypasses;
- user enumeration;
- grant/invite replay;
- concurrent double creation;
- plaintext phone/credential leakage;
- non-admin mutation;
- fail-open rollout/rollback;
- old-client compatibility.

Expected: explicit `GO`. Any `NO-GO` returns to the failing task, adds RED tests, fixes, and re-reviews.

**Step 4: Update the Dossier G3/G4 evidence and commit**

```bash
git add docs/dossiers/2026-08-01-mobile-invited-phone-registration.md
git commit -m "docs(auth): record invitation registration gates"
```

### Task 12: Deploy In Safe Order And Complete Real-Device G6

**Files:**
- Modify: `docs/dossiers/2026-08-01-mobile-invited-phone-registration.md`
- Modify if user-visible navigation changed: `docs/system-map/mobile-nav-map.md` and generated nav graph via its generator

**Step 1: Deploy additive Backend and migration with enforcement OFF**

Use the project backend deployment skill and `deploy.sh` from a clean main checkout. Verify backup, managed migration, exact SHA, service health, public health endpoint, table/index existence, and admin authorization.

**Step 2: Smoke the admin flow**

Create a test invite for a controlled phone, verify SMS provider acknowledgement, list masking, resend reuse, and revoke behavior. Do not expose credentials in deployment logs.

**Step 3: Publish Mobile OTA**

Use `scripts/mobile-ota.sh production "feat: add invitation-gated phone registration"`. Verify branch, runtime, update ID, commit, and a real device loading the OTA.

**Step 4: Enable enforcement**

Only after Mobile coverage/readiness is confirmed, enable server enforcement and remove the production default invite/auto-approve bypass. Re-run backend health and login smoke.

**Step 5: Real-device G6**

With user confirmation, prove on iOS:

1. an existing phone logs in without invite;
2. an unknown phone with valid OTP but no invite cannot create an account;
3. the SMS deep link opens the invite flow;
4. the bound phone completes registration and reaches onboarding;
5. the same invite cannot create another account;
6. a different phone cannot consume the invite.

**Step 6: Observe and close**

Observe seven-day invitation send success, registration conversion, SMS failures, mismatch/expiry, and existing-user login failure. Update G5/G6/S8 honestly; do not claim metric goals before the observation window closes.

**Step 7: Commit final evidence**

```bash
git add docs/dossiers/2026-08-01-mobile-invited-phone-registration.md docs/system-map/mobile-nav-map.md docs/_generated/mobile-nav-graph.json
git commit -m "docs(auth): close invited registration rollout"
```

