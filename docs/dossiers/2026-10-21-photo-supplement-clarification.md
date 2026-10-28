# Photo supplement record clarification

| 字段 | 值 |
|---|---|
| slug | photo-supplement-clarification |
| 当前阶段 | S5 对话界面优化，准备合并 TestFlight 更新 |
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
