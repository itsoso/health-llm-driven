#!/bin/bash

# 简化版启动脚本 - 不使用reload（避免Python 3.13兼容性问题）

echo "启动健康管理系统后端（简化模式）..."

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
    echo "创建最小.env文件..."
    cat > .env << EOF
OPENAI_API_KEY=
GARMIN_API_KEY=
GARMIN_API_SECRET=
DATABASE_URL=sqlite:///./health.db
APP_ENV=development
DEBUG=True
EOF
    echo "已创建 .env 文件，请编辑并填写配置"
fi

# 启动服务（不使用reload）
echo "启动服务（不使用自动重载）..."
echo "提示: 修改代码后需要手动重启服务"
uvicorn main:app --host 0.0.0.0 --port 8000

