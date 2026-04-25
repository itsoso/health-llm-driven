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

set -euo pipefail

CHANNEL="${1:-production}"
MESSAGE="${2:-$(git log -1 --pretty=format:'%s')}"

cd "$(dirname "$0")/.."/mobile

echo "==> EAS Update → channel=${CHANNEL}"
echo "    message: ${MESSAGE}"
echo ""

# 不打 web bundle (react-native-maps 不支持 web)
npx eas-cli update --branch "${CHANNEL}" --message "${MESSAGE}" --platform ios --non-interactive

echo ""
echo "✓ 推送完成. 设备下次冷启 (或后台 30s+) 会自动拉取新 bundle."
