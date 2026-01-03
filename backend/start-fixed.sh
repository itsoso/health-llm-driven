#!/bin/bash

# 健康管理系统后端启动脚本（修复版 - 兼容Python 3.13）

echo "启动健康管理系统后端..."

# 检查虚拟环境
if [ ! -d "venv" ]; then
    echo "创建虚拟环境..."
    python3 -m venv venv
fi

# 激活虚拟环境
source venv/bin/activate

# 安装依赖
echo "安装依赖..."
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt

# 检查.env文件
if [ ! -f ".env" ]; then
    echo "警告: .env 文件不存在，请先配置环境变量"
    echo "可以复制 .env.example 为 .env 并填写配置"
    echo "创建最小.env文件..."
    cat > .env << EOF
# OpenAI API配置（用于健康分析）
OPENAI_API_KEY=

# Garmin API配置（可选）
GARMIN_API_KEY=
GARMIN_API_SECRET=

# 数据库配置
DATABASE_URL=sqlite:///./health.db

# 应用配置
APP_ENV=development
DEBUG=True
EOF
    echo "已创建 .env 文件，请编辑并填写配置"
fi

# 启动服务
echo "启动服务..."

# Python 3.13兼容性修复：使用--reload时可能需要设置multiprocessing启动方法
# 检查Python版本
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}' | cut -d. -f1,2)
PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)

# Python 3.13+ 使用不同的启动方式
if [ "$PYTHON_MAJOR" -ge 3 ] && [ "$PYTHON_MINOR" -ge 13 ]; then
    echo "检测到Python 3.13+，使用兼容模式启动..."
    # 设置multiprocessing启动方法
    export PYTHONUNBUFFERED=1
    # 使用--reload但禁用watchfiles（如果有问题）
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload --reload-dir . 2>&1 || {
        echo "使用--reload失败，尝试不使用reload模式..."
        uvicorn main:app --host 0.0.0.0 --port 8000
    }
else
    # Python 3.12及以下使用标准方式
    uvicorn main:app --reload --host 0.0.0.0 --port 8000
fi

