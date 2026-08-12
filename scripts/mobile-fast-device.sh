#!/usr/bin/env bash
# Fast real-device loop. Reuses native state and Xcode DerivedData.
#
#   ./scripts/mobile-fast-device.sh metro [--tunnel]
#   ./scripts/mobile-fast-device.sh release

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MOBILE_DIR="${REPO_ROOT}/mobile"
MODE="${1:-release}"
DRY_RUN="${MOBILE_FAST_DEVICE_DRY_RUN:-0}"
DERIVED_DATA="${MOBILE_FAST_DEVICE_DERIVED_DATA:-${HOME}/Library/Developer/Xcode/DerivedData/RevaFastDevice}"

print_command() {
  local directory="$1"
  shift
  printf '+ (cd %q &&' "${directory}"
  printf ' %q' "$@"
  printf ')\n'
}

run_in() {
  local directory="$1"
  shift
  if [[ "${DRY_RUN}" == "1" ]]; then
    print_command "${directory}" "$@"
  else
    (cd "${directory}" && "$@")
  fi
}

if [[ "${MODE}" == "metro" ]]; then
  NETWORK_MODE="${2:---lan}"
  if [[ "${NETWORK_MODE}" != "--lan" && "${NETWORK_MODE}" != "--tunnel" ]]; then
    echo "Usage: $0 metro [--tunnel]" >&2
    exit 2
  fi
  echo "==> Development client + Metro (${NETWORK_MODE#--})"
  run_in "${MOBILE_DIR}" env APP_VARIANT=development npx expo start --dev-client "${NETWORK_MODE}"
  exit 0
fi

if [[ "${MODE}" != "release" || "${#}" -gt 1 ]]; then
  echo "Usage: $0 release | metro [--tunnel]" >&2
  exit 2
fi

if [[ "${DRY_RUN}" != "1" ]] && ! command -v xcodebuild >/dev/null 2>&1; then
  echo "✗ Xcode command line tools are unavailable." >&2
  exit 1
fi

WORKSPACE="${MOBILE_FAST_DEVICE_WORKSPACE:-}"
if [[ -z "${WORKSPACE}" ]]; then
  WORKSPACE="$(find "${MOBILE_DIR}/ios" -maxdepth 1 -name '*.xcworkspace' -print -quit 2>/dev/null || true)"
  WORKSPACE="${WORKSPACE#${MOBILE_DIR}/}"
fi
SCHEME="${MOBILE_FAST_DEVICE_SCHEME:-}"
if [[ -z "${SCHEME}" ]]; then
  SCHEME_PATH="$(find "${MOBILE_DIR}/ios" -path '*/xcshareddata/xcschemes/*.xcscheme' -print -quit 2>/dev/null || true)"
  SCHEME="$(basename "${SCHEME_PATH}" .xcscheme)"
fi
if [[ -z "${WORKSPACE}" || -z "${SCHEME}" ]]; then
  echo "✗ Native workspace or shared scheme is missing. Run mobile-local-device.sh once after native changes." >&2
  exit 1
fi

DEVICE_ID="${MOBILE_FAST_DEVICE_DEVICE_ID:-}"
XCODE_UDID="${MOBILE_FAST_DEVICE_XCODE_UDID:-}"
DDI_AVAILABLE="${MOBILE_FAST_DEVICE_DDI_AVAILABLE:-}"
if [[ -z "${DEVICE_ID}" || -z "${XCODE_UDID}" ]]; then
  DEVICE_JSON="$(mktemp)"
  trap 'rm -f "${DEVICE_JSON}"' EXIT
  if ! xcrun devicectl list devices --json-output "${DEVICE_JSON}" >/dev/null; then
    echo "✗ Unable to read connected Apple devices." >&2
    exit 1
  fi
  DEVICE_ROW="$(python3 - "${DEVICE_JSON}" <<'PY'
import json
import sys

devices = json.load(open(sys.argv[1])).get("result", {}).get("devices", [])
iphones = [
    device for device in devices
    if device.get("hardwareProperties", {}).get("deviceType") == "iPhone"
    and device.get("connectionProperties", {}).get("pairingState") == "paired"
]
iphones.sort(
    key=lambda device: device.get("connectionProperties", {}).get("lastConnectionDate", ""),
    reverse=True,
)
if iphones:
    device = iphones[0]
    print("\t".join([
        device.get("identifier", ""),
        device.get("hardwareProperties", {}).get("udid", ""),
        device.get("deviceProperties", {}).get("name", "iPhone"),
        str(bool(device.get("deviceProperties", {}).get("ddiServicesAvailable"))).lower(),
    ]))
PY
)"
  IFS=$'\t' read -r DEVICE_ID XCODE_UDID DEVICE_NAME DDI_AVAILABLE <<< "${DEVICE_ROW}"
else
  DEVICE_NAME="configured iPhone"
fi

if [[ -z "${DEVICE_ID}" || -z "${XCODE_UDID}" ]]; then
  echo "✗ No paired iPhone found. Connect and unlock the phone, then trust this Mac." >&2
  exit 1
fi
if [[ "${DDI_AVAILABLE}" == "false" ]]; then
  echo "✗ Xcode device services are unavailable. Connect and unlock the iPhone, then reopen Xcode once." >&2
  exit 1
fi

echo "==> Fast USB Release → ${DEVICE_NAME:-iPhone}"
echo "    workspace: ${WORKSPACE}"
echo "    scheme: ${SCHEME}"
echo "    DerivedData: ${DERIVED_DATA}"

run_in "${MOBILE_DIR}" xcrun devicectl device info details --device "${DEVICE_ID}"
run_in "${MOBILE_DIR}" env APP_VARIANT=production SENTRY_DISABLE_AUTO_UPLOAD=true xcodebuild \
  -workspace "${WORKSPACE}" \
  -scheme "${SCHEME}" \
  -configuration Release \
  -destination "id=${XCODE_UDID}" \
  -derivedDataPath "${DERIVED_DATA}" \
  -allowProvisioningUpdates \
  build

APP_PATH="${MOBILE_FAST_DEVICE_APP_PATH:-}"
if [[ -z "${APP_PATH}" && "${DRY_RUN}" == "1" ]]; then
  APP_PATH="${DERIVED_DATA}/Build/Products/Release-iphoneos/app.app"
fi
if [[ -z "${APP_PATH}" ]]; then
  APP_PATH="$(find "${DERIVED_DATA}/Build/Products/Release-iphoneos" -maxdepth 1 -name '*.app' -print -quit 2>/dev/null || true)"
fi
if [[ -z "${APP_PATH}" ]]; then
  echo "✗ Build succeeded but no Release iPhone app was found." >&2
  exit 1
fi

if [[ "${DRY_RUN}" != "1" ]]; then
  BUNDLE_ID="$(/usr/libexec/PlistBuddy -c 'Print:CFBundleIdentifier' "${APP_PATH}/Info.plist")"
  if [[ "${BUNDLE_ID}" != "life.executor.health" ]]; then
    echo "✗ Refusing to install unexpected bundle ${BUNDLE_ID}." >&2
    exit 1
  fi
fi

run_in "${MOBILE_DIR}" xcrun devicectl device install app --device "${DEVICE_ID}" "${APP_PATH}"
if ! run_in "${MOBILE_DIR}" xcrun devicectl device process launch --device "${DEVICE_ID}" life.executor.health; then
  echo "△ App installed, but launch needs an unlocked iPhone. Unlock it and open 小巴 once." >&2
  exit 3
fi

echo "✓ Incremental Release build installed and launched."
