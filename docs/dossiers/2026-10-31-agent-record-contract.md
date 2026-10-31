# Agent record task contract

| 字段 | 值 |
| --- | --- |
| 状态 | released |
| 当前阶段 | G6 Web, Mobile and native baseline verified |
| Controller | mobile-testflight-release, safety-gate overlay |

## G1 admission

裁决: PASS

Existing recording reliability fix; preserve Pi, bind explicit self-report facts
to capabilities and persistence evidence. No new diagnosis, treatment or schema
authority. Scope and acceptance: `docs/specs/active/2026-10-31-agent-record-contract.md`.

Baseline: origin/main 8d8475fa52902fd8a31930b7879efe90dac20120.
Scope: implementation, commit and main integration, production backend/Web deployment, applicable Mobile OTA and online verification (explicitly authorized 2026-10-31).
Controller: health-harness-orchestrator; overlay: safety-gate.
Spec: ../specs/active/2026-10-31-agent-record-contract.md.

Evidence: production metadata inspected in prior analysis showed a record request
classified as chat, no tools/receipts, but completed. The repeated request was
blocked as an unrequested query. No personal payload is retained here.

## Implementation

Official Pi is retained. New generic record obligations cannot silently become
successful chat. A registered capability binds the schema, owned user facts,
endpoint, channel policy and event readback proof. Zero-tool model responses may
receive one bounded proposal through the existing gateway; this does not bypass
policy or grant permission to unknown actions.

Nasal washing is the first event contract. PostgreSQL owner locking, immutable
event identities, tombstone undo and legacy endpoint conflict checks prevent
lost updates, duplicate retries and resurrection. Web and Mobile use the same
append contract while preserving manual time and wash/soak behavior. Health
payloads were removed from the touched legacy endpoint's log messages.

## Verification

- RED tests demonstrated missing capability and compound-task false completion.
- Official Pi + authenticated API + isolated PostgreSQL: 57 passed, 1 live case
  separately deselected; includes replay, concurrency, owner isolation, corrupt
  readback, malformed POST receipt, precise undo and legacy overwrite rejection.
- Web: 6 component/service cases passed; Mobile: 8 passed; both typechecks passed.
- Fresh live-provider synthetic-record E2E: 1 passed (12.23 seconds); official
  Pi, authenticated API and isolated PostgreSQL were real. HTTP requests used
  the app test transport and only synthetic users, with no provider mock.
- Fresh repository live LLM regression gate passed with no failed cases.
- System Map generation and drift check passed.
- Expanded backend regressions: 3762 passed, 6 skipped. Legacy suffix-command,
  analysis adjunct, symptom conjunction and supported compound compatibility
  regressions were repaired. Strict multi-target owner/date receipt checks
  reject missing identities rather than filling defaults.
- Supported two-water-record real Pi/PostgreSQL completion and same-turn replay,
  plus partial execution: 2 passed. The partial case was RED before the fix;
  final tokens, stored text, metadata and task outcome agree on partial completion.
- After the final partial-text change, the full affected completion/goal/outcome
  suite passed: 525 tests. Fresh live LLM gate passed again; the local path-based
  live-change gate passed with ephemeral local confirmation. No repository
  variable was modified and no uncommitted change is claimed as revision CI.
- Independent safety and compound-completion review: GO; all raised P1/P2
  findings closed. System Map and `git diff --check` passed.
- Evidence logs: `/tmp/reva-task-contract-{regression-final,pg-final,completion-final,live-record,live-gate,map-final}.log`;
  compound E2E `/tmp/reva-task-contract-multi-partial-green.log`;
  client tests `/tmp/reva-client-record-{web,mobile}-final.log`.

Status: implemented and locally verified. The isolated PostgreSQL test cluster
was shut down after validation. No production acceptance or release claim.

## Boundaries

No production health data was written. No commit, push, deployment or published
revision CI claim. All work is in an isolated worktree at the fetched baseline;
the original shared checkout and its changes are preserved. Client pending
identities survive in-component retries, not app restarts. New event writes
with unknown outcomes remain reconciliation_required; automatic background
reconciliation is not added. Unsupported capabilities cannot be auto-recorded.

## Release continuation

User authorized commit, main integration, production deployment and Web/Mobile
verification on 2026-10-31. Fresh fetch confirms the original baseline remains
current main. Production backend has since reached that same baseline; previously
pending release recovery is not assumed to remain blocked. Exact candidate CI,
independent committed-diff review and current release receipts govern release.

### Full CI compatibility corrections

The first exact-main CI (41190853038) rejected clinician-guard response
compatibility, a medication confirmation card hidden by the generic completion
notice, the frozen tool-schema snapshot, and missing generated API clients.
The follow-up preserves stronger clinician/confirmation terminal messages without
changing authorization or persistence checks, explicitly admits only the reviewed
nasal enum into the historical schema freeze, and regenerates both clients.
Original failed CI is retained; no production deployment consumed that candidate.
Targeted failed-file suites, both client typechecks, type-drift regeneration and
fresh live LLM regression passed. Independent correction review GO.

The PostgreSQL CI runner now explicitly selects the new record-contract E2E,
nasal event endpoint and neighboring rhinitis suites. An initially failing
selection assertion proves this closes a real CI omission; all legacy selectors
remain. Historical timing assertions are scoped to their measured original
selectors, with no invented timing evidence for the added suites.

## Mobile native continuation (2026-10-31, in progress)

User explicitly requested completing Mobile delivery with a new native baseline,
retaining compatibility gates and simulator/online acceptance. Exact source remains
1612c75ffc47af5ed470e57335e6c593c6af5817; backend and Web are already deployed.
Fresh validate run 41195589830 succeeded; native continuation run 41195692896
uses target=testflight, preserving the existing backend SUCCEEDED receipt.
Independent safety review: GO; 59 native continuation and vendor-binding tests passed.

ASC readback before the build: latest processed build 286 is VALID; app version
1.3.6 is REJECTED, not under active review. This continuation does not cancel or
submit App Review. No new build identity, fingerprint or OTA baseline is asserted
until actual vendor evidence is available. Simulator candidate has built and
launched, but signed-in UI acceptance remains pending.

The failed prior OTA validation 41194724524 consumed no OTA claim. Dependency
inputs differ from the Store 286 baseline, so no keyword/allowlist bypass is used.

Native build 287 (`039c87d2-3bbb-4a20-915b-9c61fc584e71`) finished from the exact
1612c75 source. Downloaded IPA identity, signed entitlements, team and absent
background-location capability passed static verification; Apple upload/processing
was still pending at this checkpoint. Fingerprint comparison against 286 shows
only the patch-package directory changed, matching removal of the superseded
node-forge patch; native module/plugin/config source fingerprints are unchanged.

Simulator login acceptance exposed a local build configuration error: the prior
CODE_SIGNING_ALLOWED=NO package was linker-signed, lacked application-identifier
entitlements, and securityd reported errSecMissingEntitlement (-34018). It must not
count as login acceptance. A properly signed Release simulator rebuild is running;
no production auth weakening or plaintext token fallback is introduced.

Native continuation terminal: trusted run 41195692896 completed successfully. EAS Store build
287 (`039c87d2-3bbb-4a20-915b-9c61fc584e71`) binds source `1612c75ffc47af5ed470e57335e6c593c6af5817`;
ASC readback is VALID / IN_BETA_TESTING. Exact IPA signature/capability receipt and closed cohort
are recorded in `docs/reviews/2026-10-31-ota-runtime136-build287-baseline.json`. Fingerprint source
comparison against 286 changes only patch-package input; native module/plugin/config sources are
unchanged. Future native or unknown input remains blocked, and every older runtime host remains
required in live cohort checks. This is TestFlight availability, not App Store publication.

Simulator packaging correction: the first local candidate used disabled signing and Keychain
reported errSecMissingEntitlement (-34018). Rebuilding with Xcode simulator signing embeds the
application identifier in the Mach-O simulator entitlement section. After reinstall and restart,
the candidate opens its login screen. Authenticated acceptance still awaits a fresh user login;
no plaintext fallback, injected token, or test health writes to the personal account were used.

## Final Mobile release verification

- Release policy / backend / OTA source: `82230e97d697d60623a30d6dc44bf173752016eb`,
  independently reviewed GO; 576 release/baseline regression tests passed. Full exact CI
  `41199072362` passed, including PostgreSQL integration. System Map checks passed.
- Trusted preflight `41199812389`, backend `41200800100`, OTA validation `41201430253`
  and OTA publication `41201691468` all succeeded. Production revision matches the
  release source; backend/Web active and API/database/Redis/Celery health verified.
- Production OTA group `84f737e4-1844-4351-9218-9eccb4bf7103`, iOS update
  `01a191f9-c266-7c98-b34a-d846d7396ded`, runtime 1.3.6. Server completed receipt is
  SUCCEEDED, verified receipt binds the same SHA; business lease is released.
- Native Store build 287 is VALID / IN_BETA_TESTING. The new baseline preserves
  every reviewed prior 1.3.6 host and all source/cohort checks. No second native
  build/upload was triggered for the policy-only commit.
- The user successfully logged in to the corrected signed simulator candidate.
  Today, chat history and AI data-sharing privacy page loaded. A whole simulator
  restart restored the authenticated chat without another login. Web Agenda and
  AI assistant also loaded after deployment. No synthetic health records were
  written to the personal account.
- Simulator evidence uses a same-source Release simulator artifact (local build
  number 1); it is explicitly distinct from the signed Store IPA (build 287).
  Physical installation, hardware-only integrations and simulator OTA uptake are
  not claimed. TestFlight availability is not public App Store publication.
- The first canonical activation invocation used system Python 3.10 and failed
  on a Python 3.12 audit dependency before any intent or policy mutation. After
  read-only proof of unchanged state, canonical Python 3.12 verified history and
  live native terminal evidence and completed the locked rotation. No claim,
  audit or authorization check was deleted or bypassed.

This final section supersedes earlier in-progress acceptance notes. The final
documentation-only commit does not change deployed runtime or publisher code.


## Production record acceptance, both directions

The exact original Chinese request was submitted through the real Web UI and,
separately, through a signed Release iOS simulator UI using the isolated review
test account. Both turns used Pi, classified `simple_health_record`, executed
`nasal_wash`, and ended `complete / verified_write` with one verified receipt.
Authenticated event readback proved count 1, volume 10 ml, saline solution,
correct ownership and no duplicate event. Fresh conversation reads and the
opposite client showed the same persisted answer. Each test event was then
undone through its exact owned event endpoint; fresh reads returned 404 and the
daily wash count returned to its baseline. Audit conversations were retained and
renamed. No synthetic health writes were made to the personal account.

The first event's stored local clock differed from chat display; its prior
profile timezone was not captured, so no confirmed cause is asserted. The second
round ran after both clients were authenticated and effective timezone readback
was Asia/Taipei; stored event time and both chat displays agreed.

## Mobile header polish

The chat header replaces the single mint capsule with separate rounded action
surfaces. New chat retains a green accent; history and more use the warm neutral
palette. Brand spacing, avatar scale and title weight are balanced while keeping
44-point action targets, accessibility labels, model-selection authorization and
all callbacks unchanged. This is JS/UI only; native build 287 remains the host
baseline. The first candidate passed all Mobile tests, exact-main CI 41206822841 and
simulator new/history/more interactions. Before publication, user feedback asked
for less generic new/history icons. The final refinement uses a shared rounded
conversation silhouette with plus/clock details, drawn with the already-installed
SVG module; it introduces no native input. The first candidate authorization rotation completed normally without deploying or publishing its UI. Final icon candidate passed 382 Mobile suites (4055 tests, one existing skip),
typecheck and signed Release simulator visual/new/history interaction checks.
Final production publication remains pending at this checkpoint.


## Final header publication

- Final source: `1b31ba5bf1f60f6a49518525942246bf148a4fd3`; independent safety review GO.
- Full current-main CI `41208207280`, trusted validate `41209022596`, backend
  deployment `41209808726`, OTA validate `41210213412` and OTA publish
  `41210357801` all succeeded. Production revision matches the final source;
  backend and Web services are active, and authenticated Web chat reload passed.
- Production iOS OTA group `030701a9-1cb6-4ea4-b692-8eba5e71bd41`, update
  `01a19263-08c0-7249-b6a6-613c5f8e2957`, runtime 1.3.6. Server verified/completed
  receipts bind the same SHA, state SUCCEEDED, and business lease is released.
- Both intermediate and final UI candidates were built as signed Release simulator
  artifacts. Final rounded conversation-plus and conversation-clock icons were
  visually inspected and new/history entry points operated successfully using the
  isolated test account. Personal device OTA uptake is not asserted.
- Intermediate `28c2c357a` was authorized but never deployed/published. Its unused
  authorization required canonical revoke and retirement of only its revoked
  loopback private key before ordinary rotation to the final source. Initial
  malformed public-key argument and wrong-source revoke calls failed before
  mutation; the direct rotation also failed before any retirement intent. Policy,
  absent workspace/lease and audit inventories were read back before proceeding.
  No publisher code was changed and no permission, compatibility or audit gate was
  bypassed. Existing authorized cloud identity and scope were retained.

This final section supersedes the pending UI publication checkpoint above.
