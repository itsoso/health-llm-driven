#!/usr/bin/env bash
# scripts/sync-skills.sh
#
# 把 backend/skills/ 里缺失的 skill 同步到 openclaw-skills/ 分发包.
# 两者的 auth 模式一样 (都用 ${HEALTH_API_URL} + ${HEALTH_API_TOKEN}), 所以
# 脚本只做:
#   1. 报告 diff (backend 有 / openclaw 缺 的 skill)
#   2. 把缺的 skill cp -r 过去
#   3. 顺手把 $VAR (无花括号) 规范化为 ${VAR}
#   4. 不碰已经存在的 skill (openclaw 一侧可能有独立演进的版本)
#
# 用法:
#   scripts/sync-skills.sh              # 报告差异, 不改文件
#   scripts/sync-skills.sh --apply      # 真的同步
#   scripts/sync-skills.sh --force <skill>   # 强制覆盖单个 skill

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND="$ROOT/backend/skills"
OPENCLAW="$ROOT/openclaw-skills"

[[ -d "$BACKEND" ]] || { echo "错误: $BACKEND 不存在"; exit 1; }
[[ -d "$OPENCLAW" ]] || { echo "错误: $OPENCLAW 不存在"; exit 1; }

MODE="report"
FORCE_SKILL=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply) MODE="apply"; shift ;;
    --force) MODE="force"; FORCE_SKILL="${2:-}"; shift 2 ;;
    -h|--help)
      sed -n '2,14p' "$0"; exit 0 ;;
    *) echo "未知参数: $1"; exit 1 ;;
  esac
done

# 1. 列表对比
backend_skills=()
while IFS= read -r d; do
  backend_skills+=("$(basename "$d")")
done < <(find "$BACKEND" -mindepth 1 -maxdepth 1 -type d | sort)

openclaw_skills=()
while IFS= read -r d; do
  openclaw_skills+=("$(basename "$d")")
done < <(find "$OPENCLAW" -mindepth 1 -maxdepth 1 -type d | sort)

missing=()
for s in "${backend_skills[@]}"; do
  found=false
  for o in "${openclaw_skills[@]}"; do
    [[ "$s" == "$o" ]] && { found=true; break; }
  done
  $found || missing+=("$s")
done

echo "==================================================="
echo "Skill 同步报告  ($(date +%Y-%m-%d))"
echo "==================================================="
echo "backend/skills/     : ${#backend_skills[@]} 个"
echo "openclaw-skills/    : ${#openclaw_skills[@]} 个"
echo "openclaw 缺失       : ${#missing[@]} 个"
echo ""
if [[ ${#missing[@]} -gt 0 ]]; then
  echo "缺失列表:"
  for s in "${missing[@]}"; do
    [[ -f "$BACKEND/$s/SKILL.md" ]] && desc=$(awk '/^description:/ {sub(/^description: */,""); print; exit}' "$BACKEND/$s/SKILL.md") || desc=""
    echo "  - $s  —  ${desc:0:80}"
  done
  echo ""
fi

# 2. normalize 函数: $VAR → ${VAR}  (仅针对 HEALTH_API_URL / HEALTH_API_TOKEN)
normalize_vars() {
  local f="$1"
  # sed -i 兼容 mac: 需要空串做扩展名
  sed -i.bak -E 's/([^{$])\$(HEALTH_API_URL|HEALTH_API_TOKEN)/\1${\2}/g; s/^\$(HEALTH_API_URL|HEALTH_API_TOKEN)/${\1}/' "$f"
  rm -f "$f.bak"
}

copy_skill() {
  local name="$1"
  local src="$BACKEND/$name"
  local dst="$OPENCLAW/$name"
  [[ -d "$src" ]] || { echo "  跳过 $name: 源不存在"; return; }
  rm -rf "$dst"
  cp -R "$src" "$dst"
  while IFS= read -r f; do
    normalize_vars "$f"
  done < <(find "$dst" -type f \( -name '*.md' -o -name '*.txt' \))
  echo "  ✓ $name"
}

# 3. 执行
if [[ "$MODE" == "report" ]]; then
  echo "(仅报告模式, 未改文件. 加 --apply 真的同步.)"
  exit 0
fi

if [[ "$MODE" == "force" ]]; then
  [[ -n "$FORCE_SKILL" ]] || { echo "错误: --force 需要指定 skill 名"; exit 1; }
  echo "强制覆盖 $FORCE_SKILL:"
  copy_skill "$FORCE_SKILL"
  exit 0
fi

if [[ ${#missing[@]} -eq 0 ]]; then
  echo "没有 skill 需要同步."
  exit 0
fi

echo "同步中 (不覆盖已存在的 skill):"
for s in "${missing[@]}"; do
  copy_skill "$s"
done

echo ""
echo "完成. 记得:"
echo "  1. 跑 git diff 检查同步结果"
echo "  2. 更新 openclaw-skills/README.md 里的 skill 表"
echo "  3. commit 时单独一发, 不要和 backend 改动混在一起"
