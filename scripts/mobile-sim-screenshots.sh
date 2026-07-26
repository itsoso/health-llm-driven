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
PRIVACY_STATUS="${APP_STORE_SCREENSHOT_PRIVACY_STATUS:-private}"
APP_STORE_READY=0
BUILD_ID="${APP_STORE_BUILD_ID:-}"

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
    --privacy-status)
      PRIVACY_STATUS="${2:?missing --privacy-status value}"
      shift 2
      ;;
    --app-store-ready)
      APP_STORE_READY=1
      shift
      ;;
    --build-id)
      BUILD_ID="${2:?missing --build-id value}"
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

case "${PRIVACY_STATUS}" in
  private|demo|sanitized) ;;
  *)
    echo "--privacy-status must be private, demo, or sanitized" >&2
    exit 2
    ;;
esac

if [ "${APP_STORE_READY}" = "1" ] && [ "${PRIVACY_STATUS}" = "private" ]; then
  echo "--app-store-ready requires --privacy-status demo or sanitized" >&2
  exit 2
fi

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
if [ -z "${BUILD_ID}" ]; then
  BUILD_ID="$(python3 - "${APP_INFO}" <<'PY'
import plistlib
import sys

with open(sys.argv[1], "rb") as handle:
    info = plistlib.load(handle)

print(str(info.get("CFBundleVersion", "")).strip())
PY
)"
fi
if [ -z "${BUILD_ID}" ]; then
  echo "Unable to determine CFBundleVersion; pass --build-id explicitly." >&2
  exit 2
fi
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

capture "01-today" "/(tabs)/today"
capture "02-chat" "/(tabs)/chat"
capture "03-record" "/(tabs)/record"
capture "04-me" "/me"
capture "05-import" "/import"
capture "06-privacy" "/privacy-policy"

cat > "${OUTPUT_DIR}/README.md" <<EOF
# App Store Screenshot Capture

- Captured at: $(date -u +%Y-%m-%dT%H:%M:%SZ)
- Simulator: ${DEVICE_ID}
- Bundle ID: ${BUNDLE_ID}
- URL scheme: ${URL_SCHEME}
- Privacy status: ${PRIVACY_STATUS}
- App Store ready: $([ "${APP_STORE_READY}" = "1" ] && echo "yes" || echo "no")
- Build ID: ${BUILD_ID}

Review each image before committing. Do not commit screenshots with private user data. App Store ready sets must use a demo account or sanitized data.
EOF

python3 - "${OUTPUT_DIR}/manifest.json" "${DEVICE_ID}" "${BUNDLE_ID}" "${URL_SCHEME}" "${PRIVACY_STATUS}" "${APP_STORE_READY}" "${BUILD_ID}" <<'PY'
import json
import sys
from datetime import datetime, timezone

manifest_path, simulator, bundle_id, url_scheme, privacy_status, ready, build_id = sys.argv[1:]
routes = [
    ("00-launch", "launch"),
    ("01-today", "/(tabs)/today"),
    ("02-chat", "/(tabs)/chat"),
    ("03-record", "/(tabs)/record"),
    ("04-me", "/me"),
    ("05-import", "/import"),
    ("06-privacy", "/privacy-policy"),
]
payload = {
    "captured_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    "simulator": simulator,
    "bundle_id": bundle_id,
    "url_scheme": url_scheme,
    "privacy_status": privacy_status,
    "app_store_ready": ready == "1",
    "build_id": build_id,
    "screens": [
        {"name": name, "route": route, "file": f"{name}.png"}
        for name, route in routes
    ],
}
with open(manifest_path, "w", encoding="utf-8") as handle:
    json.dump(payload, handle, ensure_ascii=False, indent=2)
    handle.write("\n")
PY

echo "Screenshots written to ${OUTPUT_DIR}"
