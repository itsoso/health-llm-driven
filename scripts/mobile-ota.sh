#!/usr/bin/env bash
# OTA 推送 mobile/ JS bundle 到已安装的小巴
#
# 何时用:
#   - 改了 .ts/.tsx/.js (JS 逻辑/UI/RN 组件) → 用本脚本, 30 秒内到设备
#   - 改了 native (Info.plist / Pods / app.json plugins / SDK 升级) → 必须 eas build
#
# 用法:
#   ./scripts/mobile-ota.sh                # 推到 production channel (默认)
#   ./scripts/mobile-ota.sh preview        # 推到 preview
#   ./scripts/mobile-ota.sh production "fix briefing pinning"
#   ./scripts/mobile-ota.sh rokid-production "Rokid diagnostics"

set -euo pipefail

CHANNEL="${1:-production}"
MESSAGE="${2:-$(git log -1 --pretty=format:'%s')}"
ENVIRONMENT="${CHANNEL}"

case "${CHANNEL}" in
  rokid-production)
    ENVIRONMENT="production"
    ;;
  rokid-preview)
    ENVIRONMENT="preview"
    ;;
esac

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ANCHOR_FILE="${OTA_ANCHOR_FILE:-${REPO_ROOT}/.last-ota-commit}"
MANIFEST_FILE="${OTA_MANIFEST_FILE:-${REPO_ROOT}/.mobile-release-manifest.json}"

# ── 发版前置守卫(2026-07-11 评审加固):OTA 打的是**工作树**,不是 HEAD ──
# 两类历史事故:① 脏树 WIP 泄进生产 bundle;② 落后 origin/main 的树整包回滚他人已上线工作。
# 机械拦截,不再靠纪律。逃生口:OTA_ALLOW_DIRTY=1(仅限明知故犯的调试)。
if [[ "${OTA_ALLOW_DIRTY:-0}" != "1" ]]; then
  git -C "${REPO_ROOT}" fetch origin --quiet
  _HEAD="$(git -C "${REPO_ROOT}" rev-parse HEAD)"
  _MAIN="$(git -C "${REPO_ROOT}" rev-parse origin/main)"
  if [[ "${_HEAD}" != "${_MAIN}" ]]; then
    echo "✗ OTA 拒绝:HEAD (${_HEAD:0:9}) ≠ origin/main (${_MAIN:0:9})。"
    echo "  从落后/分叉的树发 OTA 会回滚已上线工作。请从干净的 origin/main worktree 发;明知故犯用 OTA_ALLOW_DIRTY=1。"
    exit 1
  fi
  _DIRTY="$(git -C "${REPO_ROOT}" status --porcelain -- mobile/ packages/shared/ | head -5)"
  if [[ -n "${_DIRTY}" ]]; then
    echo "✗ OTA 拒绝:mobile/ 或 packages/shared/ 有未提交改动(会把 WIP 打进生产 bundle):"
    echo "${_DIRTY}"
    echo "  请 stash/提交后再发;明知故犯用 OTA_ALLOW_DIRTY=1。"
    exit 1
  fi
fi

cd "${REPO_ROOT}/mobile"

echo "==> EAS Update → channel=${CHANNEL}"
echo "    environment: ${ENVIRONMENT}"
echo "    message: ${MESSAGE}"
echo ""

# 不打 web bundle (react-native-maps 不支持 web)
# --environment 对普通 channel 与 channel 名字对齐;Rokid 隔离 channel 复用生产/预览环境变量。
UPDATE_LOG="$(mktemp)"
trap 'rm -f "${UPDATE_LOG}"' EXIT

run_update_attempt() {
  set +e
  if [[ -n "${OTA_EAS_RUNNER:-}" ]]; then
    CI=1 "${OTA_EAS_RUNNER}" update --channel "${CHANNEL}" --message "${MESSAGE}" --platform ios --environment "${ENVIRONMENT}" 2>&1 | tee "${UPDATE_LOG}"
  else
    CI=1 npx eas-cli update --channel "${CHANNEL}" --message "${MESSAGE}" --platform ios --environment "${ENVIRONMENT}" 2>&1 | tee "${UPDATE_LOG}"
  fi
  local exit_code=$?
  set -e
  return "${exit_code}"
}

if run_update_attempt; then
  FIRST_EXIT=0
else
  FIRST_EXIT=$?
  if grep -Eiq 'Authentication|not authorized|invalid token|runtime version|bundle error|syntax error|Metro encountered' "${UPDATE_LOG}"; then
    echo "✗ OTA failed with a non-retryable configuration or authentication error." >&2
    exit "${FIRST_EXIT}"
  fi
  if grep -Eiq 'Asset processing timed out|ETIMEDOUT|ECONNRESET|Failed to upload|network.*timed out|request failed' "${UPDATE_LOG}"; then
    echo "△ Temporary EAS upload failure; retrying once..." >&2
    sleep "${OTA_RETRY_DELAY_SECONDS:-1}"
    if run_update_attempt; then
      SECOND_EXIT=0
    else
      SECOND_EXIT=$?
      echo "✗ OTA failed after one retry." >&2
      exit "${SECOND_EXIT}"
    fi
  else
    echo "✗ OTA failed and was not safe to retry automatically." >&2
    exit "${FIRST_EXIT}"
  fi
fi

GROUP_ID="$(grep -Eio 'Update group ID[[:space:]:]+[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}' "${UPDATE_LOG}" | awk '{print $NF}' | sed -n '$p' || true)"
IOS_UPDATE_ID="$(grep -Eio 'iOS update ID[[:space:]:]+[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}' "${UPDATE_LOG}" | awk '{print $NF}' | sed -n '$p' || true)"
if [[ -z "${GROUP_ID}" || -z "${IOS_UPDATE_ID}" ]]; then
  echo "✗ OTA command exited successfully, but published identifier verification failed." >&2
  echo "  Refusing to update the production anchor without an EAS group ID and iOS update ID." >&2
  exit 1
fi

echo "    verified update group: ${GROUP_ID}"
echo "    verified iOS update: ${IOS_UPDATE_ID}"

# 记录可审计的发布事实和上一组已知可回滚更新。文件默认被 gitignore，
# 生产回滚只依赖 EAS group/update ID，不依赖当前工作树是否还保留发布代码。
RUNTIME_VERSION="${MOBILE_RUNTIME_VERSION:-$(python3 - "${REPO_ROOT}/mobile/app.json" <<'PY'
import json
import sys

try:
    with open(sys.argv[1], encoding="utf-8") as handle:
        value = json.load(handle).get("expo", {}).get("version")
except (OSError, ValueError, TypeError):
    value = None
print(value or "unknown")
PY
)}"
python3 - "${MANIFEST_FILE}" "${CHANNEL}" "${ENVIRONMENT}" "${GROUP_ID}" "${IOS_UPDATE_ID}" "$(git -C "${REPO_ROOT}" rev-parse HEAD)" "${RUNTIME_VERSION}" <<'PY'
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

path, channel, environment, group_id, update_id, commit_sha, runtime_version = sys.argv[1:]
manifest_path = Path(path)
previous = {}
if manifest_path.exists():
    try:
        previous = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        previous = {}

previous_update_id = previous.get("active_update_id") or previous.get("update_id")
previous_group_id = previous.get("active_group_id") or previous.get("group_id")
payload = {
    "schema_version": 1,
    "status": "published",
    "platform": "ios",
    "channel": channel,
    "environment": environment,
    "runtime_version": runtime_version,
    "group_id": group_id,
    "update_id": update_id,
    "active_group_id": group_id,
    "active_update_id": update_id,
    "commit_sha": commit_sha,
    "published_at": datetime.now(timezone.utc).isoformat(),
    "previous_known_good_group_id": previous_group_id,
    "previous_known_good_update_id": previous_update_id,
}
manifest_path.parent.mkdir(parents=True, exist_ok=True)
tmp_path = manifest_path.with_name(f".{manifest_path.name}.tmp")
tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
os.replace(tmp_path, manifest_path)
PY
echo "    release manifest 写入 ${MANIFEST_FILE}"

# 只有 EAS 标识验证和 manifest 原子写入都成功后，才记录这次 OTA 对应的
# commit，避免 deploy.sh 把一条不完整的发布记录当作已发布状态。
if [ "${CHANNEL}" = "production" ]; then
  CURRENT_COMMIT=$(git -C "${REPO_ROOT}" rev-parse HEAD)
  printf '%s\n' "${CURRENT_COMMIT}" > "${ANCHOR_FILE}"
  echo "    anchor 写入 ${ANCHOR_FILE} (${CURRENT_COMMIT:0:8})"
fi

echo ""
echo "✓ 推送完成. App 回到前台会下载更新,由用户确认后立即应用."
