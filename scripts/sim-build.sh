#!/usr/bin/env bash
# Build and install the iOS simulator app with native health-release-safe defaults.
#
# This script is intentionally local-only. It avoids TestFlight/EAS and gives the
# screenshot/review flow a repeatable way to install the simulator app.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEVICE="iPhone 17 Pro"
CONFIGURATION="Release"
BUILD_NUMBER="${APP_STORE_BUILD_ID:-}"
USE_TEMP_WORKTREE=1
KEEP_TEMP_WORKTREE=0

usage() {
  cat <<'EOF'
Usage: ./scripts/sim-build.sh [--device "iPhone 17 Pro"] [--configuration "Release"] [--build-number "237"] [--current-tree] [--keep-temp-worktree]

Defaults:
  - Builds in a temporary git worktree from the current HEAD, so generated native
    Pods and lockfile churn do not dirty the main checkout.
  - Builds the Release configuration without starting Metro.
  - Disables Rokid native iOS SDK for simulator builds.
  - Disables Sentry auto-upload.

Pass --build-number (or APP_STORE_BUILD_ID) when the simulator artifact must be
traceable to an App Store Connect build.
Use --current-tree only when you need to build uncommitted mobile changes.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --device)
      DEVICE="${2:?missing --device value}"
      shift 2
      ;;
    --configuration)
      CONFIGURATION="${2:?missing --configuration value}"
      shift 2
      ;;
    --build-number)
      BUILD_NUMBER="${2:?missing --build-number value}"
      shift 2
      ;;
    --current-tree)
      USE_TEMP_WORKTREE=0
      shift
      ;;
    --keep-temp-worktree)
      KEEP_TEMP_WORKTREE=1
      shift
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

if ! xcrun simctl list devices available | grep -Fq "${DEVICE}"; then
  echo "Simulator device '${DEVICE}' was not found. Check: xcrun simctl list devices available" >&2
  exit 2
fi

BUILD_ROOT="${ROOT}"
TEMP_WORKTREE=""

cleanup() {
  if [ -n "${TEMP_WORKTREE}" ] && [ "${KEEP_TEMP_WORKTREE}" -ne 1 ]; then
    git -C "${ROOT}" worktree remove --force "${TEMP_WORKTREE}" >/dev/null 2>&1 || true
  elif [ -n "${TEMP_WORKTREE}" ]; then
    echo "Temporary worktree kept at ${TEMP_WORKTREE}" >&2
  fi
}
trap cleanup EXIT

if [ "${USE_TEMP_WORKTREE}" -eq 1 ]; then
  TEMP_WORKTREE="$(mktemp -d "${TMPDIR:-/tmp}/reva-sim-build.XXXXXX")"
  rm -rf "${TEMP_WORKTREE}"
  git -C "${ROOT}" worktree add --detach "${TEMP_WORKTREE}" HEAD >/dev/null
  BUILD_ROOT="${TEMP_WORKTREE}"
  if [ -d "${ROOT}/mobile/node_modules" ] && [ ! -e "${BUILD_ROOT}/mobile/node_modules" ]; then
    # Metro resolves symlinks to the source checkout, so Release embedding fails
    # to find expo-router from the detached worktree. APFS clone-copy keeps the
    # dependency tree local without duplicating file data eagerly.
    NODE_MODULES_SOURCE="$(cd "${ROOT}/mobile/node_modules" && pwd -P)"
    cp -cR "${NODE_MODULES_SOURCE}" "${BUILD_ROOT}/mobile/node_modules"
  fi
fi

export ROKID_IOS_SDK_ENABLED="${ROKID_IOS_SDK_ENABLED:-0}"
export ROKID_IOS_SIMULATOR="${ROKID_IOS_SIMULATOR:-1}"
export SENTRY_DISABLE_AUTO_UPLOAD="${SENTRY_DISABLE_AUTO_UPLOAD:-true}"
export APP_VARIANT="${APP_VARIANT:-production}"
if [ -n "${BUILD_NUMBER}" ]; then
  if [[ ! "${BUILD_NUMBER}" =~ ^[0-9]+$ ]]; then
    echo "Build number must contain digits only: ${BUILD_NUMBER}" >&2
    exit 2
  fi
  export REVA_IOS_BUILD_NUMBER="${BUILD_NUMBER}"
fi

cd "${BUILD_ROOT}/mobile"

# Stale native Pods from a previous Rokid-enabled build can keep CXR-L frameworks
# visible to Swift even when simulator builds disable the SDK. Clearing generated
# Pods inside the build checkout keeps the compile graph honest.
rm -rf ios/Pods ios/Podfile.lock

npx expo run:ios \
  --configuration "${CONFIGURATION}" \
  --device "${DEVICE}" \
  --no-bundler
