# CI Stability and Security Waiver Review Design

## Context

The exact `main` commit `698d47120481829bf42367ff24c3d204566ae5f9` has three independent CI blockers:

- two backend integration tests create records at fixed July 2026 timestamps and now fall outside their production endpoints' rolling 30-day windows;
- the Mobile dependency audit correctly blocks two `image-size` denial-of-service advisories after their reviewed exceptions expired on 2026-08-14;
- the affected `image-size` release is already patched locally and exercised with malicious fixtures, while the npm registry still has no non-vulnerable published release.

The aggregate backend job is red only because the two backend shards are red.

## Goals

- Keep rolling-window tests stable without weakening the production 30-day filters.
- Preserve the fail-closed dependency audit while recording a bounded re-review of the existing local patch.
- Warn before the next exception expiry instead of discovering it only after the deadline.
- Restore exact-commit CI without changing product behavior, runtime dependencies, or deployment state.

## Non-goals

- Do not widen production query windows.
- Do not downgrade Expo or React Native.
- Do not override `image-size` to another release still covered by the same advisories.
- Do not suppress unknown, unresolved, or newly introduced high/critical advisories.
- Do not deploy Backend or publish another OTA for test- and policy-only changes.

## Design

### Rolling-window fixtures

Only the two time-sensitive integration fixtures will change. The TokenPlan dashboard row will use the current UTC time because the test verifies price conversion, not historical filtering. The life-event API test will use a recent UTC message timestamp while leaving deterministic parser unit-test anchors unchanged. This keeps production filtering and deterministic time-parser coverage intact.

### Reviewed dependency exception

The two existing `image-size` exceptions will be extended to 2026-09-15. The reasons will record that npm `image-size` latest remains covered by both advisories, that the dependency is build-time transitive through Expo/Metro, and that the local ICNS/JXL/HEIF loop guards remain mandatory.

The audit evaluator will additionally report active exceptions that expire within seven days. These notices are warnings, not bypasses: expired exceptions, unknown advisories, malformed policies, and unresolved dependency graphs continue to block exactly as before.

## Verification

- Reproduce both backend failures before editing.
- Add a failing audit-gate test for a seven-day expiry warning, then implement the smallest evaluator change.
- Run both corrected backend nodes and their complete test files.
- Run the malicious image parser guard, audit policy tests, production dependency audit, TypeScript check, and focused OTA workflow tests.
- Run `git diff --check`, commit only the reviewed files, push the exact commit to `main`, and monitor that commit's CI result.

