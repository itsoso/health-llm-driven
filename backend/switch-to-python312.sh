#!/bin/bash

# 切换到Python 3.12的脚本（推荐，兼容性更好）

echo "切换到Python 3.12..."

cd backend

# 检查Python 3.12是否可用
if ! command -v python3.12 &> /dev/null; then
    echo "❌ Python 3.12 未安装"
    echo "请运行: brew install python@3.12"
    exit 1
fi

echo "✅ 找到Python 3.12: $(python3.12 --version)"

# 删除旧的虚拟环境
if [ -d "venv" ]; then
    echo "删除旧的虚拟环境..."
    rm -rf venv
fi

# 使用Python 3.12创建新的虚拟环境
echo "创建新的虚拟环境（Python 3.12）..."
python3.12 -m venv venv

# 激活虚拟环境
source venv/bin/activate

# 验证Python版本
echo "当前Python版本: $(python --version)"

# 升级pip
echo "升级pip..."
pip install --upgrade pip setuptools wheel

# 安装依赖
echo "安装依赖..."
pip install -r requirements.txt

echo ""
echo "=========================================="
echo "✅ 完成！现在可以使用Python 3.12了"
echo "=========================================="
echo ""
echo "启动服务（可以使用--reload）:"
echo "  source venv/bin/activate"
echo "  uvicorn main:app --reload --host 0.0.0.0 --port 8000"
echo ""

