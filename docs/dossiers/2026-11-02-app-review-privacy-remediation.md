# App Review privacy remediation — 2026-11-02

| 字段 | 值 |
|---|---|
| 状态 | in_progress |
| 当前阶段 | S6 发布验证；新的独立安全复审 GO，等待精确 revision 入 main、CI 与 trusted release |

Controller: mobile-testflight-release; overlays: ios-app-review-gate, safety-gate.

## G1 准入

裁决：PASS。用户明确要求修复 App Review 对第三方 AI 数据共享披露、授权和
HealthKit purpose string 的拒审问题，并在发布闸通过后重新提交审核。本次只收紧既有
AI 数据发送前的明确同意、隐私说明和原生用途文案，不扩大健康数据读取、写入、诊断、
治疗或自动化权限；拒绝同意后必须保留非 AI 功能且不得发送数据。

## Scope and baseline

User authorized fixing AI disclosure, HealthKit purpose strings and privacy policies,
regression tests, simulator acceptance, a new package and an App Review reply draft.
No Apple message, submission, production deployment or Git publication has occurred.
The original shared main worktree is dirty, so the current candidate lives in an
isolated checkout based on origin/main
`9c8deb52b39c6ca5bbfdece621c99f463db6d3ad`.

Review submission: `3f8c84d4-8cc5-4123-9829-6a318e1444e9`; app `6763569720`.
Rejected: 1.3.6 (286), review date 2026-10-29, iPad Air 11-inch (M3).
Build 286 source: `e6f26f6230e429a29113e4322ff5d7be22764787`.

## Evidence and causes

- Apple requires recipient/data/purpose disclosure and permission before third-party
  AI sharing, plus adequate third-party protection in the privacy policy.
- Apple's first attachment shows the idle voice conversation screen without visible
  AI disclosure. It does not prove whether a prior dialog was shown or accepted.
- Build 286 and the current consent service reuse a server-side grant without
  displaying the disclosure on this installation/session. This behavior is covered
  by the old regression test. Read-only verification found the saved reviewer account
  already accepted the current policy on 2026-10-01, before the review. This supports
  the skipped-disclosure explanation, but does not reconstruct the reviewer's actions.
- Continuous voice conversation does call ensureAIConsent before recording.
  Realtime composer dictation did not call the client consent presenter before
  opening its ASR socket. Backend consent checks exist; this is a confirmed client
  disclosure gap, not evidence of unauthorized upstream transmission.
- react-native-health's healthSharePermission overrides the Info.plist description.
  The generated old string only said it reads device health data. Write permissions
  are empty, yet the plugin supplied a misleading default write purpose string.
- Existing policy identified recipients and controls but omitted concrete third-party
  protection discussion. Exact provider retention must not be invented.

## Remediation and acceptance

- Show a scrollable standalone disclosure with fixed explicit choices. Require one
  local decision per authenticated process/policy even if the server already has a
  grant; retain server enforcement and account/revocation invalidation.
- Gate realtime dictation before opening its socket; refusal preserves non-AI use.
- Add a visible voice-screen disclosure entry; settings retains withdrawal.
- Make Info.plist the HealthKit purpose string source and verify the full Expo plugin
  chain. Keep an honest write-purpose compatibility string because Apple's static
  validation requires it for the linked HealthKit SDK even though runtime permissions
  remain read-only.
- Keep Web and Mobile policies consistent with actual provider terms and controls.
- Test refusal, pending saves, account switches, revocation, stale policies, ASR
  cancellation, actual native configuration and responsive disclosure rendering.

## Prior local evidence (superseded by the current candidate where noted)

- Mobile: 385 main suites / 3937 passed / 1 skipped; isolated stateful suites 134
  passed; isolated composer 86 passed. Total 4157 passed, 1 skipped.
- Backend consent/media/agent boundary checks: 38 passed, 2 skipped. No schema
  changes; this does not establish PostgreSQL integration coverage for skips.
- Web privacy: 3 passed. TypeScript, design gate, System Map, diff whitespace and
  LLM-change gate passed. This earlier code GO did not cover the later streaming-TTS
  account/revocation review and is not the current safety verdict.
- Production-config Release simulator app built successfully with local signing.
  Initial unsigned build could not persist login credentials; signed rebuild fixed
  this and both simulator logins succeeded. App version 1.3.6, local build 1.
- iPhone 17 Pro / iOS 26.5: actual saved review-account login; first disclosure despite
  historical server grant; decline; voice-screen entry; revoke success; regrant and
  readback. Test account's accepted state was restored. No actual audio sent.
- iPad Air 11-inch (M3) / iOS 26.5: fresh login; readable disclosure; decline returns
  to composer; personal settings exposes AI sharing/privacy; native HealthKit sheet
  opens. Mac locked before scrolling to the purpose text, so its final visual
  verification is incomplete. The actual built Info.plist and plugin tests verify
  the full read-purpose text. The later Store upload result supersedes the earlier
  assumption that the write-description key could be absent.
- Screenshots and source-bound simulator archive are in the task artifact folder.
  Simulator archive is not a distributable Store IPA.

## Remaining gates

- In-app privacy-screen acceptance completed after unlock: current date, AI
  recipients, equivalent-protection requirements and retention/deletion boundaries
  read back and screenshot saved. HealthKit sheet opens on both devices; its final
  purpose-text screenshot remains unverified because native scrolling returned
  windowNotFoundAtPosition and then timed out. No hardware test claimed.
- Publish/read back public privacy policy only with deployment authorization;
  verify actual production provider contractual protection.
- Authorized clean commit/push, exact-revision CI-mode integration and trusted Store
  build are required before an IPA can be called ready. Local unit suites do not
  replace these gates. No commit, push, deployment, upload or review reply sent.
- Bind final Store candidate to simulator acceptance and complete final submission
  checks. Hardware-only items remain unverified under existing simulator-risk rules.

## Follow-up — unlocked UI and lock-independent evidence

- Refetched main: `0ddf52a348feb5078e15b3333911907486cec7b2`; difference from the
  tested baseline is only two unrelated documentation files. The existing archive
  remains bound to its original baseline plus source manifest, not the new SHA.
- Saved `ipad-privacy-policy.png`. Native HealthKit sheet interaction encountered
  tool errors after unlock; this is an automation limitation, not a verified pass.
- User requests future viewing without unlocking. A static local evidence index
  provides existing screenshots, report, checksums and packages without controlling
  the desktop. This is historical evidence, not live locked-desktop access. CLI/API
  checks may continue while locked if the host remains awake; UI tasks stay pending.
  No lock/security setting was weakened and no remote-access service was opened.

## 2026-11-04 current-candidate verification and safety review

- Cherry-picked the disclosure, realtime-ASR, HealthKit purpose-string, policy and
  test remediation onto current origin/main. The candidate commits before the latest
  safety fixes are `f19e2acb9` and `7d4772fe4`; the latter keeps the exact public-policy
  gate wording `AI 模型服务`.
- Fresh pre-review checks passed: Mobile 390 suites / 4188 passed / 1 skipped; Web
  114 files / 662 passed / 1 skipped; focused backend consent/media/realtime checks
  47 passed / 2 skipped; App Store release pack, iOS submission preflight, Mobile
  TypeScript and System Map checks passed.
- The first independent reviewer returned **NO-GO** for two concrete blockers:
  streaming TTS was not bound to consent revision/account invalidation, and the
  privacy policy claimed equivalent-or-stricter contractual protection without
  product-specific contract evidence.
- Streaming TTS now captures the consent revision before authentication, rechecks it
  after token load and before append/finish, subscribes to account/revocation/policy
  invalidation, closes the socket, stops playback and rejects an in-flight finish.
  Focused regression evidence: 16/16 Mobile tests passed plus Mobile TypeScript.
- Mobile and Web privacy copy now states only verifiable public provider measures:
  SOC 2, AES-256, published no-training treatment and lawful retention. It explicitly
  avoids zero-retention and product-specific DPA claims. Mobile policy tests 3/3 and
  Web policy tests 3/3 passed; the App Store release pack and iOS preflight passed.
- A new independent read-only safety reviewer returned **GO** after inspecting the
  committed fixes and independently rerunning 6 Mobile suites / 131 tests, Web
  privacy 3/3 and Mobile TypeScript. No blocking finding remains. The reviewer did
  not modify the working tree.
- The registry's deferred external capability `verification-before-completion` is
  not installed as a readable Skill in this environment. Completion discipline is
  therefore enforced through fresh full Mobile/Web suites, App Store release pack,
  iOS preflight, System Map, Dossier consistency, exact-revision CI and trusted
  release gates without claiming that unavailable Skill was executed.

## 2026-11-04 Build 288 upload rejection and correction

- Exact revision `8f272e49aebc1ee8d2640d93eee37a530b181e71` passed full CI, deployed the
  backend, published the updated public privacy policy and produced EAS build
  `2a2fb4da-71b5-477d-88ec-10b6ab29abd5`. The trusted upload workflow completed,
  but App Store Connect independently rejected Build 288 during ingestion.
- App Store Connect reported ITMS-90683: `NSHealthUpdateUsageDescription` was
  required because linked code or entitlements reference sensitive HealthKit APIs.
  Build 288 is not eligible for review and is not represented as a successful Store
  candidate. Existing Build 287 predates this remediation and must not be substituted.
- The new correction preserves the app-authored update purpose after the actual
  `react-native-health` Expo plugin runs. It states that the current app does not
  write Apple Health data, that the key is retained for linked SDK/system
  compatibility, and that any future write behavior requires separate disclosure
  and authorization. Runtime HealthKit permissions remain read-only and the clinical
  records entitlement remains removed.
- TDD evidence: the revised plugin-chain test failed while the key was absent, then
  passed after the fix (62/62 in `app-config.test.ts`). Mobile TypeScript, iOS App
  Store preflight and release-pack validation passed. A new exact main SHA, full CI,
  canonical native build and successful App Store Connect ingestion are still
  required before submission.
- The prior release workspace has both native one-shot claims consumed even though
  App Store Connect later rejected the ingested binary. Rotation therefore now uses
  a byte-pinned successful-backend continuation profile for the exact upload run,
  Build ID and EAS submission ID. It additionally binds both earlier rerun attempts
  and proves their upload step was skipped after the server claim failed. This proof
  certifies only the EAS/Apple upload terminal; the separate Build 288 ingestion
  failure remains the reason a new binary is mandatory. Focused release tests pass
  89/89 and a live read-only GitHub evidence reconstruction matches all reviewed
  job, prior-attempt and log digests.

## 2026-11-04 current native upload continuation

- Exact revision `ad8949e7eeb4abc73968b0c83ebdb38b64a6cae1` already had a
  successful backend-only release in workflow run `41801637758`. Its seven-job
  response is bound by SHA-256
  `99803a1ee17b618ed51973bd03637a5decc1eda4a526de8666dca8036569088f`.
- A later trusted release run `41806221746` reused that exact revision. Its backend
  job failed closed with `authorization already consumed; manual review required`;
  the failure log is bound by SHA-256
  `d3dd2a552675726c85cb9be2ca895f60aad7f21eaa88b9fac909b17027eee823`.
  This failure is not rewritten as a successful aggregate release.
- The same later run successfully uploaded EAS build
  `8370725c-f6b6-4c18-b408-8123b900eb36` through submission
  `76692f33-c058-48b6-8158-fc008bbab6a2`. The complete seven-job response and
  TestFlight job log are independently bound by SHA-256
  `49bce5cde5b80e199245a73451aa6299cd29a1b3569ee66548db52b41eda5cf5` and
  `dd09cc2359bf3538a30072b22879e91cc279d2d984cc38055df6e61783de876d`.
- The continuation profile accepts only this fixed combination: prior backend
  success, current consumed-authorization terminal and current vendor upload. A
  changed run, job, step, failure reason, build, submission, producer hash or log
  digest fails closed. It certifies upload only; Apple processing, TestFlight
  installability, App Review submission and OTA publication remain separate gates.
- TDD evidence: seven new linkage regressions failed before implementation and pass
  afterward. The adjacent native-retirement and continuation suite passes 120/120;
  the broader bootstrap/release/TestFlight/OTA set passes 774/774 after including
  the CI YAML parser dependency. A live read-only reconstruction returned the exact
  reviewed proof. An independent read-only safety reviewer returned **GO** after
  inspecting the rebased commit against current main, rerunning 120/120 focused
  tests and reproducing both workflow reads plus all four pinned digests.
  Exact-revision CI remains required before merge or release-state rotation.
