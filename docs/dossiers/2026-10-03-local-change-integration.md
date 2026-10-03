# Remaining local change integration and release

| Field | Value |
|---|---|
| status | blocked |
| current_stage | G3 · Main and backend delivered; retained-upload runner bootstrap repair |
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
- Network proof committed locally as `e1dbf2f47c6185351648f9e8714a126fdc81289f`.
  Root and implementer each passed 238 focused tests. Independent reviewer GO:
  independently passed 238 tests plus injected canonical/file identity drift,
  duplicate dependencies, pending daemon reload and invalid boot identity; all
  negative cases refused. Scope is source-only, not production execution.
- Retained upload implementation adds a fixed `retained-testflight` workflow
  target and canonical claim/finish module. It preserves all original build
  records, holds a real business lease, binds original closure and exact deployed
  tree, and verifies the unique finished vendor submission. Module query schema
  was validated read-only against Expo: exact 274 FINISHED, empty submissions.
- Implementer targeted tests: 385 passed. Finalization fault tests cover durable
  UPLOADED before lock release, no-clobber move, parent-fsync failure, exact
  finish-only recovery and foreign-lease replay safety. Direct deploy.sh is not
  expanded; completion evidence is durable before its business lease can be free.
  Root has started the full CI deployment-invariant command list. No push,
  production closure, backend deployment or upload has occurred in this follow-up.
- Independent review of `c994c3c7a`: **NO-GO**, one P1 durability gap. The new
  retained audit root needed fsync of its persistent parent before any claim;
  sharing a test parent with the volatile business lease had obscured this.
  Independent review ran 608 tests / one truthful Linux-only skip and reproduced
  the missing parent sync with distinct persistent/volatile directories.
- Repair syncs STATE after validating the new/existing empty registry and before
  operation intent, lease or CLAIMED. Three initial regressions RED then GREEN;
  added separate-parent success/failure tests. Latest module 39 passed / one
  Linux-only skip. Full local CI invariant command completed 2148 passed,
  9 skipped, 84 subtests; it began before the last durability-test additions,
  which are covered by the separate fresh focused run and must run in exact CI.
  Await new fixed-commit review; no push or production action while NO-GO.

### 2026-10-03 · Exact CI test-harness correction

- Fixed `19fa0743692a7057a8e1e9d41df24079aff9487d` received independent GO:
  613 passed / one Linux-only skip plus separate-parent durability verification.
  Fast-forward pushed to main; no deployment or upload followed the push.
- Exact remote CI `37124819258` failed after 1099 tests at the real Linux
  no-clobber collision negative case. The operation correctly refused an
  existing destination, but this coreutils version raises CalledProcessError
  before the test's expected ValueError. Accept only these two refusal paths,
  require exit 1/exact command for the subprocess path, and retain both inode
  preservation assertions. Production move behavior is unchanged.
- Final local invariant run independently exposed an older QR-test SSH stub
  that exits without consuming the checksum pipe (SIGPIPE / exit 141), after
  1948 passed / 10 skipped / 84 subtests. The stub now consumes and validates
  all five checksum entries. No QR publisher behavior changes. Its exact test
  path is added to the retained-build operations-only comparison allowlist;
  runtime/native paths remain rejected. Both failures remain recorded, not rerun
  away or represented as passing evidence.
- Repair remains local pending fixed-source review and authorization to push a
  verified repair onto red main; new exact full CI must pass before release.
  Original failed release, production services, lease and vendor artifact remain
  unchanged. AMap remains disabled; no App Review submission is authorized.

- Follow-up fixed `2fda08c778088248b7cca38b2a928a38bc1a09bb`: independent
  **GO**, 61 tests passed / one Linux-only skip. Reviewer additionally checked
  both collision refusal paths and rejected an unexpected exit code; this is
  assertion simulation, not Linux execution. Secret, dossier, whitespace and
  complete runtime-tree compatibility checks passed. Final local full invariant
  run is in progress; remote Linux/full CI remains required.
- User then explicitly requested solving the problems before merging to main.
  This authorizes the verified repair push after local verification; it does not
  waive exact new CI or authorize replaying the old failed release. Preserve
  prior failed CI and all production/vendor evidence. Deployment/upload remain
  separate, not established by this main merge.

### 2026-10-03 · Main green, backend deployed, upload pre-claim blocked

- Final repaired source `12dd3e41838f8297eb50fdc2f99e01a832e082ca` received
  independent GO (audit-only follow-up to 2fda). Local full deployment invariant
  list: 2153 passed / 10 skipped / 84 subtests. Fast-forward main merge followed
  the user's explicit instruction; exact CI `37125777415` completed success,
  all 28 jobs passed, including the actual Linux collision case. Trusted validate
  `37126329445` also passed. Original failed CI is preserved.
- Canonical server source and exact CI verified. Mixed-closure read-only inspect
  passed, then one execution with the same evidence digest returned
  `CLOSED_UNCHANGED_RELEASE`. Original failed 514 terminal, claims, logs and 274
  artifact retained; original lease archived preserving inode, precise old
  identities revoked and old loopback private key removed. Sensitive receipt
  was captured to a private 0600 file, never printed, then consumed through
  protected stdin by canonical rotation. Rotation to 12dd returned `INSTALLED`.
- One backend-only workflow `37127520417` completed success. Actual production
  SHA is 12dd, its terminal is `SUCCEEDED`, internal/public API health reports
  API/database/Redis/Celery healthy, actual backend/socket/celery-worker/beat
  units are active with zero restarts. Auth/me and share-location availability
  return 401 without authentication. No live audio end-to-end claim is made.
- One retained-upload workflow `37128017147` failed in job `111217263989` at
  runner bootstrap after source/tool setup passed. It emitted only the static
  blocked message, about 54ms after Python startup. Server has no retained-build
  claim directory and no active business lease; independent Expo read confirms
  exact 274 still FINISHED with zero submissions. No new build or vendor upload
  occurred. Original failed workflow will not be rerun.
- High-confidence cause: official runner image commit
  `6d942e630479cd99a93dadfc766af11242bfa402` configures `/opt` mode 0777;
  strict helper loading rejects a writable ancestor before Git/import/network.
  The workflow normalized only `/opt/reva-release`, not its ancestor. A focused
  metadata reproduction fails at `/opt` before I/O. The failed VM did not retain
  its actual stat output, so image defaults are not presented as direct VM proof.
- Bounded follow-up: harden only exact `/opt` non-recursively on a fresh runner,
  keep strict loader checks, and exercise actual helper loading in Linux CI and
  before release credentials are exposed. Fixed-source review and a new exact
  CI remain mandatory. No bypass, claim reset or repeated submit is permitted.
- App Store Connect browser session needs login for later processing/availability
  checks; that does not explain this pre-upload bootstrap failure. AMap remains
  disabled, and no App Review submission is authorized.
- Runner repair RED: two new startup regressions failed before implementation.
  Associated tests GREEN: 392 passed / two Linux-only skips on macOS. The new
  dedicated sudo Linux CI test executes the workflow's actual hardening function
  against a private fixture and then loads the real canonical helpers, including
  ownership, mode, symlink, cache and byte-drift negatives. It does not modify the
  CI host's actual `/opt` or use vendor credentials. Fixed review and exact remote
  CI are pending; these local results do not prove the hosted run has passed.

### 2026-10-03 · Runner repair merged; second credential-free startup failure

- Fixed `3e830f9ddcf284428612a7b0fe60e34fd35247d2` received independent GO:
  374 passed / two Linux-only skips. Root full CI-mode deployment/rollback
  invariant suite passed: 2155 passed / 11 skipped / 84 subtests. Authorized
  fast-forward main push followed these checks. Exact CI `37129273858` then
  completed success, including the real root-owned Linux loader fixture and
  the complete release-invariants job. Trusted validate `37129885612` passed.
- Fresh canonical server staging attested the same SHA and CI. Normal retirement
  revoked 12dd's precise cloud/loopback identities and destroyed only its old
  internal private key after terminal/idle checks. Canonical rotation returned
  `INSTALLED` for 3e830, retaining original audit records. One backend workflow
  `37130246241` succeeded; production HEAD and immutable `SUCCEEDED` receipt
  both match 3e830. Internal/public health is healthy; backend/socket/worker/beat
  are active with zero restarts, protected auth and location routes return 401.
- Retained-upload workflow `37130728257`, job `111225171685`, failed in the new
  **credential-free** startup smoke. Root hardening, canonical materialization,
  Node and locked dependency setup passed. The credential/claim/submit step was
  skipped. Server has no retained operation and no business lease. No failed
  workflow is replayed, and no claim or receipt is reset.
  Independent fresh Expo read confirms exact build 274 remains `FINISHED` with
  an empty submissions list after this failure.
- The log still provides only the static blocked message about 52ms after
  startup. This does not identify the remaining cause. The previous Linux test
  exercises a two-helper fixture, not the entire hosted dependency/CLI pipeline;
  passing it cannot establish full runner readiness. Do not present an inferred
  mode/cache/source mismatch as observed VM evidence.
- Return to G3: add bounded, static credential-free diagnostic stages and a
  full-fidelity Linux startup check before another production cycle. Preserve
  root ownership, non-writable ancestors, no-cache, exact-source and clean-tree
  requirements. Run the diagnostic candidate on the task's isolated branch first;
  the user's instruction remains to solve the issue before merging into main.
  Backend delivery is confirmed; TestFlight upload and Apple availability are not.
- Diagnostic candidate adds allowlisted static startup codes and a Linux CI
  adapter that reuses the actual retained workflow's materialization, locked
  tools/patches and CLI steps. Only the test adapter omits the main-ref admission
  and circular requirement for already-green CI; real branch SHA and runtime
  checks remain. Production workflow admission is unchanged. The CI OS label is
  pinned to the same Ubuntu 24.04 as the publisher (parity test RED then GREEN).
  Associated local tests: 402 passed / two Linux skips; after OS parity change,
  retained/workflow tests: 111 passed / two skips. These are diagnostic coverage,
  not evidence that the remaining hosted-startup failure is solved.
- Independent review of the first diagnostic candidate returned NO-GO: placing
  the pipeline in the existing invariant job initializes Node before materialize
  and can make the repeated setup hit a cache, unlike the publisher. Corrected
  design uses a separate Ubuntu 24.04 job with no earlier Node/npm setup, then
  materialize → first pinned Node → actual tools → actual CLI; release-tests
  requires its success. Existing invariant job retains its original OS label.
  The adapter verifies the observed canonical repository instead of supplying a
  constructed identifier. Associated tests passed 416 / two Linux skips before
  the final exact-path regression. The CI runtime-version test recognizes only
  the already-reviewed publisher's exact setup-node v5 pin; its test-only file
  is explicitly added to the retained compatibility allowlist, with a RED/GREEN
  regression. Unknown files and runtime changes remain forbidden.
- Revised isolated candidate e609 received diagnostic-only independent GO
  (402 passed / two skips); combined local verification was 431 passed / two
  skips. It was pushed only to `codex/retained-runner-startup-smoke`. Branch CI
  `37132428781`, fresh-runner job `111230069230`, reproduced the failure after
  successful materialize/first-Node/tools steps: `CONTRACT_METADATA`. This is
  direct hosted evidence of a helper path metadata rejection, not yet proof of
  which path or metadata field. Main and production remain at healthy 3e830.
- Add CI-only fixed-path `stat` diagnostics after a failed smoke: only numeric
  ownership/mode and file types for six fixed public-source paths, no file
  contents, credentials, arbitrary selectors or production operation. Original
  failure is re-raised even if metadata collection fails. RED/GREEN covers exact
  paths, stripped token environment and diagnostic timeout failure propagation.
- Exact metadata candidate 791cf received diagnostic-only independent GO
  (131 passed / two skips). New branch CI `37132892840`, job `111231418588`,
  reproduced `CONTRACT_METADATA` and retained direct stat evidence: `/`, `/opt`
  and `/opt/reva-release` are root:root 0755; fresh `source` and `source/scripts`
  are root:root 0777; `built_unuploaded_proof.py` is root:root 0666. Thus the
  canonical checkout itself is writable, even after the `/opt` fix. This is
  evidence from the new isolated reproduction, not retroactive metadata from
  either discarded publisher VM.
- Bounded repair is to set `umask 077` inside the retained materialization's root
  shell **before Git creates the source**. An outer caller umask is insufficient
  because sudo may change it. Preserve strict owner/type/write/cache/hash checks;
  do not normalize an existing checkout recursively or accept writable sources.
  This fix remains on the diagnostic branch pending RED/GREEN, independent GO
  and the actual full Linux startup pipeline before main integration.
- Candidate 11fe passed local full CI-mode invariants (2173 passed / 13 skipped /
  84 subtests) and conditional independent source review, but fresh branch CI
  `37133407602`, job `111233049691`, still rejected `CONTRACT_METADATA` with the
  same 0777 directories / 0666 helper. Inner umask alone is therefore insufficient;
  this candidate is not approved for main or deployment. Main and production
  remain at 3e830. Do not infer the permission-changing stage from this result.
- Next diagnostic-only revision brackets materialization and actual tool setup
  with fixed six-path numeric stat / ACL reads, also retaining failed-smoke
  evidence. It prints no file contents, credentials or arbitrary selected paths;
  diagnostic failure never changes the underlying runtime verdict. Four RED
  failures preceded implementation; focused tests are 134 passed / four skips.
  This will distinguish initial ACL inheritance from subsequent metadata changes
  on a new isolated CI run, without replaying a failed release or vendor write.
