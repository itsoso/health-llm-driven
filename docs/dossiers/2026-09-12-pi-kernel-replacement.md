# Official Pi kernel replacement

| 字段 | 值 |
|---|---|
| 状态 | shipping |
| 当前阶段 | S6 verified, release preparation |
| slug | pi-kernel-replacement |

## G1 需求准入

裁决：PASS。用户授权替换内部执行内核；沿用既有产品、数据权限和医疗边界。
准入依据见同一规格的 Requirement admission。

## Engineering delivery

Status: release preparation authorized; implementation, regression, independent
safety review and live LLM gates passed. Candidate CI and deployment pending.
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
include the pinned runtime. Local setup is documented in README.md. No deployment
was executed; Docker is unavailable locally, so the image build was not run.
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
- User explicitly authorized production deployment; source publication and backend-only release preparation are in progress.
- Production validation: not performed; local evidence does not establish rollout.

Before publication, complete live validation in a correctly configured isolated
environment and follow the existing revision-bound CI and deployment gates.

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

AGENTS section 7 stops external writes while main CI is red. The repair is
prepared locally; publication needs explicit permission to repair red main,
then a new exact-SHA confirmation/CI and the normal release gates.
