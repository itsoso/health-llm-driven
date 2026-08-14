#!/usr/bin/env bash
# Generate a local QR page for an existing, manually approved TestFlight link.
# This tool is deliberately read-only with respect to App Store Connect.

set -euo pipefail
umask 077

REPO_ROOT="$(cd "$(/usr/bin/dirname "$0")/.." && pwd)"
NODE_BINARY="/usr/local/bin/node"
QRENCODE_BINARY="/opt/homebrew/bin/qrencode"
OUTPUT_DIR="${TESTFLIGHT_OUTPUT_DIR:-${REPO_ROOT}/artifacts/testflight}"

if [ -z "${TESTFLIGHT_PUBLIC_LINK:-}" ]; then
  echo "✗ 请先在 App Store Connect 人工批准/复制公开链接，再设置 TESTFLIGHT_PUBLIC_LINK" >&2
  exit 2
fi
[ -x "${NODE_BINARY}" ] || { echo "✗ 缺少 ${NODE_BINARY}" >&2; exit 2; }
[ -x "${QRENCODE_BINARY}" ] || { echo "✗ 缺少本地 qrencode: ${QRENCODE_BINARY}" >&2; exit 2; }

export TESTFLIGHT_OUTPUT_DIR="${OUTPUT_DIR}"
output="$("${NODE_BINARY}" "${REPO_ROOT}/scripts/testflight-public-link.mjs")"
link="$(/bin/echo "${output}" | /usr/bin/sed -n '1p')"
html="$(/bin/echo "${output}" | /usr/bin/sed -n '2p')"

"${QRENCODE_BINARY}" -o "${OUTPUT_DIR}/qr.png" -s 12 -m 2 "${link}"
"${QRENCODE_BINARY}" -t ANSIUTF8 "${link}"

echo "✓ Existing public link: ${link}"
echo "✓ Local HTML page:     ${html}"
echo "✓ Local PNG QR:        ${OUTPUT_DIR}/qr.png"
echo "公开测试组/链接的创建或启用仍是独立人工批准 Gate；本工具不会修改 ASC。"
