# Feature Spec: Verified phone registration and administrator admission

> Status: implementation
> Owner: Reva engineering
> Updated: 2026-10-26
> Supersedes: invitation-only admission for current clients and production.

## Decision and problem

Allow a new user to register by verifying an SMS code, without an invitation.
Allow an authenticated administrator to create and approve accounts directly.
The previous invitation policy rejected both flows while the interfaces still
offered them and obscured the rejection with generic errors.

## Requirement admission

```yaml
RequirementAdmission:
  request: Remove invitation-only admission; allow verified-phone registration and administrator creation.
  classification: account-access capability
  first_user_fit: Users ready to start their personal health record.
  core_loop_step: Establish authenticated ownership before onboarding.
  first_class_objects: User identity; no health object changes.
  target_surface: Backend, Mobile, Web admin and registration.
  source_of_truth: Authenticated server policy and persisted verified phone.
  safety_level: authentication-sensitive
  prescription_or_causal_verdict: none
  autonomy_tier: User explicitly verifies phone; administrator explicitly creates account.
  evidence_provenance: Current source, bounded production diagnostics, regression tests.
  claim_hedging: Local validation and production activation reported separately.
  verification_window: OTP expiry and immediate post-release acceptance.
  success_metric: New verified phone creates one account and receives a session without invitation.
  added_user_burden: none
  burden_justification: SMS verification proves control of the phone.
  non_goals: Unverified phone binding, bulk creation, automatic AI consent, opening health data.
  smallest_end_to_end_slice: Request SMS, verify, create account atomically, establish session, enter onboarding.
  stale_surface_to_remove_or_archive: Normal invitation shortcuts and Web invitation application form.
  spec_required: yes
```

## Surface and data contract

- Backend retains `/auth/phone/code` and `/auth/phone/verify` and the older
  `/auth/phone/login` contract. New verified users receive `is_new_user=true`;
  existing users log in without another account being created.
- Administrator creation remains administrator-only, with existing password,
  uniqueness, active/approved status, and authorization audit checks. It does
  not attach or verify a phone entered elsewhere.
- Mobile keeps account-password login and the existing secure token persistence
  flow. Business error codes take precedence over Axios transport codes.
- Web registers through the same OTP endpoints using HttpOnly cookie sessions;
  no bearer token is stored in browser storage. Old invite applications cannot
  create unverified accounts in public-registration mode.
- Historical invitation data and compatibility code are retained; current UI
  and the target production policy do not require invitations.
- No schema, health-data access, AI-consent, or native dependency changes.

## Safety and verification

Keep OTP expiry, one-time consumption, failed-attempt limits, Redis-backed SMS
phone/IP/global limits, and refusal when quota storage is unavailable. Disabled
or unapproved existing accounts cannot reregister. Account merging always
requires both accounts active and approved, independently of admission flags.
The emergency closure stops new OTP registration on both verification routes;
existing approved accounts can still log in.

Verify administrator authorization, existing-account collisions, truthful error
messages, no invitation in the normal registration journey, transactional
rollback, and PostgreSQL concurrency. Release requires exact-revision CI and an
independent safety review. Production configuration is changed only through a
reviewed, fixed-field, no-backup activation with durable evidence and runtime
readback; changing source defaults is not production activation.
