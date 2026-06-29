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
#
# Env overrides:
#   IOS_LOCAL_QR_PUBLIC_BASE_URL=https://health.executor.life/mobile-install/ios/<id>
#   IOS_LOCAL_QR_REMOTE_DIR=/opt/health-app-shared/mobile-install/ios/<id>
#   IOS_LOCAL_QR_TEAM_ID=QA2U724DAN
#   IOS_LOCAL_QR_SCHEME=HealthPilot  # optional; auto-detected when unset
#   IOS_LOCAL_QR_EXPORT_METHOD=ad-hoc

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MOBILE_DIR="${ROOT}/mobile"
ENV_FILE="${ROOT}/.env"

PROFILE="rokid-adhoc"
IPA_INPUT=""
UPLOAD="${IOS_LOCAL_QR_UPLOAD:-1}"
BUILD_ID="$(date +%Y%m%d-%H%M%S)-$(git -C "${ROOT}" rev-parse --short HEAD)"
TEAM_ID="${IOS_LOCAL_QR_TEAM_ID:-QA2U724DAN}"
SCHEME="${IOS_LOCAL_QR_SCHEME:-}"
EXPORT_METHOD="${IOS_LOCAL_QR_EXPORT_METHOD:-ad-hoc}"

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

set -a
[ -f "${ENV_FILE}" ] && source "${ENV_FILE}"
set +a

eval "$(
  node - "${MOBILE_DIR}/eas.json" "${PROFILE}" <<'NODE'
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
for (const [key, value] of Object.entries(profile.env || {})) {
  process.stdout.write(`export ${key}=${JSON.stringify(String(value))}\n`);
}
NODE
)"

export SENTRY_DISABLE_AUTO_UPLOAD="${SENTRY_DISABLE_AUTO_UPLOAD:-true}"
export PATH="/opt/homebrew/opt/ruby@3.3/bin:/opt/homebrew/lib/ruby/gems/3.3.0/bin:${PATH}"
export LANG="${LANG:-en_US.UTF-8}"
export LC_ALL="${LC_ALL:-en_US.UTF-8}"

OUTPUT_DIR="${ROOT}/artifacts/ios-local-install/${BUILD_ID}"
mkdir -p "${OUTPUT_DIR}"

IPA_NAME="HealthPilot-${BUILD_ID}.ipa"
IPA_PATH="${OUTPUT_DIR}/${IPA_NAME}"
EXPORT_DIR="${OUTPUT_DIR}/export"
ARCHIVE_PATH="${OUTPUT_DIR}/HealthPilot.xcarchive"
EXPORT_OPTIONS="${OUTPUT_DIR}/ExportOptions.plist"
BUILD_LOG="${OUTPUT_DIR}/xcodebuild.log"

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
  <string>automatic</string>
  <key>teamID</key>
  <string>${TEAM_ID}</string>
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
  cp "${IPA_INPUT}" "${IPA_PATH}"
else
  require_command xcodebuild
  require_command pod

  cd "${MOBILE_DIR}"
  echo "==> prebuild (${PROFILE})"
  npx expo prebuild --platform ios --clean

  echo "==> pod install"
  (cd ios && pod install --repo-update)

  WORKSPACE="$(ls -d ios/*.xcworkspace 2>/dev/null | head -1)"
  if [ -z "${WORKSPACE}" ]; then
    echo "Missing ios/*.xcworkspace after prebuild" >&2
    exit 1
  fi

  AUTH_KEY_PATH=""
  AUTH_KEY_ID=""
  AUTH_ISSUER_ID=""
  KEY_ID="${APP_STORE_CONNECT_API_KEY:-${ASC_KEY_ID:-}}"
  ISSUER_ID="${APP_STORE_CONNECT_ISSUER_ID:-${ASC_ISSUER_ID:-}}"
  if [ -n "${KEY_ID}" ] && [ -n "${ISSUER_ID}" ]; then
    P8="${ASC_PRIVATE_KEY_PATH:-${HOME}/.appstoreconnect/private_keys/AuthKey_${KEY_ID}.p8}"
    if [ -f "${P8}" ]; then
      AUTH_KEY_PATH="${P8}"
      AUTH_KEY_ID="${KEY_ID}"
      AUTH_ISSUER_ID="${ISSUER_ID}"
    fi
  fi

  run_xcodebuild() {
    if [ -n "${AUTH_KEY_PATH}" ]; then
      xcodebuild \
        -authenticationKeyPath "${AUTH_KEY_PATH}" \
        -authenticationKeyID "${AUTH_KEY_ID}" \
        -authenticationKeyIssuerID "${AUTH_ISSUER_ID}" \
        "$@"
    else
      xcodebuild "$@"
    fi
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

    node - "${scheme_list}" "${workspace_name}" <<'NODE'
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
  run_xcodebuild \
    -workspace "${WORKSPACE}" \
    -scheme "${SCHEME}" \
    -configuration Release \
    -destination 'generic/platform=iOS' \
    -archivePath "${ARCHIVE_PATH}" \
    -allowProvisioningUpdates \
    CODE_SIGN_STYLE=Automatic \
    DEVELOPMENT_TEAM="${TEAM_ID}" \
    archive 2>&1 | tee "${BUILD_LOG}"

  echo "==> export ${EXPORT_METHOD} IPA"
  if ! run_xcodebuild \
    -exportArchive \
    -archivePath "${ARCHIVE_PATH}" \
    -exportPath "${EXPORT_DIR}" \
    -exportOptionsPlist "${EXPORT_OPTIONS}" \
    -allowProvisioningUpdates 2>&1 | tee -a "${BUILD_LOG}"; then
    if [ "${EXPORT_METHOD}" = "development" ]; then
      exit 1
    fi

    echo "==> ${EXPORT_METHOD} export failed; retry development export" | tee -a "${BUILD_LOG}"
    EXPORT_METHOD="development"
    EXPORT_DIR="${OUTPUT_DIR}/export-development"
    write_export_options "${EXPORT_METHOD}" "${EXPORT_OPTIONS}"
    run_xcodebuild \
      -exportArchive \
      -archivePath "${ARCHIVE_PATH}" \
      -exportPath "${EXPORT_DIR}" \
      -exportOptionsPlist "${EXPORT_OPTIONS}" \
      -allowProvisioningUpdates 2>&1 | tee -a "${BUILD_LOG}"
  fi

  EXPORTED_IPA="$(find "${EXPORT_DIR}" -maxdepth 1 -name '*.ipa' -print | head -1)"
  if [ -z "${EXPORTED_IPA}" ]; then
    echo "Export succeeded but no IPA was found in ${EXPORT_DIR}" >&2
    exit 1
  fi
  cp "${EXPORTED_IPA}" "${IPA_PATH}"
fi

TMP_UNZIP="$(mktemp -d)"
trap 'rm -rf "${TMP_UNZIP}"' EXIT
unzip -q "${IPA_PATH}" -d "${TMP_UNZIP}"
APP_INFO="$(find "${TMP_UNZIP}/Payload" -mindepth 2 -maxdepth 2 -name Info.plist -print | head -1)"
if [ -z "${APP_INFO}" ]; then
  echo "Cannot find app Info.plist inside ${IPA_PATH}" >&2
  exit 1
fi

BUNDLE_ID="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "${APP_INFO}")"
APP_VERSION="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "${APP_INFO}" 2>/dev/null || echo "1.0.0")"
BUILD_NUMBER="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleVersion' "${APP_INFO}" 2>/dev/null || echo "${BUILD_ID}")"
TITLE="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleDisplayName' "${APP_INFO}" 2>/dev/null || echo "HealthPilot")"

PUBLIC_BASE_URL="${IOS_LOCAL_QR_PUBLIC_BASE_URL:-https://health.executor.life/mobile-install/ios/${BUILD_ID}}"
PUBLIC_BASE_URL="${PUBLIC_BASE_URL%/}"
IPA_URL="${PUBLIC_BASE_URL}/${IPA_NAME}"
MANIFEST_URL="${PUBLIC_BASE_URL}/manifest.plist"
INSTALL_URL="itms-services://?action=download-manifest&url=$(python3 -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1], safe=""))' "${MANIFEST_URL}")"

python3 - "${OUTPUT_DIR}/manifest.plist" "${IPA_URL}" "${BUNDLE_ID}" "${BUILD_NUMBER}" "${TITLE}" <<'PY'
import plistlib
import sys

manifest_path, ipa_url, bundle_id, build_number, title = sys.argv[1:]
payload = {
    "items": [
        {
            "assets": [
                {
                    "kind": "software-package",
                    "url": ipa_url,
                }
            ],
            "metadata": {
                "bundle-identifier": bundle_id,
                "bundle-version": build_number,
                "kind": "software",
                "title": title,
            },
        }
    ]
}
with open(manifest_path, "wb") as handle:
    plistlib.dump(payload, handle, sort_keys=False)
PY

if command -v qrencode >/dev/null 2>&1; then
  qrencode -o "${OUTPUT_DIR}/qr.png" -s 12 -m 2 "${INSTALL_URL}"
  qrencode -t ANSIUTF8 "${INSTALL_URL}" || true
else
  echo "qrencode not found; skipping qr.png" >&2
fi

python3 - "${OUTPUT_DIR}/install.html" "${INSTALL_URL}" "${IPA_URL}" "${MANIFEST_URL}" "${BUNDLE_ID}" "${APP_VERSION}" "${BUILD_NUMBER}" "${TITLE}" <<'PY'
import html
import sys

path, install_url, ipa_url, manifest_url, bundle_id, version, build, title = sys.argv[1:]
qr_img = "qr.png"
with open(path, "w", encoding="utf-8") as handle:
    handle.write(f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)} local install</title>
  <style>
    body {{ margin: 0; min-height: 100vh; display: grid; place-items: center; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f7f8fa; color: #111827; }}
    main {{ width: min(92vw, 520px); background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; padding: 28px; text-align: center; box-shadow: 0 14px 36px rgba(15,23,42,.08); }}
    img {{ width: min(72vw, 320px); height: min(72vw, 320px); }}
    a.button {{ display: inline-block; margin: 18px 0 10px; padding: 13px 20px; border-radius: 8px; background: #0f766e; color: white; text-decoration: none; font-weight: 700; }}
    code, a {{ word-break: break-all; }}
    p {{ color: #4b5563; line-height: 1.55; }}
  </style>
</head>
<body>
  <main>
    <h1>{html.escape(title)}</h1>
    <p>{html.escape(bundle_id)} · {html.escape(version)} ({html.escape(build)})</p>
    <img src="{qr_img}" alt="Install QR code">
    <p><a class="button" href="{html.escape(install_url)}">Install on iPhone</a></p>
    <p>Open this page on iPhone, or scan the QR with Camera.</p>
    <p><a href="{html.escape(manifest_url)}">{html.escape(manifest_url)}</a></p>
    <p><code>{html.escape(ipa_url)}</code></p>
  </main>
</body>
</html>
""")
PY

cat > "${OUTPUT_DIR}/install-url.txt" <<EOF
${INSTALL_URL}
EOF

if [ "${UPLOAD}" = "1" ]; then
  if [ -z "${DEPLOY_SERVER:-}" ]; then
    echo "DEPLOY_SERVER missing; cannot upload. Re-run with --no-upload for local artifacts only." >&2
    exit 1
  fi
  REMOTE_DIR="${IOS_LOCAL_QR_REMOTE_DIR:-/opt/health-app-shared/mobile-install/ios/${BUILD_ID}}"
  echo "==> upload to ${DEPLOY_SERVER}:${REMOTE_DIR}"
  ssh "${DEPLOY_SERVER}" "mkdir -p '${REMOTE_DIR}'"
  rsync -az --delete "${OUTPUT_DIR}/" "${DEPLOY_SERVER}:${REMOTE_DIR}/"
fi

echo
echo "Build id:        ${BUILD_ID}"
echo "Bundle id:       ${BUNDLE_ID}"
echo "Version:         ${APP_VERSION} (${BUILD_NUMBER})"
echo "IPA:             ${IPA_PATH}"
echo "Manifest:        ${OUTPUT_DIR}/manifest.plist"
[ -f "${OUTPUT_DIR}/qr.png" ] && echo "QR PNG:          ${OUTPUT_DIR}/qr.png"
echo "Install page:    ${PUBLIC_BASE_URL}/install.html"
echo "Install URL:     ${INSTALL_URL}"

if [ "${UPLOAD}" = "1" ]; then
  echo "==> verify public install page"
  curl -fsSI "${PUBLIC_BASE_URL}/install.html" >/dev/null
  curl -fsSI "${MANIFEST_URL}" >/dev/null
  curl -fsSI "${IPA_URL}" >/dev/null
  echo "Public artifacts are reachable."
fi
