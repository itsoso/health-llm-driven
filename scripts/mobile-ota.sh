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
    "${OTA_EAS_RUNNER}" update --branch "${CHANNEL}" --message "${MESSAGE}" --platform ios --environment "${ENVIRONMENT}" --non-interactive 2>&1 | tee "${UPDATE_LOG}"
  else
    npx eas-cli update --branch "${CHANNEL}" --message "${MESSAGE}" --platform ios --environment "${ENVIRONMENT}" --non-interactive 2>&1 | tee "${UPDATE_LOG}"
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

# 记录这次 OTA 对应的 commit, 让 deploy.sh 检测后续 mobile/ 漂移
if [ "${CHANNEL}" = "production" ]; then
  CURRENT_COMMIT=$(git -C "${REPO_ROOT}" rev-parse HEAD)
  echo "${CURRENT_COMMIT}" > "${ANCHOR_FILE}"
  echo "    anchor 写入 ${ANCHOR_FILE} (${CURRENT_COMMIT:0:8})"
fi

echo ""
echo "✓ 推送完成. App 回到前台会下载更新,由用户确认后立即应用."
