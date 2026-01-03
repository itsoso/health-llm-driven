#!/bin/bash

# 修复版依赖安装脚本 - 解决编译问题

echo "=========================================="
echo "健康管理系统 - 依赖安装脚本（修复版）"
echo "=========================================="
echo ""

# 检查Python版本
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo "Python版本: $PYTHON_VERSION"

# 检查是否在虚拟环境中
if [ -z "$VIRTUAL_ENV" ]; then
    echo "警告: 未检测到虚拟环境"
    echo "建议使用虚拟环境: python3 -m venv venv && source venv/bin/activate"
    read -p "是否继续? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# 升级pip和构建工具
echo ""
echo "步骤1: 升级pip和构建工具..."
pip install --upgrade pip setuptools wheel

# 检查系统类型
OS_TYPE=$(uname -s)
ARCH=$(uname -m)
echo "系统: $OS_TYPE $ARCH"

# macOS特定检查
if [[ "$OS_TYPE" == "Darwin" ]]; then
    echo ""
    echo "步骤2: 检查macOS构建工具..."
    
    # 检查Xcode Command Line Tools
    if ! xcode-select -p &> /dev/null; then
        echo "❌ 未检测到Xcode Command Line Tools"
        echo "请运行: xcode-select --install"
        exit 1
    else
        echo "✅ Xcode Command Line Tools已安装"
    fi
    
    # 检查是否有编译器
    if ! command -v gcc &> /dev/null && ! command -v clang &> /dev/null; then
        echo "⚠️  警告: 未检测到C编译器"
    fi
fi

# 安装策略：先安装不需要编译的包
echo ""
echo "步骤3: 安装核心依赖（无需编译）..."
pip install fastapi uvicorn[standard] sqlalchemy pydantic pydantic-settings python-dotenv || {
    echo "❌ 核心依赖安装失败"
    exit 1
}

echo "✅ 核心依赖安装成功"

# 安装HTTP相关
echo ""
echo "步骤4: 安装HTTP和工具库..."
pip install openai httpx python-dateutil || {
    echo "❌ HTTP库安装失败"
    exit 1
}

echo "✅ HTTP库安装成功"

# 安装数据库迁移工具
echo ""
echo "步骤5: 安装数据库工具..."
pip install alembic || {
    echo "❌ Alembic安装失败"
    exit 1
}

echo "✅ 数据库工具安装成功"

# 安装numpy和pandas（可能有问题）
echo ""
echo "步骤6: 安装数据科学库（可能需要编译）..."

# 尝试使用预编译wheel
echo "尝试安装numpy（使用预编译包）..."
pip install --only-binary :all: numpy 2>/dev/null || {
    echo "预编译包失败，尝试从源码安装..."
    pip install numpy --no-cache-dir || {
        echo "⚠️  numpy安装失败，但可以继续（如果不需要数据分析功能）"
    }
}

echo "尝试安装pandas（使用预编译包）..."
pip install --only-binary :all: pandas 2>/dev/null || {
    echo "预编译包失败，尝试从源码安装..."
    pip install pandas --no-cache-dir || {
        echo "⚠️  pandas安装失败，但可以继续（如果不需要数据分析功能）"
    }
}

# 安装测试工具
echo ""
echo "步骤7: 安装测试工具..."
pip install pytest pytest-asyncio pytest-cov || {
    echo "⚠️  测试工具安装失败，但可以继续"
}

echo ""
echo "=========================================="
echo "安装完成！"
echo "=========================================="
echo ""
echo "如果numpy/pandas安装失败，可以："
echo "1. 使用conda: conda install numpy pandas"
echo "2. 使用Homebrew: brew install numpy pandas (如果可用)"
echo "3. 跳过这些包（如果不需要数据分析功能）"
echo ""
echo "验证安装:"
echo "  python3 -c 'import fastapi; print(\"FastAPI OK\")'"
echo "  python3 -c 'import uvicorn; print(\"Uvicorn OK\")'"
echo "  python3 -c 'import numpy; print(\"NumPy OK\")' 2>/dev/null || echo 'NumPy未安装'"
echo "  python3 -c 'import pandas; print(\"Pandas OK\")' 2>/dev/null || echo 'Pandas未安装'"

