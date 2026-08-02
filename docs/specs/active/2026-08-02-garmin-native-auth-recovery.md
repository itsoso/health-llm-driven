# Feature Spec: Garmin Native Auth Recovery

> Status: approved
> Owner: Reva / Personal Health OS
> Updated: 2026-08-02
> Related PRD/PDD: docs/prd/reva-personal-health-os-prd.md · docs/specs/active/2026-06-26-wearable-router-v1-productization.md
> Related code: backend/app/services/data_collection/garmin_connect.py · backend/app/services/data_collection/garmin_mfa.py · backend/app/services/workout_sync.py · backend/app/tasks/garmin_sync.py · mobile/app/settings.tsx

## 1. Decision

Restore Garmin ingestion by adopting `garminconnect` 0.3.6 native DI OAuth
token persistence across authentication, refresh, MFA, daily sync and workout
sync, and make connection recovery available in the primary Mobile surface.

## 2. Problem

The backend pins `garminconnect==0.3.6` while its adapter still relies on the
removed `.garth` object. Garmin login, session restore and sync fail before any
network authentication can occur. Mobile only offers a direct sync action, so
an unbound, revoked or MFA-challenged user cannot recover inside the product and
receives a generic error that hides the required action.

If unchanged, Garmin data becomes stale, Wearable Router confidence degrades,
and downstream health guidance may be based on incomplete inputs.

## 3. Requirement Admission

```yaml
RequirementAdmission:
  request: Restore Garmin synchronization
  classification: bugfix + privacy-sensitive connector maintenance
  first_user_fit: yes - Garmin is an existing wearable source for the first-wedge user
  core_loop_step: Data In -> Health Twin -> verification
  first_class_objects:
    - HealthTwin
    - WearableRouter
  target_surface: Backend source of truth -> Mobile primary recovery surface
  source_of_truth: backend Garmin credential and encrypted native-token state
  safety_level: privacy_sensitive
  prescription_or_causal_verdict: none
  autonomy_tier: manual confirmation for bind/MFA; automatic only for an already enabled valid connection
  evidence_provenance: production reproduction + installed 0.3.6 API + upstream package contract
  claim_hedging: connection and sync status are factual; no medical claim is added
  verification_window: immediate manual sync and next scheduled sync window
  success_metric: valid accounts sync daily/workout data; revoked or MFA states are recoverable on Mobile; no plaintext secret is stored or logged
  added_user_burden: one-time reconnect or MFA only when the legacy/revoked session cannot be resumed
  burden_justification: recovery is required to re-establish an explicitly requested private data source
  non_goals:
    - Garmin Health API partner OAuth
    - new wearable metrics
    - new medical interpretation
    - Android-native device ingestion
    - Web redesign
  smallest_end_to_end_slice: Mobile bind/MFA -> encrypted native token -> manual sync -> persisted Garmin data -> refreshed status
  stale_surface_to_remove_or_archive: garth/curl-cffi compatibility authentication and generic Mobile sync-only behavior
  spec_required: yes
```

## 4. Non-Goals

- Do not add Garmin Health API partner integration.
- Do not add, reinterpret or rank health metrics.
- Do not change SafetyGuardian, diagnosis or treatment behavior.
- Do not redesign the secondary Web settings surface.
- Do not expose credentials, raw tokens or token-store contents to clients.
- Do not require a database migration for the recovery slice.

## 5. Product Object Mapping

| Object | Change |
|---|---|
| `HealthTwin` | Restores the Garmin input and its freshness. |
| `WearableRouter` | Restores an existing source; arbitration rules are unchanged. |
| `ExecutionEvent` | No new event type; sync status remains connector operational state. |

## 6. User Flow

```text
Settings -> Garmin connection
  -> load backend-owned status
  -> bind/reconnect and test credentials
  -> if challenged, enter MFA code
  -> backend stores an encrypted native token store
  -> user starts a manual sync
  -> backend writes owner-scoped daily/workout data
  -> Mobile refreshes health data and connection status
```

An already connected user can sync immediately. A revoked or legacy session is
shown as needing reconnect/MFA instead of failing generically.

## 7. Surface Contract

| Surface | Responsibility | Contract |
|---|---|---|
| Mobile | Primary connection and recovery UI | Inspect status, bind/reconnect, complete MFA, sync, pause or delete. Show actionable server errors without secret material. |
| Backend | Source of truth | Own authentication, encrypted token persistence, refresh, MFA state, scheduled/manual sync and user isolation. |
| Web | Secondary/admin compatibility | Continue using existing auth and data-collection endpoints; no redesign. |

## 8. Data Contract

```yaml
apis:
  preserved:
    - GET /api/v1/data-collection/garmin/me/credential-status
    - POST /api/v1/auth/garmin/credentials
    - POST /api/v1/auth/garmin/test-connection
    - POST /api/v1/auth/garmin/verify-mfa
    - POST /api/v1/data-collection/garmin/me/sync
    - DELETE /api/v1/auth/garmin/credentials
models:
  GarminCredential.garth_session: retained column, redefined as a versioned encrypted Garmin token-store envelope
fields:
  token_envelope.version: 2
  token_envelope.format: garmin_di_oauth
  token_envelope.ciphertext: Fernet-encrypted client token-store payload
backward_compatibility: legacy garth JSON is detected as non-native state and recovered by credential login or explicit reconnect
migration: no schema migration; successful native login replaces the legacy blob in place
```

## 9. Safety, Privacy, And Medical Boundary

This connector reads private wearable health data but does not make a medical
claim. All endpoints remain authenticated and user-scoped. Passwords and native
token stores are encrypted with the configured Garmin encryption key; no
password, token, MFA code or token payload may appear in logs or API errors.
Authentication failures expose only actionable categories. A malformed or
undecryptable token fails closed to re-authentication and never falls back to
another user's state.

## 10. AI Behavior

No LLM participates in authentication, token refresh, source selection or sync
success determination. All connector state transitions are deterministic.

## 11. Acceptance Criteria

```gherkin
Given garminconnect 0.3.6 has no Garmin.garth attribute
When a connected user authenticates or restores a native token store
Then the service uses the native client APIs and does not dereference .garth

Given a successful native login
When the credential is persisted
Then the database contains a versioned encrypted envelope and no plaintext token

Given Garmin requires MFA
When the user submits a valid code from Mobile
Then the backend resumes the same user-bound native client, stores the encrypted token and clears requires_mfa

Given a legacy, revoked or invalid session
When the user opens the Garmin Mobile screen
Then the product offers reconnect or MFA and displays an actionable non-secret error

Given a valid connected account
When the user starts a manual sync
Then owner-scoped daily and workout data are written and Mobile refreshes health state

Given scheduled token maintenance or workout sync
When authentication is needed
Then both paths use the same native token loader and never use garth/curl-cffi fallbacks
```

## 12. Verification Plan

```bash
# Backend focused tests and imports
cd backend
venv/bin/python -m pytest tests/services/test_garmin_native_auth.py tests/services/test_workout_sync.py tests/tasks/test_garmin_sync.py tests/api/test_garmin_auth.py tests/api/test_garmin_data_collection.py -q --no-cov
venv/bin/python -m compileall -q app/services/data_collection app/services/workout_sync.py app/tasks/garmin_sync.py

# Mobile focused tests and type checking
cd ../mobile
npx jest --runInBand --runTestsByPath __tests__/garmin-connection.test.tsx __tests__/settings.test.tsx
npx tsc --noEmit

# Contract and repository hygiene
cd ..
python3 backend/scripts/check_dossier_consistency.py
python3 scripts/check_system_map_drift.py
git diff --check
```

Exact existing test paths may be adjusted in the implementation plan after the
repository test layout is confirmed; no listed gate may be silently skipped.

## 13. Rollout And Rollback

Deploy the backend first and verify authenticated route health plus a
secret-free native-token diagnostic. Publish the Mobile recovery screen by
production OTA only after backend verification. Existing native envelopes stay
in the same database column, so no destructive rollback migration is required.
A code rollback restores the prior non-working Garmin adapter but leaves the
rest of the system and stored encrypted bytes intact; forward-fixing the adapter
is the supported recovery.

Legacy sessions are migrated opportunistically through encrypted stored
credentials. Users whose account requires MFA complete one Mobile recovery step.

## 14. Open Questions

- A future project may replace password-based consumer login with Garmin Health
  API partner OAuth; it does not block this compatibility repair.

## 15. Changelog

| Date | Change | Reason |
|---|---|---|
| 2026-08-02 | Approved initial recovery contract | Restore production Garmin ingestion after the 0.3.6 dependency migration. |
