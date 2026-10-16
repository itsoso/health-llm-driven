# Knowledge workspace sign-in with Health

Status: implemented and locally verified; production activation blocked on the governed configuration rollout path.

## Admission and boundary

The user wants to enter their private knowledge workspace using their existing
Health account rather than remembering another password. Health owns account
verification; KBase owns its browser session and knowledge data. This adds no
health query or write permission and does not change the external content
provider's own login. Existing passwords are neither copied nor synchronized.

This first version links **one explicitly configured Health owner** to the
existing private KBase workspace. It is not multi-tenant account provisioning.
A different Health account, managed account, unapproved/inactive account,
family proxy, API key or native bearer credential cannot mint a login ticket.

The Web page-freeze exception is limited to `/connect/kbase`: the requested
browser sign-in needs an explicit account confirmation in the Health cookie
origin before returning to KBase. A native-only screen cannot complete that
browser-bound exchange. `FREEZE_OVERRIDE` records this reason in the commit;
the existing freeze gate remains unchanged.

## Contract

1. KBase POST `/browser/health/start` validates its own Origin and existing
   browser client ID, captures the session family's current epoch, creates a
   random state and separate HttpOnly browser-binding cookie, and returns the
   fixed Health `/connect/kbase?state=...` URL.
2. Health shows the currently authenticated account. A user action POSTs
   `/api/v1/auth/sso/kbase` using the existing host-only Web cookie, exact trusted
   Origin, state and expected user ID. Only the configured owner can continue.
3. Health records a minimal identity-only issuance audit and returns a
   domain-separated HMAC-SHA256 proof with version, purpose, issuer, audience,
   subject, state, issue time and 60-second expiry. It cannot authenticate an
   ordinary Health API. No password, health content or Health session token is
   included. It is submitted in a POST body, never a URL or local storage.
4. KBase validates the exact Health Origin, all claims and browser binding,
   atomically consumes the pending transaction, then creates its normal secure
   host-only HttpOnly session using the captured epoch. Logout fencing wins over
   an in-flight login. Missing/expired requests and process restarts fail closed.

The pending request lifetime is five minutes; memory is bounded. KBase's Nginx
start endpoint must be rate limited. The Health page CSP permits form submission
only to the exact configured KBase origin; all other pages keep `form-action
'self'`. The login document uses `strict-origin` referrer policy so form POST
retains the issuer Origin without disclosing the request path/state.
`no-referrer` is not valid here: browsers serialize the POST Origin as `null`.
Origin configuration is operator-only, never taken from query strings.

## Configuration (no live values)

Health backend:

- `KBASE_SSO_ENABLED=true`
- `KBASE_SSO_SECRET`: dedicated randomly generated secret, at least 32 bytes;
  not the JWT signing key, KBase API key or existing browser proxy secret.
- `KBASE_SSO_OWNER_ID`: the explicitly verified owner account ID.
- `KBASE_SSO_ISSUER`: canonical HTTPS Health origin, no path or trailing slash.
- `KBASE_SSO_ORIGIN`: canonical HTTPS KBase origin, no path or trailing slash.

Health frontend build and runtime must receive the identical non-secret
`KBASE_SSO_ORIGIN`. It adds a route-specific CSP rule. If origins change, rebuild
and verify the **served** response headers before enabling sign-in.

KBase receives `KBASE_HEALTH_LOGIN_ENABLED=true`, `KBASE_HEALTH_LOGIN_ISSUER`,
`KBASE_HEALTH_LOGIN_SUBJECT` and `KBASE_HEALTH_LOGIN_SECRET` with corresponding
values. Its existing `KBASE_PUBLIC_ORIGIN`, browser session database and browser
proxy configuration remain required. The existing Nginx template and server
configuration must be installed together for the login rate-limit zone.

## Session lifecycle

This is unified **sign-in**, not global sign-out. Health sign-out, owner disable,
or turning off ticket issuance prevents subsequent login tickets; it does not
revoke a KBase session already issued. KBase's existing session expiry, renewal,
logout, device revocation and revoke-all controls still apply. During account
removal or a security incident, revoke the owner's KBase sessions too. Changing
the configured owner requires revoking all old KBase sessions before activation.

## Verification and release

Local evidence: identity-only and owner tests, real Health cookie endpoint tests,
origin/bearer/proxy/API-key rejection, real browser-family logout fence,
concurrent replay tests, existing session regression, frontend submission and
account-change tests, full Next production build, served route-specific CSP
headers, and generated map checks. No database schema migration or new package
was added.

Production enablement requires the exact verified revisions, independent safety
review, existing release gates, the standing release authorization, and an actual
owner browser round trip. Anonymous access, an unrelated Health account and
replayed/expired tickets must fail. Do not report local tests as production login.

### Local review receipt

Independent read-only security review: local implementation GO after fixing the
route CSP and replacing the login document's no-referrer policy. A real browser
with entirely synthetic form data reproduced `Origin: null` under no-referrer;
strict-origin preserved the correct source Origin and sent only an origin-level
Referer. The final production Next build's HTTP headers and HTML metadata were
read back locally and matched. No production credentials were used in this test.

Health verification: 28 focused backend tests, 25 connection-page tests,
production frontend build, CSP smoke and System Map check passed. No live
production login, merge or deployment is claimed by this receipt.

### Current activation blocker

The existing deployment policy grants standing code delivery authorization, but
`deploy.sh -e` explicitly disallows configuration changes under the no-backup
release policy. This integration needs new issuer/audience/owner/secret settings
on both services and the frontend origin at build time. Enabling it requires a
reviewed configuration-activation path; do not hand-edit production environment
files, bypass the gate, reuse an unrelated secret or invent a successful receipt.
The switch remains disabled until that path and the real owner round trip pass.
