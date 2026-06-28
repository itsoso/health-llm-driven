#!/usr/bin/env bash
# PreToolUse(Bash)hook —— 把已有的确定性 doc-drift 检查从"只在 CI 事后红"
# 抬成"本地 git commit 即机械阻断"(行业对标缺口 #1:你已写好 check_doc_drift.py,
# 只是触发太晚 = Anthropic 验证排名里最弱的 advisory 层)。
#
# 行为:仅当本次 Bash 是 `git commit` 时才检查;漂移 → exit 2 阻断(stderr 给 Claude/用户看)。
# 设计取舍(本地便利闸,权威 enforcement 仍在 CI):
#   - 非 commit 命令:快速放行(grep 短路,不起 python)。
#   - SKIP_DOC_DRIFT_HOOK=1:一次性绕过(中途确需提交在途计数时)。
#   - 检查"跑不起来"(无 python/import 错)= 基建问题非漂移 → 放行 + 提示(CI 兜底)。
#   - 只有"检查跑通且报漂移"才 fail-closed 阻断。

set -uo pipefail
input="$(cat)"

# 快速短路:原始 JSON 里连 'git commit' 子串都没有 → 绝不可能是提交,立即放行
# (大多数 Bash 命令走这条,不起 python,零开销)
printf '%s' "$input" | grep -q "git commit" || exit 0

[ "${SKIP_DOC_DRIFT_HOOK:-}" = "1" ] && exit 0

# 精确取出命令字符串
cmd="$(printf '%s' "$input" | python3 -c "import sys,json;print((json.load(sys.stdin).get('tool_input') or {}).get('command',''))" 2>/dev/null || printf '%s' "$input")"

# **命令边界精确匹配**:只有 `git commit` 真的作为被调用命令(行首,或 ; & | ( 之后)才算提交;
# 排除 `echo "git commit"` / `grep "git commit" f` / `git log --grep commit` 这类把它当字符串/参数的误判。
printf '%s' "$cmd" | grep -qE '(^|[;&|(])[[:space:]]*git[[:space:]]+commit([[:space:]]|$)' || exit 0

root="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null)}"
[ -n "$root" ] && cd "$root" 2>/dev/null || exit 0
fail=""

# —— 检查 1: 架构计数漂移(check_doc_drift.py)——
if [ -f scripts/check_doc_drift.py ]; then
  out="$(python3 scripts/check_doc_drift.py 2>&1)"
  if [ $? -ne 0 ]; then
    if printf '%s' "$out" | grep -qiE "漂移|drift|不一致|EXPECTED|实际"; then
      fail+="● doc-drift(架构计数与代码不符):\n$(printf '%s' "$out" | tail -12)\n  修:更新 ARCHITECTURE 数字,或跑 scripts/dump_system_map.py 重生成。\n"
    else
      echo "⚠️ doc-drift 检查未能运行(基建问题,非漂移),放行该项;CI 兜底。" >&2
    fi
  fi
fi

# —— 检查 2: dossier 跨产物一致性(check_dossier_consistency.py,spec-kit /analyze 确定性子集)——
if [ -f backend/scripts/check_dossier_consistency.py ]; then
  outd="$(python3 backend/scripts/check_dossier_consistency.py 2>&1)"
  if [ $? -ne 0 ]; then
    if printf '%s' "$outd" | grep -qiE "不自洽|不存在|NEEDS CLARIFICATION|REJECT/BLOCK|准入"; then
      fail+="● dossier 一致性(定义环 PRD↔Plan↔Dossier 不自洽):\n$(printf '%s' "$outd" | tail -12)\n"
    else
      echo "⚠️ dossier 一致性检查未能运行(基建问题),放行该项;CI 兜底。" >&2
    fi
  fi
fi

[ -z "$fail" ] && exit 0
{
  echo "🚫 提交闸拦截 git commit —— 本地确定性检查未过:"
  echo "────────────────────────────────────────"
  printf '%b' "$fail"
  echo "────────────────────────────────────────"
  echo "临时绕过(仅本次): SKIP_DOC_DRIFT_HOOK=1 <你的 git commit 命令>"
} >&2
exit 2
