#!/bin/bash

# 运行测试脚本

echo "运行健康管理系统测试..."

# 检查虚拟环境
if [ ! -d "venv" ]; then
    echo "创建虚拟环境..."
    python3 -m venv venv
fi

# 激活虚拟环境
source venv/bin/activate

# 安装依赖（包括测试依赖）
echo "安装依赖..."
pip install -r requirements.txt

# 运行测试
echo "运行测试..."
pytest -v

# 可选：生成覆盖率报告
if [ "$1" == "--coverage" ]; then
    echo "生成覆盖率报告..."
    pytest --cov=app --cov-report=html --cov-report=term-missing
    echo "覆盖率报告已生成在 htmlcov/index.html"
fi

