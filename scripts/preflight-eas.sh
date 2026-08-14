#!/usr/bin/env bash
# preflight-eas.sh — iOS Simulator / 静态验证前的本地体检
#
# 只验证本地 native config；它不授权 EAS、真机签名或商店发布。
#
# 用法:
#   ./scripts/preflight-eas.sh           # 只读检查现有 ios/
#   ./scripts/preflight-eas.sh --rebuild # 跑一次 expo prebuild --clean 再检查 (会重置 ios/, 之后须 pod install)
#
# 默认不会改 ios/, 只读检查。ios/ 缺失时使用受控 Simulator 工具生成。
#
# 检查项:
#   - 当前 iOS 主应用目录的 Info.plist 含必须 key (NSHealthShareUsage / Camera / Microphone / Location)
#   - 当前 iOS 主应用目录的 entitlements 含 com.apple.developer.healthkit
#   - entitlements **不含** com.apple.developer.healthkit.access (空 array 会 fail provisioning profile)
#   - ios/Podfile.lock 含关键 native module (RNAppleHealthKit, ExpoSecureStore)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MOBILE_DIR="${MOBILE_DIR_OVERRIDE:-${REPO_ROOT}/mobile}"
cd "${MOBILE_DIR}"

REBUILD=0
if [ "${1:-}" = "--rebuild" ]; then
  REBUILD=1
fi

if [ ${REBUILD} -eq 1 ]; then
  echo "==> [0/3] expo prebuild --clean (--rebuild flag, 会重置 ios/)"
  npx expo prebuild --platform ios --clean --no-install >/dev/null
  echo "    ⚠ ios/ 已重置, 跑 pod install 才能 build:"
  echo "      cd mobile/ios && pod install"
  echo ""
fi

IOS_APP_DIR=""
for candidate in ios/app ios/HealthPilot; do
  if [[ -d "${candidate}" && -f "${candidate}/Info.plist" ]]; then
    IOS_APP_DIR="${candidate}"
    break
  fi
done

if [[ -z "${IOS_APP_DIR}" ]]; then
  echo "✗ 未找到 iOS 主应用目录（已尝试 ios/app 和 ios/HealthPilot）— 请使用受控 Simulator 工具生成" >&2
  exit 1
fi

INFO_PLIST="${IOS_APP_DIR}/Info.plist"
ENTITLEMENTS="$(find "${IOS_APP_DIR}" -maxdepth 1 -type f -name '*.entitlements' -print -quit)"
PODFILE_LOCK="ios/Podfile.lock"

if [[ -z "${ENTITLEMENTS}" ]]; then
  echo "✗ ${IOS_APP_DIR} 下未找到 entitlements 文件" >&2
  exit 1
fi

echo "    ✓ iOS app target: ${IOS_APP_DIR}"

echo "==> [1/3] Info.plist 关键 usage description"
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
echo "==> [2/3] entitlements 检查"
if grep -q "<key>com.apple.developer.healthkit</key>" "${ENTITLEMENTS}" 2>/dev/null; then
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
echo "==> [3/3] Podfile.lock 关键 native module"
if [ ! -f "${PODFILE_LOCK}" ]; then
  echo "    ⚠ Podfile.lock 不存在, 先跑: cd mobile/ios && pod install"
  echo "    (不影响 textual config 检查, 但 native module 不会被链接)"
  exit 1
fi
fail=0
for pod in RNAppleHealthKit ExpoSecureStore; do
  if grep -q "${pod}" "${PODFILE_LOCK}"; then
    echo "    ✓ ${pod}"
  else
    echo "    ✗ ${pod} 没在 Podfile.lock (native module 不会被链接, 会变 noop)"
    fail=1
  fi
done
[ ${fail} -eq 1 ] && exit 1

echo ""
echo "✓ preflight 全过，仅证明本地 native config 可供 Simulator / 静态验证"
echo "  不授权 EAS、真机签名、设备安装或商店发布。"
