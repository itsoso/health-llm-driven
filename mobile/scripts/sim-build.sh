#!/usr/bin/env bash
# Reva mobile — iOS Simulator build(Rokid 排除版)。
#
# 问题:Rokid CXR-L 的 RGCxrClient.framework 只有 device 切片,没有 simulator 切片。
#   直接 `npx expo run:ios <sim>` 会 `cannot find type 'RGCxrClientAudioEvent'` → xcodebuild exit 65。
#
# 三层根因 + 修复(每层都烧过,见 memory project_ios_simulator_blocked_by_rokid_framework):
#   1. plugins/withRokidIosPods.js 注入 `pod 'RGCxrClient'` 的门只看 ROKID_IOS_SDK_ENABLED,
#      不看 ROKID_IOS_SIMULATOR → 设 SIMULATOR=1 没用。**正解:ROKID_IOS_SDK_ENABLED=0**
#      → 不注入 RGCxrClient → canImport(RGCxrClient)=false → 所有 `#if canImport(RGCxrClient)`
#      Rokid 代码干净排除(代码本就为此设计)。
#   2. 上次若是 device(ENABLED=1)build,ios/Podfile.lock 残留 RGCxrClient,pod install 不会
#      自动重解析 → 必须**删 Podfile.lock 强制重装**才能真正 `Removing RGCxrClient`。
#   3. Homebrew ruby 对含中文(非 ASCII)的 Podfile,cocoapods 错误格式化器会
#      `Unicode Normalization not appropriate for ASCII-8BIT` 崩溃,掩盖真错 → 必须 **LC_ALL=en_US.UTF-8**。
#   4. 本地无 Sentry org 配置,source-map 上传(post-compile)会 exit 65 → **SENTRY_DISABLE_AUTO_UPLOAD=true**。
#
# device / 真机 Rokid 功能零影响:EAS device build 走 ROKID_IOS_SDK_ENABLED=1 → canImport=true
#   → 同一份 `#if canImport(RGCxrClient)` 代码全部编入,行为不变(本脚本只服务模拟器路径)。
#
# 用法:  ./scripts/sim-build.sh ["iPhone 17 Pro" | <sim-udid>]
set -euo pipefail

SIM="${1:-iPhone 17 Pro}"
cd "$(dirname "$0")/.."   # mobile/

export LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8            # 层3:绕 ruby unicode 崩
export ROKID_IOS_SDK_ENABLED=0 ROKID_SDK_ENABLED=0   # 层1:不注入 RGCxrClient → Rokid 代码排除
export SENTRY_DISABLE_AUTO_UPLOAD=true                # 层4:跳过 Sentry source-map 上传

# 层2:强制 pod 重解析,去掉残留的 device-only RGCxrClient(若 ios/ 已 prebuild)
if [ -d ios ]; then
  echo "==> 强制 pod 重解析(去 RGCxrClient)..."
  ( cd ios && rm -f Podfile.lock && pod install )
fi

echo "==> expo run:ios --device \"$SIM\"(Rokid 排除)..."
exec npx expo run:ios --device "$SIM"
