#!/bin/bash
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
set -euo pipefail

# Keep this pure-builtin block above every path lookup or external tool.
printf '%s\n' \
  'SECURITY BLOCK: deploy_production.sh 已停用。' \
  '旧脚本会绕过来源、发布锁、备份恢复和健康闸。' \
  '所有自动生产写入均 FROZEN (exit 78)；请走 manual Gate（人工发布闸）。' >&2
exit 78
fi
