#!/usr/bin/env bash
# Build an iOS ad-hoc IPA locally and publish a QR-code install bundle.
#
# Default profile is rokid-adhoc. It resolves to APP_VARIANT=production, so the
# bundle id stays life.executor.health and an in-place update can keep app data.
#
# Usage:
#   ./scripts/mobile-local-qr.sh
#   ./scripts/mobile-local-qr.sh --profile rokid-adhoc
#   ./scripts/mobile-local-qr.sh --ipa /path/to/existing.ipa
#   ./scripts/mobile-local-qr.sh --no-upload
#   ./scripts/mobile-local-qr.sh --no-latest  # preserve an existing latest alias
#
# Requires an already-installed ad-hoc profile (IOS_LOCAL_QR_PROFILE_UUID).
# Never creates credentials or falls back to development signing.
# --ipa requires the original adjacent .receipt.json for this exact source SHA.
# DEPLOY_SERVER defaults to the authenticated admin SSH alias health.
# No .env files are read. Public destinations are intentionally fixed.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MOBILE_DIR="${ROOT}/mobile"
SAFETY="${ROOT}/scripts/mobile_local_qr_safety.py"

PROFILE="rokid-adhoc"
IPA_INPUT=""
UPLOAD="${IOS_LOCAL_QR_UPLOAD:-1}"
UPDATE_LATEST=1
BUILD_ID="$(date +%Y%m%d-%H%M%S)-$(git -C "${ROOT}" rev-parse --short HEAD)"
TEAM_ID="QA2U724DAN"
SCHEME="${IOS_LOCAL_QR_SCHEME:-}"
EXPORT_METHOD="ad-hoc"
DEPLOY_SERVER="${DEPLOY_SERVER:-health}"

usage() {
  sed -n '1,24p' "$0"
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --profile)
      PROFILE="${2:?missing --profile value}"
      shift 2
      ;;
    --ipa)
      IPA_INPUT="${2:?missing --ipa value}"
      shift 2
      ;;
    --no-upload)
      UPLOAD=0
      shift
      ;;
    --no-latest)
      UPDATE_LATEST=0
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

if [ ! -d "${MOBILE_DIR}" ]; then
  echo "Missing mobile dir: ${MOBILE_DIR}" >&2
  exit 1
fi

python3 -I "${SAFETY}" validate-config --build-id "${BUILD_ID}" --server "${DEPLOY_SERVER}"
case "${UPLOAD}" in 0|1) ;; *) echo "IOS_LOCAL_QR_UPLOAD must be 0 or 1." >&2; exit 1 ;; esac
SOURCE_SHA="$(git -C "${ROOT}" rev-parse HEAD)"
if [ -n "$(git -C "${ROOT}" status --porcelain --untracked-files=no)" ]; then
  echo "Local QR requires a clean, reviewed canonical checkout." >&2
  exit 1
fi

PROFILE_EXPORTS="$(
  env -i "PATH=${PATH}" node - "${MOBILE_DIR}/eas.json" "${PROFILE}" <<'NODE'
const fs = require('fs');
const [easPath, profileName] = process.argv.slice(2);
const eas = JSON.parse(fs.readFileSync(easPath, 'utf8'));

function mergeProfile(name, seen = new Set()) {
  const profile = eas.build?.[name];
  if (!profile) {
    throw new Error(`Unknown EAS profile: ${name}`);
  }
  if (seen.has(name)) {
    throw new Error(`Circular EAS profile extends: ${name}`);
  }
  seen.add(name);
  if (!profile.extends) return profile;
  const base = mergeProfile(profile.extends, seen);
  return {
    ...base,
    ...profile,
    env: { ...(base.env || {}), ...(profile.env || {}) },
    ios: { ...(base.ios || {}), ...(profile.ios || {}) },
    android: { ...(base.android || {}), ...(profile.android || {}) },
  };
}

const profile = mergeProfile(profileName);
if (typeof profile.channel !== 'string' || !/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(profile.channel)) {
  throw new Error('Local QR build requires an explicit valid update channel');
}
const allowed = new Set(['APP_VARIANT', 'SENTRY_DISABLE_AUTO_UPLOAD', 'ROKID_IOS_SDK_ENABLED',
  'ROKID_IOS_CLIENT_FRAMEWORK_PATH', 'ROKID_IOS_CLIENT_HAS_CALLBACK_API',
  'ROKID_IOS_CLIENT_VERSION', 'ROKID_IOS_SIMULATOR', 'ROKID_IOS_CALLBACK_SCHEME']);
const values = Object.entries(profile.env || {});
for (const [key, value] of values) {
  if (!allowed.has(key) || typeof value !== 'string' || !/^[A-Za-z0-9_./-]+$/.test(value)) {
    throw new Error('Unsupported local QR profile setting');
  }
}
for (const [key, value] of values) process.stdout.write(`${key}\t${value}\n`);
process.stdout.write(`REVA_LOCAL_UPDATES_CHANNEL\t${profile.channel}\n`);
NODE
)"
PROFILE_ENV=()
while IFS=$'\t' read -r key value; do
  PROFILE_ENV+=("${key}=${value}")
  case "${key}" in
    APP_VARIANT) APP_VARIANT="${value}" ;;
    REVA_LOCAL_UPDATES_CHANNEL) REVA_LOCAL_UPDATES_CHANNEL="${value}" ;;
  esac
done <<< "${PROFILE_EXPORTS}"
[ "${APP_VARIANT:-}" = "production" ] || { echo "Only production variants may use local QR distribution." >&2; exit 1; }
export PATH="/opt/homebrew/opt/ruby@3.3/bin:/opt/homebrew/lib/ruby/gems/3.3.0/bin:${PATH}"
export LANG="${LANG:-en_US.UTF-8}"
export LC_ALL="${LC_ALL:-en_US.UTF-8}"

OUTPUT_DIR="${ROOT}/artifacts/ios-local-install/${BUILD_ID}"
mkdir -p "${ROOT}/artifacts/ios-local-install"
mkdir -m 0700 "${OUTPUT_DIR}"
PUBLIC_DIR="${OUTPUT_DIR}/public"

IPA_NAME="HealthPilot-${BUILD_ID}.ipa"
IPA_PATH="${OUTPUT_DIR}/${IPA_NAME}"
EXPORT_DIR="${OUTPUT_DIR}/export"
ARCHIVE_PATH="${OUTPUT_DIR}/HealthPilot.xcarchive"
EXPORT_OPTIONS="${OUTPUT_DIR}/ExportOptions.plist"
BUILD_LOG="${OUTPUT_DIR}/xcodebuild.log"
APP_VERSION="$(env -i "PATH=${PATH}" node -p 'require(process.argv[1]).expo.version' "${MOBILE_DIR}/app.json")"
NATIVE_ENV=("PATH=${PATH}" "HOME=${HOME}" "TMPDIR=${TMPDIR:-/tmp}" "LANG=${LANG}" "LC_ALL=${LC_ALL}" "EXPO_NO_DOTENV=1" "SENTRY_DISABLE_AUTO_UPLOAD=true")
[ -z "${DEVELOPER_DIR:-}" ] || NATIVE_ENV+=("DEVELOPER_DIR=${DEVELOPER_DIR}")
[ -z "${REVA_IOS_BUILD_NUMBER:-}" ] || NATIVE_ENV+=("REVA_IOS_BUILD_NUMBER=${REVA_IOS_BUILD_NUMBER}")
run_native() { env -i "${NATIVE_ENV[@]}" "${PROFILE_ENV[@]}" "$@"; }

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing command: $1" >&2
    exit 1
  fi
}

write_export_options() {
  local method="$1"
  local path="$2"
  cat > "${path}" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>method</key>
  <string>${method}</string>
  <key>signingStyle</key>
  <string>manual</string>
  <key>teamID</key>
  <string>${TEAM_ID}</string>
  <key>signingCertificate</key>
  <string>iPhone Distribution</string>
  <key>provisioningProfiles</key>
  <dict><key>life.executor.health</key><string>${IOS_LOCAL_QR_PROFILE_UUID}</string></dict>
  <key>compileBitcode</key>
  <false/>
  <key>stripSwiftSymbols</key>
  <true/>
  <key>uploadSymbols</key>
  <false/>
</dict>
</plist>
PLIST
}

if [ -n "${IPA_INPUT}" ]; then
  if [ ! -f "${IPA_INPUT}" ]; then
    echo "IPA not found: ${IPA_INPUT}" >&2
    exit 1
  fi
  if ! cmp -s "${IPA_INPUT}" "${IPA_PATH}" 2>/dev/null; then
    cp "${IPA_INPUT}" "${IPA_PATH}"
  fi
else
  require_command xcodebuild
  require_command pod
  if ! [[ "${IOS_LOCAL_QR_PROFILE_UUID:-}" =~ ^[A-Fa-f0-9]{8}-[A-Fa-f0-9]{4}-[A-Fa-f0-9]{4}-[A-Fa-f0-9]{4}-[A-Fa-f0-9]{12}$ ]]; then
    echo "Set IOS_LOCAL_QR_PROFILE_UUID to an existing installed ad-hoc profile." >&2
    exit 1
  fi
  if ! [[ "${REVA_IOS_BUILD_NUMBER:-}" =~ ^[0-9]+$ ]]; then
    echo "Set the reviewed REVA_IOS_BUILD_NUMBER before creating a native package." >&2
    exit 1
  fi

  cd "${MOBILE_DIR}"
  echo "==> prebuild (${PROFILE})"
  run_native npx --no-install expo prebuild --platform ios --clean

  echo "==> pod install"
  (cd ios && run_native pod install --repo-update)

  WORKSPACE="$(ls -d ios/*.xcworkspace 2>/dev/null | head -1)"
  if [ -z "${WORKSPACE}" ]; then
    echo "Missing ios/*.xcworkspace after prebuild" >&2
    exit 1
  fi

  run_xcodebuild() {
    run_native xcodebuild "$@"
  }

  resolve_xcode_scheme() {
    local workspace="$1"
    local configured="${IOS_LOCAL_QR_SCHEME:-}"
    if [ -n "${configured}" ]; then
      printf '%s\n' "${configured}"
      return
    fi

    local workspace_name
    workspace_name="$(basename "${workspace}" .xcworkspace)"
    local scheme_list="${OUTPUT_DIR}/xcodebuild-list.json"
    run_xcodebuild -list -json -workspace "${workspace}" > "${scheme_list}"

    env -i "PATH=${PATH}" node - "${scheme_list}" "${workspace_name}" <<'NODE'
const fs = require('fs');
const [schemeListPath, workspaceName] = process.argv.slice(2);
const list = JSON.parse(fs.readFileSync(schemeListPath, 'utf8'));
const schemes = list.workspace?.schemes || list.project?.schemes || [];
const preferred = ['HealthPilot', workspaceName, 'app'].filter(Boolean);
const selected = preferred.find((candidate) => schemes.includes(candidate)) || schemes[0];
if (!selected) {
  throw new Error(`No Xcode scheme found in ${schemeListPath}`);
}
process.stdout.write(`${selected}\n`);
NODE
  }

  SCHEME="$(resolve_xcode_scheme "${WORKSPACE}")"
  write_export_options "${EXPORT_METHOD}" "${EXPORT_OPTIONS}"

  echo "==> archive (${SCHEME})"
  # Archive may use existing local development signing; export below must use
  # the explicit distribution profile. No -allowProvisioningUpdates is passed.
  # A global profile specifier here would incorrectly apply it to CocoaPods.
  run_xcodebuild \
    -workspace "${WORKSPACE}" \
    -scheme "${SCHEME}" \
    -configuration Release \
    -destination 'generic/platform=iOS' \
    -archivePath "${ARCHIVE_PATH}" \
    CODE_SIGN_STYLE=Automatic \
    DEVELOPMENT_TEAM="${TEAM_ID}" \
    archive 2>&1 | tee "${BUILD_LOG}"

  echo "==> export ${EXPORT_METHOD} IPA"
  run_xcodebuild \
    -exportArchive \
    -archivePath "${ARCHIVE_PATH}" \
    -exportPath "${EXPORT_DIR}" \
    -exportOptionsPlist "${EXPORT_OPTIONS}" 2>&1 | tee -a "${BUILD_LOG}"

  EXPORTED_IPA="$(find "${EXPORT_DIR}" -maxdepth 1 -name '*.ipa' -print | head -1)"
  if [ -z "${EXPORTED_IPA}" ]; then
    echo "Export succeeded but no IPA was found in ${EXPORT_DIR}" >&2
    exit 1
  fi
  cp "${EXPORTED_IPA}" "${IPA_PATH}"
fi

RECEIPT_ARGS=()
if [ -n "${IPA_INPUT}" ]; then
  RECEIPT_ARGS+=(--require-receipt "${IPA_INPUT}.receipt.json")
fi
if [ "$(git -C "${ROOT}" rev-parse HEAD)" != "${SOURCE_SHA}" ] || [ -n "$(git -C "${ROOT}" status --porcelain --untracked-files=no)" ]; then
  echo "Source changed during packaging; no artifact may be published." >&2
  exit 1
fi
python3 -I "${SAFETY}" verify-ios-ipa --build-id "${BUILD_ID}" --ipa "${IPA_PATH}" \
  --version "${APP_VERSION}" --channel "${REVA_LOCAL_UPDATES_CHANNEL}" \
  --sha "${SOURCE_SHA}" --receipt "${IPA_PATH}.receipt.json" \
  --public-dir "${PUBLIC_DIR}" "${RECEIPT_ARGS[@]}"
require_command qrencode
INSTALL_URL="$(<"${PUBLIC_DIR}/install-url.txt")"
qrencode -o "${PUBLIC_DIR}/qr.png" -s 12 -m 2 "${INSTALL_URL}"
PUBLIC_ROOT_URL="https://health.executor.life/mobile-install/ios"
PUBLIC_BASE_URL="${PUBLIC_ROOT_URL}/${BUILD_ID}"
LATEST_PUBLIC_BASE_URL="${PUBLIC_ROOT_URL}/latest"
IPA_URL="${PUBLIC_BASE_URL}/app.ipa"
MANIFEST_URL="${PUBLIC_BASE_URL}/manifest.plist"

if [ "${UPLOAD}" = "1" ]; then
  REMOTE_ROOT_DIR="/opt/health-app-shared/mobile-install/ios"
  REMOTE_DIR="${REMOTE_ROOT_DIR}/${BUILD_ID}"
  REMOTE_LATEST_DIR="${REMOTE_ROOT_DIR}/latest"
  echo "==> upload to ${DEPLOY_SERVER}:${REMOTE_DIR}"
  # A unique immutable destination makes an ambiguous upload non-repeatable.
  # Do not overwrite a legacy real directory at latest; migrate it separately.
  LATEST_PREFLIGHT=""
  if [ "${UPDATE_LATEST}" = "1" ]; then
    LATEST_PREFLIGHT="if test -e '${REMOTE_LATEST_DIR}' || test -L '${REMOTE_LATEST_DIR}'; then test -L '${REMOTE_LATEST_DIR}'; fi;"
  fi
  ssh -o BatchMode=yes "${DEPLOY_SERVER}" "set -eu; test -d '${REMOTE_ROOT_DIR}'; test ! -L '${REMOTE_ROOT_DIR}'; test ! -e '${REMOTE_DIR}'; test ! -L '${REMOTE_DIR}'; ${LATEST_PREFLIGHT} mkdir -m 0755 '${REMOTE_DIR}'"
  rsync -az --chmod=D755,F644 -e 'ssh -o BatchMode=yes' "${PUBLIC_DIR}/" "${DEPLOY_SERVER}:${REMOTE_DIR}/"
  (cd "${PUBLIC_DIR}" && shasum -a 256 app.ipa manifest.plist install.html install-url.txt qr.png) | \
    ssh -o BatchMode=yes "${DEPLOY_SERVER}" "cd '${REMOTE_DIR}' && sha256sum -c -"
  # Public readback precedes changing the stable alias.
  EXPECTED_SHA="$(shasum -a 256 "${PUBLIC_DIR}/app.ipa" | awk '{print $1}')"
  ACTUAL_SHA="$(curl --proto '=https' --tlsv1.2 -fsS "${IPA_URL}" | shasum -a 256 | awk '{print $1}')"
  [ "${EXPECTED_SHA}" = "${ACTUAL_SHA}" ] || { echo "Public IPA digest mismatch." >&2; exit 1; }
  if [ "${UPDATE_LATEST}" = "1" ]; then
    ssh -o BatchMode=yes "${DEPLOY_SERVER}" "set -eu; ln -s '${BUILD_ID}' '${REMOTE_ROOT_DIR}/.latest-${BUILD_ID}'; mv -Tf '${REMOTE_ROOT_DIR}/.latest-${BUILD_ID}' '${REMOTE_LATEST_DIR}'"
  fi
fi

echo
echo "Build id:        ${BUILD_ID}"
echo "Version:         ${APP_VERSION}"
echo "IPA:             ${IPA_PATH}"
echo "Manifest:        ${PUBLIC_DIR}/manifest.plist"
echo "QR PNG:          ${PUBLIC_DIR}/qr.png"
echo "Install page:    ${PUBLIC_BASE_URL}/install.html"
[ "${UPDATE_LATEST}" = "0" ] || echo "Latest install page: ${LATEST_PUBLIC_BASE_URL}/install.html"
echo "Install URL:     ${INSTALL_URL}"

if [ "${UPLOAD}" = "1" ]; then
  echo "==> verify public install page"
  curl -fsSI "${PUBLIC_BASE_URL}/install.html" >/dev/null
  if [ "${UPDATE_LATEST}" = "1" ]; then
    curl -fsSI "${LATEST_PUBLIC_BASE_URL}/install.html" >/dev/null
  fi
  curl -fsSI "${MANIFEST_URL}" >/dev/null
  curl -fsSI "${IPA_URL}" >/dev/null
  echo "Public artifacts are reachable."
else
  echo "Private local verification only; nothing was uploaded."
fi
