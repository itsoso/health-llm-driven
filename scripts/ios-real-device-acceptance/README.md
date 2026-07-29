# iOS Real-Device Acceptance

This harness runs non-destructive App Review checks against the already installed
`life.executor.health` application on a physical iPhone.

It currently verifies:

- the installed app reaches either the authenticated Agent or login surface;
- when review credentials are provided, login persists across two terminate/cold-launch cycles;
- the authenticated session exposes the Agent composer;
- today's briefing can expand and collapse when present;
- an unsent text draft survives background/foreground without being sent;
- privacy policy and account deletion entries are reachable.

The tests do not submit a health record, delete an account, grant permissions, or
mark the full physical-device gate as passed. Voice, camera, sharing, write
idempotency and deletion completion still require their dedicated acceptance
checks.

Run:

```bash
scripts/run_ios_real_device_acceptance.sh \
  00008150-00112D220E32401C \
  /tmp/XiaobaAcceptance-Build237.xcresult
```

Run the same non-destructive harness against an installed simulator build:

```bash
set -a
source /secure/path/to/release.env
set +a
scripts/run_ios_real_device_acceptance.sh \
  --platform "iOS Simulator" \
  --device 3A80E7F0-3F0D-4BAF-B80D-587C827B5C3A \
  --result /tmp/XiaobaAcceptance-Simulator-Build237.xcresult
```

`APP_STORE_REVIEW_DEMO_ACCOUNT` and `APP_STORE_REVIEW_DEMO_PASSWORD` are copied
only into the temporary generated Xcode scheme and removed with the harness
directory after the run. They must never be committed or printed.

The command fails when the device is offline, the installed app is unavailable,
or an assertion fails. Never pipe it through `tail`; the `xcodebuild` exit code is
the acceptance result.
