# Remaining local change integration and release

| Field | Value |
|---|---|
| status | blocked |
| current_stage | G3 · Authorized network guard proof and retained-build upload implementation |
| Controller | health-harness-orchestrator |
| Overlay | safety-gate |
| Scope | Reconcile explicitly authorized local unique changes onto current main; verify and release |

## Authorization and preservation

User requested all remaining local work be merged into main and released after
the read-only inventory. Preserve original dirty checkout at
`/Users/thomas/work/personal/health-llm-driven`; integrate into the already-used
task checkout, never replace current main with old local main. No App Review
submission is authorized by this continuation; mobile delivery is TestFlight.

## Run and baseline

- Run: `docs/_generated/harness-runs/fba4d0426bc4.jsonl` (32000 allocated-token cap).
- Initial canonical baseline: `dbad4e66c`; source local main: `9fb13ee63`.
- Local inventory: 21 tracked modifications, 13 untracked files; three original
  voice commits and HTML rendering runtime are already represented upstream.
- Integration slices: share-location backend; mobile location editor and privacy
  disclosures; medication-status prompt-only delta; reconcile historical audit
  documentation without rewriting current completion claims.
- Gates remain open: new fixed-candidate safety review, fresh CI-mode/full CI,
  live prompt evaluation, AMap/Redis configuration validation, native simulator
  acceptance and reviewed production/TestFlight lifecycle.

## G1 · Authorized reconciliation

裁决：PASS。User explicitly authorized integrating the inventoried local work into
main and publishing. Existing feature definitions govern each slice; this is
reconciliation, not new product scope. Original checkout remains untouched.

## Findings / release boundaries

Original GPS feature dossier requires actual AMap configuration, quota/license
and live integration verification before enabling the client. Missing configuration
must be explicit and fail closed; mocks do not establish provider availability.
Do not revive the previously rejected medication validator exception.

## Verification and delivery

- Client slice committed as `6954cc185`; backend and prompt are staged for a
  fixed-candidate independent review. No push, production mutation or vendor task.
- Location backend RED missing-module then GREEN 51 tests, four new modules
  coverage 96.19%; actual provider and Redis Lua remain unverified.
- Client RED missing modules then GREEN 63 focused tests; full mobile suite
  3272 passed / 1 skipped. Both client TypeScript checks passed after OpenAPI
  generation. No native build or simulator GPS acceptance is claimed.
- Prompt RED 7 failures / 18 pass; two failures additionally exposed absent Pi
  dependencies. Installed exact committed Pi graph with its standard installer;
  prompt/panel GREEN 67 tests without changing test doubles or safety validator.
- Combined project CI shard (prompt/panel/medical/composed-read/location/privacy)
  258 passed, exit 0. This is local integration, not remote full CI.
- Current map generated and checked; dossier consistency (172), secret scan and
  skill governance passed. OpenAPI regenerated both clients using locked deps.
- Initial local live LLM gate failed: offline inventories passed, orchestrator 0/5 because
  local TokenPlan credential is absent and fallback recipient is undisclosed.
  Did not grant disclosure or set a passing attestation. Production has a
  TokenPlan key, but has no AMap key; presence checks disclosed no secret values.
  Isolated synthetic server evaluation and GPS availability decision requested.
- Evidence logs: `/tmp/reva-voice-release.Jtlenr/integration-*` on this machine.

## G4 / G5 / G6

Independent read-only source review of `77017fbfff4c8fb4a4e487763142a9fa6a7b7ea3`
against `dbad4e66c29f31c0ae149fecefa6c0d4f3e45283`: **GO**, no confirmed code-level
safety/privacy blocker. Reviewer independently ran backend location/medication
tests (66 passed) and mobile location service/editor (31 passed, two suites),
all exit 0; diff whitespace check passed. Logs are
`independent-integration-{backend,mobile}77017.log` in the evidence directory.

The initial live LLM block was resolved by the explicitly authorized isolated
synthetic evaluation (see update below). Source review does not clear provider
readiness or native acceptance. No deployment or TestFlight task has been
started by this integration run. Original source worktree changes remain preserved.

Read-only concurrency check found a separate backend-only trusted release
`37100225023` running for canonical `dbad4e66c`; its CI `37098891748` is green,
but neither run contains this integration. Do not seize that operation/lease.
The user subsequently authorized isolated synthetic evaluation and requested
testing the provider first, hiding unavailable lookup controls, and assessing
alternatives to AMap.

## 2026-10-03 · Live evidence and fail-closed availability follow-up

- Exact `c487d834fb25f79ace21c7a1cf6c8cc137cb4aeb` isolated live evaluation
  passed: invariants 12, core 50, orchestrator 5 (average 0.92), trajectory 12,
  goldens 9. No production database access. Result evidence is
  `/tmp/reva-isolated-live-eval-c487d834-result.json`, SHA-256
  `dc00b4766094fb119b5199091c2cd387d43a2c5cd9951ddfcf9eb159717f3940`.
- This exact revision was fast-forward pushed to main with its passing live
  attestation. Remote full CI `37101325279` is now completed/success. This is
  not deployment or TestFlight evidence and does not cover the follow-up below.
- AMap personal account / backend Web-service key created; key remains absent
  from production configuration and client code. Console still reports no
  technical service usage license; test success does not authorize public use.
- Three bounded live requests from the existing backend host used only a public
  landmark's synthetic coordinates/query: coordinate conversion, reverse
  geocoding, and text search all returned HTTP 200, status 1 / infocode 10000,
  with nonempty results. Key passed transiently in memory/SSH stdin; no key
  value, user location or health data was logged or stored. Temporary loopback
  test bridge stopped after verification; no production configuration changed.
- Follow-up implementation: `SHARE_LOCATION_ENABLED=false` by default;
  authenticated, no-store availability endpoint checks explicit rollout approval,
  key presence and Redis health without calling AMap or using lookup quota.
  Enabling requires provider testing, applicable public-use permission and
  acceptance evidence. The boolean is an operator rollout gate, not automated
  legal verification or a continuous upstream-health guarantee.
- Client hides provider consent/GPS/search while readiness is unknown/false or
  a lookup fails. Manual input stays available. Availability calls neither read
  GPS nor imply query consent. Late replies after cancel, unmount, identity
  change or backgrounding cannot enable the controls. Foreground return checks
  readiness again and requires fresh query consent.
- RED: backend missing endpoint/flag (4 failures), service missing availability
  helper (6 failures), UI visibility/lifecycle tests (6 failures). GREEN:
  project CI-mode backend location/Redis privacy 55 passed; mobile share-flow
  regression 12 suites / 235 passed; mobile and frontend TypeScript passed.
  Both API clients regenerated; System Map and secret scan passed.
- Follow-up remains local/uncommitted, pending fixed-candidate independent
  safety review, exact revision full CI, simulator acceptance and release gates.
  No new deployment/upload is claimed. Existing harness delegation budget is
  only 500 tokens; no additional agent fan-out or budget reset was performed.
- Alternative recommendation (not implemented): evaluate iOS MapKit POI search
  against the same public-place sample before switching providers. System
  reverse geocoding can supply city/street but is not exact restaurant evidence.
  Any provider switch must revise the explicit disclosure/consent recipient;
  do not silently send a failed AMap request to another provider.

## 2026-10-03 · Authorized release attempt

- Synced the existing task checkout to green `19691af34` without changing the
  original dirty source checkout. Committed the availability delta as
  `514c8c28a87ad5761a6f66b284c19a69dff33e8f` and pushed it fast-forward to main.
- Fixed-delta independent safety review: **GO**, no source blocker. Reviewer
  checked auth/no-store/default-off, no readiness GPS/provider request, strict
  true/old API 404 failure handling and late lifecycle/identity replies; no
  independent test rerun in this bounded review. Final 500-token delegation
  allocation used; ledger budget exhausted, not reset.
- Fresh root evidence: CI-mode backend 55 passed; full mobile 326 suites,
  3286 passed / 1 skipped; mobile TypeScript, API types check, System Map,
  dossier consistency, secret scan and diff check passed. Exact remote full CI
  [37115395134](https://github.com/itsoso/health-llm-driven/actions/runs/37115395134)
  and trusted validate
  [37115918123](https://github.com/itsoso/health-llm-driven/actions/runs/37115918123)
  passed.
- Server canonical source acquisition first timed out before checkout. Confirmed
  source absent and no Git children; then used the existing approved, verified
  root-owned read-only production object cache to reduce GitHub transfer, with
  the same timeout. Exact HEAD, clean source, bootstrap/executor hashes and
  server-side CI gate matched. No local source was uploaded.
- Canonical old `dbad4e66c` authorization revoked; only its exact loopback
  private key was removed after revocation proof. Rotation returned `INSTALLED`
  for `514c8c28a`, retaining all old immutable audit and reusing the current
  cloud public identity under the established policy.
- Dispatched **one** release:
  [37116403140](https://github.com/itsoso/health-llm-driven/actions/runs/37116403140).
  Server readiness passed; backend and native build ran in parallel.
- Backend job `111184079533` failed during installed Laya prepare/reuse with
  `LAYA_BLOCKED:TimeoutError`. Exact server terminal is `NEEDS_OPERATOR`.
  Log explicitly reports backend writers unchanged; candidate/rollback env were
  sealed but live env was not installed. Production remains `dbad4e66c`, and
  fresh API/database/Redis/Celery health is healthy. Business lease, claims,
  sealed stage and failed evidence remain untouched. Laya later reported
  active/running, zero restarts and HTTP 200 health; this does not clear timeout
  or authorize replay/retirement.
- Exact EAS build `63b61a31-058c-44e5-bb82-67727ca7d073` is **FINISHED**, version
  `1.3.4 (274)`, bound to `514c8c28a`. This is build completion, not TestFlight
  upload/availability. Known backend failure must block the upload claim; retain
  the artifact and original workflow, do not create another build or clear claims.
- Final workflow is **failure**. TestFlight job `111185249225` failed at
  `Claim one-time TestFlight upload permission before exposing vendor credentials`;
  `Revalidate and upload the exact finished build` was **skipped**. Therefore
  this attempt did not upload build 274. Release-result failed as required.
- Supplementary local simulator build did not pass: regenerated native config
  with no tracked changes, but existing Pods retain Rokid SDK compiler flags and
  fail on `CxrClient`. No simulator acceptance is claimed; this is separate from
  the successful vendor device build. Do not overwrite the signed-in simulator
  with an old artifact and report candidate acceptance.
- Next action requires reviewed failure handling: diagnose Laya probe timeout,
  preserve and close this failed lifecycle under the applicable authorized
  operator procedure (including native artifact/claim state), then use a new
  reviewed revision/authorization for backend recovery. No automatic retry,
  lock removal, service restart, TestFlight upload or App Review submission.

## 2026-10-03 · Authorized incident follow-up

- User approved bounded repair, independent review and safe failure closure, then
  explicitly approved an additional maximum 16000-token independent-review
  allocation. Same run retained: append-only budget extension from 32000 to
  48000, original usage/history preserved. Trace tooling gains an audited
  extension command; it does not fabricate approval or reset usage. RED two
  missing-command failures, GREEN six CI-shard tests.
- Fresh main fetch equals `514c8c28a`; unrelated original dirty checkout remains
  untouched. Four real, synthetic Laya inference probes passed in 0.27–0.36 s;
  health 200 and invalid bearer 401. Service PID unchanged and zero restarts;
  backend API/PostgreSQL/Redis/Celery healthy on old `dbad4e66c`. Historical
  timeout substage is not recorded and root cause remains unproven. Existing
  swap usage is not proof of causation; do not increase timeouts or restart.
- Existing unchanged closure explicitly rejects native build markers. Independent
  design review: conditional GO for a dedicated finished-build-unuploaded profile,
  deployment NO-GO until fixed implementation review. No simple allowlist bypass.
- New bounded profile preserves original build claim/lock, requires upload claim
  absent, verifies live GitHub/Expo exact identities and terminal outcomes, and
  retains all installed-Laya/old-writer/env proofs and two-phase closure checks.
  No Laya asset, business behavior, vendor-create or upload path changed.
- Fresh read-only vendor proof succeeded: exact `1.3.4 (274)` FINISHED, correct
  project/bundle/SHA, not simulator, submissions empty; all six GitHub jobs
  terminal, attempt 1, upload step skipped. Normalized jobs digest
  `c9321070532105cf367379484031d45d2eee6872b675efc242a55f1858b4c0df`, build log
  digest `6ebf2b921b54225dfc62b6aec59014c92213a7a367981bbcfc2fca73b629ba3d`.
  Existing CLI credentials used transiently in memory, never logged/persisted.
- System Map selector does not index this operator; direct source/test analysis
  used, and full System Map check passed with the existing Python 3.12 runtime.
  Focused closure/proof regressions passed before adding remaining transport and
  history cases. Full CI deployment-invariant list is being run locally. Neither
  this local evidence nor design GO authorizes production execution.
- Still pending: final fixed-commit safety review, exact remote CI, canonical
  server staging and read-only inspect, matching-digest closure, new backend-only
  release, separately reviewed 274 pairing/upload, simulator acceptance. No
  production mutation, claim reset, new build or TestFlight upload in this round.
- Full local CI deployment-invariant list completed: 2058 passed, 9 skipped,
  84 subtests passed. Initial launch failed only because Python 3.12 was not on
  PATH; rerun with the existing project interpreter passed. This does not
  replace exact remote CI or Linux-only native boundary coverage.
- Fixed `ed28a52eb` independent review: **NO-GO**, one P1. Both newly introduced
  imports needed an explicit pre-import `__pycache__` rejection (`-B` prevents
  writes, not cache reads). Reviewer independently ran 185 focused tests.
  Added directory/dangling-symlink regressions: RED four failures, then guarded
  both import boundaries before loader execution or protected stdin reads.
  No push or production action occurred while review was blocked.

### Mixed closure G5 inspection checkpoint (2026-10-03)

- Fixed `7182799b96c59b91ca3ed3bd056ae1490988eccd` received independent GO;
  reviewer independently passed 189 focused tests and the actual CLI cache
  rejection before protected input. The user-authorized additional 16,000-token
  review allocation is exhausted; ledger total is 48,000 with no reset.
- Fast-forward main push, exact CI `37121193698`, trusted validate `37122003535`,
  fresh canonical root staging and its exact source/CI gate all passed.
- Canonical mixed-closure read-only inspection **BLOCKED**. Location-only
  exception diagnostics identify `RecoveryProof._units`: effective drop-in
  inventory differs. No execution digest was supplied, no closure intent was
  created, no authorization was revoked/rotated, and original lease/claims remain.
- All three business services have an additional root-owned regular `0644`
  `security-network.conf`, SHA-256
  `ab8e275de385f3622c44f50beff226686e608cb1ecffe54f11d5051832336964`.
  Its exact bytes match `scripts/harden_public_host.py`: the Unit Requires/After
  dependency on `health-network-guard.service`. The guard is active/exited with
  Result=success. The current closure proof accepts only the two runtime
  drop-ins; deleting the security dependency or ignoring unknown files is not
  an acceptable workaround. This observation is not yet a complete guard proof.
- Production is still `dbad4e66c29f31c0ae149fecefa6c0d4f3e45283`; fresh health
  HTTP 200, API/PostgreSQL/Redis/Celery healthy. No backend deployment or upload
  occurred. Original 274 artifact remains retained; no duplicate build requested.
- Local simulator Release build succeeded after regenerating ignored Pods with
  production's optional Rokid SDK disabled. Installed without uninstall/data
  clearing on the already signed-in iPhone 17 simulator; visible upper-right
  realtime voice entry opens the explicit-start page and exits correctly.
  Microphone/audio end-to-end was not exercised, and this is not the store 274
  binary. No private conversation content was saved as acceptance evidence.
- Next: authorize a new bounded independent-review allocation for the exact
  security-network composition proof, implement fail-closed tests, obtain fixed
  source GO and exact CI, then fresh canonical inspect before any closure.
  Separately reviewed 274/new-backend pairing and upload remain unimplemented.

### 2026-10-03 · User removes review budget blocker

- User explicitly requested deployment/upload and to ignore the budget. The
  previous review cap no longer blocks continuation. Existing ledger/history
  stays intact; additional accounting tranches do not create new user limits.
  Safety, exact-CI, one-shot claims and failed-operation evidence remain required.
- Health Harness continues the same incident; Safety Gate mandates independent
  review of the new fixed commit before push. Existing task worktree is reused;
  original dirty checkout remains untouched. No App Review or AMap enablement.
- Network proof implementation is bounded to the existing exact security
  dependency, its canonical guard/effective configuration, unchanged activation
  and final revalidation. Removing the drop-in or accepting arbitrary extra
  overrides remains forbidden.
- Read-only release-path investigation confirms the current `testflight` target
  always creates a new build. A separate fixed-274 retained upload path is
  required; original failed 514 claims, logs, artifact and terminal are immutable.
  Its design binds the final successfully deployed publisher revision to the
  unchanged app/runtime tree of 274, globally keys one-shot upload by build ID,
  holds a business lease across vendor submission, and independently verifies
  exact vendor completion before closing that lease. No arbitrary artifact IDs,
  retry of submit, fake backend success or claim reset is permitted.
- Fresh server read-only vendor proof passed for 274 with empty submissions;
  isolated old-production schema/KB probes also passed. These diagnostics do
  not clear the failing network inventory proof or authorize upload by themselves.
