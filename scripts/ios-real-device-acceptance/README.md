# iOS Real-Device Acceptance

This harness runs non-destructive App Review checks against the already installed
`life.executor.health` application on a physical iPhone.

It currently verifies:

- the installed app reaches either the authenticated Agent or login surface;
- a manually pre-authenticated session persists across two terminate/cold-launch cycles;
- the authenticated session exposes the Agent composer;
- today's briefing can expand and collapse when present;
- an unsent text draft survives background/foreground without being sent;
- privacy policy and account deletion entries are reachable.
- Simulator-only GPS coordinates can prove the automatic city and ready state;
- production-visible safe Settings entries open and return without invoking
  destructive or third-party actions.

The tests do not submit a health record, delete an account, grant permissions, or
mark the full physical-device gate as passed. Voice, camera, sharing, write
idempotency and deletion completion still require their dedicated acceptance
checks.

The runner fails when an authenticated test is skipped. Only the optional
today-context check may skip when the signed-in account has no qualified current
context; a missing login or GPS expectation is never treated as a green result.

Run:

```bash
scripts/run_ios_real_device_acceptance.sh \
  <physical-device-udid> \
  /tmp/XiaobaAcceptance-Build237.xcresult
```

Run the same non-destructive harness against a manually pre-authenticated
simulator build:

```bash
scripts/run_ios_real_device_acceptance.sh \
  --platform "iOS Simulator" \
  --device <simulator-udid> \
  --location 30.2741,120.1551 \
  --expected-city 杭州 \
  --result /tmp/XiaobaAcceptance-Simulator-Build237.xcresult
```

`--location` and `--expected-city` must be supplied together and are rejected for
physical devices. The runner grants the installed app in-use location access,
injects the coordinate, and clears the simulated location from an EXIT/INT/TERM
trap. This smoke validates the already-authorized path; it intentionally does
not replace a real-device permission-prompt test.

Settings navigation automation never taps Garmin, Apple Health, account
deletion, update application, or logout. Garmin OAuth/MFA, HealthKit, APNs,
camera, microphone, Keychain and background execution remain real-device gates.

Before running, open the installed app and sign in manually. The harness rejects
`APP_STORE_REVIEW_DEMO_ACCOUNT` and `APP_STORE_REVIEW_DEMO_PASSWORD`; never pass
review credentials to Xcode UI tests because typed text is retained in result
bundles and console logs.

The command fails when the device is offline, the installed app is unavailable,
or an assertion fails. Never pipe it through `tail`; the `xcodebuild` exit code is
the acceptance result.
