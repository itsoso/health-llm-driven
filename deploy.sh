#!/bin/bash
# 健康应用部署脚本
# 用法: ./deploy.sh [选项]
# 选项:
#   --backend-only   仅重启后端
#   --frontend-only  仅构建并重启前端
#   --no-logs        不显示日志
#   --help           显示帮助

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 应用目录
APP_DIR="/opt/health-app"

# 解析参数
BACKEND_ONLY=false
FRONTEND_ONLY=false
NO_LOGS=false

for arg in "$@"; do
    case $arg in
        --backend-only)
            BACKEND_ONLY=true
            shift
            ;;
        --frontend-only)
            FRONTEND_ONLY=true
            shift
            ;;
        --no-logs)
            NO_LOGS=true
            shift
            ;;
        --help)
            echo "健康应用部署脚本"
            echo ""
            echo "用法: ./deploy.sh [选项]"
            echo ""
            echo "选项:"
            echo "  --backend-only   仅重启后端服务"
            echo "  --frontend-only  仅构建并重启前端服务"
            echo "  --no-logs        部署后不显示日志"
            echo "  --help           显示此帮助信息"
            exit 0
            ;;
    esac
done

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}   健康应用部署脚本${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# 1. 进入应用目录
echo -e "${YELLOW}[1/5] 进入应用目录...${NC}"
cd $APP_DIR
echo -e "${GREEN}✓ 当前目录: $(pwd)${NC}"
echo ""

# 2. 拉取最新代码
echo -e "${YELLOW}[2/5] 拉取最新代码...${NC}"
git pull
echo -e "${GREEN}✓ 代码已更新${NC}"
echo ""

# 3. 构建前端（如果不是仅后端模式）
if [ "$BACKEND_ONLY" = false ]; then
    echo -e "${YELLOW}[3/5] 构建前端应用...${NC}"
    cd frontend
    npm run build
    cd ..
    echo -e "${GREEN}✓ 前端构建完成${NC}"
    echo ""
else
    echo -e "${YELLOW}[3/5] 跳过前端构建（仅后端模式）${NC}"
    echo ""
fi

# 4. 重启服务
echo -e "${YELLOW}[4/5] 重启服务...${NC}"

if [ "$FRONTEND_ONLY" = true ]; then
    echo "重启前端服务..."
    systemctl restart health-frontend.service
    echo -e "${GREEN}✓ 前端服务已重启${NC}"
elif [ "$BACKEND_ONLY" = true ]; then
    echo "重启后端服务..."
    systemctl restart health-backend.service
    echo -e "${GREEN}✓ 后端服务已重启${NC}"
else
    echo "重启后端服务..."
    systemctl restart health-backend.service
    echo "重启前端服务..."
    systemctl restart health-frontend.service
    echo -e "${GREEN}✓ 所有服务已重启${NC}"
fi
echo ""

# 5. 检查服务状态
echo -e "${YELLOW}[5/5] 检查服务状态...${NC}"
echo ""

if [ "$FRONTEND_ONLY" != true ]; then
    echo -e "${BLUE}--- 后端服务状态 ---${NC}"
    systemctl status health-backend.service --no-pager -l | head -20
    echo ""
fi

if [ "$BACKEND_ONLY" != true ]; then
    echo -e "${BLUE}--- 前端服务状态 ---${NC}"
    systemctl status health-frontend.service --no-pager -l | head -20
    echo ""
fi

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}   部署完成！${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# 6. 显示日志（可选）
if [ "$NO_LOGS" = false ]; then
    echo -e "${YELLOW}按 Ctrl+C 退出日志查看${NC}"
    echo ""
    
    if [ "$FRONTEND_ONLY" = true ]; then
        journalctl -u health-frontend.service -f
    else
        journalctl -u health-backend.service -f
    fi
fi

