# Share composer back-navigation repair

| Field | Value |
| --- | --- |
| 状态 | building |
| 当前阶段 | Local verification passed; publication blocked by existing release incident |
| Controller | quick_fix (no controller) |

## G1 / G2

裁决: PASS. Bounded repair of existing back navigation; no new user behavior,
product object, data authority or cross-platform responsibility.

## Scope and diagnosis

Existing Mobile UI bug only: returning from the share-image flow can leave a
black native presentation surface. The composer presented a full-screen native
Modal inside its own Modal, then invoked the parent's conditional unmount before
iOS reported dismissal. No data, export content, permissions or native dependency
changes. Work is based on clean main `e13cd67e9` in the existing release checkout;
the original workspace's uncommitted location feature remains untouched.

## Fix

- Embed the image editor in the composer's single native Modal, outside the
  preview header/gesture surface. Standalone editor presentation remains available.
- Wait for native dismissal and resource cleanup before calling the parent's
  close callback, in either completion order; ignore duplicate dismissal events.
- Android finishes after the hide commit without waiting for iOS-only onDismiss.
  System back delegates to the editor's existing unsaved-edit confirmation.
- Existing generation guards, consent invalidation, redaction, cleanup and
  follow-up navigation semantics remain covered by regression tests.

## Verification

- RED: 5 failed / 51 passed, reproducing nested native presentation and premature
  parent close (`/tmp/reva-share-back-red.log`).
- Focused plus diet capture and chat-card entry regressions: 12 suites / 297
  passed (`/tmp/reva-share-back-regression.log`); TypeScript check passed.
- System Map wrapper passed; component implementation changes add no map entities.
- iPhone 17 Pro / iOS 26.5: independently installed synthetic-only audit bundle,
  using the actual edited composer/editor. Verified editing return, generated
  preview return, reopening, and rotated-photo discard-confirmation return. Native
  screenshots show the visible parent and return counts 1, 2, 3, with no black screen.
  This is component-level simulator evidence, not production-chat or device proof.
  Temporary fixture source removed; audit artifact is outside the repository at
  `/tmp/reva-share-back-native.Em3uYw/ShareBackAudit.app`.

## Release boundary

No production publication claimed. Existing backend release `36648070016` stopped
at Laya verification with NEEDS_OPERATOR and a retained lease; OTA has an independent
toolchain-ancestor hardening failure. Do not replay that release or bypass its gates
to publish this UI change. Exact-candidate CI and governed OTA remain required.
