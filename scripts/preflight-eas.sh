#!/usr/bin/env bash
# preflight-eas.sh — EAS build 前的本地体检
#
# 防止 native config 错了还触发昂贵的 EAS build (今天 LIFO 顺序错那次本来这一步能拦下来)
#
# 用法: ./scripts/preflight-eas.sh && eas build ...
#       或在 mobile-ota.sh / 其他 script 里调用
#
# 检查项 (任一失败 exit 1):
#   - npx expo prebuild --clean 跑通
#   - ios/HealthPilot/Info.plist 含必须 key (NSHealthShareUsageDescription / NSCameraUsageDescription / NSMicrophoneUsageDescription)
#   - ios/HealthPilot/HealthPilot.entitlements 含 com.apple.developer.healthkit
#   - ios/HealthPilot/HealthPilot.entitlements **不含** com.apple.developer.healthkit.access (空 array 会 fail provisioning profile)
#   - ios/Podfile.lock 含关键 native module (RNHealth, expo-secure-store)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MOBILE_DIR="${REPO_ROOT}/mobile"
cd "${MOBILE_DIR}"

echo "==> [1/4] expo prebuild --clean"
npx expo prebuild --platform ios --clean --no-install >/dev/null
echo "    ✓"

INFO_PLIST="ios/HealthPilot/Info.plist"
ENTITLEMENTS="ios/HealthPilot/HealthPilot.entitlements"
PODFILE_LOCK="ios/Podfile.lock"

echo ""
echo "==> [2/4] Info.plist 关键 usage description"
fail=0
for key in NSHealthShareUsageDescription NSCameraUsageDescription NSMicrophoneUsageDescription NSLocationWhenInUseUsageDescription; do
  if grep -q "${key}" "${INFO_PLIST}" 2>/dev/null; then
    echo "    ✓ ${key}"
  else
    echo "    ✗ ${key} 缺失"
    fail=1
  fi
done
[ ${fail} -eq 1 ] && exit 1

echo ""
echo "==> [3/4] entitlements 检查"
if grep -q "com.apple.developer.healthkit<" "${ENTITLEMENTS}" || grep -q "<key>com.apple.developer.healthkit</key>" "${ENTITLEMENTS}" 2>/dev/null; then
  echo "    ✓ com.apple.developer.healthkit 在"
else
  echo "    ✗ com.apple.developer.healthkit 缺失" >&2
  exit 1
fi

if grep -q "com.apple.developer.healthkit.access" "${ENTITLEMENTS}" 2>/dev/null; then
  echo "    ✗ com.apple.developer.healthkit.access **不应该在** (会 fail provisioning profile)" >&2
  echo "    检查 mobile/plugins/withHealthKitCleanup.js 是否在 react-native-health 之**前** (LIFO 执行)" >&2
  exit 1
else
  echo "    ✓ com.apple.developer.healthkit.access 不在 (cleanup 插件生效)"
fi

echo ""
echo "==> [4/4] Podfile.lock 关键 native module"
fail=0
for pod in RNHealth expo-secure-store; do
  if grep -q "${pod}" "${PODFILE_LOCK}" 2>/dev/null; then
    echo "    ✓ ${pod}"
  else
    echo "    ✗ ${pod} 没在 Podfile.lock (native module 不会被链接, 会变 noop)"
    fail=1
  fi
done
[ ${fail} -eq 1 ] && exit 1

echo ""
echo "✓ preflight 全过, 可以放心触发 EAS / 本地 build"
