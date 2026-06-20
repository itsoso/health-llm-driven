# Rokid iOS SDK vendor slot

Put the refreshed Rokid-provided `RGCxrClient.framework` in this directory as:

```text
mobile/modules/rokid-bridge/ios/vendor/RGCxrClient.framework
```

This is required when the public CocoaPods `RGCxrClient` artifact is stale.
The public `1.0.1` artifact currently does not expose the CustomView callback
APIs needed by Reva.

The framework checked in here keeps the Rokid binary intact but removes the
stale `arm64-apple-ios.swiftmodule` binary module so Xcode can rebuild from the
textual Swift interface. Its Swift interface header is also normalized from
`Apple Swift version 6.2.4 effective-5.10 (...)` to
`Apple Swift version 6.2.4 (...)`, because Xcode 26.5 / Swift 6.3.2 fails while
parsing the former producer-version string.

Expected refreshed CXR-L framework contract for CustomView:

- `Modules/RGCxrClient.swiftmodule/arm64-apple-ios.swiftinterface` has about 659 lines.
- The Swift interface contains `setNotifyEventListenCmds`.
- The Swift interface contains callback-style `openCustomView`.

Verify a candidate framework before building:

```bash
ROKID_IOS_CLIENT_FRAMEWORK_PATH="$PWD/mobile/modules/rokid-bridge/ios/vendor/RGCxrClient.framework" \
scripts/rokid-ios-compat-probe.sh \
  --inspect-framework \
  --check-spec-only
```

Use the vendored framework in native builds:

```bash
cd mobile/ios
ROKID_IOS_SDK_ENABLED=1 \
ROKID_IOS_CLIENT_FRAMEWORK_PATH=vendor/RGCxrClient.framework \
ROKID_IOS_CLIENT_HAS_CALLBACK_API=1 \
ROKID_IOS_SIMULATOR=0 \
pod install
```

The `RokidBridge.podspec` intentionally fails fast if the framework is missing,
or if `ROKID_IOS_CLIENT_HAS_CALLBACK_API=1` is set against an old framework.
