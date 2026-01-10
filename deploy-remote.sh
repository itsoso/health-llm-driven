#!/bin/bash
# 远程部署脚本 - 在阿里云服务器上执行部署
# 用法: ./deploy-remote.sh [服务器地址] [用户名]
# 示例: ./deploy-remote.sh health.westwetlandtech.com root

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 参数
SERVER=${1:-"health.westwetlandtech.com"}
USER=${2:-"root"}
APP_DIR="/opt/health-app"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}   远程部署到阿里云服务器${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "${YELLOW}服务器: ${SERVER}${NC}"
echo -e "${YELLOW}用户: ${USER}${NC}"
echo -e "${YELLOW}应用目录: ${APP_DIR}${NC}"
echo ""

# 1. 确保本地代码已提交
echo -e "${YELLOW}[1/6] 检查本地代码状态...${NC}"
if [ -n "$(git status --porcelain)" ]; then
    echo -e "${RED}✗ 本地有未提交的更改，请先提交代码${NC}"
    exit 1
fi

# 推送代码到远程
echo -e "${YELLOW}推送代码到远程仓库...${NC}"
git push origin main
echo -e "${GREEN}✓ 代码已推送到远程仓库${NC}"
echo ""

# 2. 连接到服务器并执行部署
echo -e "${YELLOW}[2/6] 连接到服务器...${NC}"
ssh ${USER}@${SERVER} << 'ENDSSH'
set -e

APP_DIR="/opt/health-app"

echo "=========================================="
echo "   在服务器上执行部署"
echo "=========================================="
echo ""

# 进入应用目录
echo "[1/5] 进入应用目录..."
cd $APP_DIR
echo "✓ 当前目录: $(pwd)"
echo ""

# 拉取最新代码
echo "[2/5] 拉取最新代码..."
git pull origin main
echo "✓ 代码已更新"
echo ""

# 更新后端依赖（如果需要）
echo "[3/5] 更新后端依赖..."
cd backend
if [ -d "venv" ]; then
    source venv/bin/activate
    pip install -q -r requirements.txt
    echo "✓ 后端依赖已更新"
else
    echo "⚠ 虚拟环境不存在，跳过依赖更新"
fi
cd ..
echo ""

# 构建前端
echo "[4/5] 构建前端应用..."
cd frontend
npm install --silent
npm run build
cd ..
echo "✓ 前端构建完成"
echo ""

# 重启服务
echo "[5/5] 重启服务..."
systemctl restart health-backend.service
systemctl restart health-frontend.service
echo "✓ 服务已重启"
echo ""

# 检查服务状态
echo "=========================================="
echo "   服务状态"
echo "=========================================="
echo ""
echo "--- 后端服务状态 ---"
systemctl status health-backend.service --no-pager -l | head -10
echo ""
echo "--- 前端服务状态 ---"
systemctl status health-frontend.service --no-pager -l | head -10
echo ""

echo "=========================================="
echo "   部署完成！"
echo "=========================================="
ENDSSH

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}   远程部署完成！${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "访问地址: https://${SERVER}"
