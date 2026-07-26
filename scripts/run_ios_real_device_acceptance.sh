#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HARNESS_SOURCE_DIR="${ROOT_DIR}/scripts/ios-real-device-acceptance"
DEVICE_ID="${1:-${REVA_IOS_DEVICE_ID:-}}"
RESULT_PATH="${2:-${REVA_IOS_RESULT_PATH:-/tmp/XiaobaAcceptance-$(date +%Y%m%d-%H%M%S).xcresult}}"

if [[ -z "${DEVICE_ID}" ]]; then
  echo "Usage: $0 <physical-device-udid> [result-bundle-path]" >&2
  echo "Or set REVA_IOS_DEVICE_ID and optionally REVA_IOS_RESULT_PATH." >&2
  exit 2
fi

if [[ "${RESULT_PATH}" != *.xcresult ]]; then
  echo "Result path must end with .xcresult: ${RESULT_PATH}" >&2
  exit 2
fi

if [[ -e "${RESULT_PATH}" ]]; then
  echo "Refusing to overwrite existing result bundle: ${RESULT_PATH}" >&2
  exit 2
fi

HARNESS_DIR="$(mktemp -d "${TMPDIR:-/tmp}/xiaoba-acceptance.XXXXXX")"
trap 'rm -rf "${HARNESS_DIR}"' EXIT

ruby "${HARNESS_SOURCE_DIR}/generate_project.rb" "${HARNESS_DIR}"

xcodebuild \
  -project "${HARNESS_DIR}/XiaobaAcceptance.xcodeproj" \
  -scheme XiaobaAcceptanceUITests \
  -destination "platform=iOS,id=${DEVICE_ID}" \
  -derivedDataPath "${HARNESS_DIR}/DerivedData" \
  -resultBundlePath "${RESULT_PATH}" \
  test

echo "Physical-iPhone acceptance result: ${RESULT_PATH}"
