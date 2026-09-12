# Official Pi kernel replacement

| 字段 | 值 |
|---|---|
| 状态 | shipped |
| 当前阶段 | S7 production verified |
| slug | pi-kernel-replacement |

## G1 需求准入

裁决：PASS。用户授权替换内部执行内核；沿用既有产品、数据权限和医疗边界。
准入依据见同一规格的 Requirement admission。

## Engineering delivery

Status: production deployed and independently verified at `011084fef183`.
Implementation, regression, safety review, live LLM gates and exact CI passed.
See the final deployment evidence below; earlier sections retain historical runs.
Trace run: `2a203e0ed6c7`.

The user authorized direct replacement of Reva's self-written agent kernel.
Spec: `docs/specs/active/2026-09-12-pi-kernel-replacement.md`.
Controller: health-harness-orchestrator; overlay: safety-gate.

## Delivered scope

Before this change, AgentExecutor implemented its own Python model/tool loops;
there was no official Pi dependency. Normal chat and the multi-model lead now
use `@earendil-works/pi-agent-core` and `@earendil-works/pi-ai`, pinned to 0.85.1.
The panel's independent analyses and final synthesis remain behind Reva's output
and medical evidence boundaries. Pi owns the structured message/tool loop;
Python retains provider access, permissions, health tools and durable receipts.

The Python bridge bounds frames and waits, rejects unsolicited effects, and
terminates/reaps cancelled children. The child receives no provider/database
credentials and adds no filesystem/shell tools; it is not an OS sandbox.
Text/XML/inline pseudo-tool calls no longer dispatch effects. Missing Pi fails
explicitly without switching back to the old loop.

Whole batches are checkpointed before dispatch. Pi schema rejection and cleanly
terminated, undispatched siblings are reconciled without inventing side effects;
abnormal disconnects retain unresolved checkpoints. Prior verified or
uncertain operations are preserved. Unknown writes halt subsequent dispatch,
readback and success claims. Registered goal verification, medical evidence,
final output sanitization, retry idempotency and selected-model authority remain.

The Docker build, CI test workers and backend deployment dependency installer
include the pinned runtime. Local setup is documented in README.md. Production
deployment is verified below; Docker is unavailable locally, so the image build
was not run.
Unrelated Mac shopping changes present at task start remain untouched.

## Verification evidence

- Real Node Pi runtime: 25 tests passed; dependency audit reported no vulnerabilities.
- Combined normal-stream, bridge, completion, evidence, gateway and medical
  regressions: 2914 passed (350.15 seconds). Subsequent review fixes are covered
  by the additional runs below.
- Additional final-output, provider routing, staged analysis and durable retry
  regressions: 43 passed (19.32 seconds).
- Fresh final core (bridge, real Pi executor, reconciliation, completion,
  multi-model and live-change rules): 249 passed (125.51 seconds).
- Remaining executor files: all 737 tests passed in the expanded run. Raw JSON
  output protection: 15 passed separately. Exact supplement dosage binding:
  3 passed.
- Final no-false-write regression: 150 passed (83.71 seconds). Strengthened
  doctor-feedback source, cardinality and sealed-plan/operation fingerprint
  assertions: 10 passed (8.15 seconds). Optional absent strings and domain nulls
  share the existing canonical persisted doctor-note identity.
- Final independent safety review: GO, including same-fingerprint uncertainty,
  cancelled siblings, atomic write summary preservation, supplement binding and
  doctor-feedback provenance/cardinality/identity.
- Live-change classification and static gateway coverage: 18 passed.
- Deployment suite: 159 passed / 1 fixture failed (735.07 seconds). The failed
  lost-lease fixture lacked the newly required Pi installer. After adding the
  isolated fake installer, its unchanged lease/migration assertions passed
  (1 passed, 7.84 seconds). No real deployment was invoked by these tests.
- System Map regenerated; full map/navigation/document-drift check passed.
- Syntax, undefined-name lint and git diff whitespace checks passed.

The live LLM gate was attempted, not skipped: offline invariants 12/12,
health-agent core 50/50, trajectory contract 12/12, and golden outputs 9/9 passed.
The live portion failed 0/5 before any model call because local PostgreSQL lacks
role `health_app_runtime`. No quota guard was bypassed, no live confirmation was
asserted, and no real health data was accessed to work around the failure.

## Gates and continuation

- Scope: accepted internal runtime migration.
- Implementation: complete locally.
- Local QA/safety: passed, including extended no-false-write regression.
- Live LLM gate: passed after isolated configuration and diagnostic criterion correction below.
- User authorized production deployment and local source delivery on Git failure; backend deployment completed.
- Production validation: passed for the exact deployed SHA, durable terminal state, service health and official Pi transport.

Live validation and revision-bound CI were completed before publication.
The later explicit local-delivery authorization and deployment evidence are below.

## Production release preparation (2026-09-12, Asia/Shanghai)

Fresh production proof supersedes the historical blocker: production main is
`9ddcb9d2f304c330e37ca8ef9467d851dc0c8ec9`, backend/worker/beat healthy, local
health 200, public protected API 401; old preparation failure was recovered and
retired through the reviewed operator. The two upstream commits were integrated
without changing unrelated Mac shopping work.

The merge regression test exposed a missing main-path meal correction adapter.
Restored latest-meal deletion, explicit meal correction and simple nutrition
normalization before Pi receives the full checkpointed batch. Domain rejection
stops before dispatch and preserves earlier uncertain/failed outcomes. The
original upstream stream test remains unchanged. Fresh affected tests: 182 pass,
1 PostgreSQL-only skip; the broader preceding run was 426 pass, 1 failure,
1 skip and is not represented as green. The API integration cases passed there.

Live evaluation uses a dedicated local PostgreSQL database, restricted ledger
role and synthetic subject with auditable consent. No production health data or
real-user consent is copied. Budget, recipient and consent guards remain active.
The first configured synthesis runs failed literal diagnosis keyword checks:
“not a substitute for diagnosis” and “reference rather than diagnosis” were
false positives. Three dataset prohibitions now use the existing mandatory
semantic judge assertions: explicit/hedged patient diagnosis and diagnosis hidden
by a disclaimer remain failures. No scorer bypass or quality threshold reduction.
12 counterexample tests first failed; the full eval unit suite then passed 51.
The real judge independently accepted the benign disclaimer and rejected three
unsafe counterexamples (4/4). Fresh complete live gate: invariants 12/12, health
core 50/50, synthesis 5/5 (average 0.92), trajectory contracts 12/12, goldens 9/9.
Reports: `/tmp/reva-pi-live-final.log`, `/tmp/reva-pi-final-live-orchestrator.json`,
`/tmp/reva-pi-live-diagnostic-boundary.json`. Failed runs remain preserved.

A separate actual tokenplan/Pi transport probe passed: two real model requests,
one synthetic read-only tool call, verified result marker and child exit 0.
It proves model/tool transport, not a real health write or clinical quality.
Report: `/tmp/reva-pi-live-transport.log`.

Production dependency-only provisioning installed official Node 22.19.0 into a
new root-owned versioned toolchain, validating the upstream archive SHA-256
`c0649af18e6a24f6fe5535a3e86b341dd49a8e71117c8b68bde973ef834f16f2`.
New Reva venv node/npm links select it under the exact service and deployment
PATH; system Node 20 and PM2 remain unchanged. Independent readback confirmed
Node 22.19.0/npm 10.9.3, safe ownership, unchanged service PIDs/restart counts and
health 200. This provisioning is not a backend deployment.

Independent G4 safety review is GO for executor SHA-256
`7a526c01ced1d9c6c8ad00dcdebf129da639a5a2d499d80c0a92834d654c9765`
and dataset `bb50cf03d5caa50be35618b113ed995acd092c2500e4ceab7f9c92464e75ce33`.
Exact candidate CI, short-lived authorization rotation, trusted backend release
and production Pi verification remain required.

PostgreSQL integration completed: 33/33 passed, including real owned-meal
updates and foreign-user preservation, actual Pi executor and write reconciliation.
Report: `/tmp/reva-pi-postgres-final.log`. CI now installs Pi in its PostgreSQL
job and includes these regressions.


## Candidate CI and distribution repair

Candidate `8b7e195d329df5f21fcd5dac289f48e564a1d1d9` was committed in the
existing clean release checkout with every applicable pre-commit gate passing,
then fast-forwarded to main and pushed. Exact CI `34683056697` failed before
backend tests: the lockfile inherited a developer-only registry host inaccessible
to hosted runners. Other completed quality/build/release-invariant jobs passed;
no trusted deployment was dispatched and production remains on `9ddcb9d2f`.

The repair changes only package tarball origins to public npm, preserving every
version and SHA-512 integrity value, and pins the package registry in `.npmrc`.
An origin/integrity regression test failed first and now passes. A new empty
cache fetched the public archives successfully; audit found zero vulnerabilities
and all 26 runtime tests passed against that fresh installation. Application and
eval bytes remain identical to the reviewed/live-tested candidate. Evidence:
`/tmp/reva-pi-public-install.log`, `/tmp/reva-pi-public-runtime-tests.log`.

The user explicitly authorized fixing all discovered problems and then pushing.
The registry repair was published as `fa69806888f11d7815f5bc3dadf5f3b9589f2b39`.
This authorization permits the following red-main repairs; exact-SHA CI and the
normal release gates remain mandatory before deployment.


## Full CI regression repair

Exact CI `34683544112` reached all tests after public npm installation. It failed
on old Python-loop assertions (synthesis schema removal, silent fallback and
pre-model meal execution), one real plain-text protocol disclosure, missing
metadata-only tool count logging, and an unsynchronized packaged gate script.
No failure was skipped or relabeled as a passing CI run.

The shared final-output boundary now rejects plain tool protocol lists in normal
chat and every multi-model stage, reporting error without executing text or
requesting another model repair. Negative tests preserve ordinary prose and code
examples. Pi still completes two explicit structured read-only calls before its
answer. Meal integration providers now make structured proposals while existing
canonicalization rejects forged ID 999, binds owned ID 101/calories 300, and
checks exactly one write and its durable receipt. The authenticated real API meal
fixture still checks canonical user food, enrichment and retry deduplication.
Honest refusal/data-insufficiency no longer expects a hidden fallback answer.
Tool count observability contains metadata only. The packaged LLM gate is an exact
copy of its repository source.

Fresh verification:
- CI repair regressions: 79 passed, 1 PostgreSQL-only skip (20.96 seconds).
- Meal persistence, privacy and real Pi executor: 12 passed (7.46 seconds).
- PostgreSQL latest-meal, durable meal and reconciliation: 36 passed (76.10 seconds).
- Full live gate: invariants 12/12, core 50/50, synthesis 5/5 (average 0.96).
  Same isolated synthetic subject and enforced budget/consent; no production data.
- Final completion/output/structured-chain regression: 214 passed; undefined-name
  lint and whitespace checks passed. Evidence: `/tmp/reva-pi-output-final.log`.
- Independent safety-gate review: GO. Executor SHA-256
  `224c7b7682197ed89c9da8f49c10ee1b367393094475040877e6d25b8c0361ca`;
  output quality SHA-256
  `9f39d5fabaf880743fa8920eefca52a36743554d21cb0630b990d5e11068cc38`.
Evidence: `/tmp/reva-pi-final-ci-repairs.log`,
`/tmp/reva-pi-meal-privacy-final.log`, `/tmp/reva-pi-post-ci-postgres.log`,
`/tmp/reva-pi-live-post-ci-fixes.log`. Candidate CI/deployment still pending.


## Deferred CI shard repair

Candidate `1e79ae9939d65deb3070d359e1300bbffe01e2e7`, CI `34684310680`,
exposed previously unreached downstream shards because workers stop on a failed
shard. The earlier fixes passed. Newly reached failures included old deterministic
query/empty-answer retry expectations and real terminal-output issues.

Domain meal-resolution failures now retain their existing specific messages;
zero-tool guards no longer overwrite ambiguous/missing/failed lookup guidance.
A completely rejected proposed tool batch or a proposal outside the sealed tool
scope returns error. Empty synthesis after a verified write retains the exact
receipt and warns against resubmission; no model retry or new write is introduced.
Tests retain actual official Pi transport and structured model/tool assertions.

Fresh targeted tests: 24 passed. Exact CI shard entrypoint locally: agent-a-d
139 passed, agent-f-h 315 passed. Previously unreached b: 197 passed; q: 83 passed.
The d-rest full run had 111 pass plus the known unrelated dirty Mac dossier
failure, which must be revalidated from the isolated release checkout.
PostgreSQL terminal/reconciliation: 13 passed. Actual complete LLM gate again
passed invariants 12, core 50, synthesis 5 (average 0.96), trajectories 12, goldens 9.
Independent source safety review: GO, runtime digest
`7334ed29f3fa9eaca5089f3f57991b2fd4943c4b4dac4f17b9b19f5904f53593`.
Evidence: `/tmp/reva-pi-terminal-ci-full.log`, `/tmp/reva-pi-d-rest-q-full.log`,
`/tmp/reva-pi-repair-next-final.log`, `/tmp/reva-pi-terminal-pg.log`,
`/tmp/reva-pi-terminal-live.log`.

The completion-status shard also hit its 256-second process deadline twice,
without an assertion failure; its previous exact CI run passed with individual
cases at or below 3.57 seconds. An isolated same-source CI rerun is investigating
this variance. Existing per-test/process limits and all assertions are unchanged.
No production release has been dispatched.

Final core regression: 359 passed, 1 PostgreSQL-only skip (199.13 seconds);
the separately run PostgreSQL terminal/reconciliation set passed all 13.
The isolated release checkout installed the pinned official runtime with public
npm and zero audit findings, then the complete d-rest shard passed all 112.
The strengthened receipt test rejects non-stream model repair and asserts one
actual write; its full file passed 8 tests. Evidence:
`/tmp/reva-pi-terminal-core.log`, `/tmp/reva-pi-clean-d-rest.log`,
`/tmp/reva-pi-empty-receipt-final.log`.


## Saved photo receipt on rejected synthesis

Candidate `fdc74a9b94d5d0c919a5be7934d58a11d26b4440`, CI `34685380029`,
passed every job except one photo test in balanced-08. Completion-status also
passed this fresh run; the earlier isolated rerun passed without changing limits.
No assertion or timeout was waived.

Rejected model proposals remain errors and compound requests still run through
Pi. A previously persisted photo meal now retains its verified receipt and
resubmission warning. Error responses expose only internal diet cards whose
recorded flag is true and whose record ID matches a verified diet receipt.
Unmatched cards, pending drafts and generated evidence remain excluded.

Fresh exact shard verification: food 115 passed and t-f-v-rest 325 passed;
PostgreSQL receipt regression 1 passed with exactly one persisted meal and photo
association. Injected unmatched and pending cards were both excluded. The
food/refusal/fallback group passed 127 tests, and the strengthened negative card
test passed. Full live gate on the unchanged execution path and receipt text
passed invariants 12, core 50, synthesis 5 (average 0.94), trajectories 12 and
goldens 9; the subsequent card projection is covered by the DB-backed tests.
Independent safety-gate: GO; final runtime SHA-256
`dbd03d51b2f2227822b6edc36d449fdef658f1d2be72da08df1b8ea18fc2919d`.
Evidence: `/tmp/reva-pi-final-card-ci.log`, `/tmp/reva-pi-final-card-pg.log`,
`/tmp/reva-pi-photo-card-final.log`, `/tmp/reva-pi-photo-card-guard.log`,
`/tmp/reva-pi-final-receipt-live.log`. New exact-SHA CI and deployment remain pending.


## Production deployment completed

Deployed and independently verified `011084fef183863b112aebd83fde16dd64e2550f`.
Exact CI `34686234488` attempt 2 and trusted validate `34686968992` passed.
The first CI attempt timed out in agent-s-v; an unchanged isolated rerun passed
all remaining shards on their first process attempt. Clean local agent-s-v also
passed 534 with 3 platform/DB skips in 140 seconds; diagnostic no-false-write
150 tests passed without DNS attempts or faulthandler stalls. Timeout cause was
not reproduced; limits and assertions were unchanged.

Canonical HTTPS bootstrap fetch failed again with the low-speed deadline. The
user explicitly authorized local source delivery when production Git fetch
fails. A clean isolated main checkout ran the unmodified `deploy.sh -b` after
independent fallback review GO, exact current-main CI attestation and secret
scan. Only the production-derived configuration plus deployment address/path
was used in a temporary 0600 file. The HEAD bundle was uploaded; the business
checkout's existing origin fetch succeeded, so the bundle remained a fallback.
No cloud release capability was issued or consumed for this local deployment.

Database backup, full restore drill, encrypted offsite upload/hash/manifest,
rollback schema, runtime schema/migration, exact revision, process stability,
knowledge serving and skills-manifest gates all passed. Health score was 60/60.
The durable terminal marker binds this SHA with COMMITTED/finalized, and the
business lease is absent. Backend, worker and beat are active with zero restarts.
The actual mobile public endpoint returns expected unauthenticated 401; local
health returns 200. As the packaged skill's old health-api hostname no longer
resolves, the public probe uses the actual client/Nginx health.executor.life URL.

The official Pi production probe ran as health-app with the service Node PATH:
two scripted model frames, one synthetic read-only tool, final marker and child
exit 0. This proves installed runtime transport, not live-provider quality; the
real-provider/LLM gates are documented above. No production health data was used.

Temporary repo-local HTTP/1.1 and low-speed settings bounded the inherited global
unlimited Git transfer configuration. After terminal/lease proof and exact config
comparison, the original config bytes were restored. All locally generated
release private keys and copied production configuration were deleted.
Server audit: `/var/backups/health-app/local-delivery-011084fef183863b112aebd83fde16dd64e2550f/completed.json`.
Local evidence: `/tmp/reva-pi-local-deployment.log`,
`/tmp/reva-pi-local-release-completed.json`, `/tmp/reva-pi-production-probe.log`.
