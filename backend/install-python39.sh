#!/bin/bash

# 安装Python 3.9并切换的脚本

echo "安装Python 3.9..."

# 检查Homebrew
if ! command -v brew &> /dev/null; then
    echo "❌ 未找到Homebrew，请先安装: https://brew.sh"
    exit 1
fi

# 安装Python 3.9
echo "使用Homebrew安装Python 3.9..."
brew install python@3.9

if [ $? -ne 0 ]; then
    echo "❌ 安装失败"
    exit 1
fi

echo "✅ Python 3.9 安装成功: $(python3.9 --version)"

# 切换到backend目录
cd backend

# 删除旧的虚拟环境
if [ -d "venv" ]; then
    echo "删除旧的虚拟环境..."
    rm -rf venv
fi

# 使用Python 3.9创建新的虚拟环境
echo "创建新的虚拟环境（Python 3.9）..."
python3.9 -m venv venv

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
echo "✅ 完成！现在使用Python 3.9了"
echo "=========================================="
echo ""
echo "启动服务（可以使用--reload）:"
echo "  source venv/bin/activate"
echo "  uvicorn main:app --reload --host 0.0.0.0 --port 8000"
echo ""

