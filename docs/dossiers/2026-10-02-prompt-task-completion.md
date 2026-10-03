# Production prompt task completion

| Field | Value |
| --- | --- |
| 状态 | application and release repairs verified; node-forge backport locally verified; external write authorization pending |
| 当前阶段 | application G3/G4 verified; G5 blocked by dependency audit and native closure authorization |
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
