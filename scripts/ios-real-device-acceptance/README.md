# iOS Real-Device Acceptance

This harness runs non-destructive App Review checks against the already installed
`life.executor.health` application on a physical iPhone.

It currently verifies:

- the installed app reaches either the authenticated Agent or login surface;
- a manually pre-authenticated session persists across two terminate/cold-launch cycles;
- the authenticated session exposes the Agent composer;
- a qualified Today context opens its declared Today or handling destination,
  returns to the Agent, and can be dismissed;
- an unsent text draft survives background/foreground without being sent;
- privacy policy and account deletion entries are reachable.

The tests do not submit a health record, delete an account, grant permissions, or
mark the full physical-device gate as passed. Voice, camera, sharing, write
idempotency and deletion completion still require their dedicated acceptance
checks.

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
  --result /tmp/XiaobaAcceptance-Simulator-Build237.xcresult
```

Before running, open the installed app and sign in manually. The harness rejects
`APP_STORE_REVIEW_DEMO_ACCOUNT` and `APP_STORE_REVIEW_DEMO_PASSWORD`; never pass
review credentials to Xcode UI tests because typed text is retained in result
bundles and console logs.

The command fails when the device is offline, the installed app is unavailable,
or an assertion fails. Never pipe it through `tail`; the `xcodebuild` exit code is
the acceptance result.
