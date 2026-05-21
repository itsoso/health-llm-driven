#!/usr/bin/env bash
# testflight-qr.sh — 一键生成 TestFlight 公开链接 + QR 扫码页
#
# 用法 (二选一):
#
#   1) 让 ASC API 自动开/拿 public link (推荐):
#      ./scripts/testflight-qr.sh <ASC_ISSUER_ID>
#      # ASC_ISSUER_ID 在 https://appstoreconnect.apple.com/access/integrations/api 顶部
#      # 复制后粘贴进来 (UUID 格式 xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx)
#      # 也可以写进 ~/.zshrc: export ASC_ISSUER_ID=...
#
#   2) 已有现成 link 直接生成 QR (跳过 API):
#      TESTFLIGHT_PUBLIC_LINK=https://testflight.apple.com/join/XXXXXXXX \
#        ./scripts/testflight-qr.sh
#
# 产出:
#   artifacts/testflight/index.html  — 内嵌 QR 的扫码页 (用浏览器打开 → 让别人手机扫)
#   artifacts/testflight/qr.png       — 独立 PNG QR (可直接发图给对方)
#
# 一次性 setup 后,以后**永远不需要再问 issuer ID** — 链接是 betaGroup 级,build 换不变.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${REPO_ROOT}"

# 默认本地 .p8 (May 4 那个,EAS submit 之前手动配的) — 不在就 fallback 到老的
DEFAULT_KEY_ID="QWYW6ZVS6C"
DEFAULT_KEY_PATH="${HOME}/.appstoreconnect/private_keys/AuthKey_QWYW6ZVS6C.p8"
if [ ! -f "${DEFAULT_KEY_PATH}" ]; then
  DEFAULT_KEY_ID="8KNBY5HVFJ"
  DEFAULT_KEY_PATH="${HOME}/.appstoreconnect/private_keys/AuthKey_8KNBY5HVFJ.p8"
fi

export ASC_KEY_ID="${ASC_KEY_ID:-${DEFAULT_KEY_ID}}"
export ASC_PRIVATE_KEY_PATH="${ASC_PRIVATE_KEY_PATH:-${DEFAULT_KEY_PATH}}"
export ASC_APP_ID="${ASC_APP_ID:-6763569720}"

# Issuer ID 优先级: $1 cli arg > $ASC_ISSUER_ID env > 直接走 link-only 模式
if [ "${1:-}" != "" ]; then
  export ASC_ISSUER_ID="${1}"
fi

if [ -z "${ASC_ISSUER_ID:-}" ] && [ -z "${TESTFLIGHT_PUBLIC_LINK:-}" ]; then
  cat <<EOF >&2
✗ 缺参数 — 二选一:

A) 让脚本自动开 public link (一次性 setup):
   1. 浏览器打开 https://appstoreconnect.apple.com/access/integrations/api
   2. 顶部 "Issuer ID" (UUID 格式) 复制
   3. ./scripts/testflight-qr.sh <粘贴 issuer ID>
   ( 想永久免输入: 写进 ~/.zshrc: export ASC_ISSUER_ID=... )

B) 已经有现成 link 直接出 QR (无需 issuer ID):
   TESTFLIGHT_PUBLIC_LINK=https://testflight.apple.com/join/XXXXXXXX \\
     ./scripts/testflight-qr.sh
EOF
  exit 1
fi

echo "==> 跑 testflight-public-link.mjs"
echo "    KEY_ID:     ${ASC_KEY_ID}"
echo "    KEY_PATH:   ${ASC_PRIVATE_KEY_PATH}"
[ -n "${ASC_ISSUER_ID:-}" ] && echo "    ISSUER_ID:  ${ASC_ISSUER_ID:0:8}…"
[ -n "${TESTFLIGHT_PUBLIC_LINK:-}" ] && echo "    LINK (env): ${TESTFLIGHT_PUBLIC_LINK}"
echo ""

# 跑 mjs 脚本, 把 stdout 第一行作为 link, 第二行作为 html 路径
output=$(node scripts/testflight-public-link.mjs)
link=$(echo "${output}" | head -n1)
html=$(echo "${output}" | sed -n 2p)

if [ -z "${link}" ] || [[ "${link}" != http* ]]; then
  echo "✗ 没拿到 link — mjs 输出:" >&2
  echo "${output}" >&2
  exit 1
fi

# 用本地 qrencode 多生一个 PNG (在线 QR 服务有时墙)
if command -v qrencode >/dev/null 2>&1; then
  qrencode -o artifacts/testflight/qr.png -s 12 -m 2 "${link}"
  qrencode -t ANSIUTF8 "${link}"
fi

echo ""
echo "✓ Public link: ${link}"
echo "✓ HTML 扫码页:  ${html}"
[ -f "artifacts/testflight/qr.png" ] && echo "✓ PNG QR:       artifacts/testflight/qr.png"
echo ""
echo "怎么用:"
echo "  - 直接发链接给对方"
echo "  - 或 open ${html} 让对方手机扫屏幕"
echo "  - 或发 qr.png 给对方扫"
