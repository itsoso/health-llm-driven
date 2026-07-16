#!/usr/bin/env bash
# 本地 Xcode build → 装到真机 iPhone (绕开 EAS, $0)
#
# 何时用:
#   - 第一次真机 dev-client 装机,或 native plugins / Pods / entitlements 改动后重建
#   - JS 改动后已经在设备上的 dev-client 跑 OTA / Metro 即可, 不必每次重 build
#
# 何时还得走 EAS:
#   - production .ipa 上 TestFlight (用 mobile-local-archive.sh 也可走 eas build --local)
#   - 修改 EAS server 端的 credentials
#
# 前置条件:
#   - 付费 Apple Developer Program 账号 (Xcode Signing & Capabilities 选你 Team)
#   - Xcode 已装, command line tools 已选 (xcode-select -p 能打印路径)
#   - cocoapods 已装 (sudo gem install cocoapods 或 brew install cocoapods)
#   - iPhone USB 连 Mac, "Trust This Computer" 已点

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MOBILE_DIR="${REPO_ROOT}/mobile"

if [ ! -d "${MOBILE_DIR}" ]; then
  echo "✗ ${MOBILE_DIR} 不存在" >&2
  exit 1
fi

cd "${MOBILE_DIR}"

if ! command -v xcodebuild >/dev/null 2>&1; then
  echo "✗ Xcode command line tools 未配, 跑: sudo xcode-select -s /Applications/Xcode.app/Contents/Developer" >&2
  exit 1
fi

if ! command -v pod >/dev/null 2>&1; then
  echo "✗ cocoapods 没装, 跑: brew install cocoapods (或 sudo gem install cocoapods)" >&2
  exit 1
fi

echo "==> [1/3] expo prebuild — 重新生成 ios/ 目录, 同步 app.json plugins"
echo "    (这一步必跑, 否则 entitlements / Info.plist 不会反映 app.json 最新改动)"
npx expo prebuild --platform ios --clean

echo ""
echo "==> [2/3] pod install"
cd ios
pod install --repo-update
cd ..

echo ""
echo "==> [3/3] 打开 Xcode workspace"
WORKSPACE=$(ls -d ios/*.xcworkspace 2>/dev/null | head -1)
if [ -z "${WORKSPACE}" ]; then
  echo "✗ 没找到 ios/*.xcworkspace, prebuild 可能失败" >&2
  exit 1
fi
open "${WORKSPACE}"

cat <<EOF

✓ Xcode 已打开 (${WORKSPACE})

接下去在 Xcode 里:
  1. 顶栏 device 选你的 iPhone (USB 连着, 不是 Simulator)
  2. 左侧 navigator 选 HealthPilot project → Signing & Capabilities tab
  3. Team 选你的 Apple Developer 账号
     - 第一次会自动生成 provisioning profile (1 年有效)
     - "Automatically manage signing" 保持勾选
  4. Cmd+R 跑 → 会自动 build + 装到 iPhone (3-10 分钟)

后续日常迭代 (装机后):
  - 开发内环  → ./scripts/mobile-fast-device.sh metro (Fast Refresh)
  - JS/TS 验收 → ./scripts/mobile-ota.sh production "..." (设备前台下载,确认后应用)
  - Release 验收 → ./scripts/mobile-fast-device.sh release (复用 DerivedData,不重装 Pods)
  - native 结构变化 → 才重跑本脚本 (prebuild + Pods)

完全不再消耗 EAS build credit. 只有发 TestFlight 才需要 EAS (或 eas build --local).
EOF
