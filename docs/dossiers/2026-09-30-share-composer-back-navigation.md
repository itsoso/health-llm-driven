# Share composer back-navigation repair

| Field | Value |
| --- | --- |
| 状态 | building |
| 当前阶段 | Local verification passed; publication blocked by existing release incident |
| Controller | incident / health-harness-orchestrator, safety-gate overlay |

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

## Publication continuation (2026-09-30)

Run ledger: `docs/_generated/harness-runs/e919e4c952bb.jsonl` (local only).
UI repair is committed as `235c44b27185d2f83689bec3b692fd37b97b3eaf`.
Its exact remote CI `36659917477` failed at the production dependency audit,
not at type checking. No deployment or OTA has been performed for this repair.

- Remediation updates only same-major brace-expansion and joi overrides and lock
  entries. OSV production audit passes across 1087 entries with no exceptions.
  Dependencies were installed afresh in this isolated checkout, without modifying
  the original workspace's dependency tree. TypeScript and the 12-suite / 297-test
  share, chat-entry and diet-capture regression pass with the updated lock.
- OTA validation `36601390802` rejected a writable `/opt` ancestor. The upstream
  [hosted runner initializer](https://github.com/actions/runner-images/blob/main/images/ubuntu/scripts/build/configure-system.sh)
  sets `/opt` writable. Bootstrap now seals this one directory by a no-follow file
  descriptor before materializing canonical source, and verifies identity,
  ownership and mode. Later strict toolchain checks remain unchanged. No recursive
  permissions change, alternate toolchain, credential exposure or release bypass.
  RED: 4 failed / 20 passed; fixed workflow, publisher and CI-contract tests:
  87 passed (`/tmp/reva-ota-opt-green-final.log`).
- Independent read-only recovery review: BLOCK for existing recovery operators.
  Installed, running Laya with retained e13 NEEDS_OPERATOR lease does not satisfy
  unstarted-Laya retirement, partial-install retirement or stopped-service recovery.
  A new narrow reviewed recovery contract needs explicit incident authorization;
  current services, lease, evidence and keys were not modified in this continuation.
- Publication remains blocked: current main is red, new publisher change still
  needs independent G4 and exact remote CI, and backend incident closure is pending.
  Do not push or dispatch while the existing main-red boundary is unresolved.

### Continuation checkpoint

Local remediation commit: `f07d4743921767fee344c8a58fba009ead2e29fb`.
Independent safety reviewer returned GO for that exact five-file diff and
independently reran the 87 workflow/publisher/CI-contract tests. This is not
approval of incident recovery or a claim of publication. Full fresh-dependency
Mobile CI-mode Jest regression passed: 320 suites, 3136 tests passed, one skipped
(`/tmp/reva-share-release-mobile-full.log`). System Map, dossier consistency,
secret scan and diff checks passed as well.

A subsequent fetch found concurrently advanced remote main
`b79ae86b0a8fbfd6066266f5252f78ea1a7b8214`, containing a new installed-Laya
recovery operator and the original UI fix. Its CI `36660647091` was in progress
when inspected; its recovery note explicitly leaves G4 and execution pending.
No overlap with this remediation's executable files was found. The earlier
"no recovery operator" conclusion applies to 235c44b, not the new main.
No push, merge, production recovery, credential mutation or workflow dispatch
was performed in this continuation. Await coordination with the other MacBook
and authorization for the main-red CI repair before external writes; review the
new recovery operator and its exact evidence before any incident action.

### Authorized integration

The user explicitly authorized merging this remediation. The integration retains
concurrent main `b5641a0aad72f4c52c4f37c3164b5be4c06c100b` without conflict.
That main already contains byte-identical mobile dependency fixes; the incremental
executable diff is only the previously reviewed OTA bootstrap and its regression
tests. Production incident recovery and OTA dispatch remain out of this merge-only
continuation. Hosted CI must be checked on the resulting exact main revision.
