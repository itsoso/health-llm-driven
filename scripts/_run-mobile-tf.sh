#!/usr/bin/env bash
# _run-mobile-tf.sh — 一键把 mobile/ 发到 TestFlight
#
# ⚠️ 重建版(2026-06-16):原脚本是未跟踪文件,在一次后端部署清脏树时丢失。
#    这是按本仓库当天实况重建的"最可靠路径",若与你原版不同,按需改。
#
# 为什么默认走远端 EAS,而不是本地 eas build --local:
#   本机 Homebrew ruby 4.0.3 把本地 iOS 工具链搞坏了 —— `eas build --local` 经
#   fastlane 驱动 xcodebuild 需要 PTY,在 ruby 4.0.3 下报 "Can't get Master/Slave
#   device";cocoapods 也在 ruby 4.0.3 下 Unicode 崩。本地原生 xcodebuild archive
#   能编译,但 app-store 的 export 又撞 App-Manager API key 的 cloud-signing 权限。
#   ⇒ 这台机器上真正端到端跑通(build 110/111 进 TestFlight)的就是远端 EAS。
#   远端 EAS 在它服务器上用对的工具链构建+签名(含 watch),--auto-submit 自动提交,
#   并自动分发进已配好的内部测试组「内部测试」(panbaokun@gmail.com 是测试员)。
#
# 用法:
#   ./scripts/_run-mobile-tf.sh                # 远端 production 构建 + 自动提交 TestFlight(默认,最稳)
#   ./scripts/_run-mobile-tf.sh ota "msg"      # 只是 JS/TS 改动 → 走 OTA(秒级,不出新包)
#   ./scripts/_run-mobile-tf.sh local-archive  # 本地原生 xcodebuild archive(绕 fastlane;export 可能因签名权限失败,兜底用)
#
# 前置:eas 已登录(itsoso);远端构建用 EAS 托管凭据(含 watch 两个 bundle id)。
#   local-archive 路径需 .env 里 APP_STORE_CONNECT_API_KEY / APP_STORE_CONNECT_ISSUER_ID
#   + ~/.appstoreconnect/private_keys/AuthKey_<KeyID>.p8。

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE="${1:-remote}"
source "${ROOT}/scripts/release_lock.sh"
acquire_release_lock "testflight:${MODE}"

# ruby@3.3 —— 本机默认 ruby 4.0.3 会让 pod/fastlane 崩(见 scripts 注释 / 项目记忆)
export PATH="/opt/homebrew/opt/ruby@3.3/bin:/opt/homebrew/lib/ruby/gems/3.3.0/bin:${PATH}"
export LANG="${LANG:-en_US.UTF-8}"
export LC_ALL="${LC_ALL:-en_US.UTF-8}"

cd "${ROOT}/mobile"
LOG="/tmp/run-mobile-tf-$(date +%Y%m%d-%H%M%S).log"

echo "== mobile → TestFlight (mode=${MODE}) =="
echo "ruby: $(ruby -v 2>/dev/null | cut -d' ' -f2)  日志: ${LOG}"

case "${MODE}" in
  remote)
    if ! git -C "${ROOT}" diff --quiet || [ -n "$(git -C "${ROOT}" status --porcelain)" ]; then
      echo "⚠️  工作树非干净:远端 EAS 用 git 已提交状态(committed HEAD)构建,未提交改动不会进包。"
      echo "    当前 HEAD = $(git -C "${ROOT}" rev-parse --short HEAD)"
    fi
    echo "→ 远端 EAS production 构建 + 自动提交(含 watch,自动分发进内部测试组)…"
    npx eas-cli build --platform ios --profile production --non-interactive --auto-submit-with-profile production-no-groups 2>&1 | tee "${LOG}"
    echo
    echo "✓ 完成。构建/提交详情见上方 expo.dev 链接;Apple 处理 ~5-10 分钟后 TestFlight 可装。"
    ;;

  ota)
    MSG="${2:-$(git -C "${ROOT}" log -1 --pretty=%s)}"
    echo "→ 只发 OTA(JS/TS 改动,不出新包)production channel: ${MSG}"
    if [ -x "${ROOT}/scripts/mobile-ota.sh" ]; then
      "${ROOT}/scripts/mobile-ota.sh" production "${MSG}" 2>&1 | tee "${LOG}"
    else
      npx eas-cli update --branch production --message "${MSG}" --platform ios 2>&1 | tee "${LOG}"
    fi
    ;;

  local-archive)
    # 兜底:远端不可用时,本地原生 xcodebuild(绕 fastlane PTY 坑)。
    # 注意:app-store export 可能因 App-Manager key 的 cloud-signing 权限失败 —— 那时回退 remote。
    set -a; [ -f "${ROOT}/.env" ] && source "${ROOT}/.env"; set +a
    : "${APP_STORE_CONNECT_API_KEY:?缺 APP_STORE_CONNECT_API_KEY(.env)}"
    : "${APP_STORE_CONNECT_ISSUER_ID:?缺 APP_STORE_CONNECT_ISSUER_ID(.env)}"
    P8="$HOME/.appstoreconnect/private_keys/AuthKey_${APP_STORE_CONNECT_API_KEY}.p8"
    [ -f "${P8}" ] || { echo "❌ 找不到密钥文件 ${P8}"; exit 1; }
    export SENTRY_DISABLE_AUTO_UPLOAD=true   # 本地缺 Sentry org,关掉自动上传(否则 bundle 脚本 fail)

    echo "→ prebuild(注入 watch)…"; npx expo prebuild --platform ios --clean
    ARCH="/tmp/HealthPilot-$(date +%H%M%S).xcarchive"
    cat > /tmp/exportOptions.plist <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>method</key><string>app-store</string>
<key>signingStyle</key><string>automatic</string>
<key>teamID</key><string>QA2U724DAN</string>
<key>uploadSymbols</key><true/>
</dict></plist>
PLIST
    echo "→ archive…"
    xcodebuild -workspace ios/HealthPilot.xcworkspace -scheme HealthPilot -configuration Release \
      -destination 'generic/platform=iOS' -archivePath "${ARCH}" \
      -allowProvisioningUpdates -authenticationKeyPath "${P8}" \
      -authenticationKeyID "${APP_STORE_CONNECT_API_KEY}" \
      -authenticationKeyIssuerID "${APP_STORE_CONNECT_ISSUER_ID}" \
      CODE_SIGN_STYLE=Automatic DEVELOPMENT_TEAM=QA2U724DAN archive 2>&1 | tee "${LOG}"
    echo "→ export…"
    xcodebuild -exportArchive -archivePath "${ARCH}" -exportPath /tmp/tf-export \
      -exportOptionsPlist /tmp/exportOptions.plist -allowProvisioningUpdates \
      -authenticationKeyPath "${P8}" -authenticationKeyID "${APP_STORE_CONNECT_API_KEY}" \
      -authenticationKeyIssuerID "${APP_STORE_CONNECT_ISSUER_ID}" 2>&1 | tee -a "${LOG}"
    echo "→ altool 上传…"
    xcrun altool --upload-app -f /tmp/tf-export/*.ipa -t ios \
      --apiKey "${APP_STORE_CONNECT_API_KEY}" --apiIssuer "${APP_STORE_CONNECT_ISSUER_ID}" --verbose 2>&1 | tee -a "${LOG}"
    ;;

  *)
    echo "未知 mode: ${MODE}(可用: remote | ota | local-archive)"; exit 1
    ;;
esac
