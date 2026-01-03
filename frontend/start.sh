#!/bin/bash

# 健康管理系统前端启动脚本

echo "启动健康管理系统前端..."

# 检查node_modules
if [ ! -d "node_modules" ]; then
    echo "安装依赖..."
    npm install
fi

# 启动服务
echo "启动服务..."
npm run dev

