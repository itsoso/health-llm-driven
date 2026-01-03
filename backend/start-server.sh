#!/bin/bash

# 启动服务器脚本

cd "$(dirname "$0")"

echo "=========================================="
echo "启动健康管理系统后端服务"
echo "=========================================="
echo ""

# 检查虚拟环境
if [ ! -d "venv" ]; then
    echo "❌ 虚拟环境不存在，请先运行: ./switch-to-python312.sh"
    exit 1
fi

# 激活虚拟环境
source venv/bin/activate

# 检查Python版本
PYTHON_VERSION=$(python --version)
echo "Python版本: $PYTHON_VERSION"
echo ""

# 检查.env文件
if [ ! -f ".env" ]; then
    echo "⚠️  警告: .env 文件不存在"
    echo "创建最小.env文件..."
    cat > .env << EOF
OPENAI_API_KEY=
GARMIN_API_KEY=
GARMIN_API_SECRET=
DATABASE_URL=sqlite:///./health.db
APP_ENV=development
DEBUG=True
EOF
    echo "✅ 已创建 .env 文件"
    echo ""
fi

echo "启动服务..."
echo "访问地址:"
echo "  - API文档: http://localhost:8000/docs"
echo "  - 健康检查: http://localhost:8000/health"
echo "  - API根路径: http://localhost:8000/"
echo ""
echo "按 Ctrl+C 停止服务"
echo "=========================================="
echo ""

# 启动服务
uvicorn main:app --reload --host 0.0.0.0 --port 8000

