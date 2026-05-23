#!/usr/bin/env bash
set -euo pipefail

APP_NAME="HealthAgentMac"
BUNDLE_NAME="${APP_NAME}.app"
BUNDLE_ID="life.executor.health.mac"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
OUTPUT_DIR="${PROJECT_DIR}/dist"
CONFIGURATION="release"
OPEN_AFTER_BUILD="0"
SIGN_APP="1"
SIGN_IDENTITY="${HEALTH_MAC_SIGN_IDENTITY:-}"

usage() {
  cat <<USAGE
Usage: scripts/package-app.sh [--output DIR] [--debug] [--open] [--no-sign]

Builds a double-clickable macOS app bundle at:
  apps/mac/dist/HealthAgentMac.app

Options:
  --output DIR  Write the .app bundle into DIR.
  --debug       Build the debug binary instead of release.
  --open        Open the app after packaging.
  --no-sign     Skip local ad-hoc codesign.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --output)
      OUTPUT_DIR="$2"
      shift 2
      ;;
    --debug)
      CONFIGURATION="debug"
      shift
      ;;
    --open)
      OPEN_AFTER_BUILD="1"
      shift
      ;;
    --no-sign)
      SIGN_APP="0"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

cd "${PROJECT_DIR}"

swift build -c "${CONFIGURATION}" --product "${APP_NAME}"
BIN_DIR="$(swift build -c "${CONFIGURATION}" --show-bin-path)"
EXECUTABLE="${BIN_DIR}/${APP_NAME}"

if [[ ! -x "${EXECUTABLE}" ]]; then
  echo "Missing built executable: ${EXECUTABLE}" >&2
  exit 1
fi

APP_BUNDLE="${OUTPUT_DIR}/${BUNDLE_NAME}"
CONTENTS_DIR="${APP_BUNDLE}/Contents"
MACOS_DIR="${CONTENTS_DIR}/MacOS"
RESOURCES_DIR="${CONTENTS_DIR}/Resources"

rm -rf "${APP_BUNDLE}"
mkdir -p "${MACOS_DIR}" "${RESOURCES_DIR}"
cp "${EXECUTABLE}" "${MACOS_DIR}/${APP_NAME}"
chmod 755 "${MACOS_DIR}/${APP_NAME}"

cat > "${CONTENTS_DIR}/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleDevelopmentRegion</key>
  <string>zh-Hans</string>
  <key>CFBundleDisplayName</key>
  <string>健康 Agent</string>
  <key>CFBundleExecutable</key>
  <string>${APP_NAME}</string>
  <key>CFBundleIdentifier</key>
  <string>${BUNDLE_ID}</string>
  <key>CFBundleInfoDictionaryVersion</key>
  <string>6.0</string>
  <key>CFBundleName</key>
  <string>健康 Agent</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleShortVersionString</key>
  <string>0.1.0</string>
  <key>CFBundleVersion</key>
  <string>1</string>
  <key>LSMinimumSystemVersion</key>
  <string>14.0</string>
  <key>NSHighResolutionCapable</key>
  <true/>
  <key>NSPrincipalClass</key>
  <string>NSApplication</string>
</dict>
</plist>
PLIST

printf 'APPL????' > "${CONTENTS_DIR}/PkgInfo"

if [[ "${SIGN_APP}" == "1" ]] && command -v codesign >/dev/null 2>&1; then
  if [[ -z "${SIGN_IDENTITY}" ]] && command -v security >/dev/null 2>&1; then
    SIGN_IDENTITY="$(security find-identity -v -p codesigning 2>/dev/null | awk -F'"' '/Apple Development/ {print $2; exit}')"
  fi
  if [[ -n "${SIGN_IDENTITY}" ]]; then
    codesign --force --sign "${SIGN_IDENTITY}" --timestamp=none "${APP_BUNDLE}" >/dev/null
    echo "Signed with ${SIGN_IDENTITY}"
  else
    codesign --force --sign - --timestamp=none "${APP_BUNDLE}" >/dev/null
    echo "Signed ad-hoc"
  fi
fi

echo "Packaged ${APP_BUNDLE}"

if [[ "${OPEN_AFTER_BUILD}" == "1" ]]; then
  open "${APP_BUNDLE}"
fi
