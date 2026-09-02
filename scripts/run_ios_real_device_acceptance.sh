#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HARNESS_SOURCE_DIR="${ROOT_DIR}/scripts/ios-real-device-acceptance"
DEVICE_ID="${REVA_IOS_DEVICE_ID:-}"
RESULT_PATH="${REVA_IOS_RESULT_PATH:-/tmp/XiaobaAcceptance-$(date +%Y%m%d-%H%M%S).xcresult}"
DESTINATION_PLATFORM="${REVA_IOS_DESTINATION_PLATFORM:-iOS}"

usage() {
  cat <<'EOF'
Usage:
  scripts/run_ios_real_device_acceptance.sh [options] [device-udid] [result.xcresult]

Options:
  --device <udid>       Installed-app device or simulator UDID.
  --result <path>       Result bundle path ending in .xcresult.
  --platform <name>     "iOS" for a physical iPhone or "iOS Simulator".
  -h, --help            Show this help.

Environment:
  REVA_IOS_DEVICE_ID
  REVA_IOS_RESULT_PATH
  REVA_IOS_DESTINATION_PLATFORM

Safety:
  The installed app must be pre-authenticated manually. Review credentials are
  never accepted by this harness because Xcode result bundles retain typed text.
EOF
}

POSITIONAL=()
while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --device)
      DEVICE_ID="${2:?missing --device value}"
      shift 2
      ;;
    --result)
      RESULT_PATH="${2:?missing --result value}"
      shift 2
      ;;
    --platform)
      DESTINATION_PLATFORM="${2:?missing --platform value}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    -*)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
    *)
      POSITIONAL+=("$1")
      shift
      ;;
  esac
done

if [[ "${#POSITIONAL[@]}" -gt 2 ]]; then
  echo "Too many positional arguments." >&2
  usage >&2
  exit 2
fi
if [[ "${#POSITIONAL[@]}" -ge 1 ]]; then
  DEVICE_ID="${POSITIONAL[0]}"
fi
if [[ "${#POSITIONAL[@]}" -ge 2 ]]; then
  RESULT_PATH="${POSITIONAL[1]}"
fi

if [[ -z "${DEVICE_ID}" ]]; then
  usage >&2
  exit 2
fi

case "${DESTINATION_PLATFORM}" in
  iOS|"iOS Simulator") ;;
  *)
    echo "--platform must be \"iOS\" or \"iOS Simulator\": ${DESTINATION_PLATFORM}" >&2
    exit 2
    ;;
esac

if [[ "${RESULT_PATH}" != *.xcresult ]]; then
  echo "Result path must end with .xcresult: ${RESULT_PATH}" >&2
  exit 2
fi

if [[ -e "${RESULT_PATH}" ]]; then
  echo "Refusing to overwrite existing result bundle: ${RESULT_PATH}" >&2
  exit 2
fi

if [[ -n "${APP_STORE_REVIEW_DEMO_ACCOUNT:-}" ||
      -n "${APP_STORE_REVIEW_DEMO_PASSWORD:-}" ]]; then
  echo "Refusing review credentials; the installed app must be pre-authenticated manually." >&2
  exit 2
fi

HARNESS_DIR="$(mktemp -d "${TMPDIR:-/tmp}/xiaoba-acceptance.XXXXXX")"
trap 'rm -rf "${HARNESS_DIR}"' EXIT

env -u APP_STORE_REVIEW_DEMO_ACCOUNT -u APP_STORE_REVIEW_DEMO_PASSWORD \
  ruby "${HARNESS_SOURCE_DIR}/generate_project.rb" "${HARNESS_DIR}"

PROVISIONING_ARGS=()
if [[ "${DESTINATION_PLATFORM}" == "iOS" ]]; then
  PROVISIONING_ARGS+=("-allowProvisioningUpdates")
fi

env -u APP_STORE_REVIEW_DEMO_ACCOUNT -u APP_STORE_REVIEW_DEMO_PASSWORD \
  xcodebuild \
  -project "${HARNESS_DIR}/XiaobaAcceptance.xcodeproj" \
  -scheme XiaobaAcceptanceUITests \
  -destination "platform=${DESTINATION_PLATFORM},id=${DEVICE_ID}" \
  -derivedDataPath "${HARNESS_DIR}/DerivedData" \
  -resultBundlePath "${RESULT_PATH}" \
  -collect-test-diagnostics never \
  "${PROVISIONING_ARGS[@]}" \
  test

echo "${DESTINATION_PLATFORM} acceptance result: ${RESULT_PATH}"
