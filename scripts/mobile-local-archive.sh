#!/usr/bin/env bash
# 本地 archive → 上 TestFlight (绕开 EAS production build, $0)
#
# 何时用:
#   - 发新版本到 TestFlight / App Store
#   - production credentials 已在 EAS 服务器配好 (一次性)
#
# 何时还得走 EAS remote:
#   - CI 自动发版
#   - 不想本地装 Xcode + cocoapods 完整环境
#
# 前置:
#   - mobile-local-device.sh 已跑过至少一次 (ios/ + Pods/ 已生成)
#   - Xcode Signing & Capabilities 选了正确 Team + provisioning profile
#   - .env 里有 APP_STORE_CONNECT_API_KEY / APP_STORE_CONNECT_ISSUER_ID
#     (在 https://appstoreconnect.apple.com/access/api 创建)
#
# 流程:
#   1. eas build --local --profile production: EAS 跑构建 pipeline 但本机执行
#   2. 产出 .ipa 在当前目录
#   3. xcrun altool 上传到 TestFlight (App Store Connect)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MOBILE_DIR="${REPO_ROOT}/mobile"
cd "${MOBILE_DIR}"

if ! command -v xcrun >/dev/null 2>&1; then
  echo "✗ Xcode 没装" >&2
  exit 1
fi

# 1. EAS local build — 跑在本机, 不消耗 EAS credit
echo "==> [1/2] eas build --local --profile production --platform ios"
echo "    (15-25 分钟, 跑在本机 Mac, 不收 EAS 钱)"
echo ""

OUTPUT_PATH="${MOBILE_DIR}/build-$(date +%Y%m%d-%H%M%S).ipa"
npx eas-cli build --profile production --platform ios --local --output "${OUTPUT_PATH}" --non-interactive

if [ ! -f "${OUTPUT_PATH}" ]; then
  echo "✗ build 失败, .ipa 没产出: ${OUTPUT_PATH}" >&2
  exit 1
fi

echo "✓ .ipa 已生成: ${OUTPUT_PATH}"
echo ""

# 2. 上传到 TestFlight
echo "==> [2/2] 上传到 TestFlight"

if [ -z "${APP_STORE_CONNECT_API_KEY:-}" ] || [ -z "${APP_STORE_CONNECT_ISSUER_ID:-}" ]; then
  cat <<EOF

⚠ 自动上传需要 App Store Connect API Key. 没配则手动用 Transporter:

  1. 打开 Mac App Store 装 "Transporter"
  2. 拖 ${OUTPUT_PATH} 进 Transporter
  3. 点 Deliver

或者配 API key 一次, 后续脚本自动上传:
  1. https://appstoreconnect.apple.com/access/integrations/api → 创建 Team Key
  2. 下载 .p8 文件存到 ~/.appstoreconnect/private_keys/AuthKey_XXX.p8
  3. export APP_STORE_CONNECT_API_KEY=XXX (KeyID)
  4. export APP_STORE_CONNECT_ISSUER_ID=YYY (Issuer ID)
EOF
  exit 0
fi

xcrun altool --upload-app \
  --type ios \
  --file "${OUTPUT_PATH}" \
  --apiKey "${APP_STORE_CONNECT_API_KEY}" \
  --apiIssuer "${APP_STORE_CONNECT_ISSUER_ID}"

echo ""
echo "✓ 已提交到 TestFlight. 5-10 分钟后在 App Store Connect 看到 build."
echo "  https://appstoreconnect.apple.com/apps/6763569720/testflight/ios"
