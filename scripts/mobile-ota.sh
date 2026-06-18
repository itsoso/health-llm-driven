#!/usr/bin/env bash
# OTA 推送 mobile/ JS bundle 到已安装的 HealthPilot
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
ANCHOR_FILE="${REPO_ROOT}/.last-ota-commit"

cd "${REPO_ROOT}/mobile"

echo "==> EAS Update → channel=${CHANNEL}"
echo "    environment: ${ENVIRONMENT}"
echo "    message: ${MESSAGE}"
echo ""

# 不打 web bundle (react-native-maps 不支持 web)
# --environment 对普通 channel 与 channel 名字对齐;Rokid 隔离 channel 复用生产/预览环境变量。
npx eas-cli update --branch "${CHANNEL}" --message "${MESSAGE}" --platform ios --environment "${ENVIRONMENT}" --non-interactive

# 记录这次 OTA 对应的 commit, 让 deploy.sh 检测后续 mobile/ 漂移
if [ "${CHANNEL}" = "production" ]; then
  CURRENT_COMMIT=$(git -C "${REPO_ROOT}" rev-parse HEAD)
  echo "${CURRENT_COMMIT}" > "${ANCHOR_FILE}"
  echo "    anchor 写入 .last-ota-commit (${CURRENT_COMMIT:0:8})"
fi

echo ""
echo "✓ 推送完成. 设备下次冷启 (或后台 30s+) 会自动拉取新 bundle."
