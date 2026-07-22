#!/usr/bin/env bash
# 将已验证的上一组 EAS Update 重新指向指定 channel。
# 默认 dry-run；只有显式 --confirm 才会调用 EAS。

set -euo pipefail

CHANNEL="${1:-production}"
shift || true
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MANIFEST_FILE="${OTA_MANIFEST_FILE:-${REPO_ROOT}/.mobile-release-manifest.json}"
source "${REPO_ROOT}/scripts/release_lock.sh"
TARGET_GROUP_ID="${OTA_ROLLBACK_GROUP_ID:-}"
TARGET_UPDATE_ID="${OTA_ROLLBACK_UPDATE_ID:-}"
CONFIRM=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --confirm)
      CONFIRM=1
      ;;
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
    *)
      echo "✗ 未知参数: $1" >&2
      exit 2
      ;;
  esac
  shift
done

case "${CHANNEL}" in
  production|preview) ;;
  *) echo "✗ 只允许 production 或 preview channel" >&2; exit 2 ;;
esac

if [[ -z "${TARGET_GROUP_ID}" || -z "${TARGET_UPDATE_ID}" ]]; then
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
echo "    target group: ${TARGET_GROUP_ID}"
echo "    target iOS update: ${TARGET_UPDATE_ID}"

if [[ "${CONFIRM}" != "1" ]]; then
  echo "△ dry-run: 未调用 EAS。确认执行请追加 --confirm。"
  exit 0
fi

acquire_release_lock "ota-rollback:${CHANNEL}"

if [[ -n "${OTA_EAS_RUNNER:-}" ]]; then
  "${OTA_EAS_RUNNER}" update:republish \
    --group "${TARGET_GROUP_ID}" \
    --destination-channel "${CHANNEL}" \
    --non-interactive
else
  (cd "${REPO_ROOT}/mobile" && npx eas-cli update:republish \
    --group "${TARGET_GROUP_ID}" \
    --destination-channel "${CHANNEL}" \
    --non-interactive)
fi

python3 - "${MANIFEST_FILE}" "${CHANNEL}" "${TARGET_GROUP_ID}" "${TARGET_UPDATE_ID}" <<'PY'
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

path, channel, target_group_id, target_update_id = sys.argv[1:]
manifest_path = Path(path)
payload = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
payload.update({
    "schema_version": 1,
    "status": "rolled_back",
    "rollback_channel": channel,
    "rollback_target_group_id": target_group_id,
    "rollback_target_update_id": target_update_id,
    "rollback_from_group_id": payload.get("active_group_id") or payload.get("group_id"),
    "rollback_from_update_id": payload.get("active_update_id") or payload.get("update_id"),
    "active_group_id": target_group_id,
    "active_update_id": target_update_id,
    "rolled_back_at": datetime.now(timezone.utc).isoformat(),
})
tmp_path = manifest_path.with_name(f".{manifest_path.name}.tmp")
tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
os.replace(tmp_path, manifest_path)
PY

echo "✓ rollback command completed; manifest status=rolled_back"
