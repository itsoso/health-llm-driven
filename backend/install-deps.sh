#!/bin/bash

# 依赖安装脚本 - 解决安装问题

echo "开始安装依赖..."

# 升级pip
echo "升级pip..."
pip install --upgrade pip setuptools wheel

# 如果使用虚拟环境，确保已激活
if [ -d "venv" ]; then
    echo "使用虚拟环境..."
    source venv/bin/activate
fi

# 先安装基础构建工具（如果需要）
echo "检查构建工具..."
# macOS
if [[ "$OSTYPE" == "darwin"* ]]; then
    echo "检测到macOS系统"
    # 检查是否有Xcode Command Line Tools
    if ! xcode-select -p &> /dev/null; then
        echo "警告: 可能需要安装Xcode Command Line Tools"
        echo "运行: xcode-select --install"
    fi
fi

# 尝试安装依赖
echo "安装Python依赖..."

# 方法1: 使用更新后的requirements
if [ -f "requirements-fixed.txt" ]; then
    echo "使用更新后的依赖文件..."
    pip install -r requirements-fixed.txt
else
    echo "使用原始依赖文件..."
    # 逐个安装，遇到错误时继续
    pip install fastapi uvicorn[standard] sqlalchemy pydantic pydantic-settings python-dotenv || true
    pip install openai httpx python-dateutil || true
    pip install pandas numpy alembic || true
    pip install pytest pytest-asyncio pytest-cov || true
fi

echo "依赖安装完成！"
echo ""
echo "如果仍有问题，请尝试："
echo "1. 升级pip: pip install --upgrade pip"
echo "2. 使用虚拟环境: python3 -m venv venv && source venv/bin/activate"
echo "3. 逐个安装包以定位问题包"

