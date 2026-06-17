#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IOS_DIR="${ROKID_IOS_PROJECT_DIR:-"$ROOT_DIR/mobile/ios"}"
WORKSPACE="${ROKID_IOS_WORKSPACE:-HealthPilot.xcworkspace}"
SCHEME="${ROKID_IOS_SCHEME:-RokidBridge}"
CONFIGURATION="${ROKID_IOS_CONFIGURATION:-Debug}"
DESTINATION="${ROKID_IOS_DESTINATION:-generic/platform=iOS}"
CLIENT_VERSION="${ROKID_IOS_CLIENT_VERSION:-1.0.2}"
SPECS_REPO="${ROKID_IOS_SPECS_REPO:-}"
SPECS_REPO_NAME="${ROKID_IOS_SPECS_REPO_NAME:-rokid-ios-specs}"
SIMULATOR="${ROKID_IOS_SIMULATOR:-0}"
SKIP_BUILD="${ROKID_IOS_SKIP_BUILD:-0}"
CHECK_SPEC_ONLY="${ROKID_IOS_CHECK_SPEC_ONLY:-0}"
DRY_RUN="${ROKID_IOS_DRY_RUN:-0}"
LOG_PATH="${ROKID_IOS_LOG_PATH:-"/tmp/reva-rokid-ios-compat-${CLIENT_VERSION//[^A-Za-z0-9_.-]/_}.log"}"

usage() {
  cat <<'USAGE'
Usage:
  scripts/rokid-ios-compat-probe.sh [--dry-run] [--check-spec-only] [--skip-build]

Environment:
  ROKID_IOS_CLIENT_VERSION    RGCxrClient version to probe. Default: 1.0.2
  ROKID_IOS_SPECS_REPO        Optional Rokid CocoaPods specs git URL.
  ROKID_IOS_SIMULATOR         Set 1 to exclude the device-only Rokid SDK during pod install.
  ROKID_IOS_SCHEME            Xcode scheme. Default: RokidBridge
  ROKID_IOS_DESTINATION       Xcode destination. Default: generic/platform=iOS
  ROKID_IOS_SKIP_BUILD        Set 1 to stop after pod install.
  ROKID_IOS_CHECK_SPEC_ONLY   Set 1 to only verify the podspec is visible.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=1
      ;;
    --check-spec-only)
      CHECK_SPEC_ONLY=1
      ;;
    --skip-build)
      SKIP_BUILD=1
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

log() {
  printf '[rokid-ios-probe] %s\n' "$*"
}

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 127
  fi
}

run() {
  log "+ $*"
  if [[ "$DRY_RUN" == "1" ]]; then
    return 0
  fi
  "$@"
}

require_command pod
require_command xcodebuild

log "project=$IOS_DIR"
log "client=RGCxrClient $CLIENT_VERSION"
log "scheme=$SCHEME configuration=$CONFIGURATION destination=$DESTINATION simulator_excluded=$SIMULATOR"

if [[ ! -d "$IOS_DIR" ]]; then
  echo "iOS project directory not found: $IOS_DIR" >&2
  echo "Generate it first with: cd mobile && npx expo prebuild --platform ios" >&2
  exit 66
fi

if [[ -n "$SPECS_REPO" ]]; then
  if pod repo list | grep -Eq "^${SPECS_REPO_NAME}[[:space:]]*$"; then
    run pod repo update "$SPECS_REPO_NAME"
  else
    run pod repo add "$SPECS_REPO_NAME" "$SPECS_REPO"
  fi
else
  log "ROKID_IOS_SPECS_REPO is empty; using configured CocoaPods sources only"
fi

if [[ "$DRY_RUN" == "0" ]]; then
  if ! pod spec cat RGCxrClient --version="$CLIENT_VERSION" >/tmp/reva-rgcxrclient.podspec.json 2>/tmp/reva-rgcxrclient.podspec.err; then
    log "RGCxrClient $CLIENT_VERSION is not visible to CocoaPods"
    cat /tmp/reva-rgcxrclient.podspec.err >&2
    echo "Set ROKID_IOS_SPECS_REPO to Rokid's specs repo if this version is not on CocoaPods trunk." >&2
    exit 31
  fi
else
  log "+ pod spec cat RGCxrClient --version=$CLIENT_VERSION"
fi

if [[ "$CHECK_SPEC_ONLY" == "1" ]]; then
  log "spec check complete"
  exit 0
fi

(
  cd "$IOS_DIR"
  run env \
    ROKID_IOS_SDK_ENABLED=1 \
    ROKID_IOS_CLIENT_VERSION="$CLIENT_VERSION" \
    ROKID_IOS_SIMULATOR="$SIMULATOR" \
    pod install
)

if [[ "$SKIP_BUILD" == "1" ]]; then
  log "pod install complete; build skipped"
  exit 0
fi

log "writing xcodebuild log to $LOG_PATH"
if [[ "$DRY_RUN" == "1" ]]; then
  log "+ env SENTRY_DISABLE_AUTO_UPLOAD=true ROKID_IOS_SDK_ENABLED=1 ROKID_IOS_CLIENT_VERSION=$CLIENT_VERSION ROKID_IOS_SIMULATOR=$SIMULATOR xcodebuild -workspace $WORKSPACE -scheme $SCHEME -configuration $CONFIGURATION -destination $DESTINATION CODE_SIGNING_ALLOWED=NO build"
  exit 0
fi

(
  cd "$IOS_DIR"
  env \
    SENTRY_DISABLE_AUTO_UPLOAD=true \
    ROKID_IOS_SDK_ENABLED=1 \
    ROKID_IOS_CLIENT_VERSION="$CLIENT_VERSION" \
    ROKID_IOS_SIMULATOR="$SIMULATOR" \
    xcodebuild \
      -workspace "$WORKSPACE" \
      -scheme "$SCHEME" \
      -configuration "$CONFIGURATION" \
      -destination "$DESTINATION" \
      CODE_SIGNING_ALLOWED=NO \
      build
) >"$LOG_PATH" 2>&1 || {
  log "xcodebuild failed"
  tail -n 120 "$LOG_PATH" >&2
  if grep -Eiq "unsupported by the compiler|cannot load underlying module|failed to build module" "$LOG_PATH"; then
    echo "Detected a likely Swift binary/module compatibility failure in Rokid's iOS SDK." >&2
  fi
  exit 65
}

tail -n 40 "$LOG_PATH"
log "xcodebuild complete"
