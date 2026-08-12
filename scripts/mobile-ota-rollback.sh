#!/usr/bin/env bash
# Republish a verified prior EAS group. Dry-run unless --confirm is explicit.

set -euo pipefail

CHANNEL="${1:-production}"
shift || true
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERIFY_SCRIPT="${REPO_ROOT}/scripts/verify_mobile_ota_artifact.py"
DEFAULT_MANIFEST_FILE="${REPO_ROOT}/.mobile-release-manifest.${CHANNEL}.json"
if [[ "${CHANNEL}" == "production" ]]; then
  DEFAULT_MANIFEST_FILE="${REPO_ROOT}/.mobile-release-manifest.json"
fi
MANIFEST_FILE="${OTA_MANIFEST_FILE:-${DEFAULT_MANIFEST_FILE}}"
EAS_CLI_VERSION="${OTA_EAS_CLI_VERSION:-21.8.0}"
if [[ ! "${EAS_CLI_VERSION}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "✗ OTA_EAS_CLI_VERSION 必须是精确的 x.y.z 版本。" >&2
  exit 2
fi
source "${REPO_ROOT}/scripts/release_lock.sh"
TARGET_GROUP_ID="${OTA_ROLLBACK_GROUP_ID:-}"
TARGET_UPDATE_ID="${OTA_ROLLBACK_UPDATE_ID:-}"
CONFIRM=0
ROLLBACK_TRANSACTION_ID="${OTA_ROLLBACK_TRANSACTION_ID:-rollback-$(python3 - <<'PY'
import uuid
print(uuid.uuid4())
PY
)}"

if [[ ! "${ROLLBACK_TRANSACTION_ID}" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{5,89}$ ]]; then
  echo "✗ OTA_ROLLBACK_TRANSACTION_ID 格式无效。" >&2
  exit 2
fi
export OTA_ROLLBACK_TRANSACTION_ID="${ROLLBACK_TRANSACTION_ID}"
if [[ ! "${OTA_LOOKUP_ATTEMPTS:-3}" =~ ^[1-9][0-9]*$ ]] ||
   [[ ! "${OTA_LOOKUP_DELAY_SECONDS:-2}" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
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
  production|preview) ;;
  *) echo "✗ 只允许 production 或 preview channel" >&2; exit 2 ;;
esac

if [[ "${CONFIRM}" == "1" ]]; then
  acquire_release_lock "ota-rollback:${CHANNEL}"
fi

# Never overwrite a corrupt operational receipt after mutating EAS, even when
# the rollback source was supplied explicitly.
python3 "${VERIFY_SCRIPT}" manifest \
  --manifest-file "${MANIFEST_FILE}" --allow-missing >/dev/null

if [[ -z "${TARGET_GROUP_ID}" && -n "${TARGET_UPDATE_ID}" ]] ||
   [[ -n "${TARGET_GROUP_ID}" && -z "${TARGET_UPDATE_ID}" ]]; then
  echo "✗ rollback source group/update 必须成对提供。" >&2
  exit 2
fi

if [[ -z "${TARGET_GROUP_ID}" && -z "${TARGET_UPDATE_ID}" ]]; then
  [[ -f "${MANIFEST_FILE}" ]] || {
    echo "✗ 缺少 manifest，无法安全推导上一组已知可用更新: ${MANIFEST_FILE}" >&2
    exit 1
  }
  IFS=$'\t' read -r TARGET_GROUP_ID TARGET_UPDATE_ID < <(python3 - "${MANIFEST_FILE}" <<'PY'
import json
import sys

try:
    with open(sys.argv[1], encoding="utf-8") as handle:
        payload = json.load(handle)
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
cleanup_rollback() {
  if [[ -n "${ROLLBACK_ROOT:-}" &&
        "${ROLLBACK_ROOT##*/}" == reva-mobile-ota-rollback.* &&
        -d "${ROLLBACK_ROOT}" ]]; then
    rm -rf -- "${ROLLBACK_ROOT}"
  fi
  release_release_lock
}
trap cleanup_rollback EXIT

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
    (cd "${REPO_ROOT}/mobile" && CI=1 npx --yes --package \
      "eas-cli@${EAS_CLI_VERSION}" eas "$@") >"${stdout_file}" 2>"${stderr_file}"
  fi
  local rc=$?
  set -e
  [[ ! -s "${stderr_file}" ]] || cat "${stderr_file}" >&2
  return "${rc}"
}

find_rollback_publish_with_poll() {
  local attempt group
  for ((attempt = 1; attempt <= ${OTA_LOOKUP_ATTEMPTS:-3}; attempt++)); do
    run_eas_capture "${LOOKUP_JSON}" "${ROLLBACK_ROOT}/lookup.err" \
      update:list --all --platform ios --runtime-version "${RUNTIME_VERSION}" \
      --limit 25 --json --non-interactive || return 2
    python3 "${VERIFY_SCRIPT}" find-transaction \
      --updates-json "${LOOKUP_JSON}" \
      --transaction-id "${ROLLBACK_TRANSACTION_ID}" \
      --runtime-version "${RUNTIME_VERSION}" >"${LOOKUP_RESULT}" || return $?
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

RUNTIME_VERSION="${OTA_ROLLBACK_RUNTIME_VERSION:-$(python3 - "${MANIFEST_FILE}" "${REPO_ROOT}/mobile/app.json" <<'PY'
import json
import sys
from pathlib import Path

manifest, app = map(Path, sys.argv[1:])
app_payload = json.loads(app.read_text(encoding="utf-8")).get("expo", {})
if manifest.exists():
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    value = payload.get("runtime_version")
else:
    value = None
if not value:
    runtime = app_payload.get("runtimeVersion")
    value = runtime if isinstance(runtime, str) else app_payload.get("version")
print(value or "unknown")
PY
)}"

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

if ! run_eas_capture "${REPUBLISH_JSON}" "${ROLLBACK_ROOT}/republish.err" \
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

python3 - "${MANIFEST_FILE}" "${CHANNEL}" "${TARGET_GROUP_ID}" \
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
    path, channel, source_group_id, source_update_id,
    active_group_id, active_update_id, runtime_version, verified_json, eas_cli,
    rollback_transaction_id,
) = sys.argv[1:]
manifest_path = Path(path)
payload = (
    json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest_path.exists()
    else {}
)
rollback_from_group = payload.get("active_group_id") or payload.get("group_id")
rollback_from_update = payload.get("active_update_id") or payload.get("update_id")
active = json.loads(Path(verified_json).read_text(encoding="utf-8"))
rollback_from_evidence = {
    key: payload[key]
    for key in (
        "transaction_id", "commit_sha", "source_tree", "artifact_digest",
        "artifact_file_count", "artifact_total_bytes", "eas_cli",
        "remote_verification", "published_at",
    )
    if payload.get(key) is not None
}
for key in (
    "transaction_id", "commit_sha", "source_tree", "artifact_digest",
    "artifact_file_count", "artifact_total_bytes", "published_at",
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

echo "    republished active group: ${NEW_GROUP_ID}"
echo "    republished active iOS update: ${NEW_UPDATE_ID}"
echo "✓ rollback republish verified; manifest status=rolled_back"
