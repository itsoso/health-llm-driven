#!/usr/bin/env bash
# check_frontend_page_freeze.sh
#
# Phase 0-4 期间 frontend/src/app/ 新 page.tsx 冻结.
# 允许的例外: frontend/src/app/admin/** (管理后台) 和 frontend/src/app/api/** (API routes).
# 要绕过冻结, 在任一 commit message 里加 "FREEZE_OVERRIDE" 字样.
#
# 用法:
#   scripts/check_frontend_page_freeze.sh              # 默认 vs origin/main
#   scripts/check_frontend_page_freeze.sh main         # vs 本地 main
#   scripts/check_frontend_page_freeze.sh <sha>        # vs 任意 ref
#
# Exit 0: 冻结通过 / 没有新页面 / 合法豁免
# Exit 1: 冻结违规

set -euo pipefail

BASE="${1:-origin/main}"
ALLOWED_REGEX='^frontend/src/app/(admin|api)/'
OVERRIDE_MARKER='FREEZE_OVERRIDE'

# 如果 BASE 不存在 (本地从未 fetch), 静默退出成功 (本地脚手架, 不卡本地)
if ! git rev-parse --verify --quiet "$BASE" >/dev/null; then
    echo "[page-freeze] base ref '$BASE' 不存在, skip"
    exit 0
fi

new_pages=$(git diff --diff-filter=A --name-only "$BASE"...HEAD -- 'frontend/src/app/' \
    | grep -E 'page\.(tsx|jsx|ts|js)$' \
    | grep -vE "$ALLOWED_REGEX" || true)

if [ -z "$new_pages" ]; then
    echo "[page-freeze] ✓ 没有新 frontend page (admin/ api/ 已豁免)"
    exit 0
fi

if git log "$BASE"..HEAD --format=%B 2>/dev/null | grep -q "$OVERRIDE_MARKER"; then
    echo "[page-freeze] ⚠ 检测到 FREEZE_OVERRIDE 标记, 放行:"
    echo "$new_pages" | sed 's/^/  - /'
    exit 0
fi

echo ""
echo "❌ Frontend page freeze 违规"
echo ""
echo "Phase 0–4 期间 frontend/src/app/ 下新 page 文件冻结."
echo "允许的例外: frontend/src/app/admin/** 和 frontend/src/app/api/**"
echo ""
echo "本次 PR 新增了以下 page 文件:"
echo "$new_pages" | sed 's/^/  - /'
echo ""
echo "如确需新加 page, 在 commit message 加 'FREEZE_OVERRIDE' 字样 (并说明理由)."
echo "或者考虑写 mobile/ 的 RN 版本 (Agent Native Mobile First)."
exit 1
