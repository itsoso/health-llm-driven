#!/usr/bin/env bash
set -euo pipefail

cat >&2 <<'EOF'
SECURITY BLOCK: deploy_production.sh 已停用。

旧脚本会创建 root 服务、监听 0.0.0.0:8000，并绕过依赖锁、备份恢复演练和部署健康闸。
生产部署必须使用仓库根目录的 ./deploy.sh；系统服务、Nginx 和防火墙基线位于 infra/。
EOF
exit 1
