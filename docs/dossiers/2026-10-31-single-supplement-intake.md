# Single supplement intake: preserve one parsed fact through persistence

| 字段 | 值 |
| --- | --- |
| 状态 | implementation |
| 当前阶段 | G3 复发修复验证；上一轮用户验收失败 |
| Controller | health-harness-orchestrator (incident), safety-gate overlay |
| Run | `docs/_generated/harness-runs/09731e372ccf.jsonl` (local) |

Current outcome: the user's 13:47 screenshot disproves complete user-path
acceptance of deployed revision `8d4d6c5c627ec50b27e67b6282946ec4ccb664c7`.
The follow-up below reopens G3–G6. Earlier deployment receipts remain valid
historical evidence, not proof that the newly reported sentence forms work.

## G1 admission

裁决: PASS

Admission: existing record-and-verify loop reliability. A current-user explicit
supplement intake must preserve its name, quantity and unit through authorization,
tool planning, authenticated persistence and verified receipt. This is a bounded
bugfix, not dosage advice or regimen modification. No schema, public API, client
type or mobile change. Existing `docs/specs/recording-reliability.md` provides the
shared-plan contract; this follow-up includes single-item planning and actual
quantity persistence, and adds creatine to the bounded intake grammar.

## Reproduced causes

Synthetic local probes reproduce the reported sentence shapes. No production
health records, logs or model providers were accessed, so these findings are not
a claim about the exact production request trace.

- The classifier recognizes supplement/create, but the typed intake vocabulary
  omits the target. The legacy parser retains the completed-ingestion verb in
  the name. With a comma, the record label and intake are split into separate
  authorization clauses.
- Even supported typed names are re-parsed by deterministic tool repair and
  corrupted. This can replace a correct model-proposed payload with a bad one.
- Pi's no-tool repair handles complete batches but omits a complete single item.
- The legacy single-item adapter uses NFC tap, which does not store actual
  dosage. It rejects an explicit amount different from the usual regimen.
- Unresolved target authorization falls through to a misleading create/update
  clarification even when create intent is clear.

The relevant parser and single-item repair branches are also unchanged in the
inspected `origin/main` relative to the starting local revision. Remote changes
elsewhere are not integrated or verified by this task.

## Implementation

- Authorization and deterministic repair consume the same complete typed intake.
  The bounded grammar still rejects residual text, uncertain counts, other
  people, future/planned/negated/quoted requests and quantity/type changes.
- A complete single supplement intake can supply an omitted model tool call;
  attachment and existing-receipt guards remain in force, and the normal Pi
  capability/gateway/durable-operation path still executes it.
- That exact single-item path uses the existing authenticated `/supplements/records`
  endpoint to store `actual_dosage` and server-bound current date/time. Existing
  definitions keep their usual dosage. Name-only and other legacy grammars retain
  their existing adapter semantics; broader grammar consolidation is not claimed.
- Success requires a returned record ID, matching owner, definition, date,
  `taken=true` and actual quantity. Missing/conflicting responses are unverified;
  transport uncertainty does not prove no write. Definite auth denial remains
  a no-write error. Unresolved-target copy no longer invents operation ambiguity.

## G3 evidence

- Initial new regression: 17 failed / 16 passed, including exact identity,
  misleading copy and real gateway/API execution. After parser/repair correction,
  4 runtime failures exposed the independent actual-dosage persistence defect.
- Final focused tests: 49 passed (`/tmp/reva-single-intake-final.log`), plus 4
  auth/transport negative tests (`/tmp/reva-single-intake-errors.log`).
- Dedicated temporary PostgreSQL 17 UTF8 cluster: 49 passed
  (`/tmp/reva-single-intake-postgres.log`); server stopped afterward. Includes
  existing/new definitions, model call/omission, persisted actual quantity,
  unchanged regimen, verified outcomes and client-turn replay.
- Adjacent scope, mixed intake, autocreate, fast routing and real API streams:
  797 passed / 6 existing inapplicable parameter combinations skipped
  (`/tmp/reva-single-intake-regression.log`). Synthetic provider only.
- System Map check and `git diff --check` pass; no generated structure drift.

## Release boundary

Startup branch: local `main` ahead 2 / behind 102 relative to `origin/main`, with
unrelated user/agent modifications. Those changes are preserved. AGENTS §7
blocks external writes while this divergence and candidate provenance remain
unresolved. No push, deployment, OTA or production record mutation performed.

The path-sensitive LLM gate correctly reports live evaluation required and
unconfirmed. Exact integrated main CI, project CI-mode, live synthetic evaluation,
final G4 and production receipt/user-path verification are not satisfied by local
tests. This task must not be represented as released or as eliminating every
unsupported natural-language record failure.

## Independent review correction

- Fixed initial commit `e2a3a143a`: independent reviewer NO-GO. New definition
  creation still copied the one-off dose into the regimen; successful definition
  creation followed by intake auth/transport failure lost the partial side effect.
- Additional RED: 6 failed / 4 passed. New definitions now omit regimen dosage
  for complete single intakes; intake failure preserves the created definition
  ID/message and cannot mark the whole operation as never dispatched. Transport
  uncertainty remains unverified with no blind retry.
- Expanded real Pi/gateway/API scenarios cover new/existing definitions and
  definite auth versus uncertain transport failures as well as successful writes.
  Initial correction runs found only a test ID-type assertion mismatch (the
  established failure helper returns string IDs); comparison now normalizes it.
- Initial broad capability suite before this narrow correction: 2259 passed.
  Final combined regression, final PostgreSQL and fixed-commit re-review pending.

## Final local verification and handoff

- Corrected implementation commit: `5b5ea9ed2` (with `e2a3a143a`). Independent
  safety reviewer returned **GO** after inspecting the fixed commits and
  independently executing all 71 focused synthetic tests. Both prior blockers
  are closed; this is implementation review, not release approval.
- Fresh combined focused/autocreate/capability suite: **2452 passed**
  (`/tmp/reva-single-intake-reviewed-final.log`).
- Final dedicated PostgreSQL 17 UTF8 suite: **71 passed**
  (`/tmp/reva-single-intake-postgres-final.log`), including real authenticated
  persistence, definition-only partial failure, quantity conservation, owner/date
  binding and idempotent client-turn replay. Initial final-cluster startup hit
  macOS Unix-socket path length; a shorter isolated `/tmp` path fixed the test
  environment without application changes. The temporary server was stopped.
- System Map and whitespace checks pass. Only this task's four files were
  committed locally. All unrelated work remains preserved; no external writes.
- **G5 remains BLOCKED** under AGENTS §7. Integrate with current main while
  preserving existing local work, then obtain exact candidate CI-mode/remote CI,
  live synthetic model evidence and production verification. No OTA is needed
  for these backend-only changes. No production success claim is authorized by
  this dossier.

## Authorized production continuation

The user explicitly requested full repair and production release on 2026-10-31.
The existing clean release checkout was reused at current main `14564dfc7`, and
only this task's three commits were applied. The original dirty main checkout
was preserved. The two older local mobile commits were patch-equivalent to
changes already on remote main and were not republished.

The first integrated synthetic run exposed missing official Pi dependencies in
this reused checkout: all 24 stream scenarios failed before a model/tool round,
with `ERR_MODULE_NOT_FOUND` for `@earendil-works/pi-agent-core`. This is an explicit
failed environment check, not accepted evidence. Install the unchanged lockfile
and repeat the affected suite, final independent G4, PostgreSQL, CI-mode and live
synthetic gate. Production release remains pending those fresh results and exact
main CI. Backend-only scope does not require Mobile OTA.

The existing storage contract is one supplement row per day (upsert), not a
cumulative multi-event diary. This change preserves actual quantity for that
contract; same client-turn replay is tested, and universal cross-turn exactly-once
or arbitrary unsupported natural-language interpretation is not claimed.

## Release prerequisite: newly reported dependency vulnerabilities

Push CI `41168343206` on `431e7754486f68b99641c62ba95dfaa3f37a597d`
blocked at security audits. The current main lockfiles contained newly published
advisories for pyasn1 0.6.4, joi 17.13.8, node-forge 1.4.0 and follow-redirects
1.16.1. Release remains blocked until a new exact candidate passes all gates.

- Upgrade only these lock entries to official fixed versions: pyasn1 0.6.5,
  joi 17.13.9, node-forge 1.4.1 and follow-redirects 1.16.2. Registry integrity
  and PyPI artifact SHA256 values were independently checked.
- Retire the Forge 1.4.0 patch and its narrow OSV exception. Existing release
  callers retain the verifier CLI, now read-only and pinned to upstream 1.4.1
  package metadata and the complete JS library tree. Signature positive/negative,
  identity drift, nested-copy and link/path checks remain. Any reported Forge
  HIGH advisory, including a future one on 1.4.1, remains blocking.
- Python pip-audit passed; OSV passed for release-tools (517 entries), frontend
  (313) and mobile (1087). Node verifier/audit tests 31 passed, EAS compatibility
  3 passed, mobile security compatibility 5 passed, mobile TypeScript passed.
- The original integrated backend regression passed 2460 tests, PostgreSQL 71,
  and exact `431e77544` live synthetic gate passed. Two earlier local CI-mode
  runs are not final-source proof: the first exposed a malformed dossier verdict,
  and both were superseded while dependency pins changed. Rerun final-source
  CI-mode after freezing this repair.
- No Expo/React Native/native module, permission, signing or app behavior change.
  Publishing the backend does not claim that a new website or mobile artifact
  has shipped. The reported supplement behavior is implemented on the server.

Primary advisories: https://github.com/advisories/GHSA-4528-x5fx-h6hg,
https://github.com/advisories/GHSA-5x38-2vff-x55p,
https://github.com/advisories/GHSA-mrwp-f3q8-3g9p,
https://pypi.org/project/pyasn1/0.6.5/.

The next push CI `41169150962` on `1b8221295` passed security audits but
exposed a stale `pyasn1==0.6.4` assertion in the backend dependency contract.
Local isolated reproduction: 1 failed / 4 passed. Update the assertion to the
audited 0.6.5 pin; do not weaken or skip the contract. The partial local CI-mode
run for that superseded SHA was stopped and is not accepted as a pass. Final
candidate CI-mode, exact remote CI and live gate must be rebound after this
test-only correction. No production operation has started.

## Final G3/G4 verification

裁决: PASS

- Frozen backend candidate: `8d4d6c5c627ec50b27e67b6282946ec4ccb664c7`.
  Independent implementation and one-shot operational reviews returned GO bound
  to this SHA and the exact reviewed wrapper bytes.
- Fresh project CI-mode: 5782 passed, 67 platform/inapplicable skips, zero errors
  or failures; dossier checker and its 18 tests passed. Dedicated PostgreSQL 17
  regression: 71 passed. Live synthetic model gate passed on this exact SHA.
  System Map and whitespace checks passed. No real user health records were used.
- [Exact full CI](https://github.com/itsoso/health-llm-driven/actions/runs/41169833378):
  32 jobs successful. [Trusted preflight](https://github.com/itsoso/health-llm-driven/actions/runs/41170638363)
  completed successfully; preflight success and six inapplicable jobs skipped.

## Final G5 deployment

裁决: PASS

- Canonical staging, scoped read-credential refresh and authorization rotation
  completed once, with independent byte-bound approvals and durable receipts.
  No backup, rollback copy, historical backup-body verification or repeated
  deployment was performed.
- [Backend dispatch](https://github.com/itsoso/health-llm-driven/actions/runs/41171468676)
  reports **failure** because its runner SSH connection timed out. The original
  server launcher and deployment child continued; they were observed, not
  restarted or replayed. The original operation subsequently wrote
  `/var/lib/reva-release/8d4d6c5c627ec50b27e67b6282946ec4ccb664c7/completed.json`
  with exact SHA and `state=SUCCEEDED`.
- Independent readback confirmed the matching `COMMITTED` terminal marker with
  `mode=code-only-no-backup`, no business lease, exact clean production HEAD,
  and matching hashes for the changed intake/executor code and dependency lock.
  This is server-side completion evidence, not a claim that the failed cloud
  dispatch became green.

## Post-release acceptance and remaining limits

- Backend, Celery worker and beat are active. Internal and public health requests
  return HTTP 200; unauthenticated auth/me and supplement-record reads return
  HTTP 401. The deployment's guard and final health checks passed 60/60, along
  with revision, serving-contract and manifest checks.
- Evidence: `/tmp/reva-intake-8d4-production-proof.json`; local CI-mode result
  `/tmp/reva-intake-8d4-ci-result.json`; live result
  `/tmp/reva-intake-8d4-live-result.json`; PostgreSQL log
  `/tmp/reva-intake-8d4-pg.log`.
- The independent readback also observed the GitHub release relay repeatedly
  reconnecting to its base host. A later canonical GitHub transport probe failed
  with connection refused. This remains a release-transport fault; it is not
  counted as healthy or silently removed from the evidence. Core application
  verification was recorded separately. No relay configuration was changed.
- No production supplement record was created by verification; the user's
  signed-in retry was not observed. Both screenshot sentence shapes passed real
  API/Pi/gateway tests against isolated databases. The bounded grammar and daily
  upsert limitations above remain. No Mobile OTA or website artifact was published.

## Reopened: unlabeled intake and explicit vitamin subtype

裁决: FAIL

- New user evidence: an explicit intake without the optional supplement label
  reaches meal nutrition failure; a compound vitamin name with a VB suffix is
  rejected. Current production HEAD was independently read as `8d4d6c5c6`,
  backend active and business lease absent. Sanitized journal metadata at 13:46
  shows diet/missing_nutrition and nearby write_tool_without_write_intent.
  No request ID was supplied, so timestamp proximity does not prove exact
  per-message attribution. No production health payload or record was copied.
- Local RED after correcting a test-only model import: 20 failed / 19 passed,
  including real Pi/gateway/authenticated API scenarios. The complete intake
  parser recognizes creatine but the independent routing vocabulary does not;
  a diet goal then overwrites the grounded supplement proposal. The vitamin
  subtype remains unconsumed and fails the closed grammar.
- Follow-up implementation makes the intake classifier consume the complete
  typed fact, and prevents a stale diet frame from compiling a typed supplement
  into a meal goal. Explicit vitamin subtypes retain their literal normalized
  name; VB is not silently treated as equivalent to another product, and dose,
  owner, date and receipt checks are unchanged.
- First corrected focused suite: 110 passed. Expanded regression, PostgreSQL,
  live provider-to-isolated-API evaluation, independent G4, exact CI and a new
  production receipt remain required. Test-only import failures are not RED
  behavioral evidence. New live cases require explicit opt-in and synthetic
  AI consent; no real user's health record is used for validation.
