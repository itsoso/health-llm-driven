# App Review privacy remediation — 2026-11-02

| 字段 | 值 |
|---|---|
| 状态 | in_progress |
| 当前阶段 | S5 实现与本地验证；首轮独立安全复审 NO-GO 的两项阻断已修复，等待新审查者复审 |

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
- Make Info.plist the HealthKit purpose string source; verify the full Expo plugin
  chain and remove unused write permission text.
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
  the full purpose text and absence of unused write-description key.
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
- Fresh pre-review checks passed: Mobile 390 suites / 4185 passed / 1 skipped; Web
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
- These fixes still require a new independent read-only safety re-review. Until it
  returns GO, the candidate must not be published, built, uploaded or resubmitted.
