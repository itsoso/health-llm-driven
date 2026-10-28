# Photo supplement record clarification

| 字段 | 值 |
|---|---|
| slug | photo-supplement-clarification |
| 当前阶段 | S5 昨晚血氧查询阻断修复，App Review 暂停 |
| 状态 | building |

## G1 准入

裁决: PASS。修复用户截图中的已有补剂记录请求分流，不新增自动服用写入或推断。

## Scope

User screenshot: a bottle photo with `记录益生菌补剂` received a generic guidance hold. No actual health records or live models were inspected.

## Finding and implementation

The existing deterministic photo supplement parser only supports a closed multi-product/count phrase. Incomplete single-product captions bypassed it and reached general model guidance. Add a separate, non-writing clarification branch for explicit incomplete captions. Ask whether this is an inventory entry or an already-taken event, then request product identity and, for intake, actual amount/unit/time. Never infer ingestion, recipient, or dosage from a label. Preserve the existing complete-request proposal/confirmation path. Persist a `waiting_for_user` outcome rather than claiming success or showing a retryable failure.

The clipped stop-medication message is not resolved by this change. Its exact text and target cannot be recovered reliably from this screenshot; no medication mutation is performed.

## Evidence

- SQLite focused suite: 41 passed (`/tmp/reva-photo-details-tests.log`).
- First test invocation failed during setup because the default local PostgreSQL port was unavailable; not a behavioral red result.
- PostgreSQL focused suite: 91 passed in 88.19 seconds (`/tmp/reva-photo-details-pg.log`).
- System Map gate passed (`/tmp/reva-photo-details-map.log`).
- Independent safety review: GO for b07c98c5099283175850da865a0b700d36eaea8e. Full local CI-mode running; remote main CI 39555135244 running. Deployment pending. No mobile change; no OTA warranted for this patch.

- Additional outcome/preview/guidance regression: 308 passed. Original CI 39555135244 preserved: live-model waiver missing and dossier front-matter missing. Corrected dossier metadata; explicit SHA-scoped live-model waiver follows the existing user restriction, not a claim of live evaluation.

## 2026-10-28 continuation: text-only reference to the preceding photo

The user explicitly requested fixing the new screenshot together with adopting the approved downward-opening guardian icon. Icon assets and simulator evidence are documented in `docs/design/xiaoqihou/guardian-icon.md`.

The screenshot's follow-up `记录以上图片补剂` has no new image attachment. The existing deterministic clarification only ran inside `if images` and did not recognize this wording. It therefore reached generic record-failure handling. The repair admits a bounded set of explicit photo-reference phrases into the existing non-writing clarification, with or without a current attachment. It asks inventory versus actual intake, then product name and actual amount/unit/time as needed. It does not fetch historical photos, infer product identities or ingestion, reuse label doses, or create a pending write. Complete-request preview and consent/owner checks remain unchanged. This is a clarification repair, not automatic recognition of a previous photo or completion of the user's health record.

### Current verification

- Behavioral RED: 7 failed, 52 passed before the fix (`/tmp/xiaoqihou-photo-reference-red.log`).
- Focused SQLite regressions: 130 passed before adding the durable two-turn replay case (`/tmp/xiaoqihou-photo-reference-green.log`).
- PostgreSQL 17, dedicated UTF-8 test database: all 131 focused tests passed in 108.69 seconds (`/tmp/xiaoqihou-photo-reference-pg.log`). Includes persisted `waiting_for_user`, same-turn replay, no health write or pending intent, unchanged preceding photo message, complete-request confirmation, and ownership boundaries. Initial database setup inherited SQL_ASCII and failed before tests; recreated only this run's empty test database as UTF-8.
- Adjacent food-vision, photo routing, turn outcome, meal clarification, mixed supplement/diet, unit clarification, and no-false-write-claim suites: 624 passed, 18 skipped in 132.21 seconds (`/tmp/xiaoqihou-photo-reference-routing.log`). Skips are existing gated cases, not evidence of passing coverage.
- Live synthesis gate attempted in an isolated in-memory synthetic-user database: offline invariants 12/12, health-agent core 50/50, trajectory contracts 12/12, golden traces 9/9 passed. Live orchestrator 0/5: local provider has no configured API credential and default destination was rejected by the disclosure guard (`recipient_not_disclosed`). No guard bypass, production data, or prior waiver used. Live evaluation is NOT passed (`/tmp/xiaoqihou-photo-reference-llm.log`).
- Workflow trace: `docs/_generated/harness-runs/b0492672cab8.jsonl`.
- Independent read-only safety review of fixed `ac5b874b280337a25978402cf07781e8d396dc3c`: **GO for code safety**, no blocking findings. Reviewer independently ran executor, recognition, and food-vision suites: 311 passed, 1 existing skip (`/tmp/photo-safety-review-ac5b874b2.log`). It confirmed bounded non-writing clarification, owner-scoped replay, preserved current-image complete previews and read-only/report/file restrictions. This GO is not publication approval or evidence of live-model success.
- Structural validation passed: System Map, dossier consistency, and agent-skill governance (`/tmp/xiaoqihou-photo-reference-validate.log`). Tracked-file secret scan and whitespace checks passed. The full exact-candidate CI and live-change gate are still not green; no confirmation or waiver variable was set.

### Publication boundary

Current local base is `0ff0f34aa2ab510345163bb8ee3c6d3fdc379644`. Existing production release run `40618543912` failed in read-only readiness with `exam closure history is incomplete or invalid` / `Untrusted release receipt`; backend and native publish jobs were skipped. Another active release repair owns this path; this task does not alter its receipts or retry publication. Exact-candidate full CI and live-model gate remain required before publishing this change. The icon changes need a new native build; OTA cannot update the installed launcher icon. This task has not replaced the frozen 282 review candidate, deployed backend changes, or published OTA.

## 2026-10-28 10:34 CST continuation: both fixes confirmed

The delayed clarification reply explicitly confirms both items. The initial missing-provider failure above is retained, but its local configuration blocker has now been resolved using only the existing disclosed provider configuration allowlist, a cleared child environment, an isolated working directory, and the official in-memory synthetic consent harness. No production database, screenshot image, user record, or consent/disclosure bypass was used.

- Exact candidate `4d26065d20d43374cff5f32b1afd0b89f588f687`: official live synthesis gate exited 0. Invariants 12/12, health-agent core 50/50, orchestrator 5/5, trajectory contracts 12/12, golden traces 9/9. Evidence: `/tmp/xiaoqihou-photo-reference-live-configured.log` and candidate binding `/tmp/xiaoqihou-photo-reference-live-configured-binding.json`.
- The health-agent-core and orchestrator main baseline files are absent. This proves a fresh automatic evaluation pass, not a baseline comparison or full real-user acceptance.
- Bound `HARNESS_LIVE_LLM_EVAL_CONFIRMED` to that full SHA and pushed only the two already-reviewed task commits. No waiver was used. Full current-main CI [40621691223](https://github.com/itsoso/health-llm-driven/actions/runs/40621691223) completed successfully: all 32 jobs passed. Redacted verification inventory: `docs/reviews/2026-10-28-photo-reference-verification.json`.
- Existing release `40618543912` remains failed; no new production release, receipt replacement, OTA or native upload was attempted. Original 282/source838 review candidate is unchanged. The new icon remains verified in the local iOS simulator; a new native distribution is still needed for a phone's launcher icon.
- No changes from the concurrent release-repair or benchmark work were staged or pushed. This evidence update follows the frozen code candidate and is not part of its tested source tree.

## 2026-10-28 explicit publication request: resume the interrupted launcher repair

The user now explicitly requests publishing both fixes. Read-only inspection confirms the prior publishing chat ended in a model-capacity system error, with its final runtime repair still uncommitted. That patch's provenance and 150-test result were read from the interrupted turn; it is now adopted into this task, rather than competing with a running writer. Fresh production readback is still `a8cd1e7635eb697c0f0bc528382c98b3602893c3`, all three business services active, authorization bound to `0ff0f34aa2ab510345163bb8ee3c6d3fdc379644`, no business lease, and no authorized-workspace files. This absence alone is not release authority: canonical history and rotation gates remain required.

The launcher repair re-enters the fixed secure Python 3.12 interpreter with `-I -S -B` before claims or source loads, after checking the installed bytes and authorization. Caller Python/proxy/CA/token environment is discarded. Nested history consumers also disable bytecode writes, preserving canonical source cleanliness. No closure, claim, migration, runtime transaction, or old failure receipt is changed by this code repair.

- Fresh initial launcher/history/bootstrap tests: 334 passed (`/tmp/xiaoqihou-publication-runtime-regression.log`). Existing runtime-specific RED and real 3.10-to-3.12 transfer evidence belong to the interrupted publisher; current independent review is still required.
- Added the new runtime suite to the CI release-invariants command and its required-suite contract. The new contract first failed (1 failed, 20 passed) because CI did not run the suite; the workflow now includes it. Final verification and fixed-commit independent safety review follow before any privileged installation.
- Final launcher/history/bootstrap/CI-contract verification: 356 passed (`/tmp/xiaoqihou-publication-runtime-final.log`), including an actual subprocess `execve` into `-I -S -B` with synthetic injected environment values proving their removal. This does not impersonate the installed root entry or replace server-side ownership checks.
- System Map selector for this release script is unindexed; full `system-map-check.sh` passed (`/tmp/xiaoqihou-publication-map.log`). Source and neighboring tests were inspected directly. Benchmark changes and other historical dossier/receipt changes remain outside this task's staging scope.

## 2026-10-28 publication verified

The final deployed source is `5ec09bc3ec893a7590878cf45c7add03b7faea22`. Exact full CI [40625433541](https://github.com/itsoso/health-llm-driven/actions/runs/40625433541) passed all 32 jobs. The local release-invariants command passed 5,243 tests with 65 existing skips and 127 subtests; independent fixed-commit launcher safety review returned GO. The previous failed readiness and credential-preparation attempts remain preserved.

### G3 / G4 / G5

- G3 verification: PASS for the recorded test and exact-CI scope. The earlier fresh synthetic live-model gate passed before the release-runtime-only continuation; no new health behavior was added by the launcher commit. Missing main baselines remain unclaimed.
- G4 safety: PASS. Fixed code and operator preparation received independent GO; the Web path independently passed 92 tests with 2 skips.
- G5 deployment health: PASS. Formal backend [40628656668](https://github.com/itsoso/health-llm-driven/actions/runs/40628656668) completed successfully. Independent production readback confirms exact source, `SUCCEEDED`, finalized no-backup runtime transaction, no business lease, healthy API/database/Redis/Celery, stable backend/worker/beat identities and zero restarts, and HTTP 401 for anonymous `/api/v1/agent/send`.

The user confirmed another same-version release was theirs and instructed this task to wait. This task's Web artifact `6125ecc18bec4fdfb8c0ece0cec22e7d` is READY and was never published. The external operation `d6364692216b4593a500c0d78b6274a6` completed `FRONTEND_SUCCEEDED` with the same source and frontend tree. Independent readback verified its proof-file hashes, absent lease, active frontend, HTTP 200 login/privacy pages, and public `favicon.png` and `icon.png` bytes matching this candidate. No second Web publication was issued.

The new native icon package was built and signed from a clean exact-source checkout as 1.3.6 (283), bundle `life.executor.health`, production channel/runtime 1.3.6. Existing ad-hoc provisioning covers one registered device. The public IPA, manifest, install page and QR were independently read back and hash-matched. IPA SHA-256: `4ee96dd6b9deafd708b98acf3cfa0d19b94746aa495caa6abb924cd900d3888d`. Install page: [小气候 1.3.6 (283)](https://health.executor.life/mobile-install/ios/xiaoqihou-guardian-5ec09bc3e/install.html).

### G6 acceptance boundary

Deployment and public artifact verification are complete. The approved icon was visually verified in the iOS simulator; phone installation, signed-in interaction and the original health-record request have not been exercised. No real health records were inspected, replayed or written. The clarification asks inventory versus actual intake and missing facts; it does not claim the old photo has been recognized or saved. This remains `shipping` for those unverified acceptance items. No OTA crossed the native icon boundary, no TestFlight/App Store submission was made, and the existing 282 review candidate was not replaced. No backups or rollback copies were created or inspected.

Redacted durable evidence index: `docs/reviews/2026-10-28-xiaoqihou-guardian-release.json`.

## 2026-10-28 chat UI continuation and explicit TestFlight request

User requests: “更新 testflight”; then “优化 ui 和交互 顶部状态有重复 顶部新建也不够美观”. This UI iteration joins that pending TestFlight update; no TestFlight build or upload has started. The current main is `584489075decd5c6dd63b7dcf68189c466ba54b6`; observed production remains the successful `5ec09bc3ec893a7590878cf45c7add03b7faea22` release above. The Ad Hoc IPA cannot be submitted as a Store-signed build.

The bounded presentation repair keeps running/submitted/writing/verifying progress in the current assistant reply. The top rail preserves terminal partial, waiting-for-user, blocked/refused, uncertain-write and failure outcomes, including late stream cleanup. Risk context retains priority and is not hidden with ordinary Today context. The active panel shows one current label, deduplicates equivalent understanding labels without changing stored steps, and collapses distinct preceding steps behind an explicit disclosure. Previous-step bullets are neutral rather than suggesting verified successful writes. Stop remains a separate accessible 44-point action instead of being swallowed by the assistant message's text accessibility group.

The header replaces the nested capsule and visible new-chat text with a compact mint compose button plus history and more actions. Existing callbacks and accessible labels are preserved; each action retains its 44-point touch target. No API, persistence, owner scope, retry authority, health interpretation or model prompt changes are introduced.

- Initial behavioral RED: 5 failed, 48 passed (`/tmp/xiaoqihou-chat-chrome-red-fixed.log`). A separate accessibility RED reproduces the outer group swallowing action access (`/tmp/xiaoqihou-chat-chrome-a11y-red.log`). The first initial run also caught a transient test-edit reference error; it is not counted as behavioral RED.
- Focused GREEN: 60 passed. Final chat-component/engine regression: 557 passed, including collapse/expand, Stop callback and terminal outcomes during late stream cleanup (`/tmp/xiaoqihou-chat-chrome-commit-tests.log`). Fresh TypeScript and scoped ESLint passed.
- System Map does not index the component path; source and adjacent tests were inspected directly. Full map/navigation/doc-drift checks passed before and after the change.
- Real native components rendered on iPhone 17 / iOS 26.5 in a separately identified preview app with explicitly synthetic dialogue and network-free callbacks. Native accessibility readback exposes new/history/more, current status and Stop individually. New and Stop actions were exercised and the example restored. Preview: `tmp/xiaoqihou-chat-chrome/preview.png`. The temporary entrypoint was removed after bundling; it is not a shipped route. This is component UI evidence, not signed-in chat or real-health-data acceptance.
- The original App Store review candidate remains unchanged. Final fixed-source independent review, exact main CI, canonical publication authorization, Store build/upload and Apple processing are still required for the requested TestFlight delivery.

### Integration and recovery edge

Independent review of `1390f4313638f67c4fa65c3ed6beb0188a6a5751` returned GO with 53 reviewer tests. Push was rejected without a remote write because another publisher advanced main to `b257203591c49e17222995dd1597a2b35e28d6a6`, preserving Store 282 native branding for an explicitly requested OTA. Shared dirty files overlap that publisher's documents, so integration uses a clean main checkout at `/tmp/xiaoqihou-ui-release-integration`; its cherry-picked UI is `8bd31ec5833b8e13b02a91c31af0684c156a8aee`. This task has asked whether to wait for that OTA or receive explicit release ownership; no TestFlight/vendor claim, credential refresh or authorization rotation was started.

Full integrated Mobile regression found one additional case (4,014 passed, 1 failed, 1 skipped): a running transport-recovery turn containing only a user message must retain the neutral top status because no assistant surface exists yet. The repair now suppresses the top rail only when an assistant message actually has streaming/recovery UI for the current turn, or the newest legacy message without turn metadata. Terminal outcomes remain outside this suppression. The recovery-focused run passed 86 tests. The fresh complete Mobile run then exited 0: all 381 suites passed, 4,015 tests passed, 1 existing skip and 1 snapshot passed (`/tmp/xiaoqihou-ui-mobile-final-full.log`); TypeScript exited 0 (`/tmp/xiaoqihou-ui-mobile-final-types.log`). The prior 557-test pass is not used as proof of this final change.

The first local release-invariants invocation stopped on its Python 3.12 prerequisite; a PATH-corrected run was intentionally stopped after the UI source changed. Neither is claimed as a completed exact-candidate release check. Full exact-source CI and a fresh release integration gate remain required after handoff. The production GitHub read credential is expired; the unexecuted refresh draft is not approved and must not be reused with a stale SHA.


### OTA handoff confirmed; native TestFlight candidate

The user chose to wait for the other OTA publication before this TestFlight. Fresh independent readback confirms b257203591c49e17222995dd1597a2b35e28d6a6 backend SUCCEEDED, production exact SHA and healthy services; trusted OTA validate 40635239299 and publish 40635498812 both succeeded. The durable OTA completed receipt SHA256 is fa712a9ee4939dcda0f7ba6ae751ca9e145d9e95ae2b1219eb465a1edc2c7f4f, with update group 30a312b8-c154-488c-a0fa-d354e10ba9b0 and update 01a180e8-1b3b-7e7c-a593-35d63b9623f7. The actual business lease /run/lock/health-app-release is absent. This proves publication completion, not device uptake.

The clean integrated main candidate retains the other publisher's runtime guardian-avatar asset and exam changes, and reinstates only the approved native icon/adaptive/splash/favicon and matching background configuration from the already reviewed 5ec source for the explicitly requested new TestFlight build. This is a native build change and is not an OTA candidate. App Store candidate 282 remains selected; no App Review action is authorized. UI final integrated independent review returned GO with 133 reviewer tests. Full Mobile suite passed 4015 tests with one existing skip; TypeScript, scoped lint, System Map, dossier and tracked-secret checks passed. Native-launcher background regression first failed (1 failed,3 passed) against the OTA-preserved assets. New exact-source checks, independent review and current-main full CI remain required before any publication authorization rotation or build/upload. The server read credential is expired and any old refresh drafts are stale.


### TestFlight publication completed

Exact candidate `ae7a5972921ee9d51eec2c90c7893e6941d2d7ff` passed both full CI runs `40640519405` and `40640544354`, 32/32 jobs each. The actual local CI-mode release integration exited 0 with 5243 passed, 65 skipped and 127 subtests passed. The earlier missing-runtime/dependency preparation failures remain recorded and are not counted as a pass. Independent final native/UI review returned GO. The first local credential transport stopped while importing cryptography, before private-key access or mint; dependency-enabled isolated execution was independently reviewed and completed once. Original failure evidence was retained. Normal b257 successful-authorization retirement and canonical ae7 installation completed without backups.

Trusted validate `40643806816` and release `40643892330` both succeeded. Exact EAS Store/production iOS build `ea1dda2a-86b3-4e46-adf8-b2b024465154` was built and revalidated by the trusted workflow, then uploaded via submission `436332f3-45f5-4f1a-bd97-5438e9acd90e`. ASC `1.3.6 (283)`, build `1eb785e3-54c2-42dd-81d5-66f7bb1fd2e0`, is VALID and IN_BETA_TESTING; both Team (Expo) and 内部测试 groups include the exact build. Chinese TestFlight notes were written and read back. Existing App Store selection remains build 282; no App Review submission or tester invitation was sent.

Production independently reports exact ae7, durable backend SUCCEEDED receipt SHA256 `822df66f4f266f2f78f955475241b8d974e2db806a05c57a032f5b4128e815a7`, healthy API/DB/Redis/Celery, anonymous agent POST 401 and no business lease. The completed b257 OTA was not repeated.

TestFlight distribution is complete. Signed-in phone installation, real-health-data behavior and local static inspection of this Store IPA remain unverified. Earlier simulator component and guardian-icon evidence is source/UI evidence, not same-IPA device acceptance. No real health records were read or written. EAS metadata checks are enforced in the successful trusted workflow; additional local read-only EAS metadata lookup was unavailable because no local Expo credential was available. No signing identity, upload or release was retried.

Durable redacted release index: `docs/reviews/2026-10-28-xiaoqihou-testflight-release.json`.


### New submission blocker: omitted single-domain oxygen read

After requesting App Review, the user supplied another screenshot showing “昨晚血氧饱和度如何” ending in query-incomplete output. No App Review submission has occurred; submission is paused for this known failure. The revised header is visible, so earlier UI delivery does not prove query correctness. No production health records were inspected.

Synthetic scope inspection confirms the literal phrase binds only the authenticated owner's SpO2, account-local wake date and period=sleep_night. Existing full-path tests use a provider that requests a tool. In contrast, the omitted-tool fallback `_initial_composed_read_calls` requires at least two scoped queries; a single-domain query can terminate incomplete without an actual read. New tests use the literal phrase and a tool-omitting provider through Pi/gateway/persistence. Preserve owner/date/night-period, no writes or sync, no new model-driven replay of failed reads, and clinical uncertainty. Old history is not edited or automatically replayed. The first new-test invocation used the wrong working directory and failed before creating the test; it is not behavioral RED evidence.


- Behavioral RED after correcting test setup: all six exact-phrase/mode cases failed because no gateway read was dispatched (`/tmp/xiaoqihou-last-night-oxygen-behavior-red.log`). Initial unpack-count and missing Pi dependency failures are retained but are not behavioral RED.
- Minimal change: permit the existing omitted-tool proposal path for exactly one already-bound SpO2 query as well as the existing multi-domain case. Pi schema validation, capability authorization and the existing transport retry budget are unchanged. No direct adapter dispatch, new sync, broad owner/date inference or stored-message rewrite.
- Final focused/adjacent SQLite suite: 196 passed. Dedicated UTF-8 PostgreSQL 17 synthetic database: 55 passed, including real owner/time/source-bound sample filtering, no-data completion, read-error disclosure and third-party/cancel/restriction negatives. Early expanded tests incorrectly expected model prose to include samples and assumed no existing transport retry; corrected assertions inspect the real gateway payload and preserve its existing bounded two-attempt transport behavior. No production behavior was changed to satisfy those test assumptions.
- App Review remains pending this fix's independent safety review, fresh live-model gate, exact main CI, backend deployment and acceptance. The mobile code is unchanged, so a fresh TestFlight build/OTA is not needed just for this server repair; 283 must be revalidated against the repaired backend before submission.

### Oxygen repair shipped; App Review preparation resumed

The fixed candidate is `2f94c6f1a8dbee3bea2ce3e63c2020ed9b947852`. Fresh local composed-read regression passed 1,282 tests; the focused SQLite and PostgreSQL evidence above remains unchanged. The configured live-model gate passed all invariants, core, orchestrator, trajectory and golden suites against synthetic-only data. Independent safety review returned GO, and exact main CI `40649656551` passed all 32 jobs.

Canonical staging, a new bounded read-only GitHub credential and successful ae7 authorization retirement were independently reviewed and completed without backups. The first corrected credential wrapper stopped before intent or mint because it rejected the prior release's expected skipped retained-TestFlight job; readback proved no local or remote side effect. A new uniquely named wrapper changed only that terminal-job predicate, received independent GO and completed once. Trusted validate `40652396592` and backend-only release `40652462337` succeeded. Production now reports exact `2f94c6f1a8dbee3bea2ce3e63c2020ed9b947852`, backend `SUCCEEDED`, no business lease, healthy API/database/Redis/Celery and anonymous agent POST 401.

The App Store review demo account then repeated the exact phrase `昨晚血氧饱和度如何` against production. Login and query returned 200, a new complete conversation/message pair was persisted, the response was nonempty, `health_query` was used, and neither “本轮查询未完成” nor “暂不汇总” appeared. Only the synthetic review account was used; no real health data was read or written.

Store build 283 remains the frozen mobile candidate; no new native build, TestFlight upload or OTA was issued for this backend-only repair. Its exact IPA was downloaded and inspected: SHA256 `14545db4331b53e6f9d1f39a55d93e19db21f5a0df147a83f71bdd74dd935fcd`, iPhone/portrait identity, production signing entitlements, Xcode 2660 and iOS SDK 26.5 all match the candidate receipt. A Release simulator app with actual build number 283 was built from frozen source ae7 for remaining UI review; this simulator binary is not relabeled as the Store IPA. App Store selection and review submission remain unchanged until the final UI, privacy, regulatory, age-rating, screenshot and review-account gates pass.

### App Store final gate evidence

The exact-source Release simulator for 1.3.6 (283) accepted the unchanged App Review credentials and preserved the authenticated session across a cold relaunch. Direct CUA review verified the revised compact header, non-duplicated top status, Today navigation, Personal Center, privacy policy, report import and account-deletion entry. A production probe through the synthetic review account returned a complete answer for the exact oxygen phrase. No real health record or phone was used.

The Store IPA remains bound to EAS build `ea1dda2a-86b3-4e46-adf8-b2b024465154`, ASC build `1eb785e3-54c2-42dd-81d5-66f7bb1fd2e0`, source `ae7a5972921ee9d51eec2c90c7893e6941d2d7ff` and SHA256 `14545db4331b53e6f9d1f39a55d93e19db21f5a0df147a83f71bdd74dd935fcd`. Current-main policy CI `40654808636` passed all 32 jobs. App Store Connect retains complete 1290x2796 screenshots; a separate candidate-283 simulator set was generated and privacy-sanitized for gate validation, but is not promoted as better marketing material. The saved age-rating questionnaire reports 17+, the review details contain the synthetic demo credentials and reviewer notes, privacy disclosures remain published at app level, and the release scope is declared not to be a regulated medical device. Production OTA is frozen for this candidate and manual App Store release remains selected.

The release owner accepts the simulator-only residual risks listed in `/tmp/xiaoqihou-283-simulator-acceptance.json` under the standing policy in `docs/governance/simulator-review-acceptance.md`. This is not an Apple waiver and does not claim physical installation, microphone, camera, HealthKit, share handoff, background GPS or other hardware-only acceptance.

The final release-pack gate passed with the exact Store IPA, native artifact receipt, source-bound Release-simulator acceptance, privacy-sanitized screenshot validation, current production review-account check, published privacy declaration, saved 17+ age rating and the `No` regulated-medical-device declaration. App Store Connect then replaced selected build 282 with VALID, App Store-eligible build 283 and read it back. Review submission `e85560dc-7f3a-4b27-a8f2-02c1166a78b9` contains only version 1.3.6 and was submitted once at `2026-10-28T10:43:43.49Z`; both the review submission and App Store version read back `WAITING_FOR_REVIEW`. Release type remains `MANUAL`. No App Review action was replayed, and the existing screenshots were retained rather than replacing them with privacy-blurred QA evidence.


### 2026-10-28 nominal oxygen-query incident and review withdrawal

A later production screenshot used the exact phrase `昨晚血氧饱和度情况`. Unlike the already repaired `昨晚血氧饱和度如何`, this nominal question contains no generic read verb. The semantic binder classified it as unknown, so no owner/date-bound SpO2 read reached the gateway. The visible failure is therefore a semantic-entry defect, not evidence that the prior omitted-tool recovery or Store build 283 was replaced. No production health records were inspected.

The active App Review submission was withdrawn before repair. Readback shows the old review submission `COMPLETE` and App Store version `DEVELOPER_REJECTED`; the cancellation is not replayed. Store build 283 remains the selected frozen mobile candidate and manual release remains configured.

The repair admits only a full utterance limited to optional current-user wording, `昨晚` / `昨夜`, blood-oxygen / SpO2, optional saturation wording, then `情况`. It reuses the existing owner-, wake-date- and `sleep_night`-bound query path. It does not authorize a generic `情况` suffix, arbitrary prefixes, third-party data, appended abnormality claims, writes, sync, broader dates, or model-authored owner scope. Behavioral RED was four exact phrase variants across panel and sample modes; all failed before the change because no read was dispatched. The first G4 review found that a suffix-search draft admitted named third-party prefixes; new 张三, 小王 and third-party-data-prefix tests reproduced three unauthorized reads. That draft was not committed or released. The implementation was narrowed to a whole-utterance match and the corrected G4 re-review returned GO.

Fresh verification after the minimal change:

- Focused exact phrase and expanded named-owner negative-boundary suite: 35 passed.
- Adjacent SQLite semantic, owner-scope, adversarial, sleep oxygen and read-repair suites: 1,299 passed.
- Dedicated UTF-8 PostgreSQL 17 exact and sleep-oxygen suites after the G4 correction: 107 passed. The earlier 96-test run applied to the rejected suffix-search draft and is not final evidence.
- Full System Map, mobile navigation and doc-drift gate: passed.
- The path-sensitive LLM change gate reports `live_llm_required=false` for this deterministic semantic-binder file. The no-cost synthesis gate passed invariants 12/12, health-agent core 50/50, trajectory contracts 12/12 and goldens 9/9. A separate live attempt using the ordinary local `.env` failed because no disclosed provider credential was present; it is retained as a failure and is not used as proof. No waiver or confirmation was set.
- Corrected independent safety re-review: G4 GO. Exact-main CI, backend release and production review-account repetition remain required before resubmission. No OTA or new native build is required for this backend semantic repair.

### Nominal oxygen repair deployed and production-verified

Exact candidate `e37a9c6a34bd080bd96d474cf75d7d1a245fbd20` passed full CI `40679430049`. Canonical validate `40681949042` and backend-only release `40682044453` both completed successfully. Independent production readback confirms the exact SHA, durable backend `SUCCEEDED` receipt SHA256 `cd82b555f81fc324632a6f1a91a5f9ac4a76be2372d4f04b7d332387f2a8b1ff`, absent release leases, active backend/socket/worker/beat with zero restarts, public health 200 and anonymous Agent POST 401.

The App Review synthetic account then sent the exact phrase `昨晚血氧饱和度情况` to production. Login and query returned 200, the exact user message and a nonempty assistant response were persisted, `health_query` was used, and the response contained none of the known incomplete/refusal copy. No real health data or phone was used. Store build 283 remains the selected frozen mobile candidate with manual release; no OTA, native rebuild, TestFlight upload or backup was performed for this backend repair.

The final Store release-pack gate passed again against the frozen IPA, native receipt, accepted simulator-risk evidence, privacy-sanitized screenshots, live synthetic review account and current ASC metadata. A new review submission `b1fa1609-5ef1-40fb-a3f8-c67b20840a48` was created, given exactly the 1.3.6 version item and submitted once at `2026-10-28T11:55:15.904Z`. Independent readback reports the submission and version `WAITING_FOR_REVIEW`, selected build 283 `VALID`, and release type `MANUAL`. The completed withdrawn submission was not reused or replayed.

## 2026-10-29 provenance UI OTA preclaim recovery

The prompt/response review reduced duplicate completed-answer provenance in the chat UI while preserving the full stored, copied, shared and spoken answer. Candidate `a4d922886c859f4a2a43d4322fd43d128bf934f3` passed all 32 CI jobs and its backend release completed successfully. Trusted OTA validate `40735444174` passed, but the only publish run `40735832856` stopped at `claim-ota` with `command_failed`. The preserved official artifact contains only `ota-diagnostic.json`, `ota-claim.json` and `ota-preflight.json`; no vendor receipt exists, and the reviewed publisher calls the vendor only after a confirmed server claim. The failed SHA must never be republished.

The recovery adds one byte-bound `trusted_ota_unclaimed_retirement.py` profile for that exact run, job, artifact ZIP, three JSON value digests and four original publisher source hashes. It changes no vendor, backend, prompt, health-read or health-write behavior. The operator still requires fresh official evidence, the original intent and lease, unchanged inode identities, both original locks, exact production health and an independently green closing SHA. Inspection is read-only; execution requires the returned evidence digest, writes a durable closure intent, retires the original lease by same-filesystem rename and writes a distinct `CLOSED_UNPUBLISHED_CLAIM` terminal. Any drift, vendor evidence, previous closure attempt or partial write blocks without replay.

TDD RED: the new a4d profile was rejected as unknown before implementation. The focused profile became green after adding the fixed evidence. The complete local file has 30 existing macOS-only failures because `/etc` is a symlink and its cross-module history fixture assumes the Linux host layout; all four historical profiles fail identically. That result is retained and is not counted as green. Linux exact-SHA CI and the remaining closure suite are required before any canonical staging or privileged action.

The recovery test file was not previously listed in the Linux `release-invariants` command. A CI-contract RED reproduced that omission; the workflow now runs the full closure suite and the contract requires it. This makes the real Linux producer-to-history-consumer tests part of the exact-SHA gate rather than relying on the macOS exclusion.

The first exact-main CI `40781356755` then failed in the newly enabled Linux suite after 2,378 release tests passed. Linux reused the token file inode after the test unlinked and recreated identical bytes, proving that device/inode/content alone could miss a replacement. No server or vendor action ran. A new behavioral RED changed only the token metadata while keeping the inode and contents; the old implementation did not block. Lease snapshots now bind each file's `ctime_ns` in addition to device, inode and digest, and the same-inode metadata-drift test passes. Historical closure validation accepts the four legacy records without `ctime_ns`, while the new a4d profile requires it. Fresh focused recovery: 222 passed with the 30 known macOS-only cross-module cases deselected; adjacent release/OTA suites: 173 passed, 1 existing skip. A new fixed-commit G4 review and exact-main CI are required before closure inspection.
