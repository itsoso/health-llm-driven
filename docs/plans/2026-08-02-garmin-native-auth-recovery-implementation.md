# Garmin Native Auth Recovery Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Restore Garmin daily and workout synchronization on `garminconnect==0.3.6`, persist its native DI OAuth token store securely, and let Mobile users bind, reconnect and complete MFA.

**Architecture:** A small native-auth module owns client-shape checks, encrypted versioned token envelopes and safe authentication errors. `GarminConnectService` remains the orchestration entry point; workout sync and Celery renewal reuse it instead of maintaining parallel garth/curl-cffi paths. Backend remains the source of truth. Mobile connects through one server-side atomic endpoint: authentication and token serialization complete before one database commit replaces the old connection; failed immediate or MFA flows preserve the old connection.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy, Fernet, `garminconnect==0.3.6`, pytest, React Native/Expo Router, TypeScript, TanStack Query, Jest.

---

Implementation follows `@test-driven-development`, project `safety-gate`,
`@requesting-code-review`, and `@verification-before-completion`. Work remains
on `main` because the repository-level instruction explicitly makes `main` the
default and overrides the generic worktree recommendation.

Safety-review amendment: live Garmin clients are never cached after
authentication. Only pending, user-bound MFA challenges remain in memory, and
they are destroyed after at most five attempts or after encrypted token
persistence. `POST /auth/garmin/connect` replaces the original Mobile
save-then-test sequence; the legacy test endpoint remains side-effect-free.

### Task 1: Align The Local Garmin Runtime And Freeze The Production Regression

**Files:**

- Create: `backend/tests/test_garmin_native_auth.py`
- Reference: `backend/requirements.txt`
- Reference: `backend/requirements.lock`

**Step 1: Align the local package with the committed production pin**

Run:

```bash
cd backend
venv/bin/python -m pip install garminconnect==0.3.6
venv/bin/python -m pip show garminconnect
```

Expected: the second command reports `Version: 0.3.6`. Do not edit the already
exact `requirements.txt`/lock unless installation proves they are inconsistent.

**Step 2: Write the failing native-client regression test**

Add a test that constructs `GarminConnectService("nobody@example.com", "x")`,
calls its client factory without logging in, and asserts:

```python
assert hasattr(client, "client")
assert not hasattr(client, "garth")
```

Also assert the production package object exposes `client.dumps`,
`client.loads`, and `client.is_authenticated`.

**Step 3: Run the regression test and prove the current failure**

Run:

```bash
cd backend
venv/bin/python -m pytest tests/test_garmin_native_auth.py -q --no-cov
```

Expected: FAIL at the current `_create_patched_client` dereference of
`client.garth`.

**Step 4: Commit only the red test**

```bash
git add backend/tests/test_garmin_native_auth.py
git commit -m "test(garmin): reproduce native client regression"
```

### Task 2: Add The Encrypted Native Token Contract

**Files:**

- Create: `backend/app/services/data_collection/garmin_native_auth.py`
- Modify: `backend/app/services/auth.py`
- Modify: `backend/app/models/user.py`
- Modify: `backend/tests/test_garmin_native_auth.py`
- Modify: `backend/tests/test_garmin_sync.py`

**Step 1: Add failing token-envelope and credential-reset tests**

Cover all of these behaviors:

```python
envelope = encode_native_token_store('{"di_token":"secret"}')
assert "secret" not in envelope
assert decode_native_token_store(envelope) == '{"di_token":"secret"}'
assert has_native_token_store(envelope) is True
```

- legacy `{"oauth1_token.json": ...}` returns `False` from the non-throwing
  detector and raises `GarminNativeTokenError` from strict decode;
- malformed JSON and invalid Fernet ciphertext fail closed;
- saving replacement credentials clears `garth_session`,
  `session_expires_at`, stale MFA state and login lock;
- password encryption still round-trips through the generalized secret codec.

**Step 2: Run the focused tests and verify RED**

Run:

```bash
cd backend
venv/bin/python -m pytest tests/test_garmin_native_auth.py tests/test_garmin_sync.py::TestGarminCredentialFiltering -q --no-cov
```

Expected: FAIL because the token codec and credential invalidation do not exist.

**Step 3: Implement the minimal token contract**

In `garmin_native_auth.py`, define:

```python
TOKEN_STORE_VERSION = 2
TOKEN_STORE_FORMAT = "garmin_di_oauth"

class GarminNativeTokenError(ValueError):
    pass

def encode_native_token_store(payload: str) -> str: ...
def decode_native_token_store(envelope: str) -> str: ...
def has_native_token_store(envelope: str | None) -> bool: ...
def get_native_client(client): ...
def is_native_client_authenticated(client) -> bool: ...
def dump_native_token_store(client) -> str: ...
def safe_garmin_error_message(error: Exception) -> str: ...
```

The encoder must use the configured Garmin Fernet key through generalized
`GarminCredentialService.encrypt_secret/decrypt_secret` helpers. Strict decode
validates the outer dictionary, exact version/format and string ciphertext
before decryption. The safe error mapper returns only actionable categories
for credential failure, MFA, rate limiting, account lock and temporary Garmin
availability; it never returns the upstream exception verbatim.

Update the model comment so `garth_session` is explicitly a legacy-named,
encrypted Garmin token-store envelope. No schema change is made.

**Step 4: Make credential replacement invalidate old authentication state**

When `save_credentials` updates an existing row, clear its token envelope,
expiry metadata, `requires_mfa`, `login_locked_until`, error count and last
error. Keep the operation owner-scoped and commit once.

**Step 5: Run tests and verify GREEN**

Run the Task 2 command again. Expected: PASS.

**Step 6: Commit the token boundary**

```bash
git add backend/app/services/data_collection/garmin_native_auth.py backend/app/services/auth.py backend/app/models/user.py backend/tests/test_garmin_native_auth.py backend/tests/test_garmin_sync.py
git commit -m "security(garmin): encrypt native token store"
```

### Task 3: Migrate GarminConnectService To Native 0.3.6 Authentication

**Files:**

- Modify: `backend/app/services/data_collection/garmin_connect.py:18-310`
- Modify: `backend/app/services/data_collection/garmin_connect.py:443-880`
- Modify: `backend/tests/test_garmin_native_auth.py`

**Step 1: Add failing service-state tests**

Use fakes shaped like 0.3.6 (`Garmin.client`, not `.garth`) and cover:

- fresh login returns `(None, None)`, authenticates and saves an encrypted
  native store;
- native restore calls `Garmin.login(decrypted_token_payload)`, accepts token
  refresh performed by the library, and persists the newly dumped payload;
- legacy/malformed state is not passed into `login(tokenstore)` and falls back
  to credential login;
- `("needs_mfa", None)` registers an opaque five-minute MFA session and raises
  `GarminMFARequiredError` from normal sync;
- a passed authenticated native client is recognized without network access;
- logs and returned messages do not contain a fake password/token/email.

**Step 2: Run the tests and verify RED**

```bash
cd backend
venv/bin/python -m pytest tests/test_garmin_native_auth.py -q --no-cov
```

Expected: FAIL on `.garth`, legacy file-token handling and the old MFA tuple
shape check.

**Step 3: Replace the client/session primitives**

- Replace `_create_patched_client` with `_create_client` that only constructs
  the pinned `Garmin` wrapper.
- Rewrite `_save_session_to_db` to call `client.client.dumps()`, encrypt the
  payload and clear error/MFA state on success.
- Rewrite `_load_session_from_db` to strict-decode the envelope and call
  `client.login(token_payload)`. Let 0.3.6 perform DI refresh, then immediately
  persist the rotated dump.
- Treat token restore success as `client.client.is_authenticated`; do not use a
  fixed 23-hour expiry as authentication truth.
- Detect MFA from `result[0] == "needs_mfa"` regardless of the second element.
  Store the native wrapper, nullable returned state, Garmin account identity,
  `user_id` and expiry in `_mfa_sessions`.
- Make `_ensure_display_name` use wrapper profile fields or
  `client.client.connectapi`; never dereference `.garth` or log profile/email.
- Preserve login-lock behavior only for credential login when no valid native
  envelope is available.

**Step 4: Remove secret-bearing raw errors**

Use `safe_garmin_error_message` for stored/user-facing authentication errors.
Technical exception type and user ID may be logged; raw exception strings must
not be logged where they can contain SSO material.

**Step 5: Run tests and verify GREEN**

Run the Task 3 command again. Expected: PASS and no `.garth` access in the
service authentication section.

**Step 6: Commit the core adapter migration**

```bash
git add backend/app/services/data_collection/garmin_connect.py backend/app/services/data_collection/garmin_native_auth.py backend/tests/test_garmin_native_auth.py
git commit -m "fix(garmin): use native 0.3 authentication"
```

### Task 4: Repair MFA Ownership, Persistence And API Semantics

**Files:**

- Modify: `backend/app/services/data_collection/garmin_mfa.py`
- Modify: `backend/app/api/auth.py:1129-1270`
- Create: `backend/tests/test_garmin_native_mfa.py`

**Step 1: Write failing MFA tests**

Cover:

- a native MFA client resumes successfully even though stored `client_state`
  is `None`;
- a session created by application user A cannot be verified by user B;
- expired sessions fail without calling Garmin;
- a valid code for a saved matching credential persists an encrypted token and
  clears `requires_mfa`, `last_error` and failure count;
- wrong code remains retryable but the response and log exclude the code/raw
  upstream exception;
- the API sets `requires_mfa=True` after challenge and `False` after success.

**Step 2: Run tests and verify RED**

```bash
cd backend
venv/bin/python -m pytest tests/test_garmin_native_mfa.py -q --no-cov
```

Expected: FAIL because current code rejects a falsy state, has no application
user ownership and sets `requires_mfa=True` after successful verification.

**Step 3: Implement the user-bound native MFA session**

Change `verify_mfa_with_session` to require `user_id` and optionally receive the
request DB session. Match both application user and Garmin account before any
persistence. Call `client.resume_login(client_state, code)` even when 0.3.6
returned `None`, validate the native client, then persist through the shared
encrypted token helper. Retain only an authenticated short-lived session needed
for backward-compatible Web sync; never return native state.

Pass `current_user.id` and `db` from both auth endpoints. Correct the successful
MFA update to `requires_mfa=False`. Sanitize every failure message.

**Step 4: Run tests and verify GREEN**

Run the Task 4 command again. Expected: PASS.

**Step 5: Commit MFA recovery**

```bash
git add backend/app/services/data_collection/garmin_mfa.py backend/app/api/auth.py backend/tests/test_garmin_native_mfa.py
git commit -m "fix(garmin): persist user-bound MFA recovery"
```

### Task 5: Converge Workout Sync, Renewal And Process Startup On The Shared Adapter

**Files:**

- Modify: `backend/app/services/workout_sync.py:222-365`
- Modify: `backend/app/tasks/garmin_sync.py:416-590`
- Modify: `backend/app/scheduler.py:150-175`
- Modify: `backend/main.py:15-65`
- Modify: `backend/app/celery_app.py:12-20`
- Delete: `backend/app/services/garmin_cffi_patch.py`
- Delete: `backend/app/services/garmin_cffi_login.py`
- Delete: `backend/scripts/garmin_cffi_login.py`
- Modify: `backend/tests/test_garmin_native_auth.py`
- Modify: `backend/tests/test_garmin_sync.py`
- Modify: `backend/tests/test_security_audit_and_logging.py`

**Step 1: Add failing convergence tests**

Assert that:

- `WorkoutSyncService` accepts a passed 0.3.6 authenticated client;
- when no client is passed, workout authentication delegates to one
  `GarminConnectService._ensure_authenticated(db)` and reuses its client;
- `_renew_single_session` uses the shared service/token envelope and records
  `mfa_required`, `renewed` or a safe failure without importing `garth`;
- scheduler lock bypass recognizes a valid versioned envelope without a
  synthetic expiry;
- backend and Celery imports no longer invoke a global garth monkey patch;
- application source contains no runtime `client.garth`, `import garth`,
  `garmin_cffi_login` or `patch_garth_with_cffi` paths.

**Step 2: Run tests and verify RED**

```bash
cd backend
venv/bin/python -m pytest tests/test_garmin_native_auth.py tests/test_garmin_sync.py tests/test_security_audit_and_logging.py -q --no-cov
```

Expected: FAIL on the duplicate legacy workout/renewal/startup paths.

**Step 3: Delegate all authentication to GarminConnectService**

Use `is_native_client_authenticated` for a passed workout client. For fallback,
open `SessionLocal` in a context/finally block, instantiate the shared Garmin
service, call `_ensure_authenticated(db)`, and reuse its wrapper client. Do not
copy session/token code into workout sync.

Rewrite renewal to decrypt the owner credential, call the same service and let
native restore refresh/persist its DI token. Map MFA to `requires_mfa=True` and
a safe reconnect message. Remove old garth refresh/save and curl-cffi login.

Remove both startup monkey-patch calls and the obsolete compatibility modules
and script. Keep `curl_cffi==0.15.0` because 0.3.6 uses it internally.

**Step 4: Run tests and verify GREEN**

Run the Task 5 command again. Expected: PASS.

**Step 5: Commit convergence and stale-code removal**

```bash
git add backend/app/services/workout_sync.py backend/app/tasks/garmin_sync.py backend/app/scheduler.py backend/main.py backend/app/celery_app.py backend/app/services/garmin_cffi_patch.py backend/app/services/garmin_cffi_login.py backend/scripts/garmin_cffi_login.py backend/tests/test_garmin_native_auth.py backend/tests/test_garmin_sync.py backend/tests/test_security_audit_and_logging.py
git commit -m "refactor(garmin): converge sync on native auth"
```

### Task 6: Make Status And Manual Sync Actionable

**Files:**

- Modify: `backend/app/api/data_collection.py:144-330`
- Modify: `backend/app/api/data_health.py:80-125`
- Modify: `backend/app/api/admin.py:770-790`
- Modify: `backend/tests/test_garmin_credential_status.py`
- Create: `backend/tests/test_garmin_manual_sync_api.py`

**Step 1: Add failing status and API tests**

Cover:

- bound but never-synced credentials remain `bound=True` and are not mistaken
  for missing credentials;
- MFA takes precedence in status and returns a safe actionable error;
- a valid native envelope is considered resumable without
  `session_expires_at`;
- manual sync does not reject a stale `requires_mfa` flag when a valid native
  token exists;
- missing native token plus MFA returns an actionable 409;
- invalid credentials plus no native token asks for reconnect;
- auth, rate-limit and generic upstream failures map to safe details and never
  echo fake secret material;
- successful sync invalidates the Health Twin as before.

**Step 2: Run tests and verify RED**

```bash
cd backend
venv/bin/python -m pytest tests/test_garmin_credential_status.py tests/test_garmin_manual_sync_api.py -q --no-cov
```

Expected: FAIL on the blanket MFA/credential rejection and expiry-based status.

**Step 3: Implement the operational contract**

Use `has_native_token_store` wherever the system needs a cheap resumability
check. Do not decrypt tokens in status endpoints. In manual sync, only block
MFA/invalid credentials when no valid native envelope exists; let the shared
service be the final authentication authority. Catch Garmin domain exceptions
separately and return safe actionable HTTP details; generic upstream errors use
a temporary-service message rather than `str(e)`.

**Step 4: Run tests and verify GREEN**

Run the Task 6 command again. Expected: PASS.

**Step 5: Commit API recovery semantics**

```bash
git add backend/app/api/data_collection.py backend/app/api/data_health.py backend/app/api/admin.py backend/tests/test_garmin_credential_status.py backend/tests/test_garmin_manual_sync_api.py
git commit -m "fix(garmin): expose actionable connection state"
```

### Task 7: Add The Mobile Garmin Service And Connection Screen

**Files:**

- Create: `mobile/services/garmin.ts`
- Create: `mobile/services/__tests__/garmin.test.ts`
- Create: `mobile/app/garmin-connection.tsx`
- Create: `mobile/app/__tests__/garmin-connection.test.tsx`

**Step 1: Write failing service tests**

Mock `mobile/services/api.ts` and verify exact endpoints for status, atomic
connect, MFA, manual sync, toggle and delete. Add this safe extractor:

```ts
export function garminErrorMessage(error: unknown, fallback: string): string {
  const detail = (error as any)?.response?.data?.detail;
  return typeof detail === 'string' && detail.trim() ? detail : fallback;
}
```

Test that object/HTML/empty details are not rendered.

**Step 2: Run service tests and verify RED**

```bash
cd mobile
npx jest --runInBand --runTestsByPath services/__tests__/garmin.test.ts
```

Expected: FAIL because the service does not exist.

**Step 3: Implement the typed service**

Export `GarminCredentialStatus`, `GarminCredentialsInput`,
`GarminConnectionResult`, and one function per preserved API. Do not log request
payloads or errors because inputs include credentials/MFA codes.

**Step 4: Write failing screen tests**

Cover four states with mocked service functions:

- unbound screen shows secure email/password and calls the atomic connect endpoint;
- test returning `mfa_required` reveals a six-digit code input and verification
  completes connection;
- connected screen syncs, calls `invalidateHealthSnapshot`, then refreshes
  status;
- revoked/invalid state shows reconnect and the safe backend message;
- pause/resume and delete require explicit user action and refresh state;
- raw non-string server details never appear.

**Step 5: Run screen tests and verify RED**

```bash
cd mobile
npx jest --runInBand --runTestsByPath app/__tests__/garmin-connection.test.tsx
```

Expected: FAIL because the route does not exist.

**Step 6: Implement the smallest complete Mobile flow**

Build a single Expo Router screen using existing Reva tokens. Use
`secureTextEntry` for the password, no autofill for MFA, inline actionable
errors, disabled duplicate submissions and explicit destructive confirmation
for delete. The primary action changes by state: connect, verify, sync or
reconnect. On every successful state transition invalidate `['garminStatus']`;
after sync also call `invalidateHealthSnapshot`.

**Step 7: Run service and screen tests and verify GREEN**

Run both Task 7 test commands. Expected: PASS.

**Step 8: Commit the Mobile recovery flow**

```bash
git add mobile/services/garmin.ts mobile/services/__tests__/garmin.test.ts mobile/app/garmin-connection.tsx mobile/app/__tests__/garmin-connection.test.tsx
git commit -m "feat(mobile): add Garmin connection recovery"
```

### Task 8: Route Settings To Recovery Instead Of Blind Sync

**Files:**

- Modify: `mobile/app/settings.tsx:1-85`
- Modify: `mobile/app/settings.tsx:220-240`
- Modify: `mobile/app/settings.tsx:442-492`
- Modify: `mobile/app/__tests__/settings.test.tsx`

**Step 1: Write the failing navigation test**

Render Settings in healthy, unbound and MFA states. Press Garmin and assert:

```ts
expect(mockPush).toHaveBeenCalledWith('/garmin-connection');
expect(mockApi.post).not.toHaveBeenCalled();
```

Keep assertions for status text: `未绑定`, `需 MFA 验证`, `凭证失效` and a
non-negative last-sync age.

**Step 2: Run the test and verify RED**

```bash
cd mobile
npx jest --runInBand --runTestsByPath app/__tests__/settings.test.tsx
```

Expected: FAIL because Settings currently posts a sync immediately.

**Step 3: Replace blind sync with navigation**

Remove local Garmin syncing state and `syncGarmin`. Make `GarminStatusRow`
accept `onPress`, keep its factual status indicator, and always navigate to the
dedicated screen. Do not change Apple Health or unrelated settings behavior.

**Step 4: Run focused Mobile tests and type checking**

```bash
cd mobile
npx jest --runInBand --runTestsByPath services/__tests__/garmin.test.ts app/__tests__/garmin-connection.test.tsx app/__tests__/settings.test.tsx
npx tsc --noEmit
npm run design:check
```

Expected: all tests PASS, TypeScript exits 0, and the design-token ratchet
reports no new violations.

**Step 5: Commit Settings routing**

```bash
git add mobile/app/settings.tsx mobile/app/__tests__/settings.test.tsx
git commit -m "fix(mobile): route Garmin failures to recovery"
```

### Task 9: Close Gates, Review, Deploy And Verify Production

**Files:**

- Modify: `docs/dossiers/2026-08-02-garmin-native-auth-recovery.md`
- Modify: `docs/plans/2026-08-02-garmin-native-auth-recovery-design.md`
- Modify: `docs/specs/active/2026-08-02-garmin-native-auth-recovery.md`
- Modify if architecture generator reports drift: generated system-map outputs

**Step 1: Run backend focused regression**

```bash
cd backend
venv/bin/python -m pytest tests/test_garmin_native_auth.py tests/test_garmin_native_mfa.py tests/test_garmin_manual_sync_api.py tests/test_garmin_credential_status.py tests/test_garmin_sync.py tests/test_garmin_sync_health.py tests/test_garmin_daily_merge.py tests/test_garmin_readiness_paths.py tests/test_garmin_collector_p1a.py tests/test_workout_twin_invalidation.py -q --no-cov
venv/bin/python -m compileall -q app/services/data_collection app/services/workout_sync.py app/tasks/garmin_sync.py app/api/auth.py app/api/data_collection.py
```

Expected: all focused tests PASS and compileall exits 0.

**Step 2: Run repository contract gates**

```bash
cd ..
python3 backend/scripts/check_dossier_consistency.py
python3 scripts/check_system_map_drift.py
git diff --check
git status --short
```

If architecture drift is reported, run the documented system-map generator and
commit only its generated outputs. Do not hand-edit counts.

**Step 3: Perform the project safety review**

Commit the implementation first, then follow `.claude/skills/safety-gate` with
the base commit immediately before this feature. A BLOCK finding returns to the
owning task; deployment cannot begin until the review is PASS. Review especially
MFA ownership, encrypted-at-rest tokens, error/log redaction and owner-scoped
health writes.

**Step 4: Update the dossier through G4 and commit**

Record exact commands/results and the safety verdict. Run dossier consistency,
then commit only Garmin documentation.

**Step 5: Push the exact tested `main` commits**

Before pushing, inspect divergence and ensure no unrelated user files are
staged. Because local `main` is already divergent, reconcile with current
`origin/main` without dropping the user's existing commits or dirty files. Push
only after the exact tested history is understood.

**Step 6: Deploy backend first**

Run the repository `deploy.sh` workflow and require all G5 checks to pass. This
workflow may require the user-authorized production backup path defined by the
project deployment contract. Do not bypass it.

**Step 7: Verify backend without exposing secrets**

On production verify:

- deployed SHA and `garminconnect==0.3.6`;
- `Garmin` has native `.client` and no `.garth`;
- backend, Celery worker and beat are active;
- public health route succeeds and protected Garmin status rejects anonymous
  access;
- authenticated product flow can bind/reconnect/MFA and complete one manual
  sync; logs show counts/state only.

Record G5 and backend portion of G6 in the dossier.

**Step 8: Publish and verify the Mobile OTA**

```bash
scripts/mobile-ota.sh production "fix: restore Garmin connection and sync"
```

Verify the production app opens the Garmin connection screen, shows current
status, exposes reconnect/MFA when needed, completes sync and refreshes health
data. Record the OTA update identifier and final G6 evidence in the dossier.

**Step 9: Final verification commit and push**

Run dossier consistency and `git diff --check`, commit the final gate evidence,
push, and report only the commits, tests, deployment evidence and any remaining
external account action.
