#!/bin/bash
# This legacy entry point mutates and builds from the shared production checkout.
# Keep the guard above every external command.
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  printf '%s\n' 'Production automatic writer is frozen; use the manual Gate.' >&2
  exit 78
fi

if [[ 0 -eq 1 ]]; then
set -e

echo "📦 在服务器上编译小程序..."
ssh root@39.98.206.178 "cd /opt/health-app && git pull && cd packages/mini-program && npm run build:weapp"

echo "📥 下载编译结果到本地..."
cd "$(dirname "$0")"
rm -rf dist
scp -r root@39.98.206.178:/opt/health-app/packages/mini-program/dist .

echo "✅ 编译完成！"
echo "📱 现在可以在微信开发者工具中打开项目："
echo "   项目目录: $(pwd)/dist"
fi
