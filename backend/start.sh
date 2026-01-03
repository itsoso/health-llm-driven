#!/bin/bash

# 健康管理系统后端启动脚本

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
pip install -r requirements.txt

# 检查.env文件
if [ ! -f ".env" ]; then
    echo "警告: .env 文件不存在，请先配置环境变量"
    echo "可以复制 .env.example 为 .env 并填写配置"
fi

# 启动服务
echo "启动服务..."

# Python 3.13兼容性：检查Python版本并选择合适的启动方式
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}' | cut -d. -f1,2)
PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)

# Python 3.13+ 不使用reload（避免multiprocessing问题）
if [ "$PYTHON_MINOR" -ge 13 ]; then
    echo "检测到Python 3.13+，使用兼容模式（不使用自动重载）..."
    echo "提示: 修改代码后需要手动重启服务（Ctrl+C停止，然后重新运行）"
    uvicorn main:app --host 0.0.0.0 --port 8000
else
    # Python 3.12及以下使用标准reload模式
    uvicorn main:app --reload --host 0.0.0.0 --port 8000
fi

