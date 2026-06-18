#!/usr/bin/env bash
# 原生 xcodebuild 归档 + ASC API Key 签名 → TestFlight。
#
# 何时用:EAS 凭据库里的分发证书/profile 和当前证书漂移,导致 `eas build`(远端 & --local)
# 反复撞 `Provisioning profile doesn't include signing certificate`,且无法跑交互式
# `eas credentials` 重签发(没人能输 Apple ID 2FA)。本脚本完全绕开 EAS 凭据,只用
# App Store Connect API Key(.env 里那把)+ 本机钥匙串里的分发证书,非交互出包上 TestFlight。
#
# 前置:
#   - ruby@3.3 在 PATH(见 [[project_homebrew_ruby4_breaks_ios_toolchain]]);ruby 4 会崩。
#   - .env 有 APP_STORE_CONNECT_API_KEY(KeyID)+ APP_STORE_CONNECT_ISSUER_ID;
#     ~/.appstoreconnect/private_keys/AuthKey_<KeyID>.p8 存在(altool / ASC API 共用)。
#     该 Key 需有 Certificates/Identifiers/Profiles 写权限(脚本会先验)。
#   - 本机钥匙串有 "Apple Distribution: <name>" 证书(含私钥)。`security find-identity -v
#     -p codesigning` 能看到 = 行。
#   - 干净工作树(prebuild/archive 打的是工作树)。建议在 origin/main 的隔离 worktree 跑。
#
# 用法:从 worktree 根跑  bash <repo>/.claude/skills/mobile-testflight-release/scripts/native-archive-asc.sh
set -euo pipefail
export PATH="/opt/homebrew/opt/ruby@3.3/bin:$PATH"
export LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8          # 否则 cocoapods unicode_normalize 崩
export SENTRY_DISABLE_AUTO_UPLOAD=true              # 跳过可选 source-map 上传(无 org slug 会让 archive 红)

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$SCRIPT_DIR/../../../.." && pwd)"        # .claude/skills/<name>/scripts → repo 根
MOBILE="$REPO/mobile"
WORK="${WORK:-/tmp/reva-archive}"; mkdir -p "$WORK"

# .env(优先 repo 根,其次 $HOME 里手动 export)
[ -f "$REPO/.env" ] && { set -a; . "$REPO/.env"; set +a; }
: "${APP_STORE_CONNECT_API_KEY:?need APP_STORE_CONNECT_API_KEY in .env}"
: "${APP_STORE_CONNECT_ISSUER_ID:?need APP_STORE_CONNECT_ISSUER_ID in .env}"
KEYID="$APP_STORE_CONNECT_API_KEY"; ISS="$APP_STORE_CONNECT_ISSUER_ID"
TEAM="${APPLE_TEAM_ID:-QA2U724DAN}"
BUILD_NO="${BUILD_NO:-$(date +%y%m%d%H)}"           # 单调递增即可;App Store 只拒重复已上传号

cd "$MOBILE"
# 主 bundle id + 版本(从 app.json)
read -r MAIN_BID VERSION < <(node -e 'const c=require("./app.json");console.log(c.expo.ios.bundleIdentifier, c.expo.version)')
# watch / complication 约定前缀(本仓库 withWatchApp.js)
WATCH_BID="$MAIN_BID.watchkitapp"
COMP_BID="$MAIN_BID.watchkitapp.watchkitextension"
echo "==> main=$MAIN_BID watch=$WATCH_BID comp=$COMP_BID version=$VERSION build=$BUILD_NO team=$TEAM"

echo "==> [1/6] set ios.buildNumber=$BUILD_NO"
node -e "const fs=require('fs');const c=require('./app.json');c.expo.ios=c.expo.ios||{};c.expo.ios.buildNumber='$BUILD_NO';fs.writeFileSync('./app.json',JSON.stringify(c,null,2))"

echo "==> [2/6] expo prebuild (clean) + pod install"
npx expo prebuild --platform ios --clean --no-install >"$WORK/prebuild.log" 2>&1 || { echo "PREBUILD FAILED"; tail -30 "$WORK/prebuild.log"; exit 1; }
( cd ios && pod install >"$WORK/pod.log" 2>&1 ) || { echo "POD FAILED"; tail -30 "$WORK/pod.log"; exit 1; }
WS="$(cd ios && ls -d *.xcworkspace | head -1)"; SCHEME="${WS%.xcworkspace}"

echo "==> [3/6] archive (automatic signing + ASC key cloud profiles)"
xcodebuild -workspace "ios/$WS" -scheme "$SCHEME" -configuration Release \
  -archivePath "$WORK/app.xcarchive" -destination 'generic/platform=iOS' \
  -allowProvisioningUpdates \
  -authenticationKeyPath "$HOME/.appstoreconnect/private_keys/AuthKey_$KEYID.p8" \
  -authenticationKeyID "$KEYID" -authenticationKeyIssuerID "$ISS" \
  DEVELOPMENT_TEAM="$TEAM" CODE_SIGN_STYLE=Automatic \
  clean archive >"$WORK/archive.log" 2>&1 || { echo "ARCHIVE FAILED"; grep -iE "error:|signing|provisioning" "$WORK/archive.log" | tail -25; exit 1; }
echo "    ✓ archived"

echo "==> [3.5] 对齐 watch/complication 版本到主 app(否则 altool 拒:CFBundleVersion Mismatch)"
APP="$WORK/app.xcarchive/Products/Applications/$SCHEME.app"
for P in "$APP/Watch/"*.app/Info.plist "$APP/Watch/"*.app/PlugIns/*.appex/Info.plist; do
  [ -f "$P" ] || continue
  /usr/libexec/PlistBuddy -c "Set :CFBundleVersion $BUILD_NO" "$P" 2>/dev/null || true
  /usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $VERSION" "$P" 2>/dev/null || true
  echo "    aligned $(basename "$(dirname "$P")")"
done

echo "==> [4/6] 用 ASC key 生成绑「本机证书」的 3 个 profile(绕开 EAS 漂移)"
MAP_JSON="$(python3 "$SCRIPT_DIR/asc_profiles.py" "$MAIN_BID" "$WATCH_BID" "$COMP_BID")"
echo "    $MAP_JSON"
PM(){ echo "$MAP_JSON" | python3 -c "import json,sys;print(json.load(sys.stdin)['$1'])"; }

echo "==> [5/6] export (manual signing, profile 按上面映射)"
cat > "$WORK/ExportManual.plist" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>method</key><string>app-store-connect</string>
<key>teamID</key><string>$TEAM</string>
<key>signingStyle</key><string>manual</string>
<key>signingCertificate</key><string>Apple Distribution</string>
<key>uploadSymbols</key><true/>
<key>manageAppVersionAndBuildNumber</key><false/>
<key>provisioningProfiles</key><dict>
  <key>$MAIN_BID</key><string>$(PM "$MAIN_BID")</string>
  <key>$WATCH_BID</key><string>$(PM "$WATCH_BID")</string>
  <key>$COMP_BID</key><string>$(PM "$COMP_BID")</string>
</dict>
</dict></plist>
PL
rm -rf "$WORK/export"
xcodebuild -exportArchive -archivePath "$WORK/app.xcarchive" \
  -exportPath "$WORK/export" -exportOptionsPlist "$WORK/ExportManual.plist" \
  >"$WORK/export.log" 2>&1 || { echo "EXPORT FAILED"; grep -iE "error:|profile|signing" "$WORK/export.log" | tail -25; exit 1; }
IPA="$(ls "$WORK"/export/*.ipa | head -1)"; echo "    ✓ ipa: $IPA"

echo "==> [6/6] upload to TestFlight (altool + ASC key)"
xcrun altool --upload-app -t ios -f "$IPA" --apiKey "$KEYID" --apiIssuer "$ISS" >"$WORK/upload.log" 2>&1 \
  && echo "✓✓ UPLOADED TO TESTFLIGHT (build $BUILD_NO)" \
  || { echo "UPLOAD FAILED"; grep -iE "error|mismatch|invalid|90[0-9]{3}" "$WORK/upload.log" | tail -20; exit 1; }
echo "DONE — 几分钟后 App Store Connect 处理完即可在 TestFlight 安装"
