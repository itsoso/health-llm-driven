#!/usr/bin/env bash
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
set -euo pipefail

EARLY_DESTINATION_PLATFORM="${REVA_IOS_DESTINATION_PLATFORM:-iOS Simulator}"
EARLY_ARGUMENTS=("$@")
for ((EARLY_INDEX = 0; EARLY_INDEX < ${#EARLY_ARGUMENTS[@]}; EARLY_INDEX++)); do
  if [[ "${EARLY_ARGUMENTS[EARLY_INDEX]}" == "--platform" ]]; then
    if ((EARLY_INDEX + 1 >= ${#EARLY_ARGUMENTS[@]})); then
      builtin printf '%s\n' 'missing --platform value' >&2
      exit 2
    fi
    EARLY_DESTINATION_PLATFORM="${EARLY_ARGUMENTS[EARLY_INDEX + 1]}"
    ((EARLY_INDEX += 1))
  fi
done
if [[ "${EARLY_DESTINATION_PLATFORM}" == "iOS" ]]; then
  builtin printf '%s\n' \
    'Physical iOS acceptance is frozen; use an iOS Simulator destination.' >&2
  exit 78
fi
if [[ "${EARLY_DESTINATION_PLATFORM}" != "iOS Simulator" ]]; then
  builtin printf '%s\n' \
    "--platform must be \"iOS Simulator\": ${EARLY_DESTINATION_PLATFORM}" >&2
  exit 2
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HARNESS_SOURCE_DIR="${ROOT_DIR}/scripts/ios-real-device-acceptance"
DEVICE_ID="${REVA_IOS_DEVICE_ID:-}"
RESULT_PATH="${REVA_IOS_RESULT_PATH:-/tmp/XiaobaAcceptance-$(date +%Y%m%d-%H%M%S).xcresult}"
DESTINATION_PLATFORM="${EARLY_DESTINATION_PLATFORM}"
APP_BUNDLE_ID="life.executor.health"
SIMULATED_LOCATION=""
EXPECTED_CITY=""
SIMULATED_LOCATION_ACTIVE=0
HARNESS_DIR=""

usage() {
  cat <<'EOF'
Usage:
  scripts/run_ios_real_device_acceptance.sh [options] [device-udid] [result.xcresult]

Options:
  --device <udid>       Installed-app iOS Simulator UDID.
  --result <path>       Result bundle path ending in .xcresult.
  --platform <name>     Must be "iOS Simulator".
  --location <lat,lon>  Simulator-only coordinate injected before XCTest.
  --expected-city <city>
                        Simulator-only city expected after GPS refresh.
  -h, --help            Show this help.

Environment:
  REVA_IOS_DEVICE_ID
  REVA_IOS_RESULT_PATH
  REVA_IOS_DESTINATION_PLATFORM
  REVA_IOS_SIMULATED_LOCATION
  REVA_ACCEPTANCE_EXPECTED_CITY

Safety:
  Physical iOS acceptance is frozen; this runner is Simulator-only.
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
    --location)
      SIMULATED_LOCATION="${2:?missing --location value}"
      shift 2
      ;;
    --expected-city)
      EXPECTED_CITY="${2:?missing --expected-city value}"
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

SIMULATED_LOCATION="${SIMULATED_LOCATION:-${REVA_IOS_SIMULATED_LOCATION:-}}"
EXPECTED_CITY="${EXPECTED_CITY:-${REVA_ACCEPTANCE_EXPECTED_CITY:-}}"

if [[ -n "${SIMULATED_LOCATION}" || -n "${EXPECTED_CITY}" ]]; then
  if [[ "${DESTINATION_PLATFORM}" != "iOS Simulator" ]]; then
    echo "--location and --expected-city are Simulator-only options." >&2
    exit 2
  fi
  if [[ -z "${SIMULATED_LOCATION}" || -z "${EXPECTED_CITY}" ]]; then
    echo "Simulator GPS smoke requires both --location and --expected-city." >&2
    exit 2
  fi
  if [[ ! "${SIMULATED_LOCATION}" =~ ^-?[0-9]+([.][0-9]+)?,-?[0-9]+([.][0-9]+)?$ ]]; then
    echo "Invalid --location; expected decimal latitude,longitude." >&2
    exit 2
  fi
fi

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

if ! SIMULATOR_INVENTORY="$(/usr/bin/xcrun simctl list devices available --json)"; then
  echo "Unable to read the available iOS Simulator inventory." >&2
  exit 2
fi
if ! RESOLVED_SIMULATOR_UDID="$(/usr/bin/python3 "${ROOT_DIR}/scripts/resolve_ios_simulator.py" "${DEVICE_ID}" <<<"${SIMULATOR_INVENTORY}")" ||
   [[ "${RESOLVED_SIMULATOR_UDID}" != "${DEVICE_ID}" ]]; then
  echo "Device '${DEVICE_ID}' is not an available iOS Simulator UDID." >&2
  exit 2
fi

cleanup() {
  if [[ "${SIMULATED_LOCATION_ACTIVE}" = "1" ]]; then
    xcrun simctl location "${DEVICE_ID}" clear >/dev/null 2>&1 || true
  fi
  if [[ -n "${HARNESS_DIR}" && -d "${HARNESS_DIR}" ]]; then
    rm -rf -- "${HARNESS_DIR}"
  fi
}
trap cleanup EXIT INT TERM

HARNESS_DIR="$(mktemp -d "${TMPDIR:-/tmp}/xiaoba-acceptance.XXXXXX")"

if [[ -n "${SIMULATED_LOCATION}" ]]; then
  xcrun simctl privacy "${DEVICE_ID}" grant location "${APP_BUNDLE_ID}"
  xcrun simctl location "${DEVICE_ID}" set "${SIMULATED_LOCATION}"
  SIMULATED_LOCATION_ACTIVE=1
fi

REVA_ACCEPTANCE_EXPECTED_CITY="${EXPECTED_CITY}" \
env -u APP_STORE_REVIEW_DEMO_ACCOUNT -u APP_STORE_REVIEW_DEMO_PASSWORD \
  ruby "${HARNESS_SOURCE_DIR}/generate_project.rb" "${HARNESS_DIR}"

REVA_ACCEPTANCE_EXPECTED_CITY="${EXPECTED_CITY}" \
env -u APP_STORE_REVIEW_DEMO_ACCOUNT -u APP_STORE_REVIEW_DEMO_PASSWORD \
  xcodebuild \
  -project "${HARNESS_DIR}/XiaobaAcceptance.xcodeproj" \
  -scheme XiaobaAcceptanceUITests \
  -destination "platform=${DESTINATION_PLATFORM},id=${DEVICE_ID}" \
  -derivedDataPath "${HARNESS_DIR}/DerivedData" \
  -resultBundlePath "${RESULT_PATH}" \
  -collect-test-diagnostics never \
  test

SUMMARY_PATH="${HARNESS_DIR}/test-summary.json"
TESTS_PATH="${HARNESS_DIR}/tests.json"
xcrun xcresulttool get test-results summary \
  --path "${RESULT_PATH}" --compact > "${SUMMARY_PATH}"
xcrun xcresulttool get test-results tests \
  --path "${RESULT_PATH}" --compact > "${TESTS_PATH}"
VERIFY_ARGS=(
  --summary "${SUMMARY_PATH}"
  --tests "${TESTS_PATH}"
  --platform "${DESTINATION_PLATFORM}"
)
if [[ -n "${EXPECTED_CITY}" ]]; then
  VERIFY_ARGS+=(--expected-city "${EXPECTED_CITY}")
fi
python3 "${ROOT_DIR}/scripts/verify_ios_acceptance_result.py" "${VERIFY_ARGS[@]}"

echo "${DESTINATION_PLATFORM} acceptance result: ${RESULT_PATH}"
fi
