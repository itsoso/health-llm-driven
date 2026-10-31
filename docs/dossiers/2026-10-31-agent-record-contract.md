# Agent record task contract

| 字段 | 值 |
| --- | --- |
| 状态 | implementation |
| 当前阶段 | G4 committed-diff review and release validation |
| Controller | backend-deploy, safety-gate overlay |

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
