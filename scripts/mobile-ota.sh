#!/usr/bin/env bash
# Publish one transaction-local iOS EAS Update artifact, with same-byte retry.

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
VERIFY_SCRIPT="${REPO_ROOT}/scripts/verify_mobile_ota_artifact.py"
ANCHOR_FILE="${OTA_ANCHOR_FILE:-${REPO_ROOT}/.last-ota-commit}"
if [[ ! "${CHANNEL}" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$ ]]; then
  echo "✗ OTA channel 格式无效。" >&2
  exit 2
fi
DEFAULT_MANIFEST_FILE="${REPO_ROOT}/.mobile-release-manifest.${CHANNEL}.json"
if [[ "${CHANNEL}" == "production" ]]; then
  DEFAULT_MANIFEST_FILE="${REPO_ROOT}/.mobile-release-manifest.json"
fi
MANIFEST_FILE="${OTA_MANIFEST_FILE:-${DEFAULT_MANIFEST_FILE}}"
source "${REPO_ROOT}/scripts/release_lock.sh"
acquire_release_lock "ota:${CHANNEL}"

if [[ "${OTA_FORCE_NO_BYTECODE:-0}" != "0" &&
      "${OTA_FORCE_NO_BYTECODE:-0}" != "1" ]]; then
  echo "✗ OTA_FORCE_NO_BYTECODE 只接受 0/1。" >&2
  exit 1
fi
if [[ ! "${OTA_LOOKUP_ATTEMPTS:-3}" =~ ^[1-9][0-9]*$ ]] ||
   [[ ! "${OTA_LOOKUP_DELAY_SECONDS:-2}" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
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
python3 "${VERIFY_SCRIPT}" manifest \
  --manifest-file "${MANIFEST_FILE}" --allow-missing >/dev/null

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
OTA_AUDIT_LOG="${OTA_AUDIT_LOG:-${REPO_ROOT}/.mobile-ota-audit.jsonl}"
TRANSACTION_ID="${OTA_TRANSACTION_ID:-$(python3 - <<'PY'
import uuid
print(uuid.uuid4())
PY
)}"
if [[ ! "${TRANSACTION_ID}" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{5,79}$ ]]; then
  echo "✗ OTA transaction ID 格式无效。" >&2
  exit 2
fi
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

cleanup_mobile_ota() {
  if [[ -n "${TRANSACTION_ROOT:-}" &&
        "${TRANSACTION_ROOT##*/}" == reva-mobile-ota.* &&
        -d "${TRANSACTION_ROOT}" ]]; then
    rm -rf -- "${TRANSACTION_ROOT}"
  fi
  release_release_lock
}
trap cleanup_mobile_ota EXIT

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
import sys
from datetime import datetime, timezone
from pathlib import Path

(
    path, channel, environment, runtime_version, source_commit_sha,
    main_commit_sha, mobile_tree_digest, transaction_id, attempt, result,
    failure_class, duration_seconds, group_id, update_id,
) = sys.argv[1:]
audit_path = Path(path)
audit_path.parent.mkdir(parents=True, exist_ok=True)
fd = os.open(audit_path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
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
os.chmod(audit_path, 0o600)
PY
}

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
    CI=1 npx --yes --package "eas-cli@${EAS_CLI_VERSION}" eas "$@" \
      >"${stdout_file}" 2>"${stderr_file}"
  fi
  local rc=$?
  set -e
  [[ ! -s "${stderr_file}" ]] || cat "${stderr_file}" >&2
  return "${rc}"
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
  if ! run_eas_capture "${LOOKUP_JSON}" "${TRANSACTION_ROOT}/lookup.err" \
      update:list --all --platform ios \
      --runtime-version "${SOURCE_RUNTIME}" --limit 25 --json --non-interactive; then
    echo "✗ OTA outcome is ambiguous and EAS transaction lookup failed; refusing duplicate publish." >&2
    return 2
  fi
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
  run_eas_capture "${PUBLISH_JSON}" "${PUBLISH_ERR}" update \
    --channel "${CHANNEL}" --message "${TRANSACTION_MESSAGE}" --platform ios \
    --environment "${ENVIRONMENT}" --input-dir "${INPUT_DIR}" --skip-bundler --json
}

manifest_transaction_id() {
  python3 - "${MANIFEST_FILE}" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
if path.exists():
    payload = json.loads(path.read_text(encoding="utf-8"))
    transaction_id = payload.get("transaction_id")
    if isinstance(transaction_id, str):
        print(transaction_id)
PY
}

write_release_manifest() {
  local artifact_evidence="$1"
  local artifact_digest="${2:-}"
  local artifact_json="${3:-}"
  python3 - "${MANIFEST_FILE}" "${CHANNEL}" "${ENVIRONMENT}" "${GROUP_ID}" \
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
    path, channel, environment, group_id, update_id, commit_sha, source_tree,
    runtime_version, source_commit_sha, main_commit_sha, mobile_tree_digest,
    transaction_id, artifact_digest, artifact_json, eas_cli, artifact_evidence,
) = sys.argv[1:]
manifest_path = Path(path)
previous = {}
if manifest_path.exists():
    previous = json.loads(manifest_path.read_text(encoding="utf-8"))

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
manifest_path.parent.mkdir(parents=True, exist_ok=True)
tmp_path = manifest_path.with_name(f".{manifest_path.name}.{os.getpid()}.tmp")
fd = os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, "w", encoding="utf-8") as handle:
    json.dump(payload, handle, ensure_ascii=False, indent=2)
    handle.write("\n")
    handle.flush()
    os.fsync(handle.fileno())
os.replace(tmp_path, manifest_path)
os.chmod(manifest_path, 0o600)
PY
}

write_release_anchor() {
  [[ "${CHANNEL}" == "production" ]] || return 0
  python3 - "${ANCHOR_FILE}" "${RELEASE_COMMIT_SHA}" <<'PY'
import os
import sys
from pathlib import Path

path = Path(sys.argv[1])
path.parent.mkdir(parents=True, exist_ok=True)
tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, "w", encoding="utf-8") as handle:
    handle.write(sys.argv[2] + "\n")
    handle.flush()
    os.fsync(handle.fileno())
os.replace(tmp, path)
os.chmod(path, 0o600)
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

echo "==> EAS Update transaction ${TRANSACTION_ID} → channel=${CHANNEL}"
echo "    environment: ${ENVIRONMENT}"
echo "    runtime: ${SOURCE_RUNTIME}"
echo "    source tree: ${SOURCE_TREE:0:12}"
echo "    message: ${MESSAGE}"
echo ""

# A release transaction may be retried after the remote update and local
# manifest/anchor were committed but a later local audit append failed. Query
# the stable transaction marker before every new publish so that a retry
# adopts exactly one verified remote update instead of publishing it twice.
PREEXISTING_GROUP="$(find_ambiguous_publish)" || exit $?
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

PUBLISH_OK=0
if [[ "${OTA_FORCE_NO_BYTECODE:-0}" == "1" ]]; then
  run_expo_export_no_bytecode || exit $?
  verify_artifact
  ARTIFACT_DIGEST="$(artifact_digest)"
  if publish_existing_artifact; then
    PUBLISH_OK=1
  fi
else
  if run_eas_capture "${PUBLISH_JSON}" "${PUBLISH_ERR}" update \
      --channel "${CHANNEL}" --message "${TRANSACTION_MESSAGE}" --platform ios \
      --environment "${ENVIRONMENT}" --input-dir "${INPUT_DIR}" \
      --json; then
    PUBLISH_OK=1
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

record_ota_audit 1 published "" "$(ota_elapsed_seconds)" "${GROUP_ID}" "${IOS_UPDATE_ID}"

echo "    verified update group: ${GROUP_ID}"
echo "    verified iOS update: ${IOS_UPDATE_ID}"
echo "    artifact digest: ${ARTIFACT_DIGEST}"
echo "    release manifest: ${MANIFEST_FILE}"
echo "✓ 推送完成。App 回到前台会下载更新，由用户确认后应用。"
