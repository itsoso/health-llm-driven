# iOS Simulator Acceptance

> **Current safety boundary (2026-08-12):** despite the historical directory and runner names,
> this repository harness is Simulator-only. Physical iOS connection, installation, signing and
> acceptance are frozen. Do not pass a physical-device UDID, `--platform iOS`, or `--device` to an
> Expo command.

The harness runs non-destructive checks against `life.executor.health` in an iOS Simulator. It
currently verifies:

- the app reaches either the authenticated Agent or login surface;
- a manually pre-authenticated Simulator session persists across two terminate/cold-launch cycles;
- the authenticated session exposes the Agent composer;
- today's briefing expands and collapses;
- an unsent text draft survives background/foreground without being sent;
- privacy policy and account deletion entries are reachable;
- injected Simulator GPS coordinates produce the expected city and ready state;
- production-visible safe Settings entries open and return without invoking destructive or
  third-party actions.

The tests do not submit a health record, delete an account, grant real-device permissions, or
satisfy a physical-iPhone/App Store Gate. Voice, camera, sharing, APNs, HealthKit, Keychain,
background execution, write idempotency and deletion completion remain explicit **BLOCKED** gaps.

Run only against an iOS Simulator:

```bash
scripts/run_ios_real_device_acceptance.sh \
  --platform "iOS Simulator" \
  --device <simulator-udid> \
  --location 30.2741,120.1551 \
  --expected-city 杭州 \
  --result /tmp/XiaobaAcceptance-Simulator-<build-id>.xcresult
```

Here `--device` is the runner's historical option name for a Simulator UDID. It does not authorize
Expo's `--device` flag or any physical device. `--location` and `--expected-city` must be supplied
together. The runner grants the Simulator app in-use location access, injects the coordinate, and
clears it from an EXIT/INT/TERM trap.

Before running, open the Simulator app and sign in manually. The harness rejects
`APP_STORE_REVIEW_DEMO_ACCOUNT` and `APP_STORE_REVIEW_DEMO_PASSWORD`; never pass review credentials
to Xcode UI tests because result bundles and console logs can retain typed text.

Physical iOS acceptance is not a repository command. After the global freeze is lifted, a
separately authorized external manual process must inspect the exact candidate and produce private,
sanitized, same-build evidence. Until then, physical-device, G5/G6 and App Store submission Gates
remain BLOCKED; Simulator output cannot substitute for them.

The command fails when the Simulator is unavailable, the app is not installed there, or an
assertion fails. Never pipe it through `tail`; the `xcodebuild` exit code is the acceptance result.
