# Rokid iOS SDK vendor slot

This directory is intentionally empty in git. Put a Rokid-provided refreshed
`RGCxrClient.framework` here only when the public CocoaPods artifact is stale.

Expected refreshed CXR-L framework contract for CustomView:

- `Modules/RGCxrClient.swiftmodule/arm64-apple-ios.swiftinterface` has about 659 lines.
- The Swift interface contains `setNotifyEventListenCmds`.
- The Swift interface contains callback-style `openCustomView`.

Verify a candidate framework before building:

```bash
ROKID_IOS_CLIENT_FRAMEWORK_PATH="$PWD/mobile/vendor/rokid/RGCxrClient.framework" \
scripts/rokid-ios-compat-probe.sh --inspect-framework --check-spec-only
```

Use the vendored framework in a native build:

```bash
ROKID_IOS_SDK_ENABLED=1 \
ROKID_IOS_CLIENT_FRAMEWORK_PATH="../../../vendor/rokid/RGCxrClient.framework" \
ROKID_IOS_CLIENT_HAS_CALLBACK_API=1 \
pod install
```

For EAS/TestFlight, set these env values in the `rokid-production` profile only
after the refreshed framework is committed or otherwise available inside the
build checkout.
