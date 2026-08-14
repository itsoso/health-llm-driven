#!/bin/bash
# Republish a verified prior EAS group. Dry-run unless --confirm is explicit.

# EAS channel-to-branch mappings live outside this repository and can drift or
# converge. Freeze every network rollback writer before reading argv, resolving
# paths, accessing state, acquiring locks, or invoking a caller-supplied runner.
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  printf '%s\n' '✗ EAS OTA rollback 网络写入已冻结：请走人工发布 Gate。' >&2
  exit 78
fi

if [[ 0 -eq 1 ]]; then
set -euo pipefail

CHANNEL="${1:-production}"

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
source "${REPO_ROOT}/scripts/release_lock.sh"
shift || true
VERIFY_SCRIPT="${REPO_ROOT}/scripts/verify_mobile_ota_artifact.py"
PRODUCTION_STATE_SCRIPT="${REPO_ROOT}/scripts/release_production_state.py"
LOCKED_EAS_HELPER="${REPO_ROOT}/scripts/locked_eas_cli.py"
EAS_CLI_VERSION="${OTA_EAS_CLI_VERSION:-21.8.0}"
if [[ ! "${EAS_CLI_VERSION}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "✗ OTA_EAS_CLI_VERSION 必须是精确的 x.y.z 版本。" >&2
  exit 2
fi
TARGET_GROUP_ID="${OTA_ROLLBACK_GROUP_ID:-}"
TARGET_UPDATE_ID="${OTA_ROLLBACK_UPDATE_ID:-}"
CONFIRM=0
REQUESTED_ROLLBACK_TRANSACTION_ID="${OTA_ROLLBACK_TRANSACTION_ID:-}"
if [[ ! "${OTA_LOOKUP_ATTEMPTS:-3}" =~ ^[1-9][0-9]*$ ]] ||
   [[ ! "${OTA_LOOKUP_DELAY_SECONDS:-2}" =~ ^[0-9]+([.][0-9]+)?$ ]] ||
   [[ ! "${OTA_LOOKUP_MAX_PAGES:-20}" =~ ^[1-9][0-9]*$ ]]; then
  echo "✗ OTA lookup 重试参数无效。" >&2
  exit 2
fi

while [[ $# -gt 0 ]]; do
  case "$1" in
    --confirm) CONFIRM=1 ;;
    --group)
      [[ $# -ge 2 ]] || { echo "✗ --group 需要值" >&2; exit 2; }
      TARGET_GROUP_ID="$2"
      shift
      ;;
    --update-id)
      [[ $# -ge 2 ]] || { echo "✗ --update-id 需要值" >&2; exit 2; }
      TARGET_UPDATE_ID="$2"
      shift
      ;;
    *) echo "✗ 未知参数: $1" >&2; exit 2 ;;
  esac
  shift
done

case "${CHANNEL}" in
  development|preview|rokid-preview) ;;
  *) echo "✗ channel 不在受信非生产 allowlist" >&2; exit 78 ;;
esac

if [[ "${CONFIRM}" == "1" ]]; then
  acquire_release_lock "ota-rollback:${CHANNEL}"
fi

STATE_PATH_ARGS=(
  state-paths --repo-root "${REPO_ROOT}" --channel "${CHANNEL}"
  --scope rollback
)
if [[ "${CONFIRM}" == "1" ]]; then
  STATE_PATH_ARGS+=(--migrate)
else
  STATE_PATH_ARGS+=(--read-only)
fi
[[ -z "${OTA_MANIFEST_FILE:-}" ]] || STATE_PATH_ARGS+=(--manifest-file "${OTA_MANIFEST_FILE}")
STATE_PATHS_JSON="$(python3 "${VERIFY_SCRIPT}" "${STATE_PATH_ARGS[@]}")" || exit $?
IFS=$'\t' read -r MANIFEST_FILE PENDING_FILE < <(
  python3 - "${STATE_PATHS_JSON}" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
values = [payload["manifest_file"], payload["pending_file"]]
if any("\t" in value or "\n" in value for value in values):
    raise SystemExit("OTA state paths must not contain tabs or newlines")
print("\t".join(values))
PY
)

# Never overwrite a corrupt operational receipt after mutating EAS, even when
# the rollback source was supplied explicitly.
MANIFEST_SNAPSHOT_JSON="$(python3 "${VERIFY_SCRIPT}" manifest \
  --manifest-file "${MANIFEST_FILE}" --allow-missing \
  --expected-channel "${CHANNEL}")" || exit $?
readonly MANIFEST_SNAPSHOT_JSON

if [[ -z "${TARGET_GROUP_ID}" && -n "${TARGET_UPDATE_ID}" ]] ||
   [[ -n "${TARGET_GROUP_ID}" && -z "${TARGET_UPDATE_ID}" ]]; then
  echo "✗ rollback source group/update 必须成对提供。" >&2
  exit 2
fi

if [[ -z "${TARGET_GROUP_ID}" && -z "${TARGET_UPDATE_ID}" ]]; then
  MANIFEST_EXISTS="$(python3 - "${MANIFEST_SNAPSHOT_JSON}" <<'PY'
import json
import sys

print("1" if json.loads(sys.argv[1]).get("exists") else "0")
PY
)"
  [[ "${MANIFEST_EXISTS}" == "1" ]] || {
    echo "✗ 缺少 manifest，无法安全推导上一组已知可用更新: ${MANIFEST_FILE}" >&2
    exit 1
  }
  IFS=$'\t' read -r TARGET_GROUP_ID TARGET_UPDATE_ID < <(python3 - "${MANIFEST_SNAPSHOT_JSON}" <<'PY'
import json
import sys

try:
    payload = json.loads(sys.argv[1]).get("payload") or {}
except (OSError, ValueError) as exc:
    raise SystemExit(f"manifest invalid: {exc}")
print(
    f"{payload.get('previous_known_good_group_id') or ''}\t"
    f"{payload.get('previous_known_good_update_id') or ''}"
)
PY
  )
fi

if [[ -z "${TARGET_GROUP_ID}" || -z "${TARGET_UPDATE_ID}" ]]; then
  echo "✗ manifest 没有 previous_known_good group/update，当前没有可安全回滚的目标" >&2
  exit 1
fi

UUID_PATTERN='^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
[[ "${TARGET_GROUP_ID}" =~ ${UUID_PATTERN} ]] || { echo "✗ 无效的目标 EAS group ID" >&2; exit 2; }
[[ "${TARGET_UPDATE_ID}" =~ ${UUID_PATTERN} ]] || { echo "✗ 无效的目标 iOS update ID" >&2; exit 2; }

echo "==> Mobile OTA rollback"
echo "    channel: ${CHANNEL}"
echo "    source group: ${TARGET_GROUP_ID}"
echo "    source iOS update: ${TARGET_UPDATE_ID}"

if [[ "${CONFIRM}" != "1" ]]; then
  echo "△ dry-run: 未调用 EAS。确认执行请追加 --confirm。"
  exit 0
fi

ROLLBACK_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/reva-mobile-ota-rollback.XXXXXX")"
chmod 700 "${ROLLBACK_ROOT}"
EAS_TOOL_WORKSPACE=""
EAS_BINARY=""
cleanup_rollback() {
  if [[ -n "${EAS_TOOL_WORKSPACE:-}" ]]; then
    python3 "${LOCKED_EAS_HELPER}" cleanup "${EAS_TOOL_WORKSPACE}" || true
    EAS_TOOL_WORKSPACE=""
  fi
  if [[ -n "${ROLLBACK_ROOT:-}" &&
        "${ROLLBACK_ROOT##*/}" == reva-mobile-ota-rollback.* &&
        -d "${ROLLBACK_ROOT}" ]]; then
    rm -rf -- "${ROLLBACK_ROOT}"
  fi
  release_release_lock
}
trap cleanup_rollback EXIT

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

REPUBLISH_JSON="${ROLLBACK_ROOT}/republish.json"
SOURCE_VIEW_JSON="${ROLLBACK_ROOT}/source-view.json"
VIEW_JSON="${ROLLBACK_ROOT}/view.json"
CHANNEL_JSON="${ROLLBACK_ROOT}/channel.json"
VERIFIED_JSON="${ROLLBACK_ROOT}/verified.json"
LOOKUP_JSON="${ROLLBACK_ROOT}/lookup.json"
LOOKUP_RESULT="${ROLLBACK_ROOT}/lookup-result.json"

run_eas_capture() {
  local stdout_file="$1"
  local stderr_file="$2"
  shift 2
  set +e
  if [[ -n "${OTA_EAS_RUNNER:-}" ]]; then
    "${OTA_EAS_RUNNER}" "$@" >"${stdout_file}" 2>"${stderr_file}"
  else
    (cd "${REPO_ROOT}/mobile" && CI=1 "${EAS_BINARY}" "$@") \
      >"${stdout_file}" 2>"${stderr_file}"
  fi
  local rc=$?
  set -e
  [[ ! -s "${stderr_file}" ]] || cat "${stderr_file}" >&2
  return "${rc}"
}

prepare_locked_eas_cli || exit $?

find_rollback_publish_with_poll() {
  local attempt group
  for ((attempt = 1; attempt <= ${OTA_LOOKUP_ATTEMPTS:-3}; attempt++)); do
    find_rollback_publish || return $?
    group="$(python3 - "${LOOKUP_RESULT}" <<'PY'
import json, sys
payload = json.load(open(sys.argv[1], encoding="utf-8"))
print(payload.get("group_id") or "")
PY
)"
    if [[ -n "${group}" ]]; then
      printf '%s\n' "${group}"
      return 0
    fi
    if [[ "${attempt}" -lt "${OTA_LOOKUP_ATTEMPTS:-3}" ]]; then
      sleep "${OTA_LOOKUP_DELAY_SECONDS:-2}"
    fi
  done
}

find_rollback_publish() {
  local page=1
  local offset=0
  local limit=50
  local page_file page_count
  printf '[]\n' >"${LOOKUP_JSON}"
  while true; do
    page_file="${ROLLBACK_ROOT}/lookup-page-${page}.json"
    if ! run_eas_capture "${page_file}" "${ROLLBACK_ROOT}/lookup.err" \
        update:list --all --platform ios --runtime-version "${RUNTIME_VERSION}" \
        --limit "${limit}" --offset "${offset}" --json --non-interactive; then
      echo "✗ rollback transaction lookup failed; refusing duplicate republish." >&2
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
      echo "✗ rollback transaction lookup reached the page safety cap before the terminal page; refusing republish." >&2
      return 2
    fi
    page=$((page + 1))
    offset=$((offset + limit))
  done
    python3 "${VERIFY_SCRIPT}" find-transaction \
      --updates-json "${LOOKUP_JSON}" \
      --transaction-id "${ROLLBACK_TRANSACTION_ID}" \
      --runtime-version "${RUNTIME_VERSION}" >"${LOOKUP_RESULT}" || return $?
}

RUNTIME_VERSION="${OTA_ROLLBACK_RUNTIME_VERSION:-$(python3 - "${MANIFEST_SNAPSHOT_JSON}" "${REPO_ROOT}/mobile/app.json" <<'PY'
import json
import sys
from pathlib import Path

snapshot_json, app_value = sys.argv[1:]
app = Path(app_value)
app_payload = json.loads(app.read_text(encoding="utf-8")).get("expo", {})
payload = json.loads(snapshot_json).get("payload") or {}
value = payload.get("runtime_version")
if not value:
    runtime = app_payload.get("runtimeVersion")
    value = runtime if isinstance(runtime, str) else app_payload.get("version")
print(value or "unknown")
PY
)}"

ROLLBACK_FROM_IDENTITY="$(python3 - "${MANIFEST_SNAPSHOT_JSON}" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1]).get("payload") or {}
print(
    f"{payload.get('active_group_id') or payload.get('group_id') or ''}|"
    f"{payload.get('active_update_id') or payload.get('update_id') or ''}"
)
PY
)"
IFS='|' read -r ROLLBACK_FROM_GROUP_ID ROLLBACK_FROM_UPDATE_ID \
  <<<"${ROLLBACK_FROM_IDENTITY}"

prepare_rollback_pending() {
  python3 - "${PENDING_FILE}" "${MANIFEST_FILE}" \
    "${MANIFEST_SNAPSHOT_JSON}" "${CHANNEL}" \
    "${RUNTIME_VERSION}" "${TARGET_GROUP_ID}" "${TARGET_UPDATE_ID}" \
    "${ROLLBACK_FROM_GROUP_ID}" "${ROLLBACK_FROM_UPDATE_ID}" \
    "${REQUESTED_ROLLBACK_TRANSACTION_ID}" <<'PY'
import json
import os
import re
import stat
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

(
    pending_value, manifest_value, manifest_snapshot_json, channel, runtime_version,
    source_group_id, source_update_id, rollback_from_group_id,
    rollback_from_update_id, requested_transaction_id,
) = sys.argv[1:]
pending_path = Path(pending_value).expanduser().absolute()
manifest_path = Path(manifest_value).expanduser().absolute()
manifest_snapshot = json.loads(manifest_snapshot_json)
manifest = manifest_snapshot.get("payload") or {}
if not isinstance(manifest, dict):
    raise SystemExit("verified manifest snapshot payload is invalid")
manifest_fingerprint = manifest_snapshot.get("sha256") or "missing"
manifest_identity = manifest_snapshot.get("identity")
if pending_path.resolve(strict=False) == manifest_path.resolve(strict=False):
    raise SystemExit("rollback pending receipt must be distinct from the manifest")
parent = pending_path.parent
flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
try:
    parent_fd = os.open(parent, flags)
except OSError as error:
    raise SystemExit(f"unsafe rollback pending parent: {parent}: {error}") from error

name = pending_path.name
transaction_pattern = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{5,89}")
max_receipt_bytes = 64 * 1024

def open_payload():
    read_flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    read_flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(name, read_flags, dir_fd=parent_fd)
    except FileNotFoundError:
        raise
    try:
        metadata = os.fstat(fd)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_nlink != 1
            or metadata.st_uid != os.getuid()
        ):
            raise OSError(
                "receipt must be a current-owner 0600 single-link regular file"
            )
        if metadata.st_size > max_receipt_bytes:
            raise OSError("receipt size is too large")
        chunks = []
        remaining = max_receipt_bytes + 1
        while remaining > 0:
            chunk = os.read(fd, min(64 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        if len(raw) > max_receipt_bytes:
            raise OSError("receipt size is too large")
        final_metadata = os.fstat(fd)
        stable_fields = (
            "st_dev", "st_ino", "st_mode", "st_uid", "st_nlink", "st_size",
            "st_mtime_ns", "st_ctime_ns",
        )
        if any(
            getattr(metadata, field) != getattr(final_metadata, field)
            for field in stable_fields
        ):
            raise OSError("receipt changed while reading")
        current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if (current.st_dev, current.st_ino) != (
            final_metadata.st_dev,
            final_metadata.st_ino,
        ):
            raise OSError("receipt changed while reading")
        payload = json.loads(raw.decode("utf-8", errors="strict"))
    except (OSError, UnicodeError, ValueError) as error:
        raise OSError(f"receipt JSON is invalid: {error}") from error
    finally:
        os.close(fd)
    if not isinstance(payload, dict):
        raise OSError("receipt JSON must be an object")
    return payload, final_metadata

try:
    try:
        payload, pending_metadata = open_payload()
    except FileNotFoundError:
        payload = None
        pending_metadata = None
    if payload is not None:
        transaction_id = payload.get("transaction_id")
        completed = (
            manifest.get("status") == "rolled_back"
            and manifest.get("rollback_transaction_id") == transaction_id
            and manifest.get("rollback_source_group_id") == source_group_id
            and manifest.get("rollback_source_update_id") == source_update_id
            and manifest.get("runtime_version") == runtime_version
            and manifest.get("channel") == channel
        )
        if completed:
            print(f"{transaction_id}|completed")
            raise SystemExit(0)
        expected = {
            "schema_version": 1,
            "channel": channel,
            "runtime_version": runtime_version,
            "source_group_id": source_group_id,
            "source_update_id": source_update_id,
            "rollback_from_group_id": rollback_from_group_id or None,
            "rollback_from_update_id": rollback_from_update_id or None,
            "manifest_fingerprint": manifest_fingerprint,
        }
        if not isinstance(transaction_id, str) or not transaction_pattern.fullmatch(
            transaction_id
        ):
            raise OSError("receipt transaction ID is invalid")
        if requested_transaction_id and requested_transaction_id != transaction_id:
            raise OSError("requested transaction conflicts with pending receipt")
        for key, value in expected.items():
            if payload.get(key) != value:
                raise OSError(f"receipt identity mismatch: {key}")
        if manifest_identity is not None and (
            manifest_identity.get("device"),
            manifest_identity.get("inode"),
        ) == (pending_metadata.st_dev, pending_metadata.st_ino):
            raise OSError("pending receipt and manifest must use distinct inodes")
        print(f"{transaction_id}|reused")
        raise SystemExit(0)

    transaction_id = requested_transaction_id or f"rollback-{uuid.uuid4()}"
    if not transaction_pattern.fullmatch(transaction_id):
        raise OSError("transaction ID format is invalid")
    payload = {
        "schema_version": 1,
        "status": "pending",
        "transaction_id": transaction_id,
        "channel": channel,
        "runtime_version": runtime_version,
        "source_group_id": source_group_id,
        "source_update_id": source_update_id,
        "rollback_from_group_id": rollback_from_group_id or None,
        "rollback_from_update_id": rollback_from_update_id or None,
        "manifest_fingerprint": manifest_fingerprint,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    encoded_payload = (
        json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n"
    ).encode("utf-8")
    if len(encoded_payload) > max_receipt_bytes:
        raise OSError("receipt size is too large")
    temp_name = f".{name}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
    write_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    write_flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(temp_name, write_flags, 0o600, dir_fd=parent_fd)
    try:
        remaining = memoryview(encoded_payload)
        while remaining:
            written = os.write(fd, remaining)
            if written <= 0:
                raise OSError("receipt write made no progress")
            remaining = remaining[written:]
        os.fsync(fd)
        os.close(fd)
        fd = -1
        os.link(
            temp_name,
            name,
            src_dir_fd=parent_fd,
            dst_dir_fd=parent_fd,
            follow_symlinks=False,
        )
        os.unlink(temp_name, dir_fd=parent_fd)
        os.fsync(parent_fd)
    except BaseException:
        if fd >= 0:
            os.close(fd)
        try:
            os.unlink(temp_name, dir_fd=parent_fd)
        except FileNotFoundError:
            pass
        raise
    print(f"{transaction_id}|fresh")
except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as error:
    print(f"unsafe rollback pending receipt: {pending_path}: {error}", file=sys.stderr)
    raise SystemExit(1)
finally:
    os.close(parent_fd)
PY
}

clear_rollback_pending() {
  python3 - "${PENDING_FILE}" "${ROLLBACK_TRANSACTION_ID}" <<'PY'
import json
import os
import stat
import sys
import uuid
from pathlib import Path

path = Path(sys.argv[1]).expanduser().absolute()
expected_transaction_id = sys.argv[2]
max_receipt_bytes = 64 * 1024
parent_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
parent_flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
read_flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
read_flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
parent_fd = -1
fd = -1
quarantine_fd = -1
quarantine_name = None
quarantine_has_entry = False
try:
    parent_fd = os.open(path.parent, parent_flags)
    fd = os.open(path.name, read_flags, dir_fd=parent_fd)
    metadata = os.fstat(fd)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or metadata.st_nlink != 1
        or metadata.st_uid != os.getuid()
    ):
        raise OSError(
            "receipt must be a current-owner 0600 single-link regular file"
        )
    if metadata.st_size > max_receipt_bytes:
        raise OSError("receipt size is too large")
    chunks = []
    remaining = max_receipt_bytes + 1
    while remaining > 0:
        chunk = os.read(fd, min(64 * 1024, remaining))
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    raw = b"".join(chunks)
    if len(raw) > max_receipt_bytes:
        raise OSError("receipt size is too large")
    final_metadata = os.fstat(fd)
    stable_fields = (
        "st_dev", "st_ino", "st_mode", "st_uid", "st_nlink", "st_size",
        "st_mtime_ns", "st_ctime_ns",
    )
    if any(
        getattr(metadata, field) != getattr(final_metadata, field)
        for field in stable_fields
    ):
        raise OSError("rollback pending receipt changed while reading")
    current = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
    if (current.st_dev, current.st_ino) != (
        final_metadata.st_dev,
        final_metadata.st_ino,
    ):
        raise OSError("rollback pending receipt changed while reading")
    payload = json.loads(raw.decode("utf-8", errors="strict"))
    if not isinstance(payload, dict):
        raise ValueError("receipt JSON must be an object")
    if payload.get("transaction_id") != expected_transaction_id:
        raise OSError("rollback pending transaction changed")

    quarantine_name = f".{path.name}.clear.{os.getpid()}.{uuid.uuid4().hex}"
    old_umask = os.umask(0o077)
    try:
        os.mkdir(quarantine_name, 0o700, dir_fd=parent_fd)
    finally:
        os.umask(old_umask)
    quarantine_fd = os.open(quarantine_name, parent_flags, dir_fd=parent_fd)
    quarantine_metadata = os.fstat(quarantine_fd)
    if (
        not stat.S_ISDIR(quarantine_metadata.st_mode)
        or stat.S_IMODE(quarantine_metadata.st_mode) != 0o700
        or quarantine_metadata.st_uid != os.getuid()
    ):
        raise OSError("rollback pending quarantine is unsafe")
    quarantine_entry = path.name
    os.rename(
        path.name,
        quarantine_entry,
        src_dir_fd=parent_fd,
        dst_dir_fd=quarantine_fd,
    )
    quarantine_has_entry = True
    os.fsync(quarantine_fd)
    os.fsync(parent_fd)
    os.close(fd)
    fd = -1
    moved_fd = os.open(quarantine_entry, read_flags, dir_fd=quarantine_fd)
    try:
        moved_metadata = os.fstat(moved_fd)
        # rename(2) may legitimately advance ctime, but every other identity,
        # safety, size, and content-relevant field must still match the file
        # that was verified before quarantine.
        if any(
            getattr(final_metadata, field) != getattr(moved_metadata, field)
            for field in stable_fields
            if field != "st_ctime_ns"
        ):
            raise OSError("rollback pending receipt changed before quarantine")
        moved_chunks = []
        moved_remaining = max_receipt_bytes + 1
        while moved_remaining > 0:
            chunk = os.read(moved_fd, min(64 * 1024, moved_remaining))
            if not chunk:
                break
            moved_chunks.append(chunk)
            moved_remaining -= len(chunk)
        moved_raw = b"".join(moved_chunks)
        moved_final = os.fstat(moved_fd)
        if any(
            getattr(moved_metadata, field) != getattr(moved_final, field)
            for field in stable_fields
        ):
            raise OSError("rollback pending receipt changed in quarantine")
        if len(moved_raw) > max_receipt_bytes or moved_raw != raw:
            raise OSError("rollback pending receipt content changed in quarantine")
    finally:
        os.close(moved_fd)
    quarantined = os.stat(
        quarantine_entry,
        dir_fd=quarantine_fd,
        follow_symlinks=False,
    )
    if (quarantined.st_dev, quarantined.st_ino) != (
        final_metadata.st_dev,
        final_metadata.st_ino,
    ):
        raise OSError("rollback pending receipt changed before removal")
    os.unlink(quarantine_entry, dir_fd=quarantine_fd)
    quarantine_has_entry = False
    os.fsync(quarantine_fd)
    os.close(quarantine_fd)
    quarantine_fd = -1
    os.rmdir(quarantine_name, dir_fd=parent_fd)
    quarantine_name = None
    os.fsync(parent_fd)
except (OSError, UnicodeError, ValueError) as error:
    print(f"unsafe rollback pending receipt: {path}: {error}", file=sys.stderr)
    raise SystemExit(1)
finally:
    if fd >= 0:
        os.close(fd)
    if quarantine_fd >= 0:
        os.close(quarantine_fd)
    if quarantine_name is not None and not quarantine_has_entry:
        os.rmdir(quarantine_name, dir_fd=parent_fd)
    if parent_fd >= 0:
        os.close(parent_fd)
PY
}

prove_completed_pending_against_live_eas() {
  local active_group active_update active_runtime live_identity
  IFS=$'\t' read -r active_group active_update active_runtime < <(
    python3 - "${MANIFEST_SNAPSHOT_JSON}" <<'PY'
import json
import re
import sys

payload = json.loads(sys.argv[1]).get("payload") or {}
group_id = payload.get("active_group_id") or payload.get("group_id")
update_id = payload.get("active_update_id") or payload.get("update_id")
runtime = payload.get("runtime_version")
uuid = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.IGNORECASE,
)
if (
    not isinstance(group_id, str)
    or uuid.fullmatch(group_id) is None
    or not isinstance(update_id, str)
    or uuid.fullmatch(update_id) is None
    or not isinstance(runtime, str)
    or not runtime
    or len(runtime) > 64
    or "\t" in runtime
    or "\n" in runtime
):
    raise SystemExit("completed rollback manifest has an invalid live identity")
print(f"{group_id}\t{update_id}\t{runtime}")
PY
  ) || return $?

  run_eas_capture "${VIEW_JSON}" "${ROLLBACK_ROOT}/completed-view.err" \
    update:view "${active_group}" --json || return $?
  python3 "${VERIFY_SCRIPT}" source \
    --view-json "${VIEW_JSON}" \
    --group-id "${active_group}" \
    --update-id "${active_update}" \
    --runtime-version "${active_runtime}" \
    >"${ROLLBACK_ROOT}/completed-source-verified.json" || return $?
  run_eas_capture "${CHANNEL_JSON}" "${ROLLBACK_ROOT}/completed-channel.err" \
    channel:view "${CHANNEL}" --json --non-interactive || return $?
  live_identity="$(
    python3 "${PRODUCTION_STATE_SCRIPT}" mobile-evidence \
      "${active_runtime}" "${CHANNEL_JSON}"
  )" || return $?
  python3 - "${live_identity}" "${active_group}" "${active_update}" <<'PY'
import json
import sys

identity = json.loads(sys.argv[1])
if (
    identity.get("group_id") != sys.argv[2]
    or identity.get("update_id") != sys.argv[3]
):
    raise SystemExit(
        "completed rollback manifest no longer matches the live EAS channel"
    )
PY
}

# The manifest/flags provide a pair, while EAS republishes by group. Prove the
# selected iOS update actually belongs to that group before the mutation.
run_eas_capture "${SOURCE_VIEW_JSON}" "${ROLLBACK_ROOT}/source-view.err" \
  update:view "${TARGET_GROUP_ID}" --json || {
    echo "✗ rollback source group could not be verified; republish was not called." >&2
    exit 1
  }
if [[ ! -s "${SOURCE_VIEW_JSON}" ]]; then
  echo "✗ rollback source update:view returned no structured JSON; republish was not called." >&2
  exit 1
fi
python3 "${VERIFY_SCRIPT}" source \
  --view-json "${SOURCE_VIEW_JSON}" \
  --group-id "${TARGET_GROUP_ID}" \
  --update-id "${TARGET_UPDATE_ID}" \
  --runtime-version "${RUNTIME_VERSION}" >"${ROLLBACK_ROOT}/source-verified.json" || {
    echo "✗ rollback source group/update verification failed; republish was not called." >&2
    exit 1
  }

PENDING_IDENTITY="$(prepare_rollback_pending)" || exit $?
IFS='|' read -r ROLLBACK_TRANSACTION_ID PENDING_STATE <<<"${PENDING_IDENTITY}"
export OTA_ROLLBACK_TRANSACTION_ID="${ROLLBACK_TRANSACTION_ID}"
if [[ "${PENDING_STATE}" == "completed" ]]; then
  if ! prove_completed_pending_against_live_eas; then
    echo "✗ completed rollback cannot be re-proven against live EAS; pending receipt retained." >&2
    exit 1
  fi
  clear_rollback_pending
  echo "✓ rollback was already recorded; finalized pending receipt without republishing."
  exit 0
fi

if [[ "${PENDING_STATE}" == "reused" ]]; then
  RECOVERED_GROUP="$(find_rollback_publish_with_poll)" || exit $?
  if [[ -z "${RECOVERED_GROUP}" ]]; then
    echo "✗ pending rollback transaction has no unique remote proof; manual reconciliation is required before any republish." >&2
    exit 1
  fi
  echo "△ adopting the unique remote rollback from the durable pending transaction."
  run_eas_capture "${REPUBLISH_JSON}" "${ROLLBACK_ROOT}/recovered-view.err" \
    update:view "${RECOVERED_GROUP}" --json || exit $?
elif ! run_eas_capture "${REPUBLISH_JSON}" "${ROLLBACK_ROOT}/republish.err" \
    update:republish --group "${TARGET_GROUP_ID}" \
    --destination-channel "${CHANNEL}" --platform ios \
    --message "[tx:${ROLLBACK_TRANSACTION_ID}] rollback republish verified iOS source" \
    --json --non-interactive; then
  RECOVERED_GROUP="$(find_rollback_publish_with_poll)" || exit $?
  if [[ -z "${RECOVERED_GROUP}" ]]; then
    echo "✗ rollback outcome is ambiguous; manifest unchanged. Reconcile EAS with transaction ${ROLLBACK_TRANSACTION_ID} before retrying." >&2
    exit 1
  fi
  echo "△ rollback response was lost; adopting the unique verified transaction."
  run_eas_capture "${REPUBLISH_JSON}" "${ROLLBACK_ROOT}/recovered-view.err" \
    update:view "${RECOVERED_GROUP}" --json || exit $?
fi

NEW_GROUP_ID="$(python3 - "${REPUBLISH_JSON}" <<'PY'
import json, re, sys
payload = json.load(open(sys.argv[1], encoding="utf-8"))
if not isinstance(payload, list) or len(payload) != 1:
    raise SystemExit(1)
group = payload[0].get("group")
if not isinstance(group, str) or not re.fullmatch(r"[0-9a-fA-F-]{36}", group):
    raise SystemExit(1)
print(group)
PY
)" || {
  echo "✗ structured EAS republish response is invalid; manifest was not changed." >&2
  exit 1
}
run_eas_capture "${VIEW_JSON}" "${ROLLBACK_ROOT}/view.err" \
  update:view "${NEW_GROUP_ID}" --json || exit $?
run_eas_capture "${CHANNEL_JSON}" "${ROLLBACK_ROOT}/channel.err" \
  channel:view "${CHANNEL}" --json --non-interactive || exit $?
python3 "${VERIFY_SCRIPT}" publish \
  --publish-json "${REPUBLISH_JSON}" \
  --view-json "${VIEW_JSON}" \
  --channel-json "${CHANNEL_JSON}" \
  --channel "${CHANNEL}" \
  --runtime-version "${RUNTIME_VERSION}" \
  --transaction-id "${ROLLBACK_TRANSACTION_ID}" >"${VERIFIED_JSON}"

NEW_GROUP_ID="$(python3 - "${VERIFIED_JSON}" <<'PY'
import json, sys
print(json.load(open(sys.argv[1], encoding="utf-8"))["group_id"])
PY
)"
NEW_UPDATE_ID="$(python3 - "${VERIFIED_JSON}" <<'PY'
import json, sys
print(json.load(open(sys.argv[1], encoding="utf-8"))["update_id"])
PY
)"
EAS_CLI_ID="test-runner"
if [[ -z "${OTA_EAS_RUNNER:-}" ]]; then
  EAS_CLI_ID="eas-cli@${EAS_CLI_VERSION}"
fi

python3 - "${MANIFEST_FILE}" "${MANIFEST_SNAPSHOT_JSON}" \
  "${VERIFY_SCRIPT}" "${CHANNEL}" "${TARGET_GROUP_ID}" \
  "${TARGET_UPDATE_ID}" "${NEW_GROUP_ID}" "${NEW_UPDATE_ID}" \
  "${RUNTIME_VERSION}" "${VERIFIED_JSON}" "${EAS_CLI_ID}" \
  "${ROLLBACK_TRANSACTION_ID}" <<'PY'
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

(
    path, manifest_snapshot_json, verify_script, channel,
    source_group_id, source_update_id,
    active_group_id, active_update_id, runtime_version, verified_json, eas_cli,
    rollback_transaction_id,
) = sys.argv[1:]
manifest_path = Path(path)
payload = json.loads(manifest_snapshot_json).get("payload") or {}
if not isinstance(payload, dict):
    raise SystemExit("verified manifest snapshot payload is invalid")
rollback_from_group = payload.get("active_group_id") or payload.get("group_id")
rollback_from_update = payload.get("active_update_id") or payload.get("update_id")
active = json.loads(Path(verified_json).read_text(encoding="utf-8"))
rollback_from_evidence = {
    key: payload[key]
    for key in (
        "transaction_id", "commit_sha", "source_tree", "artifact_digest",
        "artifact_file_count", "artifact_total_bytes", "artifact_evidence", "eas_cli",
        "remote_verification", "published_at",
    )
    if payload.get(key) is not None
}
for key in (
    "transaction_id", "commit_sha", "source_tree", "artifact_digest",
    "artifact_file_count", "artifact_total_bytes", "artifact_evidence", "published_at",
    "remote_verification",
):
    payload.pop(key, None)
payload.update({
    "schema_version": 2,
    "status": "rolled_back",
    "platform": "ios",
    "channel": channel,
    "environment": channel,
    "runtime_version": runtime_version,
    "rollback_channel": channel,
    "rollback_transaction_id": rollback_transaction_id,
    "rollback_source_group_id": source_group_id,
    "rollback_source_update_id": source_update_id,
    # Legacy aliases retain their original meaning: the selected source artifact.
    "rollback_target_group_id": source_group_id,
    "rollback_target_update_id": source_update_id,
    "rollback_from_group_id": rollback_from_group,
    "rollback_from_update_id": rollback_from_update,
    "group_id": active_group_id,
    "update_id": active_update_id,
    "active_group_id": active_group_id,
    "active_update_id": active_update_id,
    "previous_known_good_group_id": source_group_id,
    "previous_known_good_update_id": source_update_id,
    "commit_sha": active.get("commit_sha"),
    "eas_cli": eas_cli,
    "rollback_from_evidence": rollback_from_evidence,
    "rollback_source_verification": {
        "update_view": True,
        "group_update_runtime": True,
    },
    "rollback_remote_verification": {"update_view": True, "channel_mapping": True},
    "rolled_back_at": datetime.now(timezone.utc).isoformat(),
})
if not isinstance(payload.get("commit_sha"), str) or not re.fullmatch(
    r"[0-9a-f]{40}", payload["commit_sha"]
):
    payload.pop("commit_sha", None)
sys.path.insert(0, str(Path(verify_script).parent))
from verify_mobile_ota_artifact import replace_manifest_from_snapshot

replace_manifest_from_snapshot(
    manifest_path,
    snapshot=json.loads(manifest_snapshot_json),
    payload=payload,
    expected_channel=channel,
)
PY

clear_rollback_pending

echo "    republished active group: ${NEW_GROUP_ID}"
echo "    republished active iOS update: ${NEW_UPDATE_ID}"
echo "✓ rollback republish verified; manifest status=rolled_back"
fi
