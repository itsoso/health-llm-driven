#!/usr/bin/env bash
set -euo pipefail

# 小巴 mac 对外分发发布:Developer ID 签名 → 公证 → staple → DMG → 上传服务器。
#
# 与 package-app.sh 的分工:那个管"构建出 .app + 本机安装"(ad-hoc 够用);
# 这个管"给其他用户下载"(Gatekeeper 零弹窗需要 Developer ID + notarization)。
#
# 前置(均已一次性配好):
#   - 钥匙串有 "Developer ID Application: baokun Pan (QA2U724DAN)"(私钥+证书配对)
#   - 仓库根 .env 有 APP_STORE_CONNECT_API_KEY / APP_STORE_CONNECT_ISSUER_ID
#     (公证 App Manager 角色即可;.p8 在 ~/.appstoreconnect/private_keys/)
#   - 服务器 /opt/health-app-shared/assets/ + nginx 每文件 alias(rokid APK 同款)
#
# 用法: apps/mac/scripts/release-dmg.sh [--skip-upload]
# 产出: apps/mac/dist/xiaoba-mac.dmg + https://health.executor.life/xiaoba-mac.dmg

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${PROJECT_DIR}/../.." && pwd)"
DIST="${PROJECT_DIR}/dist"
STAGING="${DIST}/dmg-staging"
APP_DISPLAY="小巴"
DMG_NAME="xiaoba-mac.dmg"
SIGN_IDENTITY="${HEALTH_MAC_SIGN_IDENTITY:-Developer ID Application: baokun Pan (QA2U724DAN)}"
SERVER="root@39.98.206.178"
ASSET_DIR="/opt/health-app-shared/assets"
SKIP_UPLOAD="0"
[[ "${1:-}" == "--skip-upload" ]] && SKIP_UPLOAD="1"

# 公证凭据从仓库根 .env 读(不打印值)
ASC_KEY_ID="$(grep -E '^APP_STORE_CONNECT_API_KEY=' "${REPO_ROOT}/.env" | cut -d= -f2)"
ASC_ISSUER="$(grep -E '^APP_STORE_CONNECT_ISSUER_ID=' "${REPO_ROOT}/.env" | cut -d= -f2)"
ASC_P8="${HOME}/.appstoreconnect/private_keys/AuthKey_${ASC_KEY_ID}.p8"
[[ -n "${ASC_KEY_ID}" && -n "${ASC_ISSUER}" && -f "${ASC_P8}" ]] || { echo "✗ 公证凭据不齐 (.env APP_STORE_CONNECT_* / ${ASC_P8})" >&2; exit 1; }

echo "==> [1/6] 构建 .app (package-app.sh --no-sign, 签名由本脚本接管)"
"${SCRIPT_DIR}/package-app.sh" --no-sign >/dev/null
[[ -d "${DIST}/HealthAgentMac.app" ]] || { echo "✗ 构建产物缺失" >&2; exit 1; }

echo "==> [2/6] Developer ID 签名 (hardened runtime + secure timestamp)"
rm -rf "${STAGING}"; mkdir -p "${STAGING}"
cp -R "${DIST}/HealthAgentMac.app" "${STAGING}/${APP_DISPLAY}.app"
codesign --force --options runtime --timestamp \
  --sign "${SIGN_IDENTITY}" "${STAGING}/${APP_DISPLAY}.app"
codesign --verify --strict --deep "${STAGING}/${APP_DISPLAY}.app"
echo "    签名校验通过"

echo "==> [3/6] 打 DMG (含 Applications 快捷方式)"
ln -sfn /Applications "${STAGING}/Applications"
rm -f "${DIST}/${DMG_NAME}"
hdiutil create -volname "${APP_DISPLAY}" -srcfolder "${STAGING}" -ov -format UDZO \
  "${DIST}/${DMG_NAME}" >/dev/null
codesign --force --timestamp --sign "${SIGN_IDENTITY}" "${DIST}/${DMG_NAME}"

echo "==> [4/6] 公证 (notarytool --wait, 通常 2-10 分钟)"
SUBMIT_OUT="$(xcrun notarytool submit "${DIST}/${DMG_NAME}" \
  --key "${ASC_P8}" --key-id "${ASC_KEY_ID}" --issuer "${ASC_ISSUER}" \
  --wait 2>&1)" || { echo "${SUBMIT_OUT}" | tail -20 >&2; exit 1; }
echo "${SUBMIT_OUT}" | grep -E "id:|status:" | head -4
echo "${SUBMIT_OUT}" | grep -q "status: Accepted" || {
  echo "✗ 公证未通过 — 取日志:" >&2
  SUB_ID="$(echo "${SUBMIT_OUT}" | grep -m1 'id:' | awk '{print $2}')"
  xcrun notarytool log "${SUB_ID}" --key "${ASC_P8}" --key-id "${ASC_KEY_ID}" --issuer "${ASC_ISSUER}" >&2 || true
  exit 1
}

echo "==> [5/6] staple + Gatekeeper 终验"
xcrun stapler staple "${DIST}/${DMG_NAME}" >/dev/null
spctl --assess --type open --context context:primary-signature "${DIST}/${DMG_NAME}" \
  && echo "    spctl: DMG accepted (Notarized Developer ID)"

if [[ "${SKIP_UPLOAD}" == "1" ]]; then
  echo "==> [6/6] 跳过上传 (--skip-upload)。产物: ${DIST}/${DMG_NAME}"
  exit 0
fi

echo "==> [6/6] 上传服务器 + 确保 nginx alias"
scp -q "${DIST}/${DMG_NAME}" "${SERVER}:${ASSET_DIR}/${DMG_NAME}"
# nginx location 幂等注入(镜像 rokid APK 块;已存在则跳过)
ssh "${SERVER}" "grep -q 'location = /${DMG_NAME}' /etc/nginx/sites-enabled/health.executor.life.conf || \
  sed -i '/# Rokid glasses push-up APK static distribution/i\\
    # 小巴 mac app DMG static distribution\\
    location = /${DMG_NAME} {\\
        alias ${ASSET_DIR}/${DMG_NAME};\\
        default_type application/x-apple-diskimage;\\
        add_header Cache-Control \"public, max-age=3600\";\\
        add_header X-Reva-Artifact \"xiaoba-mac-dmg\";\\
    }\\
' /etc/nginx/sites-enabled/health.executor.life.conf && nginx -t && systemctl reload nginx"
HTTP_CODE="$(curl -s -o /dev/null -w '%{http_code}' "https://health.executor.life/${DMG_NAME}")"
[[ "${HTTP_CODE}" == "200" ]] || { echo "✗ 下载链接探活失败 (HTTP ${HTTP_CODE})" >&2; exit 1; }
echo "✓✓ 发布完成: https://health.executor.life/${DMG_NAME}"
