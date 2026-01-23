#!/bin/bash
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
