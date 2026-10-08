# Production prompt task completion

| Field | Value |
| --- | --- |
| 状态 | backend and frontend published; dependency mitigation and frontend availability verified |
| 当前阶段 | G5 backend/frontend receipts complete; G6 page and service readback verified; OAuth grant not exercised |
| Controller | health-harness-orchestrator |
| Overlay | safety-gate |

## Scope and admission

The user authorized the improvement plan derived from their production prompt
history. Deliver the three P0 paths first: owned reads, meal portion corrections,
and multi-day water backfill. This batch also repairs bounded P1 continuity and
historical-context provenance. Preserve owner isolation, explicit
write authorization, cancellation, verified receipts and idempotency.

Base: `d4628eecd341afcf1e533c5114907a5ba2c84de0` from freshly fetched origin/main.
The shared primary checkout is dirty and is not modified. No raw production
prompts, personal health values or credentials are committed; tests use synthetic
data and deidentified utterances.

## G3 acceptance

- Owned read requests resolve identity from the authenticated principal, preserve
  bounded dimensions and dates, and do not reject valid self queries as foreign.
- Meal corrections retain one verified meal target and absolute portion semantics;
  ambiguity produces a usable selection, not an arbitrary update or duplicate.
- Multi-day water requests preserve date and exact-versus-lower-bound semantics;
  missing facts receive targeted clarification, verified writes are not replayed.
- Add failing behavior regressions before implementation, then run adjacent
  authorization, cancellation, tenant isolation and user-flow tests.

## G4 safety

Independent review initially rejected `ecc1d7540071f2c9f639760656d797678868545b`:
the water path bypassed the Agent Runtime write circuit and the meal authorization
fingerprint omitted transitive executor dependencies. Both were reproduced with
failing tests and corrected in `f683d6f2ebfd7a54455674b441dd3baa14689a21`.

Independent fixed-commit rereview: **GO** for `f683d6f2e`, 52 passed and 3
PostgreSQL-only skips. Paused/unavailable water confirmation produces no health
writes or receipts, preserves the pending plan, and can resume after recovery.
The existing explicit manual WriteIntent API retains its own admission boundary.
Meal dependency changes and water grammar/expiry/execution changes now alter
the runtime authorization contract. No safety gate was waived.

## Implemented acceptance surface

- Self-read grammar now handles multi-domain insight and report-based exercise
  planning; unsupported restrictions and foreign owners remain blocked.
- Saved-meal corrections bind a single current owned row and original baseline.
  An immediate short follow-up can bind a verified receipt within 24 hours.
  Ambiguity shows up to five copyable explicit commands, not a new selection UI.
  Pending meal drafts never inherit permission to change a persisted record.
- Water totals use a source-bound manual WriteIntent and dated preview, expire
  after 30 minutes, and atomically add only missing amounts. PostgreSQL confirmation
  holds a short table lock to serialize against legacy writers; lock timeout is
  three seconds, no network/model work runs while holding it. A changed baseline
  requires a new preview. Replay describes historical targets, not current totals;
  no-op dates are revalidated and never receive invented write receipts.
- Sync plus an explicit bounded analysis gets one missing read through the normal
  Pi/gateway. Existing data and sync-job success remain separate evidence. No
  background polling or completion-triggered wakeup was added.
- Short acknowledgments and HTML-format requests retain an existing owned read
  scope. The early short-input gate now checks that scope before clarification.
- Expired conversation memories are excluded from context/openers. Medical
  conversation memories retain report time and self-report/clinical uncertainty.
  This does not implement a new persistent clinical-recovery state machine.
- New synthetic regressions verify dispatch, real adapter results, persisted
  outcomes, write receipts and negative authorization cases rather than model stop.

## Verification evidence

Producer tests before integration: owned-read reproduction 7 failures, sync/device
reproduction 5 failures, memory provenance/expiry 2 failures, short-ack full flow
1 failure, and new receipt grammar fingerprint 1 failure. Each was made green.

Fresh targeted evidence: read suites 378 passed; capability-policy suite 2189
passed; meal suite 231 passed with 2 PostgreSQL skips, separately PostgreSQL 11
passed; signed-portion/CAS PostgreSQL 13 passed including concurrent one-winner
updates; water PostgreSQL final 33 passed, adjacent suite 256 passed with 3 PostgreSQL
skips; memory/context PostgreSQL 23 passed. These overlapping counts are not a
combined test total.

First broad CI-mode integration: 5008 passed, 5 PostgreSQL skips, one obsolete
assertion failed because a valid meal correction now performs an owned, date/meal
bounded lookup before presenting ambiguous candidates. Updated that test to
verify the exact lookup, candidates, zero writes, no receipt and failure state.

Final CI-mode integration on `f683d6f2e`: **3907 passed, 5 skipped**, 208.47 seconds,
33 files, `DATABASE_URL=sqlite:///:memory:`, `TZ=Asia/Shanghai`. The long synthesis
projection matrix passed in the earlier broad run and was not repeated for the
narrow circuit/fingerprint/test-assertion corrections. PostgreSQL-only tests are
verified separately; a SQLite skip is never counted as a production DB pass.

Live synthetic LLM gate passed: invariants 12/12, health_agent_core 50/50,
orchestrator 5/5 (final fixed-code run average rubric score 0.94), trajectory contract 12/12 and
trajectory goldens 9/9. Run used a consented synthetic subject in in-memory
SQLite and configured provider credentials. Optional usage-log/budget tables
were absent in that harness database; warnings are retained in the local log,
so this is not production cost-accounting validation.

System Map regenerated from code and its drift gate passed. Full user-interface,
production write, native device and long-running background acceptance were not
performed. Existing production health records were not changed for testing.

## G5 release and G6 production validation

Application candidate `18b654f03883faa339aca32f9ec663210855f07a` was pushed to
GitHub main after exact-commit live-eval confirmation was published and read back.
Base main `d4628eecd` had successful CI `36880139929`. The application candidate's
CI `37024818933` completed successfully. Trusted Release validation
`37025971817` also succeeded for that exact SHA. The validation target skips
backend/native production jobs and is not a deployment receipt.

The earlier HTTP 401 was caused by stale environment-token overrides. Removing
`GH_TOKEN` and `GITHUB_TOKEN` for the CLI selects the existing valid system-keyring
login. Authenticated identity, repository permissions and Actions variable access
were verified; no new credentials or scopes were created.

Fresh production read-only inspection still shows backend
`30ac1c67be7b2df79363ac7509f70f8a56ce4834`, healthy API/database/Redis/Celery, an
active enabled GitHub relay, and no business release lease. Current permanent
release authorization remains bound to
`e19043ecb269e20f3bc0a546165e43d467f1fc8c`. Its native-only workspace has exactly
`build-started.json`, `native-started.json`, `testflight-base.json`, and
`build.lock`; it has no backend success receipt. Trusted TestFlight run
`36877321184`, attempt 1, was rechecked as successful.

The existing native-closure operator accepts only a different fixed historical
candidate. A narrow second profile for TestFlight 273 is implemented and independently
reviewed; its production use still requires authorization. Its expected build is
`20d5e73a-a6b9-4c70-ad69-e63d31e058f2`, submission
`fcfbb57d-4804-4a36-9c57-eab062bf321e`; exact workflow, jobs, original log bytes,
canonical publisher bytes and retained workspace must all match. Unknown
profiles, incomplete evidence, active leases/processes and replay remain blocked.

Proposed production sequence, requiring separate authorization for release
credential/permission changes: verify the exact canonical source and vendor
evidence; revoke only the current bound identities and remove the exact old
loopback private key as required by the canonical retirement contract; then run
the closure inspection and close the exact native-only operation with its matching
evidence digest; pass its
private receipt through protected stdin to the canonical SHA-bound rotation;
then validate and run the backend-only trusted workflow. Preserve original claims,
lock inodes and retirement history. Never relabel native-only work as backend
success, repeat an upload, delete old claims, or print private receipts. New
loopback identity generation is part of rotation; the current dedicated cloud
public key may be retained only if the canonical policy permits it.

Closure source verification: 67/67 focused tests passed, and the independent
review reran those tests successfully. The final seven-file release integration
passed **482 tests in 42.44 seconds** across native closure, bootstrap, server,
GitHub gate, workflow, TestFlight-only and EAS build contracts. Real read-only
`vendor_evidence()` verified the exact run/jobs/log and canonical hashes. The new
profile pins its distinct GitHub log storage host; cross-profile hosts and token
forwarding to storage are rejected. System Map drift, secret scan, dossier check
and selected blocking Ruff checks passed. The LLM change classifier marked this
release-only repair `live_llm_required=False`; application runtime is unchanged
from the previously live-evaluated candidate.

Independent reviewer accepted frozen helper SHA-256
`530a38e78eda0a13baed840d12bb8b7077ee4ca2ad6e1b81accc6f372de4afc0`
and test SHA-256
`d84b98d96761336543708b4624f359f86538c0f1dff6572f7466daa356bf89fe`.
Final commit binding is recorded in the local release evidence after commit.

Formal closure inspection itself requires proof of prior revocation and absent
loopback private key. Its live preconditions have not been satisfied or waived;
the currently active release identity is preserved pending explicit authorization.

No production closure, authorization rotation, backend deployment or production
health-data write has been performed by this task. Local source/CI evidence is
not production acceptance.

## Follow-up full-CI security blocker

Closure commit `b77374c002be473e5572314169427baf5cf80998` received exact G4 GO and
was pushed after the application candidate was green. Its full CI `37027725041`
failed the mobile production dependency audit on `node-forge@1.4.0`,
`GHSA-86w9-cpqp-85rv` (HIGH). The original application CI success does not override
this later failure. External writes and production release are paused while the
fix is prepared locally.

The npm registry still reports 1.4.0 as latest. The reviewed advisory reports no
published fixed version; upstream PR 1152 is open at
`ceba34402e329f0365134f23fe19898756527d65`. The dependency is used by Expo code
signing and CLI paths, and by the separate EAS release-tools installation. No
claim is made that a deployed client is proven exploitable or that the issue is
unreachable. Sources: [advisory](https://github.com/advisories/GHSA-86w9-cpqp-85rv),
[upstream fix](https://github.com/digitalbazaar/forge/pull/1152).

The local repair must keep the real 1.4.0 identity and empty audit exceptions;
backport the exact reviewed nested-DigestAlgorithm validation; bind original,
patch and installed file digests; and execute malicious/valid signature cases
against every installed copy. OSV findings remain visible as verified backports
only when those fresh checks pass. Missing copies, mixed versions, symlink
escapes, changed bytes, partial audit responses and unrelated advisories fail
closed. Trusted build/upload/OTA `--ignore-scripts` installations must apply and
verify both roots before credentials or vendor calls. This is a project backport,
not an official upstream fixed release or a risk waiver. The fixed backport has passed implementation and independent review. Final
local evidence: **35 security tests passed, 0 skipped**; **512 release integration
tests passed in 41.34 seconds**; EAS consumer compatibility **3 passed**; mobile
TypeScript check passed. Both real installation roots first rejected the original
package, then accepted the fixed patch and idempotent reapplication. Live OSV
queries on each root returned a single verified backport while retaining the
original HIGH advisory and exact lock path. Unknown/other advisories are not
suppressed. Package versions, lockfiles and `exceptions=[]` remain unchanged.

Independent review reran 35 tests, checked both real installed copies, compared
the entire patched RSA file to the fixed upstream commit, and verified fresh-runner
credential ordering and EAS archive/postinstall coverage. The final patch-format
normalization only removes unchanged hunk context to satisfy whitespace hooks;
the resulting RSA bytes remain identical to upstream. Final commit binding and
local check logs are retained in the local release evidence.

No cloud CI success is claimed for this unpushed fix. Current remote main remains
`b77374c002be473e5572314169427baf5cf80998`, with failed CI `37027725041` (mobile
audit failed; the other 27 jobs succeeded). Under AGENTS section 7, external writes
remain paused pending explicit authorization to publish the verified repair.
After publication, require fresh exact-SHA full CI and trusted validate; only then
can separately authorized native closure and release-identity rotation proceed.
No native build/upload or OTA is included in the next backend-only release.

## Braces HIGH follow-up (2026-10-03)

User authorized resolving the new HIGH dependency vulnerability, then releasing.
Refreshed current main is `f966e97394005bc0b9f297b4132ef5ab61500e2a`; its CI
`37080647733` failed on `braces@3.0.3` / `GHSA-vfj7-8cjw-p6xm`, while the prior
node-forge backport passed. Production remains `30ac1c67`, not the candidate.

The npm registry still reports 3.0.3; [upstream issue 70](https://github.com/micromatch/braces/issues/70)
remains open and recommends a depth bound. This is a local mitigation, not an
upstream release: parser bounds combined brace/parenthesis depth, and all three
recursive public/internal AST walkers reject excess depth. Literal, escaped and
normal patterns remain compatible. Invalid inputs raise a controlled SyntaxError;
this does not claim to fix arbitrary caller exception handling or other resource limits.

The first regression run failed 21 of 22 cases against the original package.
The fixed run passed all 22. Actual installation verification pins original and
fixed source bytes, unchanged executable inventory, package identity and every
nested installed copy. Normal mobile patch-package and all ignore-scripts trusted
release installations apply the same bytes. Frontend's self-contained build guard
also survives the frontend-only production build sandbox. OSV retains HIGH findings
as verified_mitigation with per-installation evidence; exceptions remain empty.
New fixed-SHA independent review, full CI and release preflight are still required.
Production authorization and release state have not been mutated.

## Work log

- Workflow ledger: `docs/_generated/harness-runs/2b523da0635a.jsonl` (local ignored evidence).
- 2026-10-02: began reproducing the production prompt failure paths.


## 2026-10-03 redeploy recovery

Fresh main and observed production are `5c3eb6ed2c0c7f18f2a36443aee4216f5fe21670`.
Exact CI 37091538573 and Trusted validate 37097918074 passed. Independent review
of this baseline: 355 release tests passed, two isolated-Linux skips; braces
regressions 30 passed. The former unknown lease and stage are gone. The runtime
transaction reports COMMITTED/finalized from 30ac1c67 to 5c3eb6ed2, but no trusted
backend SUCCEEDED receipt exists for 5c. Production frontend braces verification
fails (mitigation not applied); canonical internal/public /connect/health is 404.
Backend health and /privacy return 200. This is not complete delivery.

Add an explicit, fixed-profile native-retirement continuation for this exact
finalized transaction. Preserve the completed native closure and its protected
receipt; never manufacture backend success. Validate live revision/CI/services,
original transaction bytes and metadata, idle/process/transaction boundaries,
and capture immutable proof in retirement history. Default rotation is unchanged.
Only a subsequent real trusted backend deployment may provide the receipt needed
for isolated frontend publication. First new regression run: 17 expected failures
before implementation; focused recovery/bootstrap/native suite now 244 passed.
Full release suite and fixed-commit independent review remain pending.


The recovery candidate `dbad4e66c29f31c0ae149fecefa6c0d4f3e45283` passed independent
G4 (244 tests), exact CI 37098891748 (release integration 1955 passed, nine skips,
84 subtests, plus three isolated Linux tests) and validate 37099468139. The
redundant local full suite was interrupted after exact Linux CI passed and is
not recorded as a local pass. Canonical production preflight and rotation passed;
old e190 retirement and new dbad authorization were read back. The local private
closure receipt was removed only after the server's protected intent preserved it.

Trusted backend run 37100225023 succeeded, with exact dbad SUCCEEDED receipt,
60/60 final health, finalized runtime transaction, schema rollback probe and
serving contracts. Database dump/restore/offsite were skipped under the existing
explicit user default in deploy governance; environment backup was performed.
The earlier recovery paragraph incorrectly implied unconditional DB backup and
has been aligned with that authoritative preference, without changing the policy.

Frontend operation `c117171afc9e4bc2a85ee6ddfa419d85` has not created an intent or
lease. Its read-only preflight rejected the existing allowlisted build endpoint
`http://localhost:8000`, while the fixed service uses `http://127.0.0.1:8000`.
Normalize only those two already allowed loopback values into the fixed build
address, preserving original file bytes and fingerprints; other endpoints remain
rejected. Regression reproduced one failure with five passing negatives before
the one-line correction. Frontend publication and actual mitigation verification
remain pending. No new backend or native release is required for this correction.
# Authorized frontend incident continuation, 2026-10-03

User explicitly confirmed publication and takeover of failed operation
`637078dd8c584686a59000de91d2dad2`. A fresh readback found the old frontend
already restored: privacy 200, connection page 404, backend health 200, backend
still `dbad4e66c29f31c0ae149fecefa6c0d4f3e45283`. No successful new frontend
receipt existed. Original failure and lease remain intact.

Latest canonical main `6fe7f37e3134443fc085aed7b647c43247f52611` includes the
reviewed SIGTERM-143 stop fix from PR #276; exact CI `37106733928` succeeded.
The overlapping local `8550aa835` fix is preserved on
`codex/preserve-frontend-stop-855` rather than duplicated on main.

A fixed-operation continuation reuses the original verified built candidate,
preserves all original evidence and the original lease, and records a separate
recovery chain. It cannot publish another frontend tree, retry an attempted
recovery, retire another lease, alter backend/config, or bypass failed history.
Fresh fixed-candidate independent review and exact CI remain required before
execution. Availability of the restored old frontend is not new publication.
# Verified publication closeout, 2026-10-03 16:44 UTC+8

User-authorized takeover completed the original operation without rebuilding or
changing its ID. Recovery publisher `2c1d9d4bf95bdc55e06999e09dd3e616f31b0647`
received independent G4 GO (164 tests passed, two Linux-only skips). Exact
[CI 37109213113](https://github.com/itsoso/health-llm-driven/actions/runs/37109213113)
succeeded, including 2016 release-invariant tests, 84 subtests, and real OpenSSH
and Linux sandbox checks. The original HIGH advisories remain recorded with
verified mitigation/backport evidence rather than exemptions.

Canonical preflight digest:
`14371aa872bafb0dd306536d1c1f117f7cadce10bdc4f6dca693a00951b4cbed`.
Original frontend operation `637078dd8c584686a59000de91d2dad2` now has both
`RECOVERY_SUCCEEDED` and `FRONTEND_SUCCEEDED` on the server. Original failed.json
and all five original evidence files are retained; both old artifact directories
are retained with bound backup digests; the original business lease is released.
The publication still identifies the original f8dd build and frontend tree
`0e0a36d69a526e0ca5395f5c5082a77534dd739c`. Published artifact digest is
`2d8d765d014a5015ae6eaf016e77d8bab46ff262a3954ae15a4044914a3dfa8e`.

Independent external requests returned 200 without redirects for `/privacy`,
`/connect/health`, and `/api/v1/health`; both frontend pages contained their
expected markers. The actual installed braces copy was verified read-only as
health-web, including its exact mitigated source hash and recursion behavior.
Frontend was active/running with restart count zero. Production remained clean
at backend `dbad4e66c29f31c0ae149fecefa6c0d4f3e45283`; backend, worker and beat
process identities and configuration hashes exactly matched the original before
snapshot. No backend redeploy, native release, OTA or OAuth grant was performed
during this frontend recovery. Earlier backend DB backup/restore/offsite steps
remain explicitly skipped under the recorded user default, not claimed passed.
