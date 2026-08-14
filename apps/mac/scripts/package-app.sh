#!/bin/bash
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  builtin printf '%s\n' \
    'Mac package/sign/install writer entrypoint is frozen; use swift build/test for local validation.' >&2
  exit 78
fi

if [[ 0 -eq 1 ]]; then
set -euo pipefail

APP_NAME="HealthAgentMac"
BUNDLE_NAME="${APP_NAME}.app"
BUNDLE_ID="life.executor.health.mac"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${PROJECT_DIR}/../.." && pwd)"
OUTPUT_DIR="${PROJECT_DIR}/dist"
CONFIGURATION="release"
OPEN_AFTER_BUILD="0"
INSTALL_AFTER_BUILD="0"
SIGN_APP="1"
SIGN_IDENTITY="${HEALTH_MAC_SIGN_IDENTITY:-}"
APP_VERSION="${MAC_APP_VERSION:-0.1.0}"
APP_BUILD="${MAC_APP_BUILD:-1}"
MAC_SOURCE_SHA="${MAC_SOURCE_SHA:-$(git -C "${REPO_ROOT}" rev-parse HEAD 2>/dev/null || true)}"
MAC_SOURCE_TREE="${MAC_SOURCE_TREE:-$(git -C "${REPO_ROOT}" rev-parse 'HEAD^{tree}' 2>/dev/null || true)}"

[[ "${APP_VERSION}" =~ ^[0-9]+(\.[0-9]+){1,3}$ ]] || {
  echo "Invalid MAC_APP_VERSION: ${APP_VERSION}" >&2
  exit 2
}
[[ "${APP_BUILD}" =~ ^[0-9]+(\.[0-9]+){0,2}$ ]] || {
  echo "Invalid MAC_APP_BUILD: ${APP_BUILD}" >&2
  exit 2
}
[[ "${MAC_SOURCE_SHA}" =~ ^[0-9a-f]{40}$ ]] || {
  echo "Invalid MAC_SOURCE_SHA" >&2
  exit 2
}
[[ "${MAC_SOURCE_TREE}" =~ ^[0-9a-f]{40}$ ]] || {
  echo "Invalid MAC_SOURCE_TREE" >&2
  exit 2
}

usage() {
  cat <<USAGE
Usage: scripts/package-app.sh [--output DIR] [--debug] [--open] [--install] [--no-sign]

Builds a double-clickable macOS app bundle at:
  apps/mac/dist/HealthAgentMac.app

Options:
  --output DIR  Write the .app bundle into DIR.
  --debug       Build the debug binary instead of release.
  --open        Open the app after packaging.
  --install     Copy the packaged app to /Applications/小巴.app.
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
    --install)
      INSTALL_AFTER_BUILD="1"
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
SOURCE_RESOURCES_DIR="${PROJECT_DIR}/Sources/HealthAgentMac/Resources"

rm -rf "${APP_BUNDLE}"
mkdir -p "${MACOS_DIR}" "${RESOURCES_DIR}"
cp "${EXECUTABLE}" "${MACOS_DIR}/${APP_NAME}"
chmod 755 "${MACOS_DIR}/${APP_NAME}"

if [[ -d "${SOURCE_RESOURCES_DIR}" ]]; then
  # 平铺拷贝源资源 → Contents/Resources/(供 Bundle.main 查找,如 chat-transcript.html、icns)。
  cp -R "${SOURCE_RESOURCES_DIR}/." "${RESOURCES_DIR}/"
fi

# 同时拷贝 SwiftPM 生成的 *.bundle(供代码里的 Bundle.module 查找路径,如 AppBrandIcon /
# ChatTranscriptWebView 的资源回退)。SwiftPM 把 .process("Resources") 的产物打进
# HealthAgentMac_HealthAgentMac.bundle;不带它,Bundle.module 在打包 App 里会落空。
RESOURCE_BUNDLE="${BIN_DIR}/${APP_NAME}_${APP_NAME}.bundle"
if [[ -d "${RESOURCE_BUNDLE}" ]]; then
  cp -R "${RESOURCE_BUNDLE}" "${RESOURCES_DIR}/"
fi

cat > "${CONTENTS_DIR}/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleDevelopmentRegion</key>
  <string>zh-Hans</string>
  <key>CFBundleDisplayName</key>
  <string>小巴</string>
  <key>CFBundleExecutable</key>
  <string>${APP_NAME}</string>
  <key>CFBundleIdentifier</key>
  <string>${BUNDLE_ID}</string>
  <key>CFBundleInfoDictionaryVersion</key>
  <string>6.0</string>
  <key>CFBundleName</key>
  <string>小巴</string>
  <key>CFBundleIconFile</key>
  <string>HealthAgentIcon</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleShortVersionString</key>
  <string>${APP_VERSION}</string>
  <key>CFBundleVersion</key>
  <string>${APP_BUILD}</string>
  <key>LSMinimumSystemVersion</key>
  <string>14.0</string>
  <key>LSMultipleInstancesProhibited</key>
  <true/>
  <key>NSHighResolutionCapable</key>
  <true/>
  <key>NSPrincipalClass</key>
  <string>NSApplication</string>
  <key>RevaSourceSHA</key>
  <string>${MAC_SOURCE_SHA}</string>
  <key>RevaSourceTree</key>
  <string>${MAC_SOURCE_TREE}</string>
</dict>
</plist>
PLIST

cat > "${RESOURCES_DIR}/release-manifest.json" <<MANIFEST
{"schema_version":1,"source_sha":"${MAC_SOURCE_SHA}","source_tree":"${MAC_SOURCE_TREE}","bundle_id":"${BUNDLE_ID}","version":"${APP_VERSION}","build":"${APP_BUILD}"}
MANIFEST
chmod 644 "${RESOURCES_DIR}/release-manifest.json"

if command -v plutil >/dev/null 2>&1; then
  plutil -lint "${CONTENTS_DIR}/Info.plist" >/dev/null
fi

printf 'APPL????' > "${CONTENTS_DIR}/PkgInfo"

if [[ "${SIGN_APP}" == "1" ]] && command -v codesign >/dev/null 2>&1; then
  if [[ -n "${SIGN_IDENTITY}" ]]; then
    codesign --force --sign "${SIGN_IDENTITY}" --timestamp=none "${APP_BUNDLE}" >/dev/null
    echo "Signed with ${SIGN_IDENTITY}"
  else
    codesign --force --sign - --timestamp=none "${APP_BUNDLE}" >/dev/null
    echo "Signed ad-hoc"
  fi
fi

echo "Packaged ${APP_BUNDLE}"

if [[ "${INSTALL_AFTER_BUILD}" == "1" ]]; then
  INSTALL_APP="/Applications/小巴.app"
  rm -rf "${INSTALL_APP}"
  cp -R "${APP_BUNDLE}" "${INSTALL_APP}"
  echo "Installed ${INSTALL_APP}"
fi

if [[ "${OPEN_AFTER_BUILD}" == "1" ]]; then
  # Lock 2 (installer side): quit any running 小巴 before launching, so `open`
  # starts the freshly-installed/-built binary instead of fronting a stale one.
  # This is the dev-loop + upgrade half of the single-instance guarantee (the
  # in-app NSRunningApplication guard is Lock 1). Only runs when we're about to
  # --open; a plain build never kills anything.
  osascript -e 'quit app "小巴"' 2>/dev/null || true
  # Fallback by executable name in case the display name changes or AppleScript
  # can't reach it (ad-hoc app, no Apple event permission, etc.).
  pkill -x HealthAgentMac 2>/dev/null || true
  # Wait up to ~5s for it to actually terminate before we relaunch.
  for _ in $(seq 1 10); do
    pgrep -x HealthAgentMac >/dev/null 2>&1 || break
    sleep 0.5
  done

  if [[ "${INSTALL_AFTER_BUILD}" == "1" ]]; then
    open "/Applications/小巴.app"
  else
    open "${APP_BUNDLE}"
  fi
fi
fi
