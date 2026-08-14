#!/bin/bash
# 一键远程部署脚本
# 生成时间: 2026-01-22

# This legacy entry point bypasses the canonical release source/lease checks.
# Keep the guard above prompts, argument handling, and external commands.
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  printf '%s\n' 'Production automatic writer is frozen; use the manual Gate.' >&2
  exit 78
fi

if [[ 0 -eq 1 ]]; then
set -e

echo "=========================================="
echo "远程服务器部署脚本"
echo "=========================================="
echo ""

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 配置信息（请修改）
echo -e "${YELLOW}请输入服务器信息:${NC}"
read -p "服务器 IP 地址: " SERVER_IP
read -p "服务器用户名 [root]: " SERVER_USER
SERVER_USER=${SERVER_USER:-root}
read -p "项目路径 [/opt/health-llm-driven]: " PROJECT_PATH
PROJECT_PATH=${PROJECT_PATH:-/opt/health-llm-driven}

echo ""
echo "配置信息:"
echo "  服务器: $SERVER_USER@$SERVER_IP"
echo "  路径: $PROJECT_PATH"
echo ""

read -p "确认继续? (yes/no): " confirm
if [ "$confirm" != "yes" ]; then
    echo "部署已取消"
    exit 0
fi

echo ""
echo -e "${BLUE}=========================================="
echo "Step 1: 测试 SSH 连接"
echo -e "==========================================${NC}"
echo ""

if ssh -o ConnectTimeout=5 $SERVER_USER@$SERVER_IP "echo '连接成功'" > /dev/null 2>&1; then
    echo -e "${GREEN}✓ SSH 连接正常${NC}"
else
    echo -e "${RED}✗ SSH 连接失败${NC}"
    echo "请检查:"
    echo "  1. 服务器 IP 是否正确"
    echo "  2. SSH 密钥是否配置"
    echo "  3. 防火墙是否开放 22 端口"
    exit 1
fi

echo ""
echo -e "${BLUE}=========================================="
echo "Step 2: 上传部署脚本"
echo -e "==========================================${NC}"
echo ""

# 确保远程目录存在
ssh $SERVER_USER@$SERVER_IP "mkdir -p $PROJECT_PATH/backend/scripts"

# 上传脚本
echo "上传部署脚本..."
rsync -avz --progress \
  backend/scripts/production_setup.sh \
  backend/scripts/migrate_sqlite_to_postgres.py \
  backend/scripts/start_celery.sh \
  $SERVER_USER@$SERVER_IP:$PROJECT_PATH/backend/scripts/

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ 脚本上传完成${NC}"
else
    echo -e "${RED}✗ 脚本上传失败${NC}"
    exit 1
fi

echo ""
echo -e "${BLUE}=========================================="
echo "Step 3: 执行远程部署"
echo -e "==========================================${NC}"
echo ""

# 远程执行部署
ssh -t $SERVER_USER@$SERVER_IP << ENDSSH
cd $PROJECT_PATH/backend

# 赋予执行权限
chmod +x scripts/*.sh scripts/migrate_sqlite_to_postgres.py

# 执行部署
echo "开始部署..."
bash scripts/production_setup.sh
ENDSSH

if [ $? -eq 0 ]; then
    echo ""
    echo -e "${GREEN}=========================================="
    echo "部署完成！"
    echo -e "==========================================${NC}"
    echo ""
    echo "下一步操作:"
    echo ""
    echo "1. 验证服务状态:"
    echo "   ssh $SERVER_USER@$SERVER_IP"
    echo "   sudo systemctl status postgresql redis celery-worker celery-beat"
    echo ""
    echo "2. 查看日志:"
    echo "   sudo tail -f /var/log/celery/worker.log"
    echo ""
    echo "3. 重启应用:"
    echo "   sudo systemctl restart health-app"
    echo ""
    echo "⚠️  重要: 请保存部署过程中生成的数据库密码！"
    echo ""
else
    echo ""
    echo -e "${RED}=========================================="
    echo "部署失败"
    echo -e "==========================================${NC}"
    echo ""
    echo "请检查:"
    echo "  1. 查看错误日志"
    echo "  2. 检查服务器系统类型（支持 Ubuntu/CentOS）"
    echo "  3. 确认有 sudo 权限"
    echo ""
    exit 1
fi
fi
