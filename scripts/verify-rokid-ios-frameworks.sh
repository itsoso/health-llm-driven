#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IOS_DIR="${ROKID_IOS_PROJECT_DIR:-"$ROOT_DIR/mobile/ios"}"
RGCXR_BINARY="$IOS_DIR/Pods/RGCxrClient/RGCxrClient.framework/RGCxrClient"
EMBED_SCRIPT="$IOS_DIR/Pods/Target Support Files/Pods-HealthPilot/Pods-HealthPilot-frameworks.sh"

if [[ ! -f "$RGCXR_BINARY" ]]; then
  echo "RGCxrClient binary not found at $RGCXR_BINARY; skipping Rokid framework embed check."
  exit 0
fi

if ! otool -L "$RGCXR_BINARY" | grep -q '@rpath/RGCoreKit.framework/RGCoreKit'; then
  echo "RGCxrClient does not require RGCoreKit.framework; no extra embed check needed."
  exit 0
fi

if [[ ! -f "$EMBED_SCRIPT" ]]; then
  echo "Missing CocoaPods embed script: $EMBED_SCRIPT" >&2
  exit 1
fi

if ! grep -q 'RGCoreKit.framework' "$EMBED_SCRIPT"; then
  cat >&2 <<EOF
RGCxrClient requires @rpath/RGCoreKit.framework/RGCoreKit, but CocoaPods embed script
does not copy RGCoreKit.framework into the app bundle.

Run pod install with the Rokid iOS SDK enabled and verify the RGCoreKit pod is built
as a dynamic framework.
EOF
  exit 1
fi

echo "Rokid iOS framework embed check passed."
