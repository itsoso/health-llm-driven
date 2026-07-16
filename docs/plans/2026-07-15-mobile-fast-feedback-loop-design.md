# Mobile Fast Feedback Loop Design

**Status:** approved for P0 implementation
**Date:** 2026-07-15
**Owner:** Mobile / release engineering

## Goal

Minimize the time from a mobile code change to trustworthy feedback without weakening production release gates.

## Current Problem

The repository already supports Metro, local Xcode builds, EAS Update, QR packages, and TestFlight, but they are exposed as separate workflows. In practice:

- developers use a clean Release build for JS-only verification and repeatedly compile native dependencies;
- local checks run more tests than the changed surface needs during the inner loop;
- production OTA publishing has no targeted retry for transient asset upload timeouts;
- a successfully published update is not applied until a later cold-start cycle;
- local USB builds and TestFlight builds are visually indistinguishable in release discussions.

## Feedback Layers

### Layer 1: Inner Loop

Use a development client plus Metro Fast Refresh for JS, TS, UI, and state changes. The native development shell is installed once and rebuilt only when the native fingerprint changes. Changed files run related Jest tests, changed-file ESLint, incremental TypeScript, and `git diff --check`.

Target: visible UI feedback in seconds; focused automated feedback in under one minute after the warm cache.

### Layer 2: Device Acceptance

Use an incremental USB Release build with persistent DerivedData. Do not clean Pods, delete DerivedData, or regenerate the native project for ordinary JS changes. Install and launch through `devicectl` on the connected iPhone.

Target: production-mode device verification in under one minute after the first build, subject to Xcode signing and bundle size.

### Layer 3: Distribution

Use EAS Update for compatible JS changes and TestFlight only for native/runtime changes. OTA publication retries exactly once for known transient upload/asset-processing failures, then verifies that EAS returned an iOS update ID. The app checks for compatible updates when it becomes active, downloads them without blocking, and asks the user before reloading.

Target: verified OTA publication in under one minute under normal network conditions, with deterministic evidence of success.

## App Update Experience

`expo-updates` is already in the native runtime. A root-level provider owns a small state machine:

```text
idle -> checking -> downloading -> ready -> applying
                     |              |
                     +-> failed <---+
```

Rules:

- development and disabled-update builds remain `idle`;
- foreground checks are throttled to avoid duplicate requests;
- update download never blocks authentication or the Agent conversation;
- the app never reloads automatically while the user may have a draft, active voice session, streaming response, or pending write;
- a compact global banner appears only after the update is fully downloaded;
- applying the update always requires an explicit tap;
- Settings exposes a manual check action and the real app/build version.

## Release Safety

- Fast tests are an inner-loop accelerator, not the production release gate.
- Production OTA still requires a clean `main`, focused regressions, TypeScript, lint, and diff checks.
- Native changes still require a new runtime/build and TestFlight.
- Preview-to-production promotion should republish the exact verified update group rather than rebuilding it.
- Self-hosted Expo Update infrastructure is out of scope; it adds operational risk without shortening the dominant local feedback path.

## Verification

- Unit-test the update state machine with injected Expo Updates functions.
- Component-test ready, apply, dismiss, and error states.
- Subprocess-test shell scripts in dry-run mode.
- Measure warm focused-test duration, warm USB build duration, OTA publish duration, and returned update ID.
- Complete final validation on a connected iPhone; do not infer device success from simulator or build output alone.
