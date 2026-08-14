#!/bin/bash

# Sourcing is inert; isolated unit fixtures explicitly extract the legacy body.
if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
  return 0
fi

# This file contains historical writer logic, so no mode may execute or source
# it from a writable checkout. Keep the legacy body syntactically unreachable;
# future public proofs belong in a separate credential-free checker.
if [[ "$#" -eq 1 && ( "$1" == "-h" || "$1" == "--help" ) ]]; then
  builtin printf '%s\n' \
    'Usage: ./apps/mac/scripts/release-dmg.sh -h|--help' \
    'Mac production release entrypoint is frozen (exit 78).'
  exit 0
fi
builtin printf '%s\n' \
  'Mac production release entrypoint is frozen; use the manual release Gate.' >&2
exit 78

if [[ "REVA_UNREACHABLE_LEGACY" == "NEVER" ]]; then
# BEGIN UNREACHABLE LEGACY MAC RELEASE IMPLEMENTATION

set -euo pipefail
umask 077

# Formal macOS DMG release transaction:
# clean exact origin/main -> source-bound app -> Developer ID signature ->
# notarization + staple -> mounted-image verification -> immutable upload ->
# root-owned receipt + atomic public current manifest.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
DEFAULT_REPO_ROOT="$(cd "${PROJECT_DIR}/../.." && pwd)"
REPO_ROOT="${DEFAULT_REPO_ROOT}"
if [[ -n "${MAC_RELEASE_REPO_ROOT_FOR_TESTS:-}" ]]; then
  [[ "${MAC_RELEASE_TEST_MODE:-}" == "1" ]] || {
    echo "MAC_RELEASE_REPO_ROOT_FOR_TESTS requires explicit test mode" >&2
    exit 2
  }
  REPO_ROOT="$(cd "${MAC_RELEASE_REPO_ROOT_FOR_TESTS}" && pwd)"
fi

DIST="${PROJECT_DIR}/dist"
SIGN_IDENTITY="${HEALTH_MAC_SIGN_IDENTITY:-Developer ID Application: baokun Pan (QA2U724DAN)}"
SERVER="root@39.98.206.178"
EXPECTED_TEAM_ID="QA2U724DAN"
EXPECTED_BUNDLE_ID="life.executor.health.mac"
PINNED_KNOWN_HOSTS_COMMAND='/usr/bin/printf 39.98.206.178\ ssh-ed25519\ AAAAC3NzaC1lZDI1NTE5AAAAIC6Wg0sU8uYKL4xq1HCCpPxTPy24LOxvzr2uSpycraav\n'
ASSET_ROOT="/opt/health-app-shared/assets"
STATE_ROOT="/var/lib/health-app/release-state"
PUBLIC_BASE_URL="https://health.executor.life"
REMOTE_RELEASE_LOCK_DIR="/var/lib/health-app/release-state/deploy.lock"
REMOTE_RELEASE_LOCK_TOKEN=""
REMOTE_RELEASE_LOCK_HELD=0
REMOTE_RELEASE_LOCK_ADOPTED=0
REMOTE_RELEASE_OPERATION=""
REMOTE_RELEASE_PHASE=""
REMOTE_RELEASE_STAGE_KIND=""
REMOTE_RELEASE_SOURCE_SHA=""
REMOTE_RELEASE_SOURCE_TREE=""
REMOTE_RELEASE_ARTIFACT_SHA256="-"
REMOTE_RELEASE_ARTIFACT_SIZE="0"
REMOTE_RELEASE_CANDIDATE_SHA256="-"
SNAPSHOT_PUBLISHER_SHA256=""
REMOTE_MUTATION_DELEGATED=0
RECOVERY_HANDOFF=""
RECOVERY_HELPER=""
RECOVERY_BUNDLE_DIR=""
RECOVERY_HANDOFF_PREEXISTED=0
TARGET_REF="${MAC_RELEASE_TARGET_REF:-origin/main}"
APP_VERSION="${MAC_APP_VERSION:-}"
APP_BUILD="${MAC_APP_BUILD:-}"
SKIP_UPLOAD=0
PREFLIGHT_ONLY=0
ROUTE_PREFLIGHT_ONLY=0
PROTOCOL_RECOVERY_TEST=0
HTTP_PROOF_TEST=0
HTTP_PROOF_TEST_URL=""
HTTP_PROOF_TEST_MAX_BYTES=""
HTTP_PROOF_TEST_MAX_TIME=""
HTTP_PROOF_TEST_ROOT=""
ACTION="publish"
SOURCE_SHA=""
SOURCE_TREE=""
WORK_DIR=""
MOUNT_POINT=""
REMOTE_STAGE=""
SNAPSHOT_DIR=""
SNAPSHOT_PUBLISHER=""
CURL_BINARY="/usr/bin/curl"
CURL_STREAM_LIMIT_READY=0
PROTOCOL_PYTHON="/usr/bin/python3"

SSH_OPTIONS=(
  -F "/dev/null"
  -o "BatchMode=yes"
  -o "StrictHostKeyChecking=yes"
  -o "UserKnownHostsFile=/dev/null"
  -o "GlobalKnownHostsFile=/dev/null"
  -o "KnownHostsCommand=${PINNED_KNOWN_HOSTS_COMMAND}"
  -o "ConnectionAttempts=1"
  -o "ConnectTimeout=15"
)

ssh_release() {
  /usr/bin/ssh "${SSH_OPTIONS[@]}" "${SERVER}" "$@"
}

scp_release() {
  /usr/bin/scp "${SSH_OPTIONS[@]}" "$@"
}

assert_local_exact_helper() {
  [[ -f "${SNAPSHOT_PUBLISHER}" && ! -L "${SNAPSHOT_PUBLISHER}" ]] || {
    echo "Exact Mac protocol helper is missing" >&2
    return 73
  }
  local helper_mode helper_links helper_sha256
  helper_mode="$(/usr/bin/stat -f '%Lp' "${SNAPSHOT_PUBLISHER}")"
  helper_links="$(/usr/bin/stat -f '%l' "${SNAPSHOT_PUBLISHER}")"
  [[ "${helper_mode}" == "600" && "${helper_links}" == "1" ]] || {
    echo "Exact Mac protocol helper is unsafe" >&2
    return 73
  }
  helper_sha256="$(/usr/bin/shasum -a 256 "${SNAPSHOT_PUBLISHER}" | /usr/bin/awk '{print $1}')"
  [[ "${helper_sha256}" == "${SNAPSHOT_PUBLISHER_SHA256}" ]] || {
    echo "Exact Mac protocol helper hash changed" >&2
    return 73
  }
}

remote_publisher() {
  assert_local_exact_helper
  ssh_release "${PROTOCOL_PYTHON}" - "$@" <"${SNAPSHOT_PUBLISHER}"
}

run_isolated_protocol_test_publisher() {
  [[ "${PROTOCOL_RECOVERY_TEST}" == "1" &&
      "${MAC_RELEASE_TEST_MODE:-}" == "1" ]] || return 73
  # The real publisher CLI is unconditionally frozen.  This import-only runner
  # exists solely inside the extracted non-production recovery fixture and
  # still relies on publisher.main() to enforce non-root + fixed temporary roots.
  "${PROTOCOL_PYTHON}" -I -B -c '
import importlib.util
import sys
path = sys.argv.pop(1)
spec = importlib.util.spec_from_file_location("reva_mac_publish_shell_test", path)
if spec is None or spec.loader is None:
    raise SystemExit(73)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
raise SystemExit(module.main())
' "${SNAPSHOT_PUBLISHER}" "$@"
}

remote_protocol() {
  local command="$1"
  shift
  assert_local_exact_helper
  if [[ "${PROTOCOL_RECOVERY_TEST}" == "1" ]]; then
    run_isolated_protocol_test_publisher "${command}" \
      --lock-dir "${REMOTE_RELEASE_LOCK_DIR}" \
      --token "${REMOTE_RELEASE_LOCK_TOKEN}" \
      --operation "${REMOTE_RELEASE_OPERATION}" \
      --stage-kind "${REMOTE_RELEASE_STAGE_KIND}" \
      --stage "${REMOTE_STAGE}" \
      --asset-root "${ASSET_ROOT}" \
      --state-root "${STATE_ROOT}" \
      --source-sha "${REMOTE_RELEASE_SOURCE_SHA}" \
      --source-tree "${REMOTE_RELEASE_SOURCE_TREE}" \
      --helper-sha256 "${SNAPSHOT_PUBLISHER_SHA256}" \
      --artifact-sha256 "${REMOTE_RELEASE_ARTIFACT_SHA256}" \
      --artifact-size "${REMOTE_RELEASE_ARTIFACT_SIZE}" \
      --candidate-sha256 "${REMOTE_RELEASE_CANDIDATE_SHA256}" \
      "$@" --allow-non-root-for-tests
    return
  fi
  ssh_release "${PROTOCOL_PYTHON}" - "${command}" \
    --lock-dir "${REMOTE_RELEASE_LOCK_DIR}" \
    --token "${REMOTE_RELEASE_LOCK_TOKEN}" \
    --operation "${REMOTE_RELEASE_OPERATION}" \
    --stage-kind "${REMOTE_RELEASE_STAGE_KIND}" \
    --stage "${REMOTE_STAGE}" \
    --asset-root "${ASSET_ROOT}" \
    --state-root "${STATE_ROOT}" \
    --source-sha "${REMOTE_RELEASE_SOURCE_SHA}" \
    --source-tree "${REMOTE_RELEASE_SOURCE_TREE}" \
    --helper-sha256 "${SNAPSHOT_PUBLISHER_SHA256}" \
    --artifact-sha256 "${REMOTE_RELEASE_ARTIFACT_SHA256}" \
    --artifact-size "${REMOTE_RELEASE_ARTIFACT_SIZE}" \
    --candidate-sha256 "${REMOTE_RELEASE_CANDIDATE_SHA256}" \
    "$@" <"${SNAPSHOT_PUBLISHER}"
}

assert_remote_release_lock() {
  [[ "${REMOTE_RELEASE_LOCK_HELD}" == "1" && "${REMOTE_RELEASE_LOCK_TOKEN}" =~ ^[A-Za-z0-9._:-]{16,200}$ ]] || {
    echo "Unified remote release lock is not held" >&2
    return 73
  }
  remote_protocol lease-assert --phase "${REMOTE_RELEASE_PHASE}" >/dev/null
}

acquire_remote_release_lock() {
  [[ "${REMOTE_RELEASE_LOCK_TOKEN}" =~ ^mac-[0-9a-f]{16}-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ ]] || {
    echo "Local Mac recovery handoff token is invalid" >&2
    return 73
  }
  local acquire_output=""
  if ! acquire_output="$(remote_protocol lease-acquire --requested-action "${ACTION}")"; then
    return 73
  fi
  local status phase extra
  IFS=$'\t' read -r status phase extra < <(/usr/bin/python3 - "${acquire_output}" <<'PY'
import json, sys
value = json.loads(sys.argv[1])
print(value.get("status", ""), value.get("phase", ""), sep="\t")
PY
  )
  [[ -z "${extra:-}" ]] || return 73
  if [[ "${status}" == "created" && "${phase}" == "staging" ]]; then
    REMOTE_RELEASE_LOCK_ADOPTED=0
    REMOTE_RELEASE_PHASE="staging"
  elif [[ "${status}" == "adopted" && ( "${phase}" == "staging" || "${phase}" == "sealed" || "${phase}" == "mutating" ) ]]; then
    REMOTE_RELEASE_PHASE="${phase}"
    REMOTE_RELEASE_LOCK_ADOPTED=1
  elif [[ "${status}" == "completed" && "${phase}" == "released" && "${ACTION}" == "recover" ]]; then
    REMOTE_RELEASE_LOCK_HELD=0
    REMOTE_STAGE=""
    clear_recovery_handoff
    reset_remote_release_context
    echo "Recovered a Mac release that had already completed stage cleanup and unlock"
    exit 0
  else
    echo "Invalid unified remote release lock acquisition response" >&2
    return 73
  fi
  REMOTE_RELEASE_LOCK_HELD=1
  assert_remote_release_lock
}

set_remote_release_metadata() {
  local field="$1"
  local old_value="$2"
  local new_value="$3"
  [[ "${field}" == "phase" ]] || return 73
  assert_remote_release_lock
  remote_protocol lease-transition --old-phase "${old_value}" --new-phase "${new_value}" >/dev/null
  REMOTE_RELEASE_PHASE="${new_value}"
  assert_remote_release_lock
}

release_remote_release_lock() {
  [[ "${REMOTE_RELEASE_LOCK_HELD}" == "1" ]] || return 0
  if ! remote_protocol lease-release --phase "${REMOTE_RELEASE_PHASE}" >/dev/null; then
    echo "Unified remote release lock could not be released; it was retained fail-closed" >&2
    return 73
  fi
  REMOTE_RELEASE_LOCK_HELD=0
}

reset_remote_release_context() {
  REMOTE_RELEASE_LOCK_TOKEN=""
  REMOTE_RELEASE_LOCK_ADOPTED=0
  REMOTE_RELEASE_PHASE=""
  REMOTE_RELEASE_OPERATION=""
  REMOTE_RELEASE_STAGE_KIND=""
  REMOTE_RELEASE_SOURCE_SHA=""
  REMOTE_RELEASE_SOURCE_TREE=""
  REMOTE_RELEASE_ARTIFACT_SHA256="-"
  REMOTE_RELEASE_ARTIFACT_SIZE="0"
  REMOTE_RELEASE_CANDIDATE_SHA256="-"
}

# Capture the original read-only invocation before argument parsing shifts it
# away.  The kernel-backed guardian re-executes this exact argv after taking
# the lock; without this ordering the restart would look like default publish
# and hit the production freeze instead of resuming the requested proof.
_REVA_RELEASE_REPO_ROOT="${REPO_ROOT}"
source "${DEFAULT_REPO_ROOT}/scripts/release_lock.sh"
_REVA_RELEASE_LOCK_PY="${DEFAULT_REPO_ROOT}/scripts/release_lock.py"

usage() {
  cat <<'USAGE'
Usage: apps/mac/scripts/release-dmg.sh [publish] --version VERSION --build BUILD [options]
       apps/mac/scripts/release-dmg.sh recover
       apps/mac/scripts/release-dmg.sh rollback

Options:
  --version VERSION  CFBundleShortVersionString for this formal release.
  --build BUILD      CFBundleVersion for this formal release.
  --target REF       Exact target; must resolve to HEAD, origin/main and remote main.
  --skip-upload      Build/sign/notarize/verify, but do not mutate production.
  --preflight-only   Verify source authority only; perform no build or mutation.
  --route-preflight-only  Verify source and public nginx route markers only.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    publish|recover|rollback)
      ACTION="$1"
      shift
      ;;
    --version)
      APP_VERSION="${2:-}"
      shift 2
      ;;
    --build)
      APP_BUILD="${2:-}"
      shift 2
      ;;
    --target)
      TARGET_REF="${2:-}"
      shift 2
      ;;
    --skip-upload)
      SKIP_UPLOAD=1
      shift
      ;;
    --preflight-only)
      PREFLIGHT_ONLY=1
      shift
      ;;
    --route-preflight-only)
      ROUTE_PREFLIGHT_ONLY=1
      shift
      ;;
    --protocol-recovery-test)
      PROTOCOL_RECOVERY_TEST=1
      ACTION="recover"
      shift
      ;;
    --http-proof-test)
      HTTP_PROOF_TEST=1
      HTTP_PROOF_TEST_URL="${2:-}"
      HTTP_PROOF_TEST_MAX_BYTES="${3:-}"
      HTTP_PROOF_TEST_MAX_TIME="${4:-}"
      shift 4
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

if (( PREFLIGHT_ONLY + ROUTE_PREFLIGHT_ONLY + PROTOCOL_RECOVERY_TEST + HTTP_PROOF_TEST > 1 )); then
  echo "Choose only one read-only preflight mode" >&2
  exit 2
fi
if [[ "${ACTION}" != "publish" && ( "${PREFLIGHT_ONLY}" == "1" || "${ROUTE_PREFLIGHT_ONLY}" == "1" || "${HTTP_PROOF_TEST}" == "1" || "${SKIP_UPLOAD}" == "1" ) ]]; then
  echo "Mac recover/rollback cannot be combined with publish-only options" >&2
  exit 2
fi
if [[ "${ACTION}" != "publish" && ( -n "${APP_VERSION}" || -n "${APP_BUILD}" ) ]]; then
  echo "Mac recover/rollback do not accept version or build" >&2
  exit 2
fi
if [[ -n "${HEALTH_MAC_ASSET_ROOT:-}${HEALTH_MAC_STATE_ROOT:-}${HEALTH_MAC_PUBLIC_BASE_URL:-}" ]]; then
  [[ "${MAC_RELEASE_TEST_MODE:-}" == "1" && ( "${PREFLIGHT_ONLY}" == "1" || "${ROUTE_PREFLIGHT_ONLY}" == "1" ) ]] || {
    echo "Mac production release paths and public origin cannot be overridden" >&2
    exit 2
  }
  ASSET_ROOT="${HEALTH_MAC_ASSET_ROOT:-${ASSET_ROOT}}"
  STATE_ROOT="${HEALTH_MAC_STATE_ROOT:-${STATE_ROOT}}"
  PUBLIC_BASE_URL="${HEALTH_MAC_PUBLIC_BASE_URL:-${PUBLIC_BASE_URL}}"
fi
if [[ "${PROTOCOL_RECOVERY_TEST}" == "1" && "${MAC_RELEASE_TEST_MODE:-}" != "1" ]]; then
  echo "Mac protocol recovery test requires explicit test mode" >&2
  exit 2
fi
if [[ "${MAC_RELEASE_TEST_MODE:-}" == "1" && "${PREFLIGHT_ONLY}" != "1" && "${ROUTE_PREFLIGHT_ONLY}" != "1" && "${PROTOCOL_RECOVERY_TEST}" != "1" && "${HTTP_PROOF_TEST}" != "1" ]]; then
  echo "Mac release test mode is read-only; build, notarization and upload are forbidden" >&2
  exit 2
fi
if [[ "${PROTOCOL_RECOVERY_TEST}" != "1" && "${HTTP_PROOF_TEST}" != "1" && ( "${ACTION}" != "publish" || ( "${PREFLIGHT_ONLY}" != "1" && "${ROUTE_PREFLIGHT_ONLY}" != "1" && "${SKIP_UPLOAD}" != "1" ) ) ]]; then
  [[ "${REVA_MAC_RELEASE_VIA_DEPLOY:-}" == "1" ]] || {
    echo "Mac release mutation is allowed only through deploy.sh" >&2
    exit 73
  }
fi
if [[ "${PROTOCOL_RECOVERY_TEST}" != "1" &&
      "${HTTP_PROOF_TEST}" != "1" &&
      "${PREFLIGHT_ONLY}" != "1" &&
      "${ROUTE_PREFLIGHT_ONLY}" != "1" ]]; then
  echo "Mac production mutation is frozen pending a crash-safe unified release transaction; use the manual release Gate." >&2
  exit 78
fi

# Only the explicitly read-only proof/preflight paths acquire the local lock.
# Blocked formal commands already exited at the top-level builtin guard, before
# this source line or any path/tool access could run.
acquire_release_lock "mac-dmg-release"

if [[ -n "${MAC_RELEASE_CURL_FOR_TESTS:-}" ]]; then
  [[ "${MAC_RELEASE_TEST_MODE:-}" == "1" && ( "${ROUTE_PREFLIGHT_ONLY}" == "1" || "${HTTP_PROOF_TEST}" == "1" ) ]] || {
    echo "MAC_RELEASE_CURL_FOR_TESTS requires a read-only HTTP test mode" >&2
    exit 2
  }
  CURL_BINARY="${MAC_RELEASE_CURL_FOR_TESTS}"
  [[ "${CURL_BINARY}" == /* && -f "${CURL_BINARY}" && ! -L "${CURL_BINARY}" && -x "${CURL_BINARY}" ]] || {
    echo "Unsafe test curl executable" >&2
    exit 2
  }
fi
if [[ "${HTTP_PROOF_TEST}" == "1" ]]; then
  [[ "${MAC_RELEASE_TEST_MODE:-}" == "1" ]] || {
    echo "Mac HTTP proof test requires explicit test mode" >&2
    exit 2
  }
  HTTP_PROOF_TEST_ROOT="${MAC_RELEASE_HTTP_TEST_ROOT:-}"
  [[ "${HTTP_PROOF_TEST_ROOT}" == /* && -d "${HTTP_PROOF_TEST_ROOT}" && ! -L "${HTTP_PROOF_TEST_ROOT}" ]] || {
    echo "Mac HTTP proof test root is unsafe" >&2
    exit 2
  }
  HTTP_PROOF_TEST_ROOT="$(cd "${HTTP_PROOF_TEST_ROOT}" && pwd -P)"
fi
if [[ "${PROTOCOL_RECOVERY_TEST}" == "1" ]]; then
  PROTOCOL_TEST_ROOT="${MAC_RELEASE_PROTOCOL_TEST_ROOT:-}"
  [[ "${PROTOCOL_TEST_ROOT}" == /* && -d "${PROTOCOL_TEST_ROOT}" && ! -L "${PROTOCOL_TEST_ROOT}" ]] || {
    echo "Mac protocol recovery test root is unsafe" >&2
    exit 2
  }
  PROTOCOL_TEST_ROOT="$(cd "${PROTOCOL_TEST_ROOT}" && pwd -P)"
  ASSET_ROOT="${MAC_RELEASE_PROTOCOL_ASSET_ROOT_FOR_TESTS:-${PROTOCOL_TEST_ROOT}/assets}"
  STATE_ROOT="${MAC_RELEASE_PROTOCOL_STATE_ROOT_FOR_TESTS:-${PROTOCOL_TEST_ROOT}/state}"
  [[ "${ASSET_ROOT}" == "${PROTOCOL_TEST_ROOT}/"* && "${STATE_ROOT}" == "${PROTOCOL_TEST_ROOT}/"* ]] || {
    echo "Mac protocol recovery test paths must stay inside its temporary root" >&2
    exit 2
  }
  REMOTE_RELEASE_LOCK_DIR="${STATE_ROOT}/deploy.lock"
  SERVER="protocol-test@localhost"
  PROTOCOL_PYTHON="${MAC_RELEASE_PROTOCOL_PYTHON_FOR_TESTS:-/usr/bin/python3}"
  [[ "${PROTOCOL_PYTHON}" == /* && -x "${PROTOCOL_PYTHON}" && ! -L "${PROTOCOL_PYTHON}" ]] || {
    echo "Mac protocol recovery test Python is unsafe" >&2
    exit 2
  }
fi

git_release() {
  /usr/bin/git \
    -c core.fsmonitor=false \
    -c core.hooksPath=/dev/null \
    -c filter.lfs.process= \
    -c filter.lfs.required=false \
    -c protocol.file.allow=never \
    -C "${REPO_ROOT}" "$@"
}

verify_release_source() {
  local dirty target_sha origin_main_sha remote_main_sha remote_output
  dirty="$(git_release status --porcelain=v1 --untracked-files=all)"
  [[ -z "${dirty}" ]] || {
    echo "Mac release requires a completely clean worktree" >&2
    exit 1
  }

  if [[ "${MAC_RELEASE_TEST_MODE:-}" != "1" ]]; then
    git_release fetch --quiet --prune origin main
  fi
  SOURCE_SHA="$(git_release rev-parse HEAD)"
  SOURCE_TREE="$(git_release rev-parse 'HEAD^{tree}')"
  target_sha="$(git_release rev-parse "${TARGET_REF}^{commit}")"
  origin_main_sha="$(git_release rev-parse 'origin/main^{commit}')"
  if [[ "${MAC_RELEASE_TEST_MODE:-}" == "1" && -n "${MAC_RELEASE_REMOTE_MAIN_SHA_FOR_TESTS:-}" ]]; then
    remote_main_sha="${MAC_RELEASE_REMOTE_MAIN_SHA_FOR_TESTS}"
  else
    remote_output="$(git_release ls-remote --exit-code origin refs/heads/main)"
    remote_main_sha="${remote_output%%[[:space:]]*}"
  fi

  [[ "${SOURCE_SHA}" =~ ^[0-9a-f]{40}$ ]] || {
    echo "Invalid source SHA" >&2
    exit 1
  }
  [[ "${SOURCE_TREE}" =~ ^[0-9a-f]{40}$ ]] || {
    echo "Invalid source tree" >&2
    exit 1
  }
  [[ "${SOURCE_SHA}" == "${target_sha}" ]] || {
    echo "HEAD does not match the requested Mac release target" >&2
    exit 1
  }
  [[ "${SOURCE_SHA}" == "${origin_main_sha}" ]] || {
    echo "HEAD does not match origin/main" >&2
    exit 1
  }
  [[ "${SOURCE_SHA}" == "${remote_main_sha}" ]] || {
    echo "HEAD does not match remote refs/heads/main" >&2
    exit 1
  }
}

ensure_work_dir() {
  if [[ -n "${WORK_DIR}" ]]; then
    return 0
  fi
  /bin/mkdir -p "${DIST}"
  WORK_DIR="$(/usr/bin/mktemp -d "${DIST}/.mac-release.XXXXXX")"
}

prepare_source_snapshot() {
  ensure_work_dir
  if [[ -n "${SNAPSHOT_DIR}" ]]; then
    return 0
  fi
  SNAPSHOT_DIR="${WORK_DIR}/source"
  local snapshot_tar="${WORK_DIR}/source.tar"
  /bin/mkdir -p "${SNAPSHOT_DIR}"
  git_release archive --format=tar --output="${snapshot_tar}" "${SOURCE_SHA}"
  /usr/bin/tar -xf "${snapshot_tar}" -C "${SNAPSHOT_DIR}"
  local package_script="${SNAPSHOT_DIR}/apps/mac/scripts/package-app.sh"
  SNAPSHOT_PUBLISHER="${SNAPSHOT_DIR}/apps/mac/scripts/mac_release_publish.py"
  [[ -f "${package_script}" && ! -L "${package_script}" && -x "${package_script}" ]] || {
    echo "Exact source snapshot is missing its package script" >&2
    exit 1
  }
  [[ -f "${SNAPSHOT_PUBLISHER}" && ! -L "${SNAPSHOT_PUBLISHER}" ]] || {
    echo "Exact source snapshot is missing its release publisher" >&2
    exit 1
  }
  SNAPSHOT_PUBLISHER_SHA256="$(/usr/bin/shasum -a 256 "${SNAPSHOT_PUBLISHER}" | /usr/bin/awk '{print $1}')"
  [[ "${SNAPSHOT_PUBLISHER_SHA256}" =~ ^[0-9a-f]{64}$ ]] || {
    echo "Exact source release publisher hash is invalid" >&2
    exit 1
  }
  verify_release_source
}

initialize_recovery_handoff_paths() {
  if [[ "${PROTOCOL_RECOVERY_TEST}" == "1" ]]; then
    RECOVERY_BUNDLE_DIR="${MAC_RELEASE_PROTOCOL_HANDOFF_FOR_TESTS:-${PROTOCOL_TEST_ROOT}/git common dir/reva-mac-release-recovery}"
    [[ "${RECOVERY_BUNDLE_DIR}" == "${PROTOCOL_TEST_ROOT}/"* ]] || return 73
    RECOVERY_HANDOFF="${RECOVERY_BUNDLE_DIR}/handoff"
    RECOVERY_HELPER="${RECOVERY_BUNDLE_DIR}/mac_release_publish.py"
    return
  fi
  local git_common_dir
  git_common_dir="$(git_release rev-parse --path-format=absolute --git-common-dir)"
  [[ "${git_common_dir}" == /* ]] || git_common_dir="${REPO_ROOT}/${git_common_dir}"
  git_common_dir="$(cd "${git_common_dir}" && pwd -P)"
  [[ -d "${git_common_dir}" && ! -L "${git_common_dir}" ]] || {
    echo "Git common directory is unsafe for the Mac recovery handoff" >&2
    return 73
  }
  RECOVERY_BUNDLE_DIR="${git_common_dir}/reva-mac-release-recovery"
  RECOVERY_HANDOFF="${RECOVERY_BUNDLE_DIR}/handoff"
  RECOVERY_HELPER="${RECOVERY_BUNDLE_DIR}/mac_release_publish.py"
}

persist_recovery_handoff() {
  initialize_recovery_handoff_paths
  [[ ! -e "${RECOVERY_BUNDLE_DIR}" && ! -L "${RECOVERY_BUNDLE_DIR}" ]] || {
    echo "An unresolved Mac release recovery handoff already exists" >&2
    return 73
  }
  local bundle_tmp helper_tmp handoff_tmp
  bundle_tmp="$(/usr/bin/mktemp -d "${RECOVERY_BUNDLE_DIR}.tmp.XXXXXX")"
  /bin/chmod 0700 "${bundle_tmp}"
  helper_tmp="${bundle_tmp}/mac_release_publish.py"
  handoff_tmp="${bundle_tmp}/handoff"
  /bin/cp "${SNAPSHOT_PUBLISHER}" "${helper_tmp}"
  /bin/chmod 0600 "${helper_tmp}"
  : >"${handoff_tmp}"
  /bin/chmod 0600 "${handoff_tmp}"
  [[ "$(/usr/bin/shasum -a 256 "${helper_tmp}" | /usr/bin/awk '{print $1}')" == "${SNAPSHOT_PUBLISHER_SHA256}" ]] || {
    /bin/rm -rf -- "${bundle_tmp}"
    echo "Failed to persist the exact Mac release helper" >&2
    return 73
  }
  {
    /usr/bin/printf 'schema=1\n'
    /usr/bin/printf 'server=%s\n' "${SERVER}"
    /usr/bin/printf 'lock_dir=%s\n' "${REMOTE_RELEASE_LOCK_DIR}"
    /usr/bin/printf 'token=%s\n' "${REMOTE_RELEASE_LOCK_TOKEN}"
    /usr/bin/printf 'operation=%s\n' "${REMOTE_RELEASE_OPERATION}"
    /usr/bin/printf 'stage_kind=%s\n' "${REMOTE_RELEASE_STAGE_KIND}"
    /usr/bin/printf 'stage=%s\n' "${REMOTE_STAGE}"
    /usr/bin/printf 'source_sha=%s\n' "${REMOTE_RELEASE_SOURCE_SHA}"
    /usr/bin/printf 'source_tree=%s\n' "${REMOTE_RELEASE_SOURCE_TREE}"
    /usr/bin/printf 'helper_sha256=%s\n' "${SNAPSHOT_PUBLISHER_SHA256}"
    /usr/bin/printf 'artifact_sha256=%s\n' "${REMOTE_RELEASE_ARTIFACT_SHA256}"
    /usr/bin/printf 'artifact_size=%s\n' "${REMOTE_RELEASE_ARTIFACT_SIZE}"
    /usr/bin/printf 'candidate_sha256=%s\n' "${REMOTE_RELEASE_CANDIDATE_SHA256}"
  } >"${handoff_tmp}"
  /usr/bin/python3 - "${helper_tmp}" "${handoff_tmp}" "${bundle_tmp}" <<'PY'
import os, sys
for raw in sys.argv[1:3]:
    fd = os.open(raw, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
directory = os.open(sys.argv[3], os.O_RDONLY)
try:
    os.fsync(directory)
finally:
    os.close(directory)
PY
  /bin/mv "${bundle_tmp}" "${RECOVERY_BUNDLE_DIR}"
  /usr/bin/python3 - "${RECOVERY_BUNDLE_DIR}" <<'PY'
import os, sys
directory = os.open(os.path.dirname(sys.argv[1]), os.O_RDONLY)
try:
    os.fsync(directory)
finally:
    os.close(directory)
PY
  SNAPSHOT_PUBLISHER="${RECOVERY_HELPER}"
}

load_recovery_handoff() {
  initialize_recovery_handoff_paths
  local loaded marker extra
  if ! loaded="$(/usr/bin/python3 - \
    "${RECOVERY_HANDOFF}" "${RECOVERY_HELPER}" "${SERVER}" \
    "${REMOTE_RELEASE_LOCK_DIR}" "${ASSET_ROOT}" <<'PY'
import hashlib, os, re, stat, sys
handoff, helper, expected_server, expected_lock, asset_root = sys.argv[1:]
expected_keys = {
    "schema", "server", "lock_dir", "token", "operation", "stage_kind",
    "stage", "source_sha", "source_tree", "helper_sha256",
    "artifact_sha256", "artifact_size", "candidate_sha256",
}
def safe_file(path, maximum):
    info = os.lstat(path)
    if (not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_uid != os.geteuid() or info.st_gid != os.getegid()
            or info.st_nlink != 1 or not (0 < info.st_size <= maximum)):
        raise SystemExit("unsafe local Mac recovery handoff")
    return info
bundle = os.lstat(os.path.dirname(handoff))
if (not stat.S_ISDIR(bundle.st_mode) or stat.S_IMODE(bundle.st_mode) != 0o700
        or bundle.st_uid != os.geteuid() or bundle.st_gid != os.getegid()
        or bundle.st_nlink < 2):
    raise SystemExit("unsafe local Mac recovery bundle")
if set(os.listdir(os.path.dirname(handoff))) != {"handoff", "mac_release_publish.py"}:
    raise SystemExit("unexpected local Mac recovery bundle entry")
safe_file(handoff, 4096)
safe_file(helper, 1024 * 1024)
values = {}
with open(handoff, encoding="utf-8") as stream:
    for raw in stream:
        if raw.count("=") != 1:
            raise SystemExit("invalid local Mac recovery handoff")
        key, value = raw.rstrip("\n").split("=", 1)
        if key in values:
            raise SystemExit("duplicate local Mac recovery handoff field")
        values[key] = value
if set(values) != expected_keys or values["schema"] != "1":
    raise SystemExit("invalid local Mac recovery handoff fields")
if values["server"] != expected_server or values["lock_dir"] != expected_lock:
    raise SystemExit("local Mac recovery authority does not match production")
if not re.fullmatch(r"mac-[0-9a-f]{16}-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", values["token"]):
    raise SystemExit("invalid local Mac recovery token")
if values["operation"] not in {"publish", "recover", "rollback"}:
    raise SystemExit("invalid local Mac recovery operation")
if values["stage_kind"] not in {"publish", "maintenance"}:
    raise SystemExit("invalid local Mac recovery stage kind")
expected_stage = f"{asset_root}/mac/.staging/{values['token']}"
if values["stage"] != expected_stage:
    raise SystemExit("invalid local Mac recovery stage")
if not re.fullmatch(r"[0-9a-f]{40}", values["source_sha"]):
    raise SystemExit("invalid local Mac recovery source SHA")
if not re.fullmatch(r"[0-9a-f]{40}", values["source_tree"]):
    raise SystemExit("invalid local Mac recovery source tree")
if not re.fullmatch(r"[0-9a-f]{64}", values["helper_sha256"]):
    raise SystemExit("invalid local Mac recovery helper hash")
if values["stage_kind"] == "publish":
    if not re.fullmatch(r"[0-9a-f]{64}", values["artifact_sha256"]):
        raise SystemExit("invalid local Mac recovery artifact hash")
    if not re.fullmatch(r"[1-9][0-9]{0,9}", values["artifact_size"]):
        raise SystemExit("invalid local Mac recovery artifact size")
    if int(values["artifact_size"]) > 1024 * 1024 * 1024:
        raise SystemExit("oversized local Mac recovery artifact")
    if not re.fullmatch(r"[0-9a-f]{64}", values["candidate_sha256"]):
        raise SystemExit("invalid local Mac recovery candidate hash")
elif (values["artifact_sha256"], values["artifact_size"], values["candidate_sha256"]) != ("-", "0", "-"):
    raise SystemExit("maintenance handoff cannot carry publish artifact identity")
digest = hashlib.sha256()
with open(helper, "rb") as stream:
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(chunk)
if digest.hexdigest() != values["helper_sha256"]:
    raise SystemExit("local Mac recovery helper was tampered")
print("OK", values["token"], values["operation"], values["stage_kind"],
      values["stage"], values["source_sha"], values["source_tree"],
      values["helper_sha256"], values["artifact_sha256"],
      values["artifact_size"], values["candidate_sha256"], sep="\t")
PY
  )"; then
    return 73
  fi
  IFS=$'\t' read -r marker REMOTE_RELEASE_LOCK_TOKEN REMOTE_RELEASE_OPERATION \
    REMOTE_RELEASE_STAGE_KIND REMOTE_STAGE REMOTE_RELEASE_SOURCE_SHA \
    REMOTE_RELEASE_SOURCE_TREE SNAPSHOT_PUBLISHER_SHA256 \
    REMOTE_RELEASE_ARTIFACT_SHA256 REMOTE_RELEASE_ARTIFACT_SIZE \
    REMOTE_RELEASE_CANDIDATE_SHA256 extra <<<"${loaded}"
  [[ "${marker}" == "OK" && -z "${extra:-}" ]] || return 73
  SNAPSHOT_PUBLISHER="${RECOVERY_HELPER}"
}

prepare_remote_release_context() {
  initialize_recovery_handoff_paths
  local nullglob_was_set=0
  shopt -q nullglob && nullglob_was_set=1
  shopt -s nullglob
  local clearing_candidates=("${RECOVERY_BUNDLE_DIR}.clearing-"*)
  [[ "${nullglob_was_set}" == "1" ]] || shopt -u nullglob
  local clearing_count="${#clearing_candidates[@]}" clearing_path=""
  if [[ "${clearing_count}" -gt 0 ]]; then
    [[ "${clearing_count}" == "1" ]] || {
      echo "Multiple Mac recovery cleanup tombstones require operator review" >&2
      return 73
    }
    clearing_path="${clearing_candidates[0]}"
    local clearing_token="${clearing_path##*.clearing-}"
    [[ "${clearing_token}" =~ ^mac-[0-9a-f]{16}-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ ]] || return 73
    REMOTE_RELEASE_LOCK_TOKEN="${clearing_token}"
    clear_recovery_handoff
  fi
  if [[ -e "${RECOVERY_BUNDLE_DIR}" || -L "${RECOVERY_BUNDLE_DIR}" ]]; then
    RECOVERY_HANDOFF_PREEXISTED=1
    [[ "${ACTION}" != "publish" ]] || {
      echo "A prior Mac release requires deploy.sh --recover-mac-release before publishing" >&2
      return 73
    }
    load_recovery_handoff
    if [[ "${ACTION}" != "recover" ]]; then
      echo "An interrupted Mac release must be reconciled with deploy.sh --recover-mac-release before rollback or publish" >&2
      return 73
    fi
    return
  fi
  RECOVERY_HANDOFF_PREEXISTED=0
  REMOTE_RELEASE_LOCK_TOKEN="mac-${SOURCE_SHA:0:16}-$(/usr/bin/uuidgen | /usr/bin/tr '[:upper:]' '[:lower:]')"
  REMOTE_RELEASE_OPERATION="${ACTION}"
  REMOTE_RELEASE_STAGE_KIND="$([[ "${ACTION}" == "publish" ]] && /usr/bin/printf publish || /usr/bin/printf maintenance)"
  REMOTE_STAGE="${ASSET_ROOT}/mac/.staging/${REMOTE_RELEASE_LOCK_TOKEN}"
  REMOTE_RELEASE_SOURCE_SHA="${SOURCE_SHA}"
  REMOTE_RELEASE_SOURCE_TREE="${SOURCE_TREE}"
  if [[ "${ACTION}" == "publish" ]]; then
    REMOTE_RELEASE_ARTIFACT_SHA256="${ARTIFACT_SHA256}"
    REMOTE_RELEASE_ARTIFACT_SIZE="${ARTIFACT_SIZE}"
    REMOTE_RELEASE_CANDIDATE_SHA256="$(/usr/bin/shasum -a 256 "${CANDIDATE_JSON}" | /usr/bin/awk '{print $1}')"
  else
    REMOTE_RELEASE_ARTIFACT_SHA256="-"
    REMOTE_RELEASE_ARTIFACT_SIZE="0"
    REMOTE_RELEASE_CANDIDATE_SHA256="-"
  fi
  persist_recovery_handoff
}

clear_recovery_handoff() {
  [[ -n "${RECOVERY_HANDOFF}" && -n "${RECOVERY_HELPER}" ]] || initialize_recovery_handoff_paths
  local cleanup_helper="${SNAPSHOT_PUBLISHER}"
  if [[ ! -f "${cleanup_helper}" && -f "${RECOVERY_HELPER}" ]]; then
    cleanup_helper="${RECOVERY_HELPER}"
  fi
  [[ -f "${cleanup_helper}" && ! -L "${cleanup_helper}" ]] || return 73
  local cleanup_mode cleanup_links
  cleanup_mode="$(/usr/bin/stat -f '%Lp' "${cleanup_helper}")"
  cleanup_links="$(/usr/bin/stat -f '%l' "${cleanup_helper}")"
  [[ ( "${cleanup_mode}" == "600" || "${cleanup_mode}" == "755" ) && "${cleanup_links}" == "1" ]] || return 73
  if [[ "${PROTOCOL_RECOVERY_TEST}" == "1" ]]; then
    SNAPSHOT_PUBLISHER="${cleanup_helper}" \
      run_isolated_protocol_test_publisher handoff-clear \
      --bundle "${RECOVERY_BUNDLE_DIR}" \
      --token "${REMOTE_RELEASE_LOCK_TOKEN}" \
      --allow-non-root-for-tests >/dev/null
    return
  fi
  "${PROTOCOL_PYTHON}" "${cleanup_helper}" handoff-clear \
    --bundle "${RECOVERY_BUNDLE_DIR}" \
    --token "${REMOTE_RELEASE_LOCK_TOKEN}" >/dev/null
}

stage_remote_publisher() {
  if [[ "${REMOTE_RELEASE_PHASE}" == "sealed" || "${REMOTE_RELEASE_PHASE}" == "mutating" ]]; then
    assert_remote_release_lock
    return 0
  fi
  [[ "${REMOTE_RELEASE_PHASE}" == "staging" ]] || return 73
  assert_remote_release_lock
  remote_protocol stage-reset >/dev/null
  scp_release -q "${SNAPSHOT_PUBLISHER}" "${SERVER}:${REMOTE_STAGE}/.mac_release_publish.py.upload"
  remote_protocol stage-bind-helper >/dev/null
}

seal_remote_release_stage() {
  [[ "${REMOTE_RELEASE_PHASE}" == "staging" ]] || return 73
  assert_remote_release_lock
  set_remote_release_metadata phase staging sealed
}

abandon_pre_mutation_remote_release() {
  [[ "${ACTION}" != "publish" && "${RECOVERY_HANDOFF_PREEXISTED}" == "1" && ( "${REMOTE_RELEASE_PHASE}" == "staging" || "${REMOTE_RELEASE_PHASE}" == "sealed" ) ]] || return 73
  assert_remote_release_lock
  local abandoned_stage="${REMOTE_STAGE}"
  if ! remote_protocol stage-cleanup --allow-partial-stage >/dev/null; then
    echo "Pre-mutation Mac stage cleanup failed; retained the lease and handoff" >&2
    return 75
  fi
  if ! release_remote_release_lock; then
    return 75
  fi
  REMOTE_STAGE=""
  clear_recovery_handoff
  reset_remote_release_context
  echo "Recovered a pre-mutation Mac release attempt; production pointers were never delegated"
  exit 0
}

delegate_remote_release_mutation() {
  REMOTE_MUTATION_DELEGATED=1
  if [[ "${REMOTE_RELEASE_PHASE}" == "sealed" ]]; then
    set_remote_release_metadata phase sealed mutating
  fi
  [[ "${REMOTE_RELEASE_PHASE}" == "mutating" ]] || return 73
  assert_remote_release_lock
}

assert_curl_stream_limit_supported() {
  if [[ "${CURL_STREAM_LIMIT_READY}" == "1" ]]; then
    return 0
  fi
  local version_output=""
  if ! version_output="$("${CURL_BINARY}" --version)"; then
    echo "Unable to determine curl version for bounded public proof download" >&2
    return 1
  fi
  if ! /usr/bin/python3 - "${version_output}" <<'PY'
import re
import sys

match = re.match(r"^curl ([0-9]+)\.([0-9]+)(?:\.([0-9]+))?\b", sys.argv[1])
if match is None or tuple(int(part or 0) for part in match.groups()) < (8, 4, 0):
    raise SystemExit("curl 8.4.0 or newer is required for streaming --max-filesize enforcement")
PY
  then
    return 1
  fi
  CURL_STREAM_LIMIT_READY=1
}

fetch_public_proof() {
  local url="${1:-}"
  local destination="${2:-}"
  local maximum_bytes="${3:-}"
  local maximum_time="${4:-}"
  local partial="${destination}.partial"
  local http_status=""
  local actual_size=""
  local file_links=""
  [[ "${url}" =~ ^https://[^[:space:]]+$ ]] || {
    echo "Public proof URL must use HTTPS" >&2
    return 1
  }
  [[ "${destination}" == /* && "${maximum_bytes}" =~ ^[1-9][0-9]{0,9}$ && "${maximum_time}" =~ ^[1-9][0-9]{0,2}$ ]] || {
    echo "Invalid bounded public proof download arguments" >&2
    return 1
  }
  (( maximum_bytes <= 1073741824 && maximum_time <= 300 )) || {
    echo "Bounded public proof download exceeds the release safety ceiling" >&2
    return 1
  }
  [[ ! -e "${destination}" && ! -L "${destination}" && ! -e "${partial}" && ! -L "${partial}" ]] || {
    echo "Public proof destination already exists" >&2
    return 1
  }
  assert_curl_stream_limit_supported || return 1
  if ! http_status="$("${CURL_BINARY}" \
    --proto '=https' \
    --tlsv1.2 \
    --max-redirs 0 \
    --fail \
    --silent \
    --show-error \
    --max-time "${maximum_time}" \
    --max-filesize "${maximum_bytes}" \
    --output "${partial}" \
    --write-out '%{http_code}' \
    "${url}")"; then
    /bin/rm -f -- "${partial}"
    echo "Bounded public proof download failed" >&2
    return 1
  fi
  if [[ "${http_status}" != "200" ]]; then
    /bin/rm -f -- "${partial}"
    echo "Public proof route must return HTTP 200 without redirect" >&2
    return 1
  fi
  if [[ ! -f "${partial}" || -L "${partial}" ]]; then
    /bin/rm -f -- "${partial}"
    echo "Public proof download did not create a safe regular file" >&2
    return 1
  fi
  file_links="$(/usr/bin/stat -f '%l' "${partial}")"
  actual_size="$(/usr/bin/stat -f '%z' "${partial}")"
  if [[ "${file_links}" != "1" || ! "${actual_size}" =~ ^[0-9]+$ ]] || (( actual_size > maximum_bytes )); then
    /bin/rm -f -- "${partial}"
    echo "Public proof download exceeded its streaming bound" >&2
    return 1
  fi
  /bin/mv -- "${partial}" "${destination}"
}

verify_remote_release_and_http() {
  local proof_json="${WORK_DIR}/remote-state.json"
  local kind digest size artifact_url
  assert_remote_release_lock
  remote_publisher verify \
    --asset-root "${ASSET_ROOT}" --state-root "${STATE_ROOT}" \
    --release-lock-dir "${REMOTE_RELEASE_LOCK_DIR}" \
    --release-lock-token "${REMOTE_RELEASE_LOCK_TOKEN}" >"${proof_json}"
  IFS=$'\t' read -r kind digest size artifact_url < <(/usr/bin/python3 - "${proof_json}" <<'PY'
import json, sys
value = json.load(open(sys.argv[1], encoding="utf-8"))
release = value.get("release")
legacy = value.get("legacy_baseline")
if release is not None:
    print("release", release["artifact_sha256"], release["artifact_size"], release["artifact_url"], sep="\t")
elif legacy is not None:
    print("legacy", legacy["sha256"], legacy["size"], "-", sep="\t")
else:
    print("empty", "-", "0", "-", sep="\t")
PY
  )
  [[ "${digest}" =~ ^[0-9a-f]{64}$ && "${size}" =~ ^[0-9]+$ ]] || {
    [[ "${kind}" == "empty" ]] || { echo "Invalid remote Mac verification proof" >&2; return 1; }
  }
  if [[ "${kind}" == "release" ]]; then
    local current_json="${WORK_DIR}/verified-current.json"
    local immutable_proof="${WORK_DIR}/verified-immutable.dmg"
    fetch_public_proof "${PUBLIC_BASE_URL}/mac/current.json" "${current_json}" 16384 30
    /usr/bin/python3 - "${proof_json}" "${current_json}" <<'PY'
import json, sys
receipt = json.load(open(sys.argv[1], encoding="utf-8"))["release"]
public = json.load(open(sys.argv[2], encoding="utf-8"))
fields = {"schema_version", "source_sha", "source_tree", "artifact_sha256", "artifact_size", "bundle_id", "version", "build", "architectures", "min_os", "artifact_url", "published_at"}
if set(public) != fields or public != {key: receipt[key] for key in fields}:
    raise SystemExit("public current manifest does not match private receipt")
PY
    fetch_public_proof "${artifact_url}" "${immutable_proof}" "${size}" 300
    [[ "$(/usr/bin/shasum -a 256 "${immutable_proof}" | /usr/bin/awk '{print $1}')" == "${digest}" ]] || return 1
    [[ "$(/usr/bin/stat -f '%z' "${immutable_proof}")" == "${size}" ]] || return 1
  fi
  if [[ "${kind}" != "empty" ]]; then
    local stable_proof="${WORK_DIR}/verified-stable.dmg"
    fetch_public_proof "${PUBLIC_BASE_URL}/xiaoba-mac.dmg" "${stable_proof}" "${size}" 300
    [[ "$(/usr/bin/shasum -a 256 "${stable_proof}" | /usr/bin/awk '{print $1}')" == "${digest}" ]] || return 1
    [[ "$(/usr/bin/stat -f '%z' "${stable_proof}")" == "${size}" ]] || return 1
  fi
}

require_artifact_header() {
  local headers="$1"
  local expected="$2"
  /usr/bin/awk -F: -v expected="${expected}" '
    tolower($1) == "x-reva-artifact" {
      value = $2
      sub(/^[[:space:]]+/, "", value)
      sub(/[[:space:]\r]+$/, "", value)
      if (value == expected) found = 1
    }
    END { exit(found ? 0 : 1) }
  ' "${headers}"
}

probe_public_route() {
  local label="$1"
  local url="$2"
  local headers="$3"
  local status=""
  if ! status="$("${CURL_BINARY}" --proto '=https' --tlsv1.2 --max-redirs 0 --silent --show-error --max-time 30 --dump-header "${headers}" --output /dev/null --write-out '%{http_code}' "${url}")"; then
    echo "Public Mac route probe failed: ${label}" >&2
    return 1
  fi
  printf '%s\n' "${status}"
}

preflight_public_routes() {
  ensure_work_dir
  local legacy_headers="${WORK_DIR}/route-legacy.headers"
  local current_headers="${WORK_DIR}/route-current.headers"
  local immutable_headers="${WORK_DIR}/route-immutable.headers"
  local legacy_status current_status immutable_status
  local zero_sha="0000000000000000000000000000000000000000"
  local zero_digest="0000000000000000000000000000000000000000000000000000000000000000"

  legacy_status="$(probe_public_route legacy "${PUBLIC_BASE_URL}/xiaoba-mac.dmg" "${legacy_headers}")" || return 1
  [[ "${legacy_status}" == "200" ]] || {
    echo "Legacy Mac download route must return 200" >&2
    return 1
  }

  current_status="$(probe_public_route current "${PUBLIC_BASE_URL}/mac/current.json" "${current_headers}")" || return 1
  [[ "${current_status}" == "200" || "${current_status}" == "404" ]] || {
    echo "Mac current manifest route must return 200 or first-release 404" >&2
    return 1
  }
  require_artifact_header "${current_headers}" "mac-current-manifest" || {
    echo "Mac current manifest route is missing X-Reva-Artifact: mac-current-manifest" >&2
    return 1
  }

  immutable_status="$(probe_public_route immutable "${PUBLIC_BASE_URL}/mac/releases/${zero_sha}/${zero_digest}.dmg" "${immutable_headers}")" || return 1
  [[ "${immutable_status}" == "404" ]] || {
    echo "Fake immutable Mac route must return 404" >&2
    return 1
  }
  require_artifact_header "${immutable_headers}" "mac-immutable-dmg" || {
    echo "Immutable Mac route is missing X-Reva-Artifact: mac-immutable-dmg" >&2
    return 1
  }
}

finalize_remote_release() {
  [[ "${REMOTE_RELEASE_LOCK_HELD}" == "1" ]] || return 0
  local completed_stage="${REMOTE_STAGE}"
  local completed_token="${REMOTE_RELEASE_LOCK_TOKEN}"
  if [[ -n "${completed_stage}" ]]; then
    [[ "${completed_stage}" == "${ASSET_ROOT}/mac/.staging/${completed_token}" ]] || {
      echo "Refusing to clean a non-canonical Mac release stage" >&2
      return 75
    }
    local cleanup_ok=0
    if [[ "${REMOTE_RELEASE_PHASE}" == "mutating" ]]; then
      remote_protocol stage-cleanup >/dev/null && cleanup_ok=1
    else
      remote_protocol stage-cleanup --allow-partial-stage >/dev/null && cleanup_ok=1
    fi
    if [[ "${cleanup_ok}" != "1" ]]; then
      echo "Mac release completed, but its unique root-only stage requires manual cleanup: ${completed_stage}" >&2
      return 75
    fi
  fi
  if ! release_remote_release_lock; then
    echo "MAC_RELEASE_PRODUCTION_MAY_HAVE_ADVANCED: unified release lock outcome is ambiguous; retained the exact helper handoff for reconciliation" >&2
    REMOTE_RELEASE_LOCK_HELD=0
    return 75
  fi
  REMOTE_STAGE=""
  if ! clear_recovery_handoff; then
    echo "Mac release completed, but the local recovery handoff requires manual cleanup: ${RECOVERY_HANDOFF}" >&2
    return 75
  fi
  reset_remote_release_context
}

run_protocol_recovery_test() {
  # This harness exercises the production shell orchestration with the exact
  # publisher over stdin, but confines every mutation to an explicit temporary
  # root and replaces SSH with local exec. It is unavailable outside test mode.
  ssh_release() {
    "$@"
  }
  initialize_recovery_handoff_paths
  RECOVERY_HANDOFF_PREEXISTED=1
  load_recovery_handoff
  acquire_remote_release_lock
  [[ "${REMOTE_RELEASE_LOCK_ADOPTED}" == "1" ]] || {
    echo "Protocol recovery harness expected an adopted Mac lease" >&2
    return 73
  }
  if [[ "${REMOTE_RELEASE_PHASE}" == "staging" || "${REMOTE_RELEASE_PHASE}" == "sealed" ]]; then
    abandon_pre_mutation_remote_release
  fi
  [[ "${REMOTE_RELEASE_PHASE}" == "mutating" ]] || {
    echo "Protocol recovery harness received an invalid Mac lease phase" >&2
    return 73
  }
  remote_protocol stage-cleanup >/dev/null
  finalize_remote_release
  echo "Mac protocol recovery harness completed"
}

cleanup() {
  local status=$?
  local cleanup_status=0
  trap - EXIT INT TERM
  if [[ -n "${MOUNT_POINT}" && -d "${MOUNT_POINT}" ]]; then
    /usr/bin/hdiutil detach "${MOUNT_POINT}" -force >/dev/null 2>&1 || true
  fi
  if [[ "${REMOTE_MUTATION_DELEGATED}" == "1" || "${REMOTE_RELEASE_PHASE}" == "mutating" ]]; then
    echo "MAC_RELEASE_PRODUCTION_MAY_HAVE_ADVANCED: interrupted during remote mutation; retained the unified lock and exact helper stage for reconciliation" >&2
    REMOTE_RELEASE_LOCK_HELD=0
  elif [[ "${REMOTE_RELEASE_LOCK_HELD}" == "1" ]]; then
    finalize_remote_release || cleanup_status=$?
  elif [[ -n "${REMOTE_STAGE}" ]]; then
    echo "Retained root-only Mac release stage for reconciliation: ${REMOTE_STAGE}" >&2
  fi
  if [[ -n "${WORK_DIR}" && -d "${WORK_DIR}" && "${WORK_DIR}" == "${DIST}/.mac-release."* ]]; then
    /bin/rm -rf -- "${WORK_DIR}"
  fi
  if [[ "${status}" == "0" && "${cleanup_status}" != "0" ]]; then
    status="${cleanup_status}"
  fi
  exit "${status}"
}
if [[ "${HTTP_PROOF_TEST}" == "1" ]]; then
  fetch_public_proof \
    "${HTTP_PROOF_TEST_URL}" \
    "${HTTP_PROOF_TEST_ROOT}/proof" \
    "${HTTP_PROOF_TEST_MAX_BYTES}" \
    "${HTTP_PROOF_TEST_MAX_TIME}"
  echo "Mac bounded HTTP proof test passed"
  exit 0
fi
if [[ "${PROTOCOL_RECOVERY_TEST}" == "1" ]]; then
  run_protocol_recovery_test
  exit 0
fi

trap cleanup EXIT INT TERM

verify_release_source
echo "Source verified: ${SOURCE_SHA} tree=${SOURCE_TREE}"
if [[ "${PREFLIGHT_ONLY}" == "1" ]]; then
  exit 0
fi
if [[ "${ROUTE_PREFLIGHT_ONLY}" == "1" ]]; then
  preflight_public_routes
  echo "Public route preflight passed"
  exit 0
fi
if [[ "${ACTION}" == "recover" || "${ACTION}" == "rollback" ]]; then
  prepare_source_snapshot
  preflight_public_routes
  prepare_remote_release_context
  acquire_remote_release_lock
  verify_release_source
  if [[ "${REMOTE_RELEASE_LOCK_ADOPTED}" == "1" && ( "${REMOTE_RELEASE_PHASE}" == "staging" || "${REMOTE_RELEASE_PHASE}" == "sealed" ) ]]; then
    abandon_pre_mutation_remote_release
  fi
  if [[ "${REMOTE_RELEASE_LOCK_ADOPTED}" == "0" || "${REMOTE_RELEASE_PHASE}" != "mutating" ]]; then
    stage_remote_publisher
  fi
  if [[ "${REMOTE_RELEASE_PHASE}" == "staging" ]]; then
    seal_remote_release_stage
  fi
  delegate_remote_release_mutation
  if ! remote_publisher "${ACTION}" \
    --asset-root "${ASSET_ROOT}" --state-root "${STATE_ROOT}" \
    --release-lock-dir "${REMOTE_RELEASE_LOCK_DIR}" \
    --release-lock-token "${REMOTE_RELEASE_LOCK_TOKEN}" >/dev/null; then
    echo "MAC_RELEASE_PRODUCTION_MAY_HAVE_ADVANCED: ${ACTION} outcome is ambiguous; retained the unified lock and exact helper stage for operator reconciliation" >&2
    REMOTE_RELEASE_LOCK_HELD=0
    exit 75
  fi
  REMOTE_MUTATION_DELEGATED=0
  if ! verify_remote_release_and_http; then
    echo "MAC_RELEASE_PRODUCTION_MAY_HAVE_ADVANCED: ${ACTION} completed but terminal proof failed; retained the unified lock and exact helper stage for operator reconciliation" >&2
    REMOTE_RELEASE_LOCK_HELD=0
    exit 75
  fi
  finalize_remote_release
  echo "Mac release ${ACTION} completed and passed private/public/stable/immutable verification"
  exit 0
fi

[[ "${APP_VERSION}" =~ ^[0-9]+(\.[0-9]+){1,3}$ ]] || {
  echo "--version is required and must be a valid app version" >&2
  exit 2
}
[[ "${APP_BUILD}" =~ ^[0-9]+(\.[0-9]+){0,2}$ ]] || {
  echo "--build is required and must be a valid bundle build" >&2
  exit 2
}
[[ "${SERVER}" =~ ^[A-Za-z0-9._-]+@[A-Za-z0-9.-]+$ ]] || {
  echo "Invalid Mac release server" >&2
  exit 2
}
[[ "${ASSET_ROOT}" =~ ^/[A-Za-z0-9._/-]+$ && "${STATE_ROOT}" =~ ^/[A-Za-z0-9._/-]+$ ]] || {
  echo "Invalid Mac release path configuration" >&2
  exit 2
}
[[ "${PUBLIC_BASE_URL}" =~ ^https://[A-Za-z0-9.-]+$ ]] || {
  echo "Invalid Mac release public URL" >&2
  exit 2
}

read_env_value() {
  local name="$1"
  /usr/bin/awk -F= -v key="${name}" '$1 == key {sub(/^[^=]*=/, ""); print; exit}' "${REPO_ROOT}/.env"
}

ASC_KEY_ID="$(read_env_value APP_STORE_CONNECT_API_KEY)"
ASC_ISSUER="$(read_env_value APP_STORE_CONNECT_ISSUER_ID)"
ASC_P8="${HOME}/.appstoreconnect/private_keys/AuthKey_${ASC_KEY_ID}.p8"
[[ "${ASC_KEY_ID}" =~ ^[A-Z0-9]{10}$ && "${ASC_ISSUER}" =~ ^[0-9a-fA-F-]{36}$ ]] || {
  echo "Notarization credentials are incomplete" >&2
  exit 1
}

P8_TYPE="$(/usr/bin/stat -f '%HT' "${ASC_P8}" 2>/dev/null || true)"
P8_OWNER="$(/usr/bin/stat -f '%Su' "${ASC_P8}" 2>/dev/null || true)"
P8_MODE="$(/usr/bin/stat -f '%Lp' "${ASC_P8}" 2>/dev/null || true)"
P8_LINKS="$(/usr/bin/stat -f '%l' "${ASC_P8}" 2>/dev/null || true)"
P8_SIZE="$(/usr/bin/stat -f '%z' "${ASC_P8}" 2>/dev/null || true)"
[[ ! -L "${ASC_P8}" && "${P8_TYPE}" == "Regular File" ]] &&
  [[ "${P8_OWNER}" == "$(/usr/bin/id -un)" ]] &&
  [[ "${P8_MODE}" == "400" || "${P8_MODE}" == "600" ]] &&
  [[ "${P8_LINKS}" == "1" ]] &&
  [[ "${P8_SIZE}" =~ ^[0-9]+$ && "${P8_SIZE}" -gt 0 && "${P8_SIZE}" -le 65536 ]] || {
  echo "Notarization credential file is unsafe" >&2
  exit 1
}

prepare_source_snapshot
PACKAGE_DIR="${WORK_DIR}/package"
STAGING_DIR="${WORK_DIR}/dmg-staging"
MOUNT_POINT="${WORK_DIR}/mounted"
NOTARY_JSON="${WORK_DIR}/notary.json"
CANDIDATE_JSON="${WORK_DIR}/candidate.json"
/bin/mkdir -p "${PACKAGE_DIR}" "${STAGING_DIR}" "${MOUNT_POINT}"

echo "[1/7] Build source-bound app bundle"
MAC_APP_VERSION="${APP_VERSION}" \
MAC_APP_BUILD="${APP_BUILD}" \
MAC_SOURCE_SHA="${SOURCE_SHA}" \
MAC_SOURCE_TREE="${SOURCE_TREE}" \
  "${SNAPSHOT_DIR}/apps/mac/scripts/package-app.sh" --output "${PACKAGE_DIR}" --no-sign >/dev/null
SOURCE_APP="${PACKAGE_DIR}/HealthAgentMac.app"
SIGNED_APP="${STAGING_DIR}/小巴.app"
[[ -d "${SOURCE_APP}" ]] || { echo "Packaged app is missing" >&2; exit 1; }
/bin/cp -R "${SOURCE_APP}" "${SIGNED_APP}"

echo "[2/7] Developer ID sign and verify"
/usr/bin/codesign --force --deep --options runtime --timestamp \
  --sign "${SIGN_IDENTITY}" "${SIGNED_APP}"
/usr/bin/codesign --verify --strict --deep --verbose=2 "${SIGNED_APP}"

PLIST="${SIGNED_APP}/Contents/Info.plist"
[[ "$(/usr/libexec/PlistBuddy -c 'Print :RevaSourceSHA' "${PLIST}")" == "${SOURCE_SHA}" ]] || {
  echo "Signed app source SHA mismatch" >&2
  exit 1
}
[[ "$(/usr/libexec/PlistBuddy -c 'Print :RevaSourceTree' "${PLIST}")" == "${SOURCE_TREE}" ]] || {
  echo "Signed app source tree mismatch" >&2
  exit 1
}

echo "[3/7] Create and sign DMG"
/bin/ln -s /Applications "${STAGING_DIR}/Applications"
DMG_PATH="${DIST}/xiaoba-mac-${APP_VERSION}-${APP_BUILD}-${SOURCE_SHA:0:12}.dmg"
/bin/rm -f -- "${DMG_PATH}"
/usr/bin/hdiutil create -volname "小巴" -srcfolder "${STAGING_DIR}" -ov -format UDZO \
  "${DMG_PATH}" >/dev/null
/usr/bin/codesign --force --timestamp --sign "${SIGN_IDENTITY}" "${DMG_PATH}"
/usr/bin/codesign --verify --strict --verbose=2 "${DMG_PATH}"

echo "[4/7] Submit structured notarization request"
if ! /usr/bin/xcrun notarytool submit "${DMG_PATH}" \
  --key "${ASC_P8}" --key-id "${ASC_KEY_ID}" --issuer "${ASC_ISSUER}" \
  --wait --output-format json >"${NOTARY_JSON}"; then
  echo "Notarization submission failed" >&2
  /bin/cat "${NOTARY_JSON}" >&2 || true
  exit 1
fi
NOTARY_ID="$(/usr/bin/python3 - "${NOTARY_JSON}" <<'PY'
import json, sys
value = json.load(open(sys.argv[1], encoding="utf-8"))
print(value.get("id", ""))
PY
)"
NOTARY_STATUS="$(/usr/bin/python3 - "${NOTARY_JSON}" <<'PY'
import json, sys
value = json.load(open(sys.argv[1], encoding="utf-8"))
print(value.get("status", ""))
PY
)"
[[ "${NOTARY_ID}" =~ ^[0-9a-fA-F-]{36}$ && "${NOTARY_STATUS}" == "Accepted" ]] || {
  echo "Notarization was not accepted" >&2
  exit 1
}

echo "[5/7] Staple and Gatekeeper verification"
/usr/bin/xcrun stapler staple "${DMG_PATH}" >/dev/null
/usr/bin/xcrun stapler validate "${DMG_PATH}"
/usr/sbin/spctl --assess --type open --context context:primary-signature --verbose=2 "${DMG_PATH}"

echo "[6/7] Mount exact DMG and verify embedded app identity"
/usr/bin/hdiutil attach -readonly -nobrowse -mountpoint "${MOUNT_POINT}" "${DMG_PATH}" >/dev/null
MOUNTED_APP="${MOUNT_POINT}/小巴.app"
MOUNTED_PLIST="${MOUNTED_APP}/Contents/Info.plist"
MOUNTED_MANIFEST="${MOUNTED_APP}/Contents/Resources/release-manifest.json"
[[ -d "${MOUNTED_APP}" && -f "${MOUNTED_MANIFEST}" ]] || {
  echo "Mounted DMG is missing its app or release manifest" >&2
  exit 1
}
/usr/bin/codesign --verify --strict --deep --verbose=2 "${MOUNTED_APP}"
/usr/sbin/spctl --assess --type execute --verbose=2 "${MOUNTED_APP}"
[[ "$(/usr/libexec/PlistBuddy -c 'Print :RevaSourceSHA' "${MOUNTED_PLIST}")" == "${SOURCE_SHA}" ]] || exit 1
[[ "$(/usr/libexec/PlistBuddy -c 'Print :RevaSourceTree' "${MOUNTED_PLIST}")" == "${SOURCE_TREE}" ]] || exit 1
[[ "$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "${MOUNTED_PLIST}")" == "${APP_VERSION}" ]] || exit 1
[[ "$(/usr/libexec/PlistBuddy -c 'Print :CFBundleVersion' "${MOUNTED_PLIST}")" == "${APP_BUILD}" ]] || exit 1
/usr/bin/python3 - "${MOUNTED_MANIFEST}" "${SOURCE_SHA}" "${SOURCE_TREE}" "${APP_VERSION}" "${APP_BUILD}" <<'PY'
import json, sys
value = json.load(open(sys.argv[1], encoding="utf-8"))
expected = {
    "schema_version": 1,
    "source_sha": sys.argv[2],
    "source_tree": sys.argv[3],
    "bundle_id": "life.executor.health.mac",
    "version": sys.argv[4],
    "build": sys.argv[5],
}
if value != expected:
    raise SystemExit("embedded release manifest mismatch")
PY

SIGN_INFO="$(/usr/bin/codesign -d --verbose=4 "${MOUNTED_APP}" 2>&1)"
TEAM_ID="$(printf '%s\n' "${SIGN_INFO}" | /usr/bin/awk -F= '$1 == "TeamIdentifier" {print $2; exit}')"
CDHASH="$(printf '%s\n' "${SIGN_INFO}" | /usr/bin/awk -F= '$1 == "CDHash" {print tolower($2); exit}')"
BUNDLE_ID="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "${MOUNTED_PLIST}")"
MIN_OS="$(/usr/libexec/PlistBuddy -c 'Print :LSMinimumSystemVersion' "${MOUNTED_PLIST}")"
ARCHITECTURES_RAW="$(/usr/bin/lipo -archs "${MOUNTED_APP}/Contents/MacOS/HealthAgentMac")"
ARCHITECTURES="$(printf '%s\n' ${ARCHITECTURES_RAW} | /usr/bin/sort -u)"
[[ "${TEAM_ID}" =~ ^[A-Z0-9]{10}$ && "${CDHASH}" =~ ^[0-9a-f]{40}$ ]] || {
  echo "Developer ID identity metadata is incomplete" >&2
  exit 1
}
[[ "${BUNDLE_ID}" == "${EXPECTED_BUNDLE_ID}" ]] || {
  echo "Signed app bundle identifier is not the production identifier" >&2
  exit 1
}
[[ "${TEAM_ID}" == "${EXPECTED_TEAM_ID}" ]] || {
  echo "Signed app Developer Team is not the production team" >&2
  exit 1
}

/usr/bin/hdiutil detach "${MOUNT_POINT}" >/dev/null
MOUNT_POINT=""
ARTIFACT_SHA256="$(/usr/bin/shasum -a 256 "${DMG_PATH}" | /usr/bin/awk '{print $1}')"
ARTIFACT_SIZE="$(/usr/bin/stat -f '%z' "${DMG_PATH}")"
REMOTE_ARTIFACT_PATH="${ASSET_ROOT}/mac/releases/${SOURCE_SHA}/${ARTIFACT_SHA256}.dmg"
ARTIFACT_URL="${PUBLIC_BASE_URL}/mac/releases/${SOURCE_SHA}/${ARTIFACT_SHA256}.dmg"
PUBLISHED_AT="$(/bin/date -u '+%Y-%m-%dT%H:%M:%SZ')"

CANDIDATE_ARGS=(
  create-candidate
  --output "${CANDIDATE_JSON}"
  --source-sha "${SOURCE_SHA}"
  --source-tree "${SOURCE_TREE}"
  --artifact-sha256 "${ARTIFACT_SHA256}"
  --artifact-size "${ARTIFACT_SIZE}"
  --artifact-path "${REMOTE_ARTIFACT_PATH}"
  --artifact-url "${ARTIFACT_URL}"
  --bundle-id "${BUNDLE_ID}"
  --version "${APP_VERSION}"
  --build "${APP_BUILD}"
  --team-id "${TEAM_ID}"
  --cdhash "${CDHASH}"
  --min-os "${MIN_OS}"
  --notary-submission-id "${NOTARY_ID}"
  --notary-status "${NOTARY_STATUS}"
  --stapled
  --published-at "${PUBLISHED_AT}"
)
while IFS= read -r architecture; do
  CANDIDATE_ARGS+=(--architecture "${architecture}")
done <<< "${ARCHITECTURES}"
/usr/bin/python3 "${SNAPSHOT_PUBLISHER}" "${CANDIDATE_ARGS[@]}" >/dev/null

if [[ "${SKIP_UPLOAD}" == "1" ]]; then
  echo "Verified notarized artifact: ${DMG_PATH}"
  echo "Candidate receipt: ${CANDIDATE_JSON}"
  exit 0
fi

verify_release_source
preflight_public_routes
prepare_remote_release_context
acquire_remote_release_lock
verify_release_source
stage_remote_publisher
echo "[7/7] Upload immutable artifact and atomically switch current"
assert_remote_release_lock
  scp_release -q "${DMG_PATH}" "${SERVER}:${REMOTE_STAGE}/.upload.dmg.upload"
  scp_release -q "${CANDIDATE_JSON}" "${SERVER}:${REMOTE_STAGE}/.candidate.json.upload"
remote_protocol stage-bind-payload >/dev/null
assert_remote_release_lock
seal_remote_release_stage

REMOTE_PUBLISH=(
  publish
  --artifact "${REMOTE_STAGE}/upload.dmg"
  --candidate "${REMOTE_STAGE}/candidate.json"
  --asset-root "${ASSET_ROOT}"
  --state-root "${STATE_ROOT}"
  --release-lock-dir "${REMOTE_RELEASE_LOCK_DIR}"
  --release-lock-token "${REMOTE_RELEASE_LOCK_TOKEN}"
)
# Reconcile any durable transaction left by a killed prior publisher before
# admitting new immutable bytes or changing any current pointer.
delegate_remote_release_mutation
if ! remote_publisher recover \
  --asset-root "${ASSET_ROOT}" --state-root "${STATE_ROOT}" \
  --release-lock-dir "${REMOTE_RELEASE_LOCK_DIR}" \
  --release-lock-token "${REMOTE_RELEASE_LOCK_TOKEN}" >/dev/null; then
  echo "MAC_RELEASE_PRODUCTION_MAY_HAVE_ADVANCED: automatic pre-publish recovery outcome is ambiguous; retained the unified lock and exact helper stage for reconciliation" >&2
  REMOTE_RELEASE_LOCK_HELD=0
  exit 75
fi
# Install immutable bytes without changing either current pointer.  This makes
# the public nginx route a precondition rather than a post-publication surprise.
if ! remote_publisher "${REMOTE_PUBLISH[@]}" --prepare-only >/dev/null; then
  echo "MAC_RELEASE_PRODUCTION_MAY_HAVE_ADVANCED: immutable preparation outcome is ambiguous; retained the unified lock and exact helper stage for reconciliation" >&2
  REMOTE_RELEASE_LOCK_HELD=0
  exit 75
fi
HTTP_PROOF="${WORK_DIR}/http-proof.dmg"
fetch_public_proof "${ARTIFACT_URL}" "${HTTP_PROOF}" "${ARTIFACT_SIZE}" 300
[[ "$(/usr/bin/shasum -a 256 "${HTTP_PROOF}" | /usr/bin/awk '{print $1}')" == "${ARTIFACT_SHA256}" ]] || {
  echo "Public immutable DMG hash mismatch; current was not changed" >&2
  exit 1
}
[[ "$(/usr/bin/stat -f '%z' "${HTTP_PROOF}")" == "${ARTIFACT_SIZE}" ]] || {
  echo "Public immutable DMG size mismatch; current was not changed" >&2
  exit 1
}
if ! remote_publisher "${REMOTE_PUBLISH[@]}" >/dev/null; then
  echo "MAC_RELEASE_PRODUCTION_MAY_HAVE_ADVANCED: remote publish outcome is ambiguous; retain the unified lock and stage, then reconcile with the supported Mac recovery workflow before retrying" >&2
  REMOTE_RELEASE_LOCK_HELD=0
  exit 75
fi
REMOTE_MUTATION_DELEGATED=0

CURRENT_JSON="${WORK_DIR}/current.json"
if ! fetch_public_proof "${PUBLIC_BASE_URL}/mac/current.json" "${CURRENT_JSON}" 16384 30; then
  echo "MAC_RELEASE_PRODUCTION_MAY_HAVE_ADVANCED: current manifest verification failed after switch; retained the unified lock and exact helper stage for reconciliation" >&2
  REMOTE_RELEASE_LOCK_HELD=0
  exit 75
fi
if ! /usr/bin/python3 - "${CURRENT_JSON}" "${CANDIDATE_JSON}" <<'PY'
import json, sys
public = json.load(open(sys.argv[1], encoding="utf-8"))
private = json.load(open(sys.argv[2], encoding="utf-8"))
fields = {
    "schema_version", "source_sha", "source_tree", "artifact_sha256",
    "artifact_size", "bundle_id", "version", "build", "architectures",
    "min_os", "artifact_url", "published_at",
}
if set(public) != fields or public != {key: private[key] for key in fields}:
    raise SystemExit("public current manifest verification failed")
PY
then
  echo "MAC_RELEASE_PRODUCTION_MAY_HAVE_ADVANCED: current manifest does not match the candidate after switch; retained the unified lock and exact helper stage for reconciliation" >&2
  REMOTE_RELEASE_LOCK_HELD=0
  exit 75
fi
STABLE_PROOF="${WORK_DIR}/stable-proof.dmg"
if ! fetch_public_proof "${PUBLIC_BASE_URL}/xiaoba-mac.dmg" "${STABLE_PROOF}" "${ARTIFACT_SIZE}" 300; then
  echo "MAC_RELEASE_PRODUCTION_MAY_HAVE_ADVANCED: stable download verification failed after switch; retained the unified lock and exact helper stage for reconciliation" >&2
  REMOTE_RELEASE_LOCK_HELD=0
  exit 75
fi
[[ "$(/usr/bin/shasum -a 256 "${STABLE_PROOF}" | /usr/bin/awk '{print $1}')" == "${ARTIFACT_SHA256}" ]] || {
  echo "MAC_RELEASE_PRODUCTION_MAY_HAVE_ADVANCED: stable download did not match after switch; retained the unified lock and exact helper stage for reconciliation" >&2
  REMOTE_RELEASE_LOCK_HELD=0
  exit 75
}
[[ "$(/usr/bin/stat -f '%z' "${STABLE_PROOF}")" == "${ARTIFACT_SIZE}" ]] || {
  echo "MAC_RELEASE_PRODUCTION_MAY_HAVE_ADVANCED: stable download size did not match after switch; retained the unified lock and exact helper stage for reconciliation" >&2
  REMOTE_RELEASE_LOCK_HELD=0
  exit 75
}
IMMUTABLE_FINAL_PROOF="${WORK_DIR}/immutable-final-proof.dmg"
if ! fetch_public_proof "${ARTIFACT_URL}" "${IMMUTABLE_FINAL_PROOF}" "${ARTIFACT_SIZE}" 300; then
  echo "MAC_RELEASE_PRODUCTION_MAY_HAVE_ADVANCED: immutable download verification failed after switch; retained the unified lock and exact helper stage for reconciliation" >&2
  REMOTE_RELEASE_LOCK_HELD=0
  exit 75
fi
[[ "$(/usr/bin/shasum -a 256 "${IMMUTABLE_FINAL_PROOF}" | /usr/bin/awk '{print $1}')" == "${ARTIFACT_SHA256}" ]] || {
  echo "MAC_RELEASE_PRODUCTION_MAY_HAVE_ADVANCED: immutable download did not match after switch; retained the unified lock and exact helper stage for reconciliation" >&2
  REMOTE_RELEASE_LOCK_HELD=0
  exit 75
}
[[ "$(/usr/bin/stat -f '%z' "${IMMUTABLE_FINAL_PROOF}")" == "${ARTIFACT_SIZE}" ]] || {
  echo "MAC_RELEASE_PRODUCTION_MAY_HAVE_ADVANCED: immutable download size did not match after switch; retained the unified lock and exact helper stage for reconciliation" >&2
  REMOTE_RELEASE_LOCK_HELD=0
  exit 75
}
REMOTE_MUTATION_DELEGATED=0
finalize_remote_release
echo "Published immutable Mac release: ${ARTIFACT_URL}"
# END UNREACHABLE LEGACY MAC RELEASE IMPLEMENTATION
fi
