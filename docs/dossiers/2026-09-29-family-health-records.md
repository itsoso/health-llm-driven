# Family health records delivery

| Field | Value |
| --- | --- |
| status | shipping |
| current_stage | S6 release validation |
| Primary controller | backend-deploy (release); Mobile OTA follows backend |
| Overlay | safety-gate |

## G1/G2 Scope and admission

裁决: PASS

Deliver existing-account family consent, daughter/son relationships, readonly
reports and illness records, and revocable access across Backend, Mobile and Web.
The admitted spec is `docs/specs/active/2026-09-29-family-health-records.md`.
No prescription changes, account merge, new credential or implicit proxy grant.
Existing models suffice; no family schema migration is required.

## Execution record

Updated: 2026-09-29 (Asia/Shanghai).
Implementation baseline: origin/main 623407d6d41d72b8f130aa2db765b2cbc6fba132; isolated worktree;
unrelated main changes preserved.
Scope: docs/specs/active/2026-09-29-family-health-records.md.
Router: feature; primary product-pipeline; safety overlay; S5 harness implementation.

## Delivery state
- G1: accepted, caregiver evidence/review flow, no medical decisions.
- G2: existing family models suffice, no schema migration; identity/consent checks required.
- G3: implementation complete locally in Backend, Mobile and Web.
- G4: focused verification and independent Backend/Mobile/Web safety review passed.
  Full repository CI-mode integration gate has not been run.
- G5/G6: in progress. User explicitly authorized commit, push, merge, deployment,
  and authenticated family association on 2026-09-29.
- Live relationship setup: pending authenticated owner/member flow. Existing API-key
  restrictions remain; no production family grant or credential was created.

## Implemented behavior
Authenticated invitations connect existing accounts with daughter/son relationships
and household nicknames. Owners can read authorized reports and illness timelines
without replacing their session or moving records. Existing registered accounts are
readonly; managed editing requires the original managing owner. Family listing,
dashboard, daily checks and weekly digest share the same grant boundary. Arbitrary
ID attachment, sibling reads, legacy unconsented editable links, revoked grants,
inactive subjects and proxy privilege expansion fail closed. Every caller can leave
nonowned household memberships even while owning another household.

Mobile and Web provide consent, record details, denied/retry states and revocation.
Shared details are not persisted; foreground/periodic reads revalidate permissions.
Server authorization revokes subsequent reads immediately; already visible client
records disappear on the next permission check, not by instantaneous push.

## Verification evidence
All data used by tests is synthetic. PostgreSQL tests use a dedicated local database
and a restricted role (not superuser, no BYPASSRLS). Explicit subject query filters
provide tested isolation; this is not a claim of database row-level security.

- Initial red test observed the missing member-health endpoint (404).
- Backend family + web-session + API-key scope suite: **46 passed**, 238.36 seconds.
  Local log: `/tmp/reva-family-backend-final.log`.
- Latest stable family suite: **25 passed**, 127.14 seconds. Coverage: new access
  service 89%, new record service 100%, family route 78%.
  Logs: `/tmp/reva-family-backend-stable.log`, `/tmp/reva-family-coverage-stable.json`.
- Mobile: **18 tests / 5 suites passed**, full TypeScript check passed.
  Focused ESLint passed. Scope: family screen, health details, relationship form,
  service requests and query persistence.
- Web: **9 tests / 4 suites passed**, full TypeScript check passed, including a
  red-first regression for dashboard denial with delayed proxy-status resolution:
  the user can still switch back to their own account. Focused ESLint has no errors;
  two existing navigation warnings remain.
- Ruff passed for new backend service/test files; git diff whitespace checks passed.
- System Map regeneration and generated-map/navigation/document drift checks passed.
- Independent safety review approved Backend/Mobile after legacy grant and multiple
  household revocation fixes. Web review found a managed proxy return-control issue;
  the recovery control is now visible during loading and errors. The new regression
  passed and independent review closed the finding with GO for the source changes.

## Existing regression and release boundary
A broader run including `test_agent_web_credential_relay.py` produced 24 failures
and 47 passes. Its first failure, `test_web_cookie_reaches_internal_owned_batch`
(cookie-only-stream), was reproduced on a separate untouched worktree at the same
623407d6d baseline: current Pi agent execution does not match the old `_call_llm`
mock and raises PiKernelError. This proves the representative failure predates this
change; it does not independently establish the cause of every one of the 24 failures.
Logs: `/tmp/reva-family-backend-tests.log`, `/tmp/reva-family-baseline-test.log`.
The earlier broader gate was not green. Release verification installs the locked
Pi Node runtime used by CI before repeating these tests; the old isolated test
worktrees did not contain that dependency. Final cause awaits the rerun result.

No iOS simulator acceptance, production request readback, deployment or OTA was
performed. Real relationship setup must validate the parent's normal authenticated
identity, create an invitation, accept in the existing child's authenticated account,
then read back the relationship and original reports from the parent account. Never
replace this with direct database grants, API-key bypass, a duplicate child profile,
or copying health records. Private identity details are kept outside the repository.

## Continuation
1. Authorization received. Release worktree rebased by applying the feature-only
   diff to origin/main 40d874f4dcefeead0a31b20975da762b3910e136, whose exact CI
   run 36575676539 passed. Generated both API client contracts.
2. Meet full CI-mode and applicable release gates; resolve the existing Agent
   regression as a separate scoped change rather than hiding the failed gate.
3. Release Backend/Web and Mobile through their supported release paths, then
   verify the actual owner/member linkage and read-only reports in the app.

## Release verification in progress
- Pi locked runtime install and its 26 Node tests passed.
- Latest-base Mobile18 and Web9 focused tests plus both full TypeScript checks passed.
- PostgreSQL family/auth/Agent relay/integration suite is running with the real Pi runtime.
- Production read-only inspection: clean source at 623407d6d; backend, Celery worker
  and beat active; local health reports API/database/Redis/Celery healthy.
- No production mutation yet. Candidate release must pass its own exact-SHA CI.
