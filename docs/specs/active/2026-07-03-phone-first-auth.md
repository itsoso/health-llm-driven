# Feature Spec: Phone-First Auth

> Status: building
> Owner: Codex
> Updated: 2026-07-03
> Related PRD/PDD: `docs/specs/reva-product-governance-spec.md`
> Related code: `backend/app/api/auth.py`, `backend/app/services/phone_auth.py`, `mobile/app/login.tsx`

## 1. Decision

Add phone verification-code login/register as the default mobile entry path, while keeping account/password login as a fallback and adding password set/change after phone login.

## 2. Problem

The current account/password-first login is too heavy for a daily health app and makes first-use onboarding harder. Users should be able to start with a phone number, verify ownership, and later add or change a password from account security settings.

## 3. Requirement Admission

```yaml
RequirementAdmission:
  request: "一期先做手机号方式登录注册，后续再考虑其他方式。"
  classification: new_product_behavior
  first_user_fit: lowers entry friction for the first daily mobile user
  core_loop_step: Mobile daily product entry -> authenticated health execution loop
  first_class_objects: ExecutionEvent, WriteIntent
  target_surface: Backend auth, Mobile login/settings
  source_of_truth: backend users table and auth_phone_codes table
  safety_level: privacy_sensitive
  prescription_or_causal_verdict: none
  autonomy_tier: none
  evidence_provenance: n/a
  claim_hedging: n/a
  verification_window: immediate login/register result
  success_metric: phone code login creates/reuses one account and stores token
  added_user_burden: low
  burden_justification: one phone number plus short code replaces full registration form
  non_goals: social login, WeChat login, passkeys, MFA policy, admin user management
  smallest_end_to_end_slice: request code -> verify code -> auto-register/login -> set/change password
  stale_surface_to_remove_or_archive: none; account password fallback remains
  spec_required: yes
```

## 4. Product Object Mapping

| Object | Change |
|---|---|
| `ExecutionEvent` | A successful phone verification becomes an authenticated entry event into the health execution loop. |
| `WriteIntent` | Password set/change is a deliberate authenticated write, not an autonomous action. |

## 5. User Flow

```text
open mobile login
  -> enter phone
  -> backend issues one-time code through SMS or dev echo
  -> enter code
  -> backend verifies, creates or reuses the user, returns JWT
  -> mobile stores token and enters Today
  -> user may set/change password from Settings > 账号安全
```

## 6. Surface Contract

| Surface | Responsibility | Contract |
|---|---|---|
| Mobile | Default phone-first login UI, fallback account login, account security page. | `requestPhoneCode`, `loginByPhoneCode`, `setPassword`, `changePassword`. |
| Backend | Code lifecycle, phone normalization, user creation/reuse, JWT issuance, SMS fail-loud. | `POST /api/v1/auth/phone/code`, `/phone/login`, `/password/set`, `/password/change`. |

## 7. Data Contract

```yaml
apis:
  - POST /api/v1/auth/phone/code
  - POST /api/v1/auth/phone/login
  - POST /api/v1/auth/password/set
  - POST /api/v1/auth/password/change
models:
  - users.phone
  - users.phone_verified_at
  - auth_phone_codes
backward_compatibility:
  - username/email/password login remains
  - generated mobile API types updated
migration:
  - managed PostgreSQL and SQLite migrations under backend/migrations/managed
```

## 8. Safety, Privacy, And Medical Boundary

This feature is privacy-sensitive auth infrastructure. Phone numbers are normalized, masked in logs, and stored on the user row. Verification codes are stored as HMAC hashes, are time-limited, single-use, attempt-limited, and rate-limited at the API layer. Production must use a configured SMS provider; otherwise the backend returns a clear 503 instead of pretending delivery succeeded. No health advice or medical claim is introduced.

## 9. Acceptance Criteria

```gherkin
Given a new phone number
When the user verifies a valid code
Then the backend creates exactly one active user, marks the phone verified, and returns a JWT.

Given an existing phone user
When the user verifies a new valid code
Then the backend reuses the same account instead of creating a duplicate.

Given a consumed, expired, or over-attempted code
When the user tries to login
Then the backend rejects it.

Given a phone-login user without a password
When the user sets a password
Then password login by phone works.

Given production without SMS configuration
When a code is requested
Then the backend fails loud with 503.
```

## 10. Verification Plan

```bash
source backend/venv/bin/activate && DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai pytest backend/tests/test_phone_auth.py -q
cd mobile && npm test -- --runInBand services/__tests__/auth.test.ts app/__tests__/login.test.tsx app/__tests__/settings.test.tsx
cd mobile && npm run generate-types
source backend/venv/bin/activate && python3 scripts/dump_system_map.py
source backend/venv/bin/activate && python3 scripts/check_doc_drift.py
git diff --check
```
