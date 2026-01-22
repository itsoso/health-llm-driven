#!/bin/bash
# Celery Worker 和 Beat 启动脚本
# 生成时间: 2026-01-22

set -e

echo "=================================="
echo "Celery 启动脚本"
echo "=================================="
echo ""

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 切换到 backend 目录
cd "$(dirname "$0")/.."

# 检查 Redis
echo -e "${YELLOW}检查 Redis 连接...${NC}"
if redis-cli ping > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Redis 运行中${NC}"
else
    echo -e "${RED}✗ Redis 未运行${NC}"
    echo "请先启动 Redis: brew services start redis"
    exit 1
fi
echo ""

# 创建日志目录
mkdir -p logs

# 检查是否已有 Celery 进程在运行
echo -e "${YELLOW}检查现有 Celery 进程...${NC}"
if pgrep -f "celery.*worker" > /dev/null; then
    echo -e "${YELLOW}发现运行中的 Celery Worker${NC}"
    echo "是否停止现有进程? (yes/no)"
    read -r response
    if [ "$response" = "yes" ]; then
        pkill -f "celery.*worker"
        pkill -f "celery.*beat"
        echo -e "${GREEN}✓ 已停止现有进程${NC}"
        sleep 2
    fi
fi
echo ""

# 启动模式选择
echo "选择启动模式:"
echo "1) 前台运行（用于调试）"
echo "2) 后台运行（生产环境）"
echo "3) 仅启动 Worker"
echo "4) 仅启动 Beat"
echo ""
read -p "请选择 (1-4): " mode

case $mode in
    1)
        echo -e "${YELLOW}前台模式启动...${NC}"
        echo ""
        echo "Worker 日志:"
        echo "=================================="
        celery -A app.celery_app worker --loglevel=info &
        WORKER_PID=$!
        
        sleep 3
        
        echo ""
        echo "Beat 日志:"
        echo "=================================="
        celery -A app.celery_app beat --loglevel=info &
        BEAT_PID=$!
        
        echo ""
        echo -e "${GREEN}✓ Celery 已启动${NC}"
        echo "Worker PID: $WORKER_PID"
        echo "Beat PID: $BEAT_PID"
        echo ""
        echo "按 Ctrl+C 停止"
        
        # 等待进程
        wait $WORKER_PID $BEAT_PID
        ;;
        
    2)
        echo -e "${YELLOW}后台模式启动...${NC}"
        
        # 启动 Worker
        nohup celery -A app.celery_app worker \
            --loglevel=info \
            --logfile=logs/celery_worker.log \
            --pidfile=logs/celery_worker.pid \
            > /dev/null 2>&1 &
        WORKER_PID=$!
        echo "Worker PID: $WORKER_PID"
        
        sleep 2
        
        # 启动 Beat
        nohup celery -A app.celery_app beat \
            --loglevel=info \
            --logfile=logs/celery_beat.log \
            --pidfile=logs/celery_beat.pid \
            > /dev/null 2>&1 &
        BEAT_PID=$!
        echo "Beat PID: $BEAT_PID"
        
        echo ""
        echo -e "${GREEN}✓ Celery 已在后台启动${NC}"
        echo ""
        echo "查看日志:"
        echo "  Worker: tail -f logs/celery_worker.log"
        echo "  Beat: tail -f logs/celery_beat.log"
        echo ""
        echo "停止服务:"
        echo "  pkill -f 'celery.*worker'"
        echo "  pkill -f 'celery.*beat'"
        ;;
        
    3)
        echo -e "${YELLOW}仅启动 Worker...${NC}"
        celery -A app.celery_app worker --loglevel=info
        ;;
        
    4)
        echo -e "${YELLOW}仅启动 Beat...${NC}"
        celery -A app.celery_app beat --loglevel=info
        ;;
        
    *)
        echo -e "${RED}无效选择${NC}"
        exit 1
        ;;
esac
