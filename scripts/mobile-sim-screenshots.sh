#!/usr/bin/env bash
# Capture App Store review screenshots from an already installed iOS simulator app.
#
# Build first if needed:
#   cd mobile
#   ROKID_IOS_SDK_ENABLED=0 ROKID_IOS_SIMULATOR=1 SENTRY_DISABLE_AUTO_UPLOAD=true npx expo run:ios --device "iPhone 17 Pro"

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUNDLE_ID="${IOS_SIM_BUNDLE_ID:-life.executor.health}"
DEVICE="${IOS_SIM_DEVICE:-booted}"
OUTPUT_DIR="${ROOT}/design/screenshots/app-store/$(date +%Y%m%d-%H%M%S)"
URL_SCHEME="${IOS_SIM_URL_SCHEME:-}"

usage() {
  sed -n '1,12p' "$0"
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --bundle-id)
      BUNDLE_ID="${2:?missing --bundle-id value}"
      shift 2
      ;;
    --device)
      DEVICE="${2:?missing --device value}"
      shift 2
      ;;
    --output)
      OUTPUT_DIR="${2:?missing --output value}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if ! command -v xcrun >/dev/null 2>&1; then
  echo "xcrun not found. Install Xcode command line tools first." >&2
  exit 1
fi

if [ "${DEVICE}" = "booted" ]; then
  DEVICE_ID="$(xcrun simctl list devices booted | awk -F '[()]' '/Booted/ && /iPhone/ {print $2; exit}')"
  if [ -z "${DEVICE_ID:-}" ]; then
    echo "No booted iPhone simulator found. Boot an iPhone simulator first." >&2
    exit 2
  fi
else
  DEVICE_ID="${DEVICE}"
fi

if ! xcrun simctl get_app_container "${DEVICE_ID}" "${BUNDLE_ID}" app >/dev/null 2>&1; then
  cat >&2 <<EOF
App ${BUNDLE_ID} is not installed on simulator ${DEVICE_ID}.

Build and install it with:
  cd mobile
  ROKID_IOS_SDK_ENABLED=0 ROKID_IOS_SIMULATOR=1 SENTRY_DISABLE_AUTO_UPLOAD=true npx expo run:ios --device "iPhone 17 Pro"

Then rerun:
  ./scripts/mobile-sim-screenshots.sh
EOF
  exit 2
fi

APP_CONTAINER="$(xcrun simctl get_app_container "${DEVICE_ID}" "${BUNDLE_ID}" app)"
APP_INFO="${APP_CONTAINER}/Info.plist"
if [ -z "${URL_SCHEME}" ]; then
  URL_SCHEME="$(python3 - "${APP_INFO}" <<'PY'
import plistlib
import sys

with open(sys.argv[1], "rb") as handle:
    info = plistlib.load(handle)

schemes = []
for entry in info.get("CFBundleURLTypes", []):
    schemes.extend(entry.get("CFBundleURLSchemes", []))

preferred = ["health", "mobile", "exp+health-pilot"]
for scheme in preferred:
    if scheme in schemes:
        print(scheme)
        raise SystemExit(0)

for scheme in schemes:
    if not scheme.startswith("life.executor.health.") and scheme != "cxrl":
        print(scheme)
        raise SystemExit(0)

raise SystemExit(1)
PY
)" || {
    echo "No usable URL scheme found in ${APP_INFO}. Rebuild the simulator app from current mobile/app.json." >&2
    exit 2
  }
fi

mkdir -p "${OUTPUT_DIR}"

route_url() {
  local route="$1"
  if [ "${route}" = "/" ]; then
    printf '%s://\n' "${URL_SCHEME}"
  elif [ "${URL_SCHEME}" = "exp+health-pilot" ]; then
    printf '%s:///%s\n' "${URL_SCHEME}" "${route#/}"
  else
    printf '%s://%s\n' "${URL_SCHEME}" "${route#/}"
  fi
}

capture() {
  local name="$1"
  local route="$2"
  local delay="${3:-2}"
  local url
  url="$(route_url "${route}")"
  echo "==> ${name}: ${url}"
  xcrun simctl openurl "${DEVICE_ID}" "${url}" >/dev/null
  sleep "${delay}"
  xcrun simctl io "${DEVICE_ID}" screenshot "${OUTPUT_DIR}/${name}.png" >/dev/null
}

xcrun simctl launch "${DEVICE_ID}" "${BUNDLE_ID}" >/dev/null || true
sleep 3
xcrun simctl io "${DEVICE_ID}" screenshot "${OUTPUT_DIR}/00-launch.png" >/dev/null

capture "01-today" "/"
capture "02-chat" "/chat"
capture "03-record" "/record"
capture "04-me" "/me"
capture "05-import" "/import"
capture "06-privacy" "/privacy-policy"

cat > "${OUTPUT_DIR}/README.md" <<EOF
# App Store Screenshot Capture

- Captured at: $(date -u +%Y-%m-%dT%H:%M:%SZ)
- Simulator: ${DEVICE_ID}
- Bundle ID: ${BUNDLE_ID}
- URL scheme: ${URL_SCHEME}

Review each image before committing. Do not commit screenshots with private user data.
EOF

echo "Screenshots written to ${OUTPUT_DIR}"
