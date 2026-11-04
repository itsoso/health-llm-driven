# App Review reply — draft, not sent

Submission: 3f8c84d4-8cc5-4123-9829-6a318e1444e9
Version: 1.3.6. Replacement Store build: PENDING trusted build.

Do not send this draft until the exact Store build, live privacy policy and
candidate acceptance are verified. Replace the build placeholder with that
artifact's actual build number. Local simulator build 1 is NOT a Store build.

## Proposed reply

Hello App Review,

Thank you for the detailed feedback. We have prepared changes addressing both
privacy findings in version 1.3.6, replacement build [VERIFIED STORE BUILD].

**Third-party AI disclosure and permission (5.1.1(i), 5.1.2(i))**

The app now presents a dedicated, scrollable AI Data Sharing screen before the
first AI action in the current authenticated app session, even if the account
already has a previously saved permission. It identifies the actual recipients,
the data categories to be transmitted and their purposes, and provides separate
“Not now” and “Agree and continue” choices. Permission must be successfully saved
before transmission. Login, HealthKit access and microphone permission do not
constitute AI sharing consent.

We also added the missing client disclosure gate to realtime voice dictation.
Withdrawing permission cancels active realtime recording/transmission and blocks
subsequent audio frames. Declining preserves the existing composer draft and
non-AI functionality. The voice conversation screen has a visible link to review
AI recipients and sharing permission.

Please sign in with the review account, open the voice conversation from the
more menu and tap the microphone, or use realtime dictation in the message
composer. The AI Data Sharing screen appears before audio transmission. Choose
“暂不使用” to decline, or “同意并继续” to agree. You can review or withdraw permission
under Personal Center → Settings → AI Data Sharing (“AI 数据共享”).

The in-app and public privacy policies explain collection methods, AI recipients,
processing purposes, equivalent protection requirements, and retention/deletion
boundaries. Withdrawal stops future transmission; it does not automatically
recall or delete previously transmitted data. Provider policy links are included.
Public policy: https://health.executor.life/privacy

**HealthKit purpose string (5.1.1(ii))**

We corrected a native configuration-plugin override that shortened the HealthKit
purpose string. The replacement binary describes the selected health data, its
use in the user's health record and trends, and a concrete example: reviewing
weekly steps and sleep duration. It also explains that users choose the granted
data and can revoke access in Apple Health. The app requests read access only;
we removed the unused write-purpose description.

[Attach verified replacement-build screenshots of AI disclosure, withdrawal and
HealthKit permission explanation. State the actual tested device and environment;
do not characterize simulator acceptance as physical-device testing.]

Thank you.

## Internal release checklist (not part of the message)

- Verify production provider identities and applicable contractual protection.
- Publish and read back Web privacy policy only after deployment authorization.
- Commit/push candidate only with authorization, verify exact-revision CI and
  trusted build gates; retain actual IPA signature, source and build binding.
- Complete source-bound simulator evidence and final review gate.
- Recheck review account and current ASC submission before sending or resubmitting.
