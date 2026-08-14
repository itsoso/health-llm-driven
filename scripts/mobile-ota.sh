#!/bin/bash
# Publish one transaction-local iOS EAS Update artifact, with same-byte retry.

# EAS channel-to-branch mappings live outside this repository and can drift or
# converge. No repository-local channel name proves that a network update cannot
# reach an ASC-distributed binary. Freeze every EAS Update writer before reading
# argv, deriving messages, resolving paths, acquiring locks, or invoking a
# caller-supplied runner. Local Metro/simulator/device development remains
# available through its separate non-EAS workflows.
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  printf '%s\n' '✗ EAS OTA 网络写入已冻结：请走人工发布 Gate。' >&2
  exit 78
fi

if [[ 0 -eq 1 ]]; then
set -euo pipefail

CHANNEL="${1:-production}"

MESSAGE="${2:-$(git log -1 --pretty=format:'%s')}"
ENVIRONMENT="${CHANNEL}"
EAS_CLI_VERSION="${OTA_EAS_CLI_VERSION:-21.8.0}"

if [[ ! "${EAS_CLI_VERSION}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "✗ OTA_EAS_CLI_VERSION 必须是精确的 x.y.z 版本。" >&2
  exit 2
fi

case "${CHANNEL}" in
  rokid-production) ENVIRONMENT="production" ;;
  rokid-preview) ENVIRONMENT="preview" ;;
esac

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOCKED_EAS_HELPER="${REPO_ROOT}/scripts/locked_eas_cli.py"
VERIFY_SCRIPT="${REPO_ROOT}/scripts/verify_mobile_ota_artifact.py"
NATIVE_COMPATIBILITY_SCRIPT="${REPO_ROOT}/scripts/verify_mobile_native_ota_compatibility.py"
NATIVE_BUILD_PAGE_LIMIT=50
NATIVE_BUILD_MAX_PAGES=20
if [[ ! "${CHANNEL}" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$ ]]; then
  echo "✗ OTA channel 格式无效。" >&2
  exit 2
fi
source "${REPO_ROOT}/scripts/release_lock.sh"
acquire_release_lock "ota:${CHANNEL}"

STATE_PATH_ARGS=(
  state-paths --repo-root "${REPO_ROOT}" --channel "${CHANNEL}"
  --scope mobile --migrate
)
[[ -z "${OTA_MANIFEST_FILE:-}" ]] || STATE_PATH_ARGS+=(--manifest-file "${OTA_MANIFEST_FILE}")
[[ -z "${OTA_ANCHOR_FILE:-}" ]] || STATE_PATH_ARGS+=(--anchor-file "${OTA_ANCHOR_FILE}")
[[ -z "${OTA_AUDIT_LOG:-}" ]] || STATE_PATH_ARGS+=(--audit-file "${OTA_AUDIT_LOG}")
STATE_PATHS_JSON="$(python3 "${VERIFY_SCRIPT}" "${STATE_PATH_ARGS[@]}")" || exit $?
IFS=$'\t' read -r MANIFEST_FILE PENDING_FILE ANCHOR_FILE OTA_AUDIT_LOG < <(
  python3 - "${STATE_PATHS_JSON}" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
values = [
    payload["manifest_file"], payload["pending_file"],
    payload["anchor_file"], payload["audit_file"],
]
if any("\t" in value or "\n" in value for value in values):
    raise SystemExit("OTA state paths must not contain tabs or newlines")
print("\t".join(values))
PY
)

python3 - "${PENDING_FILE}" "${CHANNEL}" <<'PY'
import json
import os
import re
import stat
import sys
from pathlib import Path

path = Path(sys.argv[1])
channel = sys.argv[2]
max_receipt_bytes = 64 * 1024
parent_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
parent_flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
try:
    parent_descriptor = os.open(path.parent, parent_flags)
except OSError as error:
    raise SystemExit(f"unsafe pending rollback receipt: {path}: {error}") from error
descriptor = -1
try:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(path.name, flags, dir_fd=parent_descriptor)
    except FileNotFoundError:
        raise SystemExit(0) from None
    metadata = os.fstat(descriptor)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or metadata.st_nlink != 1
        or metadata.st_uid != os.getuid()
    ):
        raise OSError("receipt must be a current-owner 0600 single-link regular file")
    if metadata.st_size > max_receipt_bytes:
        raise OSError("receipt size is too large")
    chunks = []
    remaining = max_receipt_bytes + 1
    while remaining > 0:
        chunk = os.read(descriptor, min(64 * 1024, remaining))
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    raw = b"".join(chunks)
    if len(raw) > max_receipt_bytes:
        raise OSError("receipt size is too large")
    final_metadata = os.fstat(descriptor)
    stable_fields = (
        "st_dev", "st_ino", "st_mode", "st_uid", "st_nlink", "st_size",
        "st_mtime_ns", "st_ctime_ns",
    )
    if any(
        getattr(metadata, field) != getattr(final_metadata, field)
        for field in stable_fields
    ):
        raise OSError("receipt changed while reading")
    current = os.stat(path.name, dir_fd=parent_descriptor, follow_symlinks=False)
    if (current.st_dev, current.st_ino) != (
        final_metadata.st_dev,
        final_metadata.st_ino,
    ):
        raise OSError("receipt changed while reading")
    payload = json.loads(raw.decode("utf-8", errors="strict"))
    if not isinstance(payload, dict):
        raise ValueError("receipt JSON must be an object")
except (OSError, UnicodeError, ValueError) as error:
    raise SystemExit(f"unsafe pending rollback receipt: {path}: {error}") from error
finally:
    if descriptor >= 0:
        os.close(descriptor)
    os.close(parent_descriptor)
transaction_id = payload.get("transaction_id")
fingerprint = payload.get("manifest_fingerprint")
if (
    payload.get("schema_version") != 1
    or payload.get("status") != "pending"
    or payload.get("channel") != channel
    or not isinstance(transaction_id, str)
    or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{5,89}", transaction_id)
    or not isinstance(fingerprint, str)
    or (fingerprint != "missing" and not re.fullmatch(r"[0-9a-f]{64}", fingerprint))
):
    raise SystemExit(f"unsafe pending rollback receipt identity: {path}")
raise SystemExit(
    f"pending rollback transaction {transaction_id} requires reconciliation; "
    "forward OTA is blocked"
)
PY

if [[ "${OTA_FORCE_NO_BYTECODE:-0}" != "0" &&
      "${OTA_FORCE_NO_BYTECODE:-0}" != "1" ]]; then
  echo "✗ OTA_FORCE_NO_BYTECODE 只接受 0/1。" >&2
  exit 1
fi
if [[ ! "${OTA_LOOKUP_ATTEMPTS:-3}" =~ ^[1-9][0-9]*$ ]] ||
   [[ ! "${OTA_LOOKUP_DELAY_SECONDS:-2}" =~ ^[0-9]+([.][0-9]+)?$ ]] ||
   [[ ! "${OTA_LOOKUP_MAX_PAGES:-20}" =~ ^[1-9][0-9]*$ ]]; then
  echo "✗ OTA lookup 重试参数无效。" >&2
  exit 2
fi

# Prove the committed Mobile/shared runtime is clean and equivalent to current
# origin/main. A docs-only main advance is safe; any runtime or working-tree
# divergence remains fail closed. OTA_ALLOW_DIRTY is a local test escape hatch
# and is stripped by the production planner.
if [[ "${OTA_ALLOW_DIRTY:-0}" != "1" ]]; then
  git -C "${REPO_ROOT}" fetch origin --quiet
  SOURCE_GUARD_FLAGS=()
else
  SOURCE_GUARD_FLAGS=(--allow-divergence --allow-dirty)
fi
SOURCE_GUARD_OUTPUT="$(python3 "${REPO_ROOT}/scripts/ota_source_guard.py" \
  --repo "${REPO_ROOT}" --source HEAD --main origin/main --format shell \
  "${SOURCE_GUARD_FLAGS[@]}")" || exit $?
SOURCE_COMMIT_SHA=""
MAIN_COMMIT_SHA=""
RELEASE_COMMIT_SHA=""
MOBILE_TREE_DIGEST=""
MAIN_ADVANCED=0
RUNTIME_EQUIVALENT=0
while IFS='=' read -r key value; do
  case "${key}" in
    SOURCE_COMMIT_SHA) SOURCE_COMMIT_SHA="${value}" ;;
    MAIN_COMMIT_SHA) MAIN_COMMIT_SHA="${value}" ;;
    RELEASE_COMMIT_SHA) RELEASE_COMMIT_SHA="${value}" ;;
    MOBILE_TREE_DIGEST) MOBILE_TREE_DIGEST="${value}" ;;
    MAIN_ADVANCED) MAIN_ADVANCED="${value}" ;;
    RUNTIME_EQUIVALENT) RUNTIME_EQUIVALENT="${value}" ;;
    *) echo "✗ OTA source guard returned unknown field: ${key}" >&2; exit 1 ;;
  esac
done <<< "${SOURCE_GUARD_OUTPUT}"
if [[ "${MAIN_ADVANCED}" == "1" && "${RUNTIME_EQUIVALENT}" == "1" ]]; then
  echo "△ origin/main advanced without Mobile/shared changes; publishing the proven equivalent tree."
fi

# A corrupt operational receipt would erase the known-good rollback target if
# overwritten after publishing. Validate it before any EAS mutation.
MANIFEST_SNAPSHOT_JSON="$(python3 "${VERIFY_SCRIPT}" manifest \
  --manifest-file "${MANIFEST_FILE}" --allow-missing \
  --expected-channel "${CHANNEL}")" || exit $?
readonly MANIFEST_SNAPSHOT_JSON

runtime_version() {
  python3 - "${REPO_ROOT}/mobile/app.json" <<'PY'
import json
import sys

try:
    with open(sys.argv[1], encoding="utf-8") as handle:
        expo = json.load(handle).get("expo", {})
        runtime = expo.get("runtimeVersion")
        value = runtime if isinstance(runtime, str) else expo.get("version")
except (OSError, ValueError, TypeError):
    value = None
print(value or "unknown")
PY
}

SOURCE_HEAD="$(git -C "${REPO_ROOT}" rev-parse HEAD)"
SOURCE_TREE="$(git -C "${REPO_ROOT}" rev-parse 'HEAD^{tree}')"
SOURCE_RUNTIME="${MOBILE_RUNTIME_VERSION:-$(runtime_version)}"
SOURCE_STATUS="$(git -C "${REPO_ROOT}" status --porcelain -- mobile/ packages/shared/)"
if [[ -n "${OTA_TRANSACTION_REUSED:-}" &&
      "${OTA_TRANSACTION_REUSED}" != "0" &&
      "${OTA_TRANSACTION_REUSED}" != "1" ]]; then
  echo "✗ OTA_TRANSACTION_REUSED 只接受 0/1。" >&2
  exit 2
fi
if [[ -n "${OTA_TRANSACTION_REUSED:-}" && -z "${OTA_TRANSACTION_ID:-}" ]]; then
  echo "✗ OTA_TRANSACTION_REUSED 必须与 OTA_TRANSACTION_ID 一起使用。" >&2
  exit 2
fi
REUSED_TRANSACTION_ID=0
if [[ -n "${OTA_TRANSACTION_ID:-}" ]]; then
  # An explicit ID without the planner's fresh marker is conservative: it may
  # have crossed a prior process boundary and therefore needs reconciliation.
  REUSED_TRANSACTION_ID="${OTA_TRANSACTION_REUSED:-1}"
fi
TRANSACTION_ID="${OTA_TRANSACTION_ID:-$(python3 - <<'PY'
import uuid
print(uuid.uuid4())
PY
)}"
if [[ ! "${TRANSACTION_ID}" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{5,79}$ ]]; then
  echo "✗ OTA transaction ID 格式无效。" >&2
  exit 2
fi
python3 - "${MANIFEST_FILE}" "${ANCHOR_FILE}" "${OTA_AUDIT_LOG}" "${PENDING_FILE}" <<'PY'
import os
import stat
import sys
from pathlib import Path

paths = [Path(value).expanduser().absolute() for value in sys.argv[1:]]
resolved = [path.resolve(strict=False) for path in paths]
if len(set(resolved)) != len(resolved):
    raise SystemExit("OTA manifest, anchor, audit, and rollback-pending paths must be distinct")
existing = []
for path in paths:
    try:
        metadata = path.stat(follow_symlinks=False)
    except FileNotFoundError:
        continue
    if path == paths[1] and (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or metadata.st_nlink != 1
        or metadata.st_uid != os.getuid()
    ):
        raise SystemExit(f"unsafe OTA anchor file: {path}")
    existing.append((path, metadata.st_dev, metadata.st_ino))
identities = {(device, inode) for _path, device, inode in existing}
if len(identities) != len(existing):
    raise SystemExit("OTA manifest, anchor, and audit files must use distinct inodes")
PY
TRANSACTION_MESSAGE="[tx:${TRANSACTION_ID}] ${MESSAGE}"
TRANSACTION_STARTED_NS="$(python3 - <<'PY'
import time
print(time.time_ns())
PY
)"
TRANSACTION_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/reva-mobile-ota.XXXXXX")"
chmod 700 "${TRANSACTION_ROOT}"
INPUT_DIR="${TRANSACTION_ROOT}/export"
mkdir -m 700 "${INPUT_DIR}"
PUBLISH_JSON="${TRANSACTION_ROOT}/publish.json"
PUBLISH_ERR="${TRANSACTION_ROOT}/publish.err"
ARTIFACT_JSON="${TRANSACTION_ROOT}/artifact.json"
VIEW_JSON="${TRANSACTION_ROOT}/view.json"
CHANNEL_JSON="${TRANSACTION_ROOT}/channel.json"
VERIFIED_JSON="${TRANSACTION_ROOT}/verified.json"
LOOKUP_JSON="${TRANSACTION_ROOT}/lookup.json"
LOOKUP_RESULT="${TRANSACTION_ROOT}/lookup-result.json"
NATIVE_BUILD_AGGREGATE="${TRANSACTION_ROOT}/native-builds.json"
NATIVE_COMPATIBILITY_EVIDENCE="${TRANSACTION_ROOT}/native-compatibility.json"
NATIVE_COHORT_BASELINE_DIGEST=""
EAS_TOOL_WORKSPACE=""
EAS_BINARY=""

cleanup_mobile_ota() {
  if [[ -n "${EAS_TOOL_WORKSPACE:-}" ]]; then
    python3 "${LOCKED_EAS_HELPER}" cleanup "${EAS_TOOL_WORKSPACE}" || true
    EAS_TOOL_WORKSPACE=""
  fi
  if [[ -n "${TRANSACTION_ROOT:-}" &&
        "${TRANSACTION_ROOT##*/}" == reva-mobile-ota.* &&
        -d "${TRANSACTION_ROOT}" ]]; then
    rm -rf -- "${TRANSACTION_ROOT}"
  fi
  release_release_lock
}
trap cleanup_mobile_ota EXIT

prepare_locked_eas_cli() {
  [[ -n "${OTA_EAS_RUNNER:-}" ]] && return 0
  local prepared extra
  prepared="$(
    python3 "${LOCKED_EAS_HELPER}" prepare --repo-root "${REPO_ROOT}"
  )" || return $?
  IFS=$'\t' read -r EAS_TOOL_WORKSPACE EAS_BINARY extra <<<"${prepared}"
  if [[ -n "${extra}" || -z "${EAS_TOOL_WORKSPACE}" ||
        -z "${EAS_BINARY}" || ! -x "${EAS_BINARY}" ]]; then
    echo "✗ integrity-locked EAS CLI preparation returned invalid evidence." >&2
    return 2
  fi
}

validate_ota_audit_log() {
  python3 - "${OTA_AUDIT_LOG}" <<'PY'
import os
import stat
import sys
from pathlib import Path

path = Path(sys.argv[1])
parent = path.parent
try:
    parent.mkdir(parents=True, exist_ok=True)
    if parent.is_symlink() or not parent.is_dir():
        raise OSError("unsafe audit parent")
    if path.exists() or path.is_symlink():
        metadata = path.lstat()
        if (
            stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_nlink != 1
            or metadata.st_uid != os.getuid()
        ):
            raise OSError("unsafe audit file")
    else:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        flags |= getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags, 0o600)
        os.close(descriptor)
except OSError as error:
    print(f"unsafe OTA audit log: {path}: {error}", file=sys.stderr)
    raise SystemExit(1)
PY
}

record_ota_audit() {
  local attempt="$1"
  local result="$2"
  local failure_class="$3"
  local duration_seconds="$4"
  local group_id="${5:-}"
  local update_id="${6:-}"
  python3 - "${OTA_AUDIT_LOG}" "${CHANNEL}" "${ENVIRONMENT}" \
    "${SOURCE_RUNTIME}" "${SOURCE_COMMIT_SHA}" "${MAIN_COMMIT_SHA}" \
    "${MOBILE_TREE_DIGEST}" "${TRANSACTION_ID}" "${attempt}" \
    "${result}" "${failure_class}" "${duration_seconds}" \
    "${group_id}" "${update_id}" <<'PY'
import json
import os
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path

(
    path, channel, environment, runtime_version, source_commit_sha,
    main_commit_sha, mobile_tree_digest, transaction_id, attempt, result,
    failure_class, duration_seconds, group_id, update_id,
) = sys.argv[1:]
audit_path = Path(path)
flags = os.O_WRONLY | os.O_APPEND
flags |= getattr(os, "O_CLOEXEC", 0)
flags |= getattr(os, "O_NOFOLLOW", 0)
fd = os.open(audit_path, flags)
metadata = os.fstat(fd)
if (
    not stat.S_ISREG(metadata.st_mode)
    or stat.S_IMODE(metadata.st_mode) != 0o600
    or metadata.st_nlink != 1
    or metadata.st_uid != os.getuid()
):
    os.close(fd)
    raise OSError(f"unsafe OTA audit log: {audit_path}")
payload = {
    "schema_version": 2,
    "recorded_at": datetime.now(timezone.utc).isoformat(),
    "platform": "ios",
    "channel": channel,
    "environment": environment,
    "runtime_version": runtime_version,
    "source_commit_sha": source_commit_sha,
    "main_commit_sha": main_commit_sha,
    "mobile_tree_digest": mobile_tree_digest,
    "transaction_id": transaction_id,
    "attempt": int(attempt),
    "result": result,
    "failure_class": failure_class or None,
    "duration_seconds": round(float(duration_seconds), 3),
    "group_id": group_id or None,
    "update_id": update_id or None,
}
with os.fdopen(fd, "a", encoding="utf-8") as handle:
    handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
    handle.flush()
    os.fsync(handle.fileno())
PY
}

validate_ota_audit_log

OTA_STAGE_STARTED_NS="$(python3 - <<'PY'
import time
print(time.monotonic_ns())
PY
)"
ota_elapsed_seconds() {
  python3 - "${OTA_STAGE_STARTED_NS}" <<'PY'
import sys
import time
print(f"{(time.monotonic_ns() - int(sys.argv[1])) / 1_000_000_000:.3f}")
PY
}

cd "${REPO_ROOT}/mobile"
NESTED_EXPO_CLI_NODE_PATH="${REPO_ROOT}/mobile/node_modules/expo/node_modules"
if [[ -d "${NESTED_EXPO_CLI_NODE_PATH}/@expo/cli" ]]; then
  export NODE_PATH="${NESTED_EXPO_CLI_NODE_PATH}${NODE_PATH:+:${NODE_PATH}}"
fi

run_eas_capture() {
  local stdout_file="$1"
  local stderr_file="$2"
  shift 2
  set +e
  if [[ -n "${OTA_EAS_RUNNER:-}" ]]; then
    CI=1 "${OTA_EAS_RUNNER}" "$@" >"${stdout_file}" 2>"${stderr_file}"
  else
    CI=1 "${EAS_BINARY}" "$@" \
      >"${stdout_file}" 2>"${stderr_file}"
  fi
  local rc=$?
  set -e
  [[ ! -s "${stderr_file}" ]] || cat "${stderr_file}" >&2
  return "${rc}"
}

verify_production_native_cohort() {
  [[ "${CHANNEL}" == "production" ]] || return 0
  local phase="${1:-initial}"
  local page=1
  local offset=0
  local page_file page_count aggregate_file evidence_file cohort_digest
  if [[ "${phase}" != "initial" && "${phase}" != "recheck" ]]; then
    echo "✗ Invalid production native cohort verification phase." >&2
    return 2
  fi
  aggregate_file="${NATIVE_BUILD_AGGREGATE%.json}-${phase}.json"
  evidence_file="${NATIVE_COMPATIBILITY_EVIDENCE%.json}-${phase}.json"
  printf '[]\n' >"${aggregate_file}"
  while true; do
    page_file="${TRANSACTION_ROOT}/native-build-${phase}-page-${page}.json"
    if ! run_eas_capture "${page_file}" "${TRANSACTION_ROOT}/native-build-page-${page}.err" \
        build:list --platform ios --status finished --distribution store \
        --build-profile production --channel production \
        --runtime-version "${SOURCE_RUNTIME}" \
        --limit "${NATIVE_BUILD_PAGE_LIMIT}" --offset "${offset}" \
        --json --non-interactive; then
      echo "✗ Production OTA native cohort query failed; publish is blocked." >&2
      return 2
    fi
    page_count="$(python3 "${NATIVE_COMPATIBILITY_SCRIPT}" append-page \
      --page-json "${page_file}" \
      --aggregate-json "${aggregate_file}" \
      --runtime-version "${SOURCE_RUNTIME}" \
      --channel production)" || return $?
    if [[ "${page_count}" -lt "${NATIVE_BUILD_PAGE_LIMIT}" ]]; then
      break
    fi
    if [[ "${page}" -ge "${NATIVE_BUILD_MAX_PAGES}" ]]; then
      echo "✗ Production OTA native build:list reached the page safety cap before a terminal page; refusing a truncated cohort." >&2
      return 2
    fi
    page=$((page + 1))
    offset=$((offset + NATIVE_BUILD_PAGE_LIMIT))
  done
  python3 "${NATIVE_COMPATIBILITY_SCRIPT}" verify \
    --repo-root "${REPO_ROOT}" \
    --target-sha "${SOURCE_HEAD}" \
    --runtime-version "${SOURCE_RUNTIME}" \
    --channel production \
    --builds-json "${aggregate_file}" \
    >"${evidence_file}" || return $?
  cohort_digest="$(python3 - "${aggregate_file}" "${evidence_file}" <<'PY'
import hashlib
import sys
from pathlib import Path

digest = hashlib.sha256()
for value in sys.argv[1:]:
    digest.update(Path(value).read_bytes())
    digest.update(b"\0")
print(digest.hexdigest())
PY
)" || return $?
  if [[ "${phase}" == "initial" ]]; then
    NATIVE_COHORT_BASELINE_DIGEST="${cohort_digest}"
  elif [[ -z "${NATIVE_COHORT_BASELINE_DIGEST}" ||
          "${cohort_digest}" != "${NATIVE_COHORT_BASELINE_DIGEST}" ]]; then
    echo "✗ Production OTA native cohort changed after validation/export; rerun planning before publish." >&2
    return 2
  fi
  echo "✓ Production OTA native cohort compatibility verified (${phase})."
}

run_expo_export_no_bytecode() {
  local stdout_file="${TRANSACTION_ROOT}/expo-export.out"
  local stderr_file="${TRANSACTION_ROOT}/expo-export.err"
  echo "△ 使用显式 --no-bytecode 单次导出；后续重试只复用同一目录。"
  set +e
  if [[ -n "${OTA_EXPO_RUNNER:-}" ]]; then
    CI=1 "${OTA_EXPO_RUNNER}" export --platform ios --output-dir "${INPUT_DIR}" \
      --no-bytecode --dump-assetmap --source-maps >"${stdout_file}" 2>"${stderr_file}"
  else
    CI=1 npx expo export --platform ios --output-dir "${INPUT_DIR}" \
      --no-bytecode --dump-assetmap --source-maps >"${stdout_file}" 2>"${stderr_file}"
  fi
  local rc=$?
  set -e
  [[ ! -s "${stdout_file}" ]] || cat "${stdout_file}"
  [[ ! -s "${stderr_file}" ]] || cat "${stderr_file}" >&2
  return "${rc}"
}

ensure_source_unchanged() {
  local head tree runtime status
  head="$(git -C "${REPO_ROOT}" rev-parse HEAD)"
  tree="$(git -C "${REPO_ROOT}" rev-parse 'HEAD^{tree}')"
  runtime="${MOBILE_RUNTIME_VERSION:-$(runtime_version)}"
  status="$(git -C "${REPO_ROOT}" status --porcelain -- mobile/ packages/shared/)"
  if [[ "${head}" != "${SOURCE_HEAD}" ||
        "${tree}" != "${SOURCE_TREE}" ||
        "${runtime}" != "${SOURCE_RUNTIME}" ||
        "${status}" != "${SOURCE_STATUS}" ]]; then
    echo "✗ OTA source mismatch: HEAD/tree/runtime/working input changed during transaction." >&2
    return 1
  fi
}

verify_artifact() {
  local expected_digest="${1:-}"
  local args=(artifact --input-dir "${INPUT_DIR}" --platform ios)
  if [[ -n "${expected_digest}" ]]; then
    args+=(--expected-digest "${expected_digest}")
  else
    args+=(--not-before-ns "${TRANSACTION_STARTED_NS}")
  fi
  python3 "${VERIFY_SCRIPT}" "${args[@]}" >"${ARTIFACT_JSON}"
}

artifact_digest() {
  python3 - "${ARTIFACT_JSON}" <<'PY'
import json
import sys
print(json.load(open(sys.argv[1], encoding="utf-8"))["artifact_digest"])
PY
}

is_non_retryable() {
  grep -Eiq \
    'Authentication|not authorized|invalid token|runtime version|bundle error|syntax error|Metro encountered|configuration error' \
    "${PUBLISH_ERR}" "${PUBLISH_JSON}"
}

is_safe_precommit_retry() {
  grep -Eiq \
    'Asset processing timed out' \
    "${PUBLISH_ERR}" "${PUBLISH_JSON}"
}

extract_group_id() {
  python3 - "$1" <<'PY'
import json
import re
import sys

payload = json.load(open(sys.argv[1], encoding="utf-8"))
if isinstance(payload, dict):
    payload = payload.get("updates", [])
if not isinstance(payload, list) or len(payload) != 1:
    raise SystemExit(1)
group = payload[0].get("group")
if not isinstance(group, str) or not re.fullmatch(r"[0-9a-fA-F-]{36}", group):
    raise SystemExit(1)
print(group)
PY
}

verify_remote_publish() {
  local group_id
  group_id="$(extract_group_id "${PUBLISH_JSON}")" || {
    echo "✗ published identifier verification failed: structured EAS publish response did not contain one group." >&2
    return 1
  }
  run_eas_capture "${VIEW_JSON}" "${TRANSACTION_ROOT}/view.err" \
    update:view "${group_id}" --json || return $?
  run_eas_capture "${CHANNEL_JSON}" "${TRANSACTION_ROOT}/channel.err" \
    channel:view "${CHANNEL}" --json --non-interactive || return $?
  python3 "${VERIFY_SCRIPT}" publish \
    --publish-json "${PUBLISH_JSON}" \
    --view-json "${VIEW_JSON}" \
    --channel-json "${CHANNEL_JSON}" \
    --channel "${CHANNEL}" \
    --runtime-version "${SOURCE_RUNTIME}" \
    --commit-sha "${SOURCE_HEAD}" \
    --transaction-id "${TRANSACTION_ID}" >"${VERIFIED_JSON}"
}

find_ambiguous_publish() {
  local page=1
  local offset=0
  local limit=50
  local page_file page_count
  printf '[]\n' >"${LOOKUP_JSON}"
  while true; do
    page_file="${TRANSACTION_ROOT}/lookup-page-${page}.json"
    if ! run_eas_capture "${page_file}" "${TRANSACTION_ROOT}/lookup.err" \
        update:list --all --platform ios \
        --runtime-version "${SOURCE_RUNTIME}" --limit "${limit}" \
        --offset "${offset}" --json --non-interactive; then
      echo "✗ OTA outcome is ambiguous and EAS transaction lookup failed; refusing duplicate publish." >&2
      return 2
    fi
    page_count="$(python3 - "${page_file}" "${LOOKUP_JSON}" <<'PY'
import json
import sys
from pathlib import Path

page_path = Path(sys.argv[1])
aggregate_path = Path(sys.argv[2])
try:
    payload = json.loads(page_path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        items = payload.get("currentPage", payload.get("updates"))
    else:
        items = None
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise ValueError("invalid update page")
    aggregate = json.loads(aggregate_path.read_text(encoding="utf-8"))
    if not isinstance(aggregate, list):
        raise ValueError("invalid update aggregate")
except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as error:
    print(f"invalid paginated EAS update:list response: {error}", file=sys.stderr)
    raise SystemExit(2)
aggregate.extend(items)
aggregate_path.write_text(
    json.dumps(aggregate, ensure_ascii=False, separators=(",", ":")) + "\n",
    encoding="utf-8",
)
print(len(items))
PY
    )" || return $?
    if [[ "${page_count}" -lt "${limit}" ]]; then
      break
    fi
    if [[ "${page}" -ge "${OTA_LOOKUP_MAX_PAGES:-20}" ]]; then
      echo "✗ OTA transaction lookup reached the page safety cap before the terminal page; refusing publish." >&2
      return 2
    fi
    page=$((page + 1))
    offset=$((offset + limit))
  done
  python3 "${VERIFY_SCRIPT}" find-transaction \
    --updates-json "${LOOKUP_JSON}" \
    --transaction-id "${TRANSACTION_ID}" \
    --runtime-version "${SOURCE_RUNTIME}" >"${LOOKUP_RESULT}" || return $?
  python3 - "${LOOKUP_RESULT}" <<'PY'
import json
import sys
payload = json.load(open(sys.argv[1], encoding="utf-8"))
if payload.get("found"):
    print(payload["group_id"])
PY
}

find_publish_with_poll() {
  local attempt group
  for ((attempt = 1; attempt <= ${OTA_LOOKUP_ATTEMPTS:-3}; attempt++)); do
    group="$(find_ambiguous_publish)" || return $?
    if [[ -n "${group}" ]]; then
      printf '%s\n' "${group}"
      return 0
    fi
    if [[ "${attempt}" -lt "${OTA_LOOKUP_ATTEMPTS:-3}" ]]; then
      sleep "${OTA_LOOKUP_DELAY_SECONDS:-2}"
    fi
  done
}

publish_existing_artifact() {
  verify_production_native_cohort recheck || return 97
  run_eas_capture "${PUBLISH_JSON}" "${PUBLISH_ERR}" update \
    --channel "${CHANNEL}" --message "${TRANSACTION_MESSAGE}" --platform ios \
    --environment "${ENVIRONMENT}" --input-dir "${INPUT_DIR}" --skip-bundler --json
}

publish_bundled_artifact() {
  verify_production_native_cohort recheck || return 97
  run_eas_capture "${PUBLISH_JSON}" "${PUBLISH_ERR}" update \
    --channel "${CHANNEL}" --message "${TRANSACTION_MESSAGE}" --platform ios \
    --environment "${ENVIRONMENT}" --input-dir "${INPUT_DIR}" --json
}

manifest_transaction_id() {
  python3 - "${MANIFEST_SNAPSHOT_JSON}" <<'PY'
import json
import sys

snapshot = json.loads(sys.argv[1])
payload = snapshot.get("payload") or {}
transaction_id = payload.get("transaction_id")
if isinstance(transaction_id, str):
    print(transaction_id)
PY
}

write_release_manifest() {
  local artifact_evidence="$1"
  local artifact_digest="${2:-}"
  local artifact_json="${3:-}"
  python3 - "${MANIFEST_FILE}" "${MANIFEST_SNAPSHOT_JSON}" \
    "${VERIFY_SCRIPT}" \
    "${CHANNEL}" "${ENVIRONMENT}" "${GROUP_ID}" \
    "${IOS_UPDATE_ID}" "${RELEASE_COMMIT_SHA}" "${SOURCE_TREE}" "${SOURCE_RUNTIME}" \
    "${SOURCE_COMMIT_SHA}" "${MAIN_COMMIT_SHA}" "${MOBILE_TREE_DIGEST}" \
    "${TRANSACTION_ID}" "${artifact_digest}" "${artifact_json}" "${EAS_CLI_ID}" \
    "${artifact_evidence}" <<'PY'
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

(
    path, snapshot_json, verify_script, channel, environment, group_id, update_id,
    commit_sha, source_tree,
    runtime_version, source_commit_sha, main_commit_sha, mobile_tree_digest,
    transaction_id, artifact_digest, artifact_json, eas_cli, artifact_evidence,
) = sys.argv[1:]
manifest_path = Path(path)
snapshot = json.loads(snapshot_json)
previous = snapshot.get("payload") or {}
if not isinstance(previous, dict):
    raise SystemExit("verified manifest snapshot payload is invalid")

previous_active_group = previous.get("active_group_id") or previous.get("group_id")
previous_active_update = previous.get("active_update_id") or previous.get("update_id")
same_transaction_id = previous.get("transaction_id") == transaction_id
same_transaction = (
    same_transaction_id
    and previous_active_group == group_id
    and previous_active_update == update_id
)

if artifact_evidence != "verified_transaction_artifact" and same_transaction_id:
    if not same_transaction:
        raise SystemExit("remote adoption conflicts with the local transaction identity")
    expected_fields = {
        "channel": channel,
        "environment": environment,
        "runtime_version": runtime_version,
        "commit_sha": commit_sha,
        "source_commit_sha": source_commit_sha,
        "main_commit_sha": main_commit_sha,
        "mobile_tree_digest": mobile_tree_digest,
        "source_tree": source_tree,
    }
    for field, expected in expected_fields.items():
        actual = previous.get(field)
        if actual is not None and actual != expected:
            raise SystemExit(f"remote adoption conflicts with local manifest field {field}")

if artifact_evidence == "verified_transaction_artifact":
    if not artifact_digest or not artifact_json:
        raise SystemExit("verified artifact evidence is incomplete")
    artifact = json.loads(Path(artifact_json).read_text(encoding="utf-8"))
    artifact_file_count = artifact.get("file_count")
    artifact_total_bytes = artifact.get("total_bytes")
    published_at = datetime.now(timezone.utc).isoformat()
    previous_group = previous_active_group
    previous_update = previous_active_update
elif same_transaction:
    artifact_digest = previous.get("artifact_digest")
    artifact_file_count = previous.get("artifact_file_count")
    artifact_total_bytes = previous.get("artifact_total_bytes")
    artifact_evidence = previous.get("artifact_evidence") or (
        "verified_transaction_artifact"
        if artifact_digest
        else "unavailable_after_remote_adoption"
    )
    published_at = previous.get("published_at") or datetime.now(timezone.utc).isoformat()
    previous_group = previous.get("previous_known_good_group_id")
    previous_update = previous.get("previous_known_good_update_id")
else:
    artifact_digest = None
    artifact_file_count = None
    artifact_total_bytes = None
    artifact_evidence = "unavailable_after_remote_adoption"
    published_at = datetime.now(timezone.utc).isoformat()
    previous_group = previous_active_group
    previous_update = previous_active_update

payload = {
    "schema_version": 2,
    "status": "published",
    "transaction_id": transaction_id,
    "platform": "ios",
    "channel": channel,
    "environment": environment,
    "runtime_version": runtime_version,
    "group_id": group_id,
    "update_id": update_id,
    "active_group_id": group_id,
    "active_update_id": update_id,
    "commit_sha": commit_sha,
    "source_commit_sha": source_commit_sha,
    "main_commit_sha": main_commit_sha,
    "mobile_tree_digest": mobile_tree_digest,
    "source_tree": source_tree,
    "artifact_digest": artifact_digest,
    "artifact_file_count": artifact_file_count,
    "artifact_total_bytes": artifact_total_bytes,
    "artifact_evidence": artifact_evidence,
    "eas_cli": eas_cli,
    "remote_verification": {"update_view": True, "channel_mapping": True},
    "published_at": published_at,
    "previous_known_good_group_id": previous_group,
    "previous_known_good_update_id": previous_update,
}
sys.path.insert(0, str(Path(verify_script).parent))
from verify_mobile_ota_artifact import replace_manifest_from_snapshot

replace_manifest_from_snapshot(
    manifest_path,
    snapshot=snapshot,
    payload=payload,
    expected_channel=channel,
)
PY
}

write_release_anchor() {
  [[ "${CHANNEL}" == "production" ]] || return 0
  python3 - "${ANCHOR_FILE}" "${RELEASE_COMMIT_SHA}" "${VERIFY_SCRIPT}" <<'PY'
import sys
from pathlib import Path

path_value, commit_sha, verify_script = sys.argv[1:]
sys.path.insert(0, str(Path(verify_script).parent))
from verify_mobile_ota_artifact import replace_private_text_receipt

replace_private_text_receipt(
    Path(path_value),
    commit_sha + "\n",
    label="OTA anchor",
)
PY
}

verified_remote_ids() {
  GROUP_ID="$(python3 - "${VERIFIED_JSON}" <<'PY'
import json, sys
print(json.load(open(sys.argv[1], encoding="utf-8"))["group_id"])
PY
)"
  IOS_UPDATE_ID="$(python3 - "${VERIFIED_JSON}" <<'PY'
import json, sys
print(json.load(open(sys.argv[1], encoding="utf-8"))["update_id"])
PY
)"
}

EAS_CLI_ID="test-runner"
if [[ -z "${OTA_EAS_RUNNER:-}" ]]; then
  EAS_CLI_ID="eas-cli@${EAS_CLI_VERSION}"
fi

prepare_locked_eas_cli || exit $?

echo "==> EAS Update transaction ${TRANSACTION_ID} → channel=${CHANNEL}"
echo "    environment: ${ENVIRONMENT}"
echo "    runtime: ${SOURCE_RUNTIME}"
echo "    source tree: ${SOURCE_TREE:0:12}"
echo "    message: ${MESSAGE}"
echo ""

# Native runtime selection happens before JavaScript starts, so a remote-config
# minimum-build guard cannot protect an incompatible OTA. Prove compatibility
# against the complete eligible production iOS Store cohort before any export
# or EAS update mutation.
verify_production_native_cohort initial || exit $?

# A release transaction may be retried after the remote update and local
# manifest/anchor were committed but a later local audit append failed. Query
# the stable transaction marker before every new publish so that a retry
# adopts exactly one verified remote update instead of publishing it twice.
if [[ "${REUSED_TRANSACTION_ID}" == "1" ]]; then
  PREEXISTING_GROUP="$(find_publish_with_poll)" || exit $?
else
  PREEXISTING_GROUP="$(find_ambiguous_publish)" || exit $?
fi
EXISTING_MANIFEST_TRANSACTION_ID="$(manifest_transaction_id)"
if [[ -z "${PREEXISTING_GROUP}" &&
      "${EXISTING_MANIFEST_TRANSACTION_ID}" == "${TRANSACTION_ID}" ]]; then
  PREEXISTING_GROUP="$(find_publish_with_poll)" || exit $?
  if [[ -z "${PREEXISTING_GROUP}" ]]; then
    record_ota_audit 1 failed ambiguous_remote_outcome "$(ota_elapsed_seconds)"
    echo "✗ Local manifest already records this transaction but EAS lookup found no unique remote update; refusing a duplicate publish." >&2
    exit 1
  fi
fi
if [[ -n "${PREEXISTING_GROUP}" ]]; then
  echo "△ EAS preflight found this exact transaction; verifying and restoring local state without republishing."
  run_eas_capture "${PUBLISH_JSON}" "${PUBLISH_ERR}" \
    update:view "${PREEXISTING_GROUP}" --json || exit $?
  ensure_source_unchanged
  verify_remote_publish
  verified_remote_ids
  write_release_manifest remote_adoption
  write_release_anchor
  record_ota_audit 1 published "" "$(ota_elapsed_seconds)" "${GROUP_ID}" "${IOS_UPDATE_ID}"
  echo "    verified update group: ${GROUP_ID}"
  echo "    verified iOS update: ${IOS_UPDATE_ID}"
  echo "    artifact evidence: remote transaction adopted"
  echo "    release manifest: ${MANIFEST_FILE}"
  echo "✓ 已复用远端 OTA 事务并补齐本地发布状态，未重复推送。"
  exit 0
fi
if [[ "${REUSED_TRANSACTION_ID}" == "1" ]]; then
  record_ota_audit 1 failed needs_reconciliation "$(ota_elapsed_seconds)"
  echo "✗ Reused OTA transaction has no unique remote proof; manual reconciliation is required before any publish." >&2
  exit 1
fi

PUBLISH_OK=0
if [[ "${OTA_FORCE_NO_BYTECODE:-0}" == "1" ]]; then
  run_expo_export_no_bytecode || exit $?
  verify_artifact
  ARTIFACT_DIGEST="$(artifact_digest)"
  if publish_existing_artifact; then
    PUBLISH_OK=1
  elif [[ "$?" == "97" ]]; then
    exit 2
  fi
else
  if publish_bundled_artifact; then
    PUBLISH_OK=1
  elif [[ "$?" == "97" ]]; then
    exit 2
  fi
fi

if [[ "${PUBLISH_OK}" == "1" && ! -f "${INPUT_DIR}/metadata.json" ]]; then
  record_ota_audit 1 failed missing_artifact "$(ota_elapsed_seconds)"
  echo "✗ published identifier verification failed: EAS reported success without a verifiable iOS export artifact." >&2
  exit 1
fi

if [[ "${PUBLISH_OK}" != "1" ]]; then
  if is_non_retryable; then
    record_ota_audit 1 failed non_retryable "$(ota_elapsed_seconds)"
    echo "✗ OTA failed with a non-retryable configuration/auth/runtime error." >&2
    exit 1
  fi
  if [[ ! -f "${INPUT_DIR}/metadata.json" ]]; then
    record_ota_audit 1 failed missing_artifact "$(ota_elapsed_seconds)"
    echo "✗ transient failure left no verifiable export; refusing a second bundle." >&2
    exit 1
  else
    verify_artifact
    ARTIFACT_DIGEST="$(artifact_digest)"
    if [[ -n "${OTA_TEST_AFTER_ARTIFACT_VERIFIED:-}" ]]; then
      "${OTA_TEST_AFTER_ARTIFACT_VERIFIED}" "${INPUT_DIR}"
    fi
    ensure_source_unchanged
    EXISTING_GROUP="$(find_publish_with_poll)" || exit $?
    if [[ -n "${EXISTING_GROUP}" ]]; then
      echo "△ EAS lookup found this exact transaction; verifying it instead of republishing."
      run_eas_capture "${PUBLISH_JSON}" "${PUBLISH_ERR}" \
        update:view "${EXISTING_GROUP}" --json || exit $?
      PUBLISH_OK=1
    else
      if ! is_safe_precommit_retry; then
        record_ota_audit 1 failed ambiguous_remote_outcome "$(ota_elapsed_seconds)"
        echo "✗ OTA outcome remains ambiguous after lookup; refusing a duplicate publish. Re-run with OTA_TRANSACTION_ID=${TRANSACTION_ID} only after reconciling EAS state." >&2
        exit 1
      fi
      echo "△ transient upload failure; retrying the same verified artifact once with --skip-bundler."
      sleep "${OTA_RETRY_DELAY_SECONDS:-1}"
      ensure_source_unchanged
      verify_artifact "${ARTIFACT_DIGEST}"
      if publish_existing_artifact; then
        PUBLISH_OK=1
      elif [[ "$?" == "97" ]]; then
        exit 2
      else
        EXISTING_GROUP="$(find_publish_with_poll)" || exit $?
        if [[ -z "${EXISTING_GROUP}" ]]; then
          record_ota_audit 2 failed retry_exhausted "$(ota_elapsed_seconds)"
          echo "✗ OTA failed after one same-artifact retry and no matching remote transaction was found." >&2
          exit 1
        fi
        echo "△ retry response was ambiguous; EAS lookup found the exact transaction, verifying it without a third publish."
        run_eas_capture "${PUBLISH_JSON}" "${PUBLISH_ERR}" \
          update:view "${EXISTING_GROUP}" --json || exit $?
        PUBLISH_OK=1
      fi
    fi
  fi
fi

ensure_source_unchanged
if [[ -z "${ARTIFACT_DIGEST:-}" ]]; then
  verify_artifact
  ARTIFACT_DIGEST="$(artifact_digest)"
else
  verify_artifact "${ARTIFACT_DIGEST}"
fi
verify_remote_publish

verified_remote_ids
write_release_manifest verified_transaction_artifact "${ARTIFACT_DIGEST}" "${ARTIFACT_JSON}"
write_release_anchor
if [[ -n "${OTA_TEST_AFTER_RECEIPTS_WRITTEN:-}" ]]; then
  "${OTA_TEST_AFTER_RECEIPTS_WRITTEN}"
fi

record_ota_audit 1 published "" "$(ota_elapsed_seconds)" "${GROUP_ID}" "${IOS_UPDATE_ID}"

echo "    verified update group: ${GROUP_ID}"
echo "    verified iOS update: ${IOS_UPDATE_ID}"
echo "    artifact digest: ${ARTIFACT_DIGEST}"
echo "    release manifest: ${MANIFEST_FILE}"
echo "✓ 推送完成。App 回到前台会下载更新，由用户确认后应用。"
fi
